"""Local operator tools; reset passwords without putting secrets in command history.

    python -m app.manage reset-password admin@example.com
    python -m app.manage rescore            # recompute relevance after a scoring change
"""

import argparse
from getpass import getpass

from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.core.security import passwords
from app.models import Candidate, LoginSession, ResearchRequest, User
from app.services.candidates import audit
from app.services.requirements import build_spec
from app.services.scoring import analyze


def reset_password(db, email):
    user = db.scalar(select(User).where(User.email == email.lower()).with_for_update())
    if not user:
        raise SystemExit("User not found")
    password = getpass("New password (12+ characters): ")
    if not 12 <= len(password) <= 256:
        raise SystemExit("Password must contain 12–256 characters")
    if getpass("Repeat new password: ") != password:
        raise SystemExit("Passwords do not match")
    user.password_hash = passwords.hash(password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    audit(db, None, "auth.operator_password_reset", user.id)
    db.commit()
    print("Password updated; all sessions revoked.")


def rescore(db):
    """Scores, reasons and requirement decisions only; statuses, notes and edits stay as they are."""
    total = 0
    for research in db.scalars(select(ResearchRequest)):
        spec = build_spec(research)
        for candidate in db.scalars(select(Candidate).where(Candidate.research_request_id == research.id)):
            analyze(candidate, research, spec)
            total += 1
        db.commit()
    print(f"Rescored {total} candidates.")
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["reset-password", "rescore"])
    parser.add_argument("email", nargs="?")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "rescore":
            rescore(db)
        elif not args.email:
            raise SystemExit("reset-password needs an e-mail address")
        else:
            reset_password(db, args.email)


if __name__ == "__main__":
    main()
