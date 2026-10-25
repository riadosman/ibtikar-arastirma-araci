import os
import secrets
import tempfile
from pathlib import Path

# Never connect tests to the user's configured workspace database. SQLite is the
# fast default; set TEST_DATABASE_URL to a disposable PostgreSQL database (its name
# must contain "test") to exercise row locks and PostgreSQL types.
test_dir = tempfile.TemporaryDirectory(prefix="relationships-tests-")
test_url = os.environ.get("TEST_DATABASE_URL")
if test_url and "test" not in test_url.rsplit("/", 1)[-1]:
    raise RuntimeError("TEST_DATABASE_URL must name a disposable database containing 'test'.")
os.environ["DATABASE_URL"] = test_url or (
    "sqlite:///" + (Path(test_dir.name) / "test.db").as_posix()
)
os.environ["SECRET_KEY"] = secrets.token_hex(32)
# Containers run with APP_ENV=production; tests use SQLite and toggle auth themselves.
os.environ["APP_ENV"] = "development"
os.environ["N8N_API_KEY"] = secrets.token_urlsafe(32)
os.environ["DEMO_MODE"] = "true"
os.environ["AI_PROVIDER"] = "mock"
os.environ["COOKIE_SECURE"] = "false"
os.environ["AUTH_REQUIRED"] = "true"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["RETRY_BACKOFF_SECONDS"] = "0.01"
os.environ["SEARCH_PAUSE_SECONDS"] = "0"
os.environ["SEARCH_QUERY_INTERVAL_SECONDS"] = "0"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest
from fastapi.testclient import TestClient
from app.core.ratelimit import limiter
from app.main import app
from app.core.db import Base, engine, SessionLocal
from app.core.security import passwords
from app.models import User

TEST_PASSWORD = secrets.token_urlsafe(20)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    limiter.clear()
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    email="admin@example.com",
                    name="Test Admin",
                    role="ADMIN",
                    password_hash=passwords.hash(TEST_PASSWORD),
                ),
                User(
                    email="reviewer@example.com",
                    name="Reviewer",
                    role="USER",
                    password_hash=passwords.hash(TEST_PASSWORD),
                ),
            ]
        )
        db.commit()
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth(client):
    client.headers["X-Requested-With"] = "RelationshipPlatform"
    response = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def service(client):
    client.headers["Authorization"] = "Bearer " + os.environ["N8N_API_KEY"]
    return client
