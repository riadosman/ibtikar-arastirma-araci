"""Replace this adapter to use a different search engine; no user credentials."""

import time
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from app.core.config import get_settings
from app.schemas import valid_url
from app.services.requirements import build_spec, plan
from app.services.search_quality import REGIONS


def clean(value):
    return " ".join(unescape(value or "").split())


def query_rounds(research):
    """Query rounds from specific to broad (see requirements.plan); collection runs them in
    order until it has enough people. A query is never repeated in a later round."""
    return plan(build_spec(research))


def build_queries(research):
    """The first round: the brief's most specific queries."""
    rounds = query_rounds(research)
    return rounds[0] if rounds else []


TRACKING_PARAMS = {"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref", "ref_src"}


def canonical_url(url):
    """Same page, same key: drop fragments, tracking parameters and host case."""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    host = (parts.hostname or "").lower()
    netloc = host if parts.port in (None, 80, 443) else f"{host}:{parts.port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), ""))


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: str
    engine: str = ""  # which engine returned it, for per-query yield statistics
    rank: int = 0  # position on its result page, from 1


class DiscoveryProvider(Protocol):
    def discover(self, query: str, limit: int) -> list[SearchHit]: ...


class PublicSearchProvider:
    def __init__(self, language="auto", region=None, sleep=time.sleep):
        self.region = region or REGIONS.get(language, REGIONS["auto"])
        self.backends = [b.strip() for b in get_settings().search_backends.split(",") if b.strip()]
        self.sleep = sleep

    def discover(self, query, limit, page=1):
        # One engine at a time: an engine that blocks this server answers with an empty page, and
        # DDGS mixes engines unpredictably. The first engine with results wins and is tried first
        # for the rest of the job.
        hits, failure = self.ask(self.backends, query, limit, page)
        if not hits and not failure:
            # Free engines rate-limit bursts: every engine empty is often "not now", not "none".
            # One more try with the two most reliable engines after a pause recovers some.
            self.sleep(get_settings().search_pause_seconds)
            hits, failure = self.ask(self.backends[:2], query, limit, page)
        if hits:
            return hits
        if failure:
            raise failure
        return []

    def ask(self, backends, query, limit, page):
        failure = None
        for backend in list(backends):
            try:
                rows = DDGS(timeout=8).text(
                    query,
                    max_results=min(limit, 20),
                    page=page,
                    backend=backend,
                    safesearch="moderate",
                    region=self.region,
                )
            except DDGSException as exc:
                # DDGS raises for an empty result page too; that is "no hits", not a failure.
                if not str(exc).startswith("No results found"):
                    failure = exc
                continue
            hits = self.hits(rows, backend)
            if hits:
                self.backends.remove(backend)
                self.backends.insert(0, backend)
                return hits, None
        return [], failure

    @staticmethod
    def hits(rows, engine=""):
        hits, seen = [], set()
        for row in rows:
            try:
                url = canonical_url(valid_url(row.get("href", "")))
            except (ValueError, AttributeError, TypeError):
                continue
            if url not in seen and len(url) <= 2000:
                hits.append(
                    SearchHit(
                        url, str(row.get("title", ""))[:2000], str(row.get("body", ""))[:5000],
                        engine, len(hits) + 1,
                    )
                )
                seen.add(url)
        return hits
