"""Collection pipeline, independent of HTTP routes and the panel.

One job runs these stages, recording counters in ``job.stats`` and structured logs:

    plan (requirements -> query rounds) -> discovery (search engines, provenance kept)
      -> triage (page kind and priority from URL/title/snippet; job ads, definitions and
         documents are skipped unread) -> fetching (robots, SSRF guards, retries)
      -> extraction (person records, page owner and place) -> matching (role, topic, place)
      -> import (ranked within the page; normalize, deduplicate, score) -> human review

Discovery runs in rounds of ever broader queries (``query_rounds``), then asks for the next
result page of each query that is still bringing new sources (up to RESULT_PAGES). Sources are
read best-first by triage priority. A relevant page without people may lead to its own site's
team or staff page (at most COLLECTION_MAX_FOLLOWED_LINKS per job). The job stops when the
requested number of people is found, the user stops it, no new source is left,
COLLECTION_MAX_SOURCES is full or the COLLECTION_TIME_BUDGET_SECONDS safety ceiling passes.

Only people with page evidence, a fitting role, no conflicting place and (unless the role names
the field, e.g. chefs) some topic evidence count toward the requested number. Platform leads
(search result titles), people elsewhere (another city by their own or their page's address) and
people without topic evidence are kept for review, each capped at the requested number.

A failing source never fails the job. The job heartbeats at every step; the worker
requeues a job whose heartbeat stops (crash) or that is interrupted by shutdown, up to
COLLECTION_MAX_ATTEMPTS. Repeating work is safe: imports merge by identity and the same
page is never stored twice in one job. n8n can trigger and poll the same jobs.
"""

import hashlib
import logging
import re
import time
from datetime import timedelta
from html import unescape
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import log_event
from app.models import (
    Candidate,
    CollectionJob,
    ResearchRequest,
    SourceDocument,
    now,
)
from app.services.candidates import CandidateLimitError, audit, import_candidates
from app.services.discovery import (
    PublicSearchProvider,
    build_queries,
    canonical_url,
    query_rounds,
)
from app.services.extraction import extract_profiles, name_key
from app.services.fetching import FetchError, PageFetcher
from app.services.matching import counts_for_target, decide, qualifies, shortfall
from app.services.platforms import never_fetch, profile_lead
from app.services.requirements import build_spec, region
from app.services.search_quality import REGIONS, contains, language_matches
from app.services.triage import follow_links, triage

logger = logging.getLogger("relationships.collection")
ACTIVE_JOB = ("QUEUED", "RUNNING")
RUNNING_RESEARCH = ("SEARCHING", "COLLECTING", "PROCESSING")
# Result pages read per query; deeper pages rarely name anyone relevant.
RESULT_PAGES = 5
# A followed same-site people page is read before ordinary search results.
FOLLOWED_PRIORITY = 70
LINKS_PER_PAGE = 3
STAT_KEYS = (
    "search_rounds",
    "search_pages",
    "search_queries",
    "search_errors",
    "search_empty",
    "search_results",
    "duplicate_urls",
    "triage_skipped",
    "links_followed",
    "sources_fetched",
    "sources_failed",
    "duplicate_content",
    "profiles_extracted",
    "profiles_qualified",
    "profiles_elsewhere",
    "profiles_unconfirmed",
    "candidates_created",
    "candidates_merged",
    "platform_leads",
)


class JobInterrupted(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason  # "cancelled" or "shutdown"


def has_candidates(db, research_id):
    return bool(
        db.scalar(select(Candidate.id).where(Candidate.research_request_id == research_id).limit(1))
    )


def active_job(db, research_id, lock=False):
    query = (
        select(CollectionJob)
        .where(
            CollectionJob.research_request_id == research_id,
            CollectionJob.status.in_(ACTIVE_JOB),
        )
        .order_by(CollectionJob.created_at.desc())
        .limit(1)
    )
    return db.scalar(query.with_for_update() if lock else query)


def enqueue(db, research, actor):
    """Queue a job. Caller holds the research row lock and commits. `actor` may be an Actor."""
    if research.status in RUNNING_RESEARCH or active_job(db, research.id):
        raise ValueError("An existing collection is still running.")
    job = CollectionJob(
        research_request_id=research.id,
        search_language=research.search_language,
        created_by=getattr(actor, "id", actor),
        query="\n".join(build_queries(research))[:1000],
        stats={},
    )
    research.status, research.error = "SEARCHING", None
    db.add(job)
    db.flush()
    audit(db, actor, "collection.queued", research.id, {"job_id": job.id})
    log_event(logger, "collection.queued", job_id=job.id, research_id=research.id)
    return job


def settle_research(db, research, job):
    """Research status after a job ends; existing candidates always stay reviewable."""
    if has_candidates(db, research.id):
        research.status = "READY_FOR_REVIEW"
    elif job.status == "NO_RESULTS":
        research.status = "NO_RESULTS"
    elif job.status == "CANCELLED":
        research.status = "CREATED"
    else:
        research.status = "FAILED"
    research.error = job.error


def request_cancel(db, research, actor):
    """Cancel a queued job now, or ask the worker to stop a running job at its next step."""
    job = active_job(db, research.id, lock=True)
    if not job:
        raise ValueError("No collection is running for this research request.")
    if job.status == "QUEUED":
        job.status, job.finished_at = "CANCELLED", now()
        job.error = "Arama kullanıcı tarafından iptal edildi."
        settle_research(db, research, job)
    else:
        job.cancel_requested = True
    audit(db, actor, "collection.cancel", research.id, {"job_id": job.id})
    log_event(logger, "collection.cancel_requested", job_id=job.id, status=job.status)
    return job


def recover_jobs(db):
    """Requeue RUNNING jobs whose worker stopped heartbeating; fail them after max attempts."""
    settings = get_settings()
    cutoff = now() - timedelta(seconds=settings.collection_stale_after_seconds)
    jobs = db.scalars(
        select(CollectionJob)
        .where(
            CollectionJob.status == "RUNNING",
            func.coalesce(CollectionJob.heartbeat_at, CollectionJob.updated_at) < cutoff,
        )
        .with_for_update(skip_locked=True)
    )
    for job in jobs:
        research = db.get(ResearchRequest, job.research_request_id)
        if job.attempts < settings.collection_max_attempts and not job.cancel_requested:
            job.status = "QUEUED"
            audit(db, None, "collection.requeued", research.id, {"job_id": job.id})
            log_event(logger, "collection.requeued", logging.WARNING, job_id=job.id,
                      attempts=job.attempts)
            continue
        job.status, job.finished_at = ("CANCELLED" if job.cancel_requested else "FAILED"), now()
        job.error = (
            "Arama kullanıcı tarafından iptal edildi."
            if job.cancel_requested
            else "Toplama işçisi durdu veya süre aşıldı. Bulunan kanıtlar korundu; "
            "yeniden deneyebilirsiniz."
        )
        settle_research(db, research, job)
        audit(db, None, "collection.interrupted", research.id, {"job_id": job.id})
        log_event(logger, "collection.interrupted", logging.WARNING, job_id=job.id)
    db.commit()


class CollectionRun:
    def __init__(self, db, job, research, discovery, fetcher, stop_event=None,
                 on_heartbeat=None, sleep=time.sleep, clock=time.monotonic):
        self.settings = get_settings()
        self.db, self.job, self.research = db, job, research
        self.discovery, self.fetcher = discovery, fetcher
        self.stop_event, self.on_heartbeat, self.sleep = stop_event, on_heartbeat, sleep
        self.clock = clock
        self.deadline = clock() + self.settings.collection_time_budget_seconds
        self.stop_reason = "exhausted"
        self.spec = build_spec(research)
        saved = job.stats or {}
        self.stats = {key: int(saved.get(key, 0)) for key in STAT_KEYS}
        # Persisted so a resumed job knows which stages finished and whom it already found.
        self.stage = saved.get("stage", "")
        self.candidate_ids = set(saved.get("candidate_ids", []))
        # People known only from a platform's search result; they never satisfy the target.
        self.lead_ids = set(saved.get("lead_ids", []))
        # People whose own or page address is another place, or with no topic evidence;
        # reviewable, not counted.
        self.elsewhere_ids = set(saved.get("elsewhere_ids", []))
        self.unconfirmed_ids = set(saved.get("unconfirmed_ids", []))
        # Queries whose last result page brought no new source; their next page is not asked for.
        self.spent = set(saved.get("spent_queries", []))
        self.limit_reached = False
        self.queried = False
        # Resume after a restart: keep this job's sources and re-read unfinished ones.
        self.documents = list(
            db.scalars(
                select(SourceDocument)
                .where(SourceDocument.collection_job_id == job.id)
                .order_by(SourceDocument.created_at)
            )
        )
        for document in self.documents:
            if document.status == "READING":
                document.status = "DISCOVERED"
        if self.documents:
            # A crash between a source's commit and its counter update must not skew progress.
            job.processed = sum(d.status != "DISCOVERED" for d in self.documents)
        self.urls = {canonical_url(d.url) for d in self.documents}
        self.hashes = {d.content_hash for d in self.documents if d.content_hash}

    # -- bookkeeping -------------------------------------------------------------
    def log(self, event, level=logging.INFO, **fields):
        log_event(logger, event, level, job_id=self.job.id, research_id=self.research.id, **fields)

    def out_of_time(self):
        return self.clock() >= self.deadline

    def should_stop(self):
        """Only the safety ceiling stops a search that still has sources to try."""
        if self.out_of_time():
            self.stop_reason = "time"
            return True
        return False

    def sources_full(self):
        return len(self.documents) >= self.settings.collection_max_sources

    def stop_message(self):
        return {
            "time": f"Arama {self.settings.collection_time_budget_seconds // 60} dk güvenlik "
                    "süre sınırına ulaştı",
            "sources": f"İş başına kaynak sınırına ({self.settings.collection_max_sources}) ulaşıldı",
            "limit": "Talep başına aday sınırına ulaşıldı",
        }.get(self.stop_reason, "Aranacak yeni kaynak kalmadı")

    def checkpoint(self):
        """Persist progress, prove liveness and stop early when cancelled or shutting down."""
        self.job.heartbeat_at = self.job.updated_at = now()
        self.job.stats = self.snapshot()
        self.db.commit()
        if self.on_heartbeat:
            self.on_heartbeat()
        if self.db.scalar(
            select(CollectionJob.cancel_requested).where(CollectionJob.id == self.job.id)
        ):
            raise JobInterrupted("cancelled")
        if self.stop_event is not None and self.stop_event.is_set():
            raise JobInterrupted("shutdown")

    def snapshot(self):
        return {**self.stats, "stage": self.stage, "candidate_ids": sorted(self.candidate_ids),
                "lead_ids": sorted(self.lead_ids), "elsewhere_ids": sorted(self.elsewhere_ids),
                "unconfirmed_ids": sorted(self.unconfirmed_ids),
                "spent_queries": sorted(self.spent)}

    def verified_count(self):
        return len(self.candidate_ids - self.lead_ids - self.elsewhere_ids - self.unconfirmed_ids)

    def target_reached(self):
        return self.limit_reached or self.verified_count() >= self.research.requested_quantity

    # -- stage 1: discovery and triage ---------------------------------------------
    def add_source(self, url, title, snippet="", query=None, engine=None, rank=None, via=None):
        """Queue a new source, classified and prioritized before any fetch; True when added."""
        try:
            key = canonical_url(url)
        except ValueError:
            return False
        if key in self.urls:
            self.stats["duplicate_urls"] += 1
            return False
        if self.sources_full():
            return False
        verdict = triage(url, title, snippet, self.spec)
        document = SourceDocument(collection_job_id=self.job.id, url=url, title=title,
                                  snippet=snippet, created_by=self.job.created_by,
                                  query=(f"Bağlantı: {via}" if via else query or None),
                                  engine=(engine or None) and str(engine)[:30], rank=rank,
                                  page_kind="people_list" if via else verdict.kind,
                                  priority=FOLLOWED_PRIORITY if via else verdict.priority)
        if verdict.skip and not via:
            document.status, document.error = "SKIPPED", verdict.reason[:200]
            self.stats["triage_skipped"] += 1
            self.job.processed += 1
        self.db.add(document)
        self.documents.append(document)
        self.urls.add(key)
        self.job.discovered = len(self.documents)
        return True

    def discover(self, query, page):
        retries = self.settings.discovery_retries
        for attempt in range(retries + 1):
            try:
                hits = self.discovery.discover(query, 10, page=page)
            except Exception as exc:  # provider errors vary; each is logged and bounded
                self.stats["search_errors"] += 1
                # Type only: provider messages may echo request details.
                self.log("discovery.failed", logging.WARNING, attempt=attempt + 1,
                         error=type(exc).__name__)
                wait = self.settings.retry_backoff_seconds * 2**attempt
                if attempt == retries or self.clock() + wait >= self.deadline:
                    return []
                self.sleep(wait)
                continue
            self.stats["search_results"] += len(hits)
            self.stats["search_empty"] += not hits
            self.log("discovery.results", results=len(hits), attempt=attempt + 1)
            return hits
        return []

    def search(self, queries, page):
        self.research.status = "SEARCHING"
        self.checkpoint()
        batches = []
        for query in queries:
            if self.should_stop():
                break
            if page > 1:
                self.sleep(self.settings.search_pause_seconds)
            elif self.queried and self.settings.search_query_interval_seconds:
                self.sleep(self.settings.search_query_interval_seconds)
            self.queried = True
            self.stats["search_queries"] += 1
            batches.append((query, self.discover(query, page)))
            self.checkpoint()
        # Interleave results so one query cannot fill the source limit on its own.
        fresh = set()
        for index in range(max((len(hits) for _, hits in batches), default=0)):
            for query, hits in batches:
                if index >= len(hits):
                    continue
                hit = hits[index]
                if self.add_source(hit.url, hit.title, hit.snippet, query, getattr(hit, "engine", None),
                                   getattr(hit, "rank", None) or index + 1):
                    fresh.add(query)
        # A page with nothing new means the engine has no more for this query.
        self.spent.update(query for query, _ in batches if query not in fresh)
        self.research.status = "COLLECTING"
        self.checkpoint()

    # -- stages 2-4: fetch, extract, match, import ---------------------------------
    def next_pending(self):
        """The best unread source: highest triage priority, then search order."""
        best = None
        for index, document in enumerate(self.documents):
            if document.status == "DISCOVERED" and (
                    best is None or (document.priority or 0) > (best[1].priority or 0)):
                best = (index, document)
        return best[1] if best else None

    def process_pending(self):
        while True:
            document = self.next_pending()
            if document is None:
                return
            if self.target_reached():
                document.status, document.error = "NOT_NEEDED", "Hedef aday sayısına ulaşıldı."
            elif self.should_stop():
                document.status = "SKIPPED"
                document.error = f"{self.stop_message()}; kaynak okunmadı."
            else:
                document.status = "READING"
                self.checkpoint()
                self.process(document)
            self.job.processed += 1
            self.checkpoint()

    def ranked(self, profiles, page_text, own_text=""):
        """Profiles whose role fits, best match first, with their decisions."""
        scored = [(profile, decide(profile, self.spec, page_text, own_text + " " + (profile.source_evidence or "")))
                  for profile in profiles]
        fitting = [(p, d) for p, d in scored if qualifies(d)]
        fitting.sort(key=lambda item: (counts_for_target(item[1]), item[1]["score"]), reverse=True)
        return fitting

    def read_page(self, document):
        """Fetch, extract and match one page. Profiles are None for already-seen content."""
        final_url, html = self.fetcher.fetch(document.url)
        self.stats["sources_fetched"] += 1
        digest = hashlib.sha256(html).hexdigest()
        document.content_hash = digest
        if digest in self.hashes:
            self.stats["duplicate_content"] += 1
            document.status = "DUPLICATE"
            document.error = "Aynı içerik bu aramada başka bir adreste zaten incelendi."
            self.log("source.duplicate_content", url=document.url)
            return None, digest
        text, profiles = extract_profiles(html, final_url, document.title)
        self.stats["profiles_extracted"] += len(profiles)
        page_title = html_title(html) or next((p.source_name for p in profiles if p.source_name), "")
        page_text = " ".join(dict.fromkeys(filter(None, [document.title, page_title])))
        own_text = ""
        if len(profiles) == 1 and profile_page(profiles[0].full_name, page_title or document.title, final_url):
            # The person's own profile page: its body is about them (kept as the bio, so the
            # stored decision rests on the same evidence as the import decision).
            own_text = text[:5000]
            if not profiles[0].bio:
                profiles[0].bio = text[:2000]
        ranked = self.ranked(profiles, page_text, own_text)
        if not ranked:
            document.error = ("Hedef rolle eşleşen, yeterli kişi kanıtı bulunamadı." if profiles
                              else "Sayfada kişi kaydı bulunamadı.")
            self.follow(document, html, final_url, text)
        elif not language_matches(html, self.job.search_language):
            # A preference, not a filter: pages often declare the wrong language, and
            # Turkish universities publish their staff lists in English.
            document.error = "Not: kaynağın dili seçilen arama dilinden farklı; kişiler yine de eklendi."
        self.stats["profiles_qualified"] += len(ranked)
        document.text = text
        document.status = "EXTRACTED" if ranked else "NEEDS_REVIEW"
        return ranked, digest

    def follow(self, document, html, url, text):
        """A relevant page without people may link to its own site's team or staff page."""
        budget = self.settings.collection_max_followed_links - self.stats["links_followed"]
        if budget <= 0 or document.query and document.query.startswith("Bağlantı:"):
            return
        if (document.priority or 0) < 45 and not any(
                contains(text[:20000], term) for t in self.spec.topics for term in t.match_terms if len(term) > 3):
            return  # an unrelated page's team is not this brief's team
        try:
            links = follow_links(BeautifulSoup(html, "html.parser"), url, min(LINKS_PER_PAGE, budget))
        except Exception:  # a malformed page must not stop the job
            return
        for link in links:
            if self.add_source(link, f"{document.title or url} → kişi listesi", "", via=url):
                self.stats["links_followed"] += 1

    def read_lead(self, document):
        """A platform that forbids retrieval is never fetched; its search result may name a
        person. Leads are capped at the requested number and never count as verified."""
        lead = profile_lead(document.url, document.title, document.snippet, self.research.location)
        ranked = self.ranked([lead], document.title or "") if lead else []
        if ranked and len(self.lead_ids) >= self.research.requested_quantity:
            ranked = []
            document.error = "Platform ipucu sınırına ulaşıldı; sayfa açılmadı."
        elif ranked:
            document.error = ("Platform otomatik okumaya kapalı; sayfa açılmadı. Kişi arama sonucu "
                              "başlığından alındı, doğrulanmadı.")
        else:
            document.error = "Platform otomatik okumaya kapalı; sayfa açılmadı."
        document.status = "EXTRACTED" if ranked else "SKIPPED"
        return ranked

    def process(self, document):
        started = time.monotonic()
        try:
            lead = never_fetch(document.url)
            if lead:
                ranked, digest = self.read_lead(document), None
            else:
                ranked, digest = self.read_page(document)
                if ranked is None:
                    return
            source_ids, counted, created, merged = set(), set(), 0, 0
            uncounted = {"place": set(), "topic": set()}
            known = {"place": self.elsewhere_ids, "topic": self.unconfirmed_ids}
            quantity = self.research.requested_quantity
            for profile, details in ranked:
                if len((self.candidate_ids - self.lead_ids - self.elsewhere_ids - self.unconfirmed_ids)
                       | counted) >= quantity:
                    break
                reason = None if lead else shortfall(details)
                if reason and len(known[reason] | uncounted[reason]) >= quantity:
                    continue  # enough people of this kind are already listed for review
                result = import_candidates(self.db, self.research, [profile], self.job.created_by)
                ids = set(result["candidate_ids"])
                source_ids |= ids
                (uncounted[reason] if reason else counted).update(ids)
                created += result["created"]
                merged += result["merged"]
            self.job.created_count += created
            self.job.merged_count += merged
            self.db.commit()
            # In-memory bookkeeping only after the commit, so a rollback cannot desync it.
            if digest:
                self.hashes.add(digest)
            new = source_ids - self.candidate_ids
            if lead:
                self.lead_ids |= new
                self.stats["platform_leads"] += len(new)
            else:
                # A page now backs a person first seen only as a platform lead.
                self.lead_ids -= source_ids
                self.elsewhere_ids = (self.elsewhere_ids | uncounted["place"]) - counted
                self.unconfirmed_ids = (self.unconfirmed_ids | uncounted["topic"]) - counted - self.elsewhere_ids
                self.stats["profiles_elsewhere"] += len(uncounted["place"] - counted - self.candidate_ids)
                self.stats["profiles_unconfirmed"] += len(uncounted["topic"] - counted - self.candidate_ids)
            self.candidate_ids.update(source_ids)
            self.stats["candidates_created"] += created
            self.stats["candidates_merged"] += merged
            self.log("source.processed", url=document.url, status=document.status, kind=document.page_kind,
                     profiles=len(ranked), candidates=len(source_ids),
                     duration=round(time.monotonic() - started, 3))
        except CandidateLimitError as exc:
            self.db.rollback()
            self.limit_reached = True
            document.status, document.error = "NOT_NEEDED", str(exc)[:200]
            self.log("collection.candidate_limit", logging.WARNING)
        except FetchError as exc:
            self.db.rollback()
            self.stats["sources_failed"] += 1
            document.status, document.error = "FAILED", str(exc)[:200]
            self.log("source.failed", logging.WARNING, url=document.url, error=str(exc)[:200],
                     retryable=exc.retryable)
        except JobInterrupted:
            raise
        except Exception:
            self.db.rollback()
            self.stats["sources_failed"] += 1
            document.status = "FAILED"
            document.error = "Kaynak okunamadı veya profil doğrulanamadı."
            self.log("source.error", logging.ERROR, exc_info=True, url=document.url)

    # -- orchestration -------------------------------------------------------------
    def reuse_previous_sources(self):
        # Re-read previously useful sources for the same brief; never copy stale people.
        previous = self.db.execute(
            select(SourceDocument, CollectionJob.query)
            .join(CollectionJob, CollectionJob.id == SourceDocument.collection_job_id)
            .where(
                CollectionJob.research_request_id == self.research.id,
                CollectionJob.id != self.job.id,
                CollectionJob.search_language == self.job.search_language,
                SourceDocument.status == "EXTRACTED",
            )
            .order_by(SourceDocument.created_at.desc())
            .limit(20)
        ).all()
        first_query = self.job.query.splitlines()[0] if self.job.query else ""
        for source, query in previous:
            if query.splitlines()[:1] == [first_query] and len(self.documents) < 3:
                self.add_source(source.url, source.title, source.snippet, source.query)

    def searched_rounds(self):
        # "primary" and "fallback" were saved by the earlier two-round pipeline.
        legacy = {"primary": 1, "fallback": 2}
        if self.stage in legacy:
            return legacy[self.stage]
        return int(self.stage.split(":", 1)[1]) if self.stage.startswith("round:") else 0

    def execute(self):
        self.log("collection.started", attempt=self.job.attempts, stage=self.stage or "new")
        try:
            rounds = query_rounds(self.research)
            done = self.searched_rounds()
            if done:
                # Resume: read the interrupted round's sources before searching further.
                self.process_pending()
            else:
                self.reuse_previous_sources()
            # Every round on result page 1, then every round again on page 2, and so on. The
            # stage counts finished steps, so jobs saved before paging resume where they were.
            steps = [(page, number, queries) for page in range(1, RESULT_PAGES + 1)
                     for number, queries in enumerate(rounds, start=1)]
            for step, (page, number, queries) in enumerate(steps[done:], start=done + 1):
                if self.target_reached() or self.should_stop():
                    break
                if self.sources_full():
                    self.stop_reason = "sources"
                    break
                if page > 1:
                    queries = [q for q in queries if q not in self.spent]
                if queries:
                    self.stats["search_rounds"], self.stats["search_pages"] = number, page
                    known = self.job.query.splitlines()
                    new = [q for q in queries if q not in known]
                    if new:
                        self.job.query = "\n".join(known + new)[:4000]
                    self.search(queries, page)
                # A step is marked done only after its sources are committed; an interrupted
                # step simply runs again (add_source ignores URLs this job already has).
                self.stage = f"round:{step}"
                self.checkpoint()
                self.process_pending()
            if self.limit_reached:
                self.stop_reason = "limit"
            self.finish()
        except JobInterrupted as stop:
            self.db.rollback()
            self.finish_interrupted(stop.reason)
        except Exception:
            self.db.rollback()
            self.log("collection.error", logging.ERROR, exc_info=True)
            self.job.status = "FAILED"
            self.job.error = (
                "Web araması tamamlanamadı. Daha sonra yeniden deneyin; mevcut kayıtlar korundu."
            )
            self.close()

    def close(self):
        self.job.finished_at = self.job.updated_at = now()
        self.job.stats = self.snapshot()
        settle_research(self.db, self.research, self.job)
        audit(self.db, self.job.created_by, "collection.finished", self.research.id,
              {"job_id": self.job.id, "status": self.job.status})
        self.db.commit()
        self.log("collection.finished", status=self.job.status, processed=self.job.processed,
                 discovered=self.job.discovered, created=self.job.created_count,
                 merged=self.job.merged_count, **self.stats)

    def finish(self):
        # Closed platforms and triage skips are by design, not because a source failed.
        failed = sum(d.status == "FAILED" or (d.status == "SKIPPED" and not never_fetch(d.url)
                                              and not (d.error or "").startswith("Ön eleme"))
                     for d in self.documents)
        # A job ad skipped by triage or a closed platform was reached; only fetch failures were not.
        readable = sum(d.status in ("EXTRACTED", "NEEDS_REVIEW", "DUPLICATE") or never_fetch(d.url)
                       or (d.error or "").startswith("Ön eleme") for d in self.documents)
        tried = f"{self.stats['search_queries']} sorgu, {len(self.documents)} kaynak"
        if self.stats["search_pages"] > 1:
            tried += f", {self.stats['search_pages']}. sonuç sayfasına kadar"
        if self.lead_ids:
            tried += f", {len(self.lead_ids)} doğrulanmamış platform ipucu"
        if self.elsewhere_ids:
            tried += f", {len(self.elsewhere_ids)} kişi başka konumda (hedefe sayılmadı)"
        if self.unconfirmed_ids:
            tried += f", {len(self.unconfirmed_ids)} kişinin konusu doğrulanmadı (hedefe sayılmadı)"
        if not self.documents or not readable:
            self.job.status = "FAILED"
            self.job.error = ("Arama kaynaklarına erişilemedi. Biraz sonra yeniden deneyebilirsiniz; "
                              "önceki adaylar korundu.")
        elif not self.candidate_ids and not self.job.created_count and not self.job.merged_count:
            self.job.status = "NO_RESULTS"
            self.job.error = (f"{self.stop_message()} ({tried}); kaynakla doğrulanabilen kişi "
                              "bulunamadı. Kaynakları inceleyebilir veya hedef kişi rolünü daha "
                              "açık yazabilirsiniz.")
        elif self.verified_count() < self.research.requested_quantity:
            self.job.status = "PARTIAL"
            self.job.error = (f"Arama kısmi tamamlandı: {self.stop_message()} ({tried}). "
                              "Bulunan adayları şimdi inceleyebilirsiniz.")
        elif failed:
            self.job.status = "PARTIAL"
            self.job.error = "Arama kısmi tamamlandı. Bulunan adayları şimdi inceleyebilirsiniz."
        else:
            self.job.status, self.job.error = "COMPLETED", None
        self.close()

    def finish_interrupted(self, reason):
        if reason == "shutdown" and self.job.attempts < self.settings.collection_max_attempts:
            # Resume after restart; sources found so far stay attached to this job.
            self.job.status = "QUEUED"
            self.job.stats = self.snapshot()
            self.db.commit()
            self.log("collection.requeued_on_shutdown", logging.WARNING)
            return
        self.job.status = "CANCELLED" if reason == "cancelled" else "FAILED"
        self.job.error = (
            "Arama kullanıcı tarafından iptal edildi. Bulunan adaylar korundu."
            if reason == "cancelled"
            else "Toplama işçisi kapatıldı. Bulunan adaylar korundu; yeniden deneyebilirsiniz."
        )
        for document in self.documents:
            if document.status in ("DISCOVERED", "READING"):
                document.status, document.error = "SKIPPED", "Arama durduruldu."
        self.close()


def html_title(html):
    match = re.search(rb"<title[^>]*>(.*?)</title>", html[:200000], re.I | re.S)
    return unescape(match.group(1).decode("utf-8", "replace")).strip()[:300] if match else ""


def profile_page(name, title, url):
    """A page about one person: the name is in its title or its address."""
    key = name_key(name)
    return bool(key) and (key in name_key(title or "") or key in name_key(unquote(urlsplit(url).path)))


def claim_next(db):
    job = db.scalar(
        select(CollectionJob)
        .where(CollectionJob.status == "QUEUED")
        .order_by(CollectionJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not job:
        return None
    job.status, job.attempts = "RUNNING", job.attempts + 1
    job.started_at = job.started_at or now()
    job.heartbeat_at = now()
    db.commit()
    return job


def run_next(discovery=None, fetcher=None, stop_event=None, on_heartbeat=None, sleep=time.sleep,
             clock=time.monotonic):
    """Run one queued job to completion. Returns False when the queue is empty."""
    with SessionLocal() as db:
        recover_jobs(db)
        job = claim_next(db)
        if not job:
            return False
        research = db.get(ResearchRequest, job.research_request_id)
        if discovery is None:
            # An automatic-language brief for a Turkish city searches the Turkish region.
            spec = build_spec(research)
            discovery = PublicSearchProvider(
                job.search_language, region(spec, REGIONS.get(job.search_language, REGIONS["auto"]))
                if job.search_language == "auto" else None, sleep=sleep)
        CollectionRun(
            db,
            job,
            research,
            discovery,
            fetcher or PageFetcher(sleep=sleep),
            stop_event=stop_event,
            on_heartbeat=on_heartbeat,
            sleep=sleep,
            clock=clock,
        ).execute()
    return True
