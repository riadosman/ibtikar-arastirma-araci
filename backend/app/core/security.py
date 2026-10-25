import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import LoginSession, User, as_utc, now

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(24))


@dataclass
class Actor:
    id: str | None
    role: str
    user: User | None = None


def token_hash(token):
    return hmac.new(get_settings().secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def new_session(db, user):
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=token_hash(token), user_id=user.id, expires_at=now() + timedelta(hours=12)
        )
    )
    return token


def authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if credentials:
        # Compare bytes: compare_digest raises TypeError for non-ASCII str input.
        if settings.n8n_api_key and hmac.compare_digest(
            credentials.credentials.encode(), settings.n8n_api_key.encode()
        ):
            request.state.user_id = "n8n"
            return Actor(None, "SERVICE")
        raise HTTPException(401, "Invalid API key.")
    token = request.cookies.get("rip_session")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if not session or as_utc(session.expires_at) <= now():
        if settings.auth_required:
            raise HTTPException(401, "Please sign in.")
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and request.headers.get("x-requested-with") != "RelationshipPlatform"
        ):
            raise HTTPException(403, "Missing request protection header.")
        request.state.user_id = None
        return Actor(None, "LOCAL")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account is inactive.")
    # Custom header plus same-origin proxy protects cookie-authenticated mutations.
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and request.headers.get("x-requested-with") != "RelationshipPlatform"
    ):
        raise HTTPException(403, "Missing request protection header.")
    request.state.user_id = user.id
    return Actor(user.id, user.role, user)


def human(actor: Actor = Depends(authenticate)):
    if actor.role == "SERVICE":
        raise HTTPException(403, "A signed-in reviewer is required.")
    return actor


def signed_in(actor: Actor = Depends(human)):
    if actor.user is None:
        raise HTTPException(401, "Please sign in to manage an account.")
    return actor


def writer(actor: Actor = Depends(authenticate)):
    """Integration key or a person allowed to change research data."""
    if actor.role == "VIEWER":
        raise HTTPException(403, "Viewers have read-only access.")
    return actor


def researcher(actor: Actor = Depends(human)):
    if actor.role == "VIEWER":
        raise HTTPException(403, "Viewers have read-only access.")
    return actor


def manage_research(actor: Actor = Depends(researcher)):
    if get_settings().auth_required and actor.role != "ADMIN":
        raise HTTPException(403, "Administrator access is required.")
    return actor


def admin(actor: Actor = Depends(human)):
    if actor.role != "ADMIN":
        raise HTTPException(403, "Administrator access is required.")
    return actor
