"""Periodic housekeeping run by the worker: expired sessions, idempotency records, old page text."""

import logging
from datetime import timedelta

from sqlalchemy import delete, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.idempotency import purge_expired
from app.core.logging import log_event
from app.models import LoginSession, SourceDocument, now

logger = logging.getLogger("relationships.maintenance")


def run_maintenance():
    settings = get_settings()
    with SessionLocal() as db:
        sessions = db.execute(delete(LoginSession).where(LoginSession.expires_at < now())).rowcount
        keys = purge_expired(db)
        texts = 0
        if settings.source_text_retention_days:
            # Keep URL, title, status and hash as evidence; drop stored page text (personal data).
            cutoff = now() - timedelta(days=settings.source_text_retention_days)
            texts = db.execute(
                update(SourceDocument)
                .where(SourceDocument.created_at < cutoff, SourceDocument.text != "")
                .values(text="")
            ).rowcount
        db.commit()
    log_event(logger, "maintenance.completed", expired_sessions=sessions or 0,
              idempotency_records=keys or 0, source_texts_cleared=texts or 0)
