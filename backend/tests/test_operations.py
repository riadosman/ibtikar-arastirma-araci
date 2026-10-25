from datetime import timedelta

from conftest import TEST_PASSWORD
from sqlalchemy import select
from test_workflow import BASE, request

from app.core.db import SessionLocal
from app.core.security import new_session
from app.models import LoginSession, ResearchRequest, User, now
from app.services.recovery import recover_interrupted_research


def test_password_change_revokes_every_session(auth):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        another_token = new_session(db, user)
        db.commit()
    assert (
        auth.post(
            BASE + "/auth/password",
            json={"current_password": "incorrect", "new_password": "New-test-password-123"},
        ).status_code
        == 400
    )
    assert (
        auth.post(
            BASE + "/auth/password",
            json={"current_password": TEST_PASSWORD, "new_password": "short"},
        ).status_code
        == 422
    )
    assert (
        auth.post(
            BASE + "/auth/password",
            json={"current_password": TEST_PASSWORD, "new_password": "New-test-password-123"},
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        assert list(db.scalars(select(LoginSession))) == []
    auth.cookies.set("rip_session", another_token)
    assert auth.get(BASE + "/auth/me").status_code == 401
    assert (
        auth.post(
            BASE + "/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        auth.post(
            BASE + "/auth/login",
            json={"email": "admin@example.com", "password": "New-test-password-123"},
        ).status_code
        == 200
    )


def test_service_cannot_change_password(service):
    assert (
        service.post(
            BASE + "/auth/password",
            json={"current_password": TEST_PASSWORD, "new_password": "New-test-password-123"},
        ).status_code
        == 403
    )


def test_deactivation_revokes_sessions_even_after_reactivation(auth):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "reviewer@example.com"))
        uid = user.id
        new_session(db, user)
        db.commit()
    assert auth.post(f"{BASE}/admin/users/{uid}/toggle").json()["active"] is False
    assert auth.post(f"{BASE}/admin/users/{uid}/toggle").json()["active"] is True
    with SessionLocal() as db:
        assert list(db.scalars(select(LoginSession).where(LoginSession.user_id == uid))) == []


def test_startup_recovery_preserves_finished_research(auth):
    interrupted, untouched = request(auth), request(auth)
    with SessionLocal() as db:
        research = db.get(ResearchRequest, interrupted)
        research.status = "PROCESSING"
        research.updated_at = now() - timedelta(minutes=5)
        db.commit()
        assert recover_interrupted_research(db) == 1
        assert db.get(ResearchRequest, interrupted).status == "FAILED"
        assert db.get(ResearchRequest, untouched).status == "CREATED"
        assert recover_interrupted_research(db) == 0
