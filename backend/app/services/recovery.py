"""Startup recovery for the single-process, synchronous demo runner."""

from sqlalchemy import select

from app.models import CollectionJob, ResearchRequest
from app.services.candidates import audit


def recover_interrupted_research(db):
    requests = list(
        db.scalars(
            select(ResearchRequest).where(
                ResearchRequest.status.in_(["SEARCHING", "COLLECTING", "PROCESSING"]),
                ~ResearchRequest.id.in_(
                    select(CollectionJob.research_request_id).where(
                        CollectionJob.status.in_(["QUEUED", "RUNNING"])
                    )
                ),
            )
        )
    )
    for research in requests:
        research.status = "FAILED"
        research.error = "Collection was interrupted by a server restart. Review existing candidates before retrying."
        audit(db, None, "research.interrupted", research.id)
    db.commit()
    return len(requests)
