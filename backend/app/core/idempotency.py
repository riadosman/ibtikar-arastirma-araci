"""Idempotency-Key support for POST endpoints that create data.

The stored outcome is committed in the same transaction as the work, so a retry after
a lost response replays the first result. When two identical requests race, the unique
(scope, key) constraint rolls the second transaction back and it replays the winner.
"""

import hashlib
import json
import re
from datetime import timedelta

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models import IdempotencyRecord, now

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
RETENTION = timedelta(days=7)


class Idempotency:
    def __init__(self, request: Request, actor, payload=None):
        self.key = request.headers.get("idempotency-key")
        if self.key is not None and not KEY_PATTERN.fullmatch(self.key):
            raise HTTPException(422, "Idempotency-Key must contain 8–128 letters, digits or ._:-")
        self.scope = (actor.id or actor.role)[:64]
        body = json.dumps(jsonable_encoder(payload), sort_keys=True, ensure_ascii=False)
        self.fingerprint = hashlib.sha256(
            f"{request.method} {request.url.path}\n{body}".encode()
        ).hexdigest()

    def _find(self, db):
        return db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == self.scope, IdempotencyRecord.key == self.key
            )
        )

    def replay(self, db):
        """Return the stored response for this key, or None when the work must run."""
        if not self.key:
            return None
        record = self._find(db)
        if not record:
            return None
        if record.fingerprint != self.fingerprint:
            raise HTTPException(422, "This Idempotency-Key was already used for a different request.")
        if record.status_code is None:
            raise HTTPException(409, "A request with this Idempotency-Key is still being processed.")
        return JSONResponse(record.response, status_code=record.status_code)

    def commit(self, db, status_code, body):
        """Commit the caller's work together with its replayable response."""
        if self.key:
            db.add(
                IdempotencyRecord(
                    scope=self.scope,
                    key=self.key,
                    fingerprint=self.fingerprint,
                    status_code=status_code,
                    response=jsonable_encoder(body),
                )
            )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if not self.key:
                raise
            replayed = self.replay(db)
            if replayed is None:
                raise
            return replayed
        return JSONResponse(jsonable_encoder(body), status_code=status_code)


def purge_expired(db):
    result = db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.created_at < now() - RETENTION))
    return result.rowcount or 0
