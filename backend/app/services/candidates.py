from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import request_id_var
from app.models import AuditLog, Candidate, CandidateSource, ResearchRequest
from app.services.deduplication import deduplicate_candidates
from app.services.requirements import build_spec
from app.services.scoring import analyze

REVIEWED = ("APPROVED", "REJECTED", "CONTACTED", "ARCHIVED")


class CandidateLimitError(ValueError):
    pass


def audit(db, actor_id, action, entity_id, detail=None):
    """Record an action. `actor_id` may be an Actor, so service/local actions stay distinguishable."""
    detail = dict(detail or {})
    if hasattr(actor_id, "role"):
        detail.setdefault("actor", actor_id.role)
        actor_id = actor_id.id
    request_id = request_id_var.get()
    if request_id:
        detail.setdefault("request_id", request_id)
    db.add(AuditLog(user_id=actor_id, action=action, entity_id=entity_id, detail=detail))


def payload_sources(payload):
    sources = [source.model_dump() for source in payload.sources]
    if payload.source_url:
        sources.append(
            {
                "url": payload.source_url,
                "name": payload.source_name or "Public source",
                "source_type": payload.source_type,
                "source_date": payload.source_date,
                "evidence": payload.source_evidence,
            }
        )
    return sources


def import_candidates(db, research, payloads, actor_id, is_demo=False):
    """Create or merge sourced candidates. Caller commits; safe to repeat (dedup merges)."""
    # Lock the parent to serialize imports for a request in PostgreSQL.
    db.execute(
        select(ResearchRequest).where(ResearchRequest.id == research.id).with_for_update()
    ).scalar_one()
    # populate_existing: a long-lived worker session must see edits reviewers made meanwhile.
    existing = list(
        db.scalars(
            select(Candidate)
            .where(Candidate.research_request_id == research.id)
            .options(selectinload(Candidate.sources))
            .execution_options(populate_existing=True)
        )
    )
    limit = get_settings().max_candidates_per_research
    actor_ref = actor_id
    actor_id = getattr(actor_id, "id", actor_id)
    created, merged, ids = 0, 0, []
    spec = build_spec(research)
    for payload in payloads:
        sources = payload_sources(payload)
        data = payload.model_dump(
            exclude={
                "sources",
                "source_url",
                "source_name",
                "source_type",
                "source_date",
                "source_evidence",
                "relevance_score",
                "confidence_score",
            }
        )
        candidate = deduplicate_candidates(existing, payload)
        if candidate:
            # Never change what a reviewer already decided on; only attach new evidence.
            # Unreviewed records fill blanks, so automated data cannot overwrite edits.
            if candidate.status not in REVIEWED:
                for key, value in data.items():
                    if value and not getattr(candidate, key):
                        setattr(candidate, key, value)
            merged += 1
        else:
            if len(existing) >= limit:
                raise CandidateLimitError(
                    f"A research request can hold at most {limit} candidates."
                )
            candidate = Candidate(
                **data,
                research_request_id=research.id,
                status="NEW",
                is_demo=is_demo,
                created_by=actor_id,
            )
            db.add(candidate)
            existing.append(candidate)
            created += 1
        known = {source.url: source for source in candidate.sources}
        for source in sources:
            if source["url"] in known:
                # Same page seen again: keep the first record, add evidence if missing.
                if source.get("evidence") and not known[source["url"]].evidence:
                    known[source["url"]].evidence = source["evidence"]
                continue
            entity = CandidateSource(**source, created_by=actor_id)
            candidate.sources.append(entity)
            known[source["url"]] = entity
        candidate.updated_by = actor_id
        analyze(candidate, research, spec)
        db.flush()
        ids.append(candidate.id)
    audit(
        db,
        actor_ref,
        "candidates.import",
        research.id,
        {"created": created, "merged": merged, "demo": is_demo},
    )
    return {"created": created, "merged": merged, "candidate_ids": list(dict.fromkeys(ids))}
