from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import passwords
from app.models import Candidate, ResearchKeyword, ResearchRequest, User
from app.services.candidates import import_candidates
from app.services.search import MockSearchProvider


def seed():
    settings = get_settings()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == settings.admin_email.lower()))
        if not user:
            if len(settings.admin_password) < 12:
                raise RuntimeError("Set ADMIN_PASSWORD to at least 12 characters before seeding.")
            user = User(
                email=settings.admin_email.lower(),
                name="Workspace Admin",
                role="ADMIN",
                password_hash=passwords.hash(settings.admin_password),
            )
            db.add(user)
            db.flush()
        if settings.demo_mode:
            for index, title in enumerate(["Computer Vision Experts", "AI Industry Speakers"]):
                if db.scalar(select(ResearchRequest).where(ResearchRequest.title == title)):
                    continue
                research = ResearchRequest(
                    title=title,
                    description="Demo request with fictional profiles to explore the review workflow.",
                    field="Artificial Intelligence",
                    location="Istanbul",
                    target_type="Speaker",
                    requested_quantity=20 if index == 0 else 15,
                    status="READY_FOR_REVIEW",
                    created_by=user.id,
                )
                research.keywords = [
                    ResearchKeyword(value="Computer Vision"),
                    ResearchKeyword(value="Machine Learning"),
                ]
                db.add(research)
                db.flush()
                import_candidates(
                    db, research, MockSearchProvider().search(title), user.id, is_demo=True
                )
                for i, candidate in enumerate(
                    db.scalars(
                        select(Candidate)
                        .where(Candidate.research_request_id == research.id)
                        .order_by(Candidate.full_name)
                    )
                ):
                    candidate.status = [
                        "NEW",
                        "REVIEW",
                        "APPROVED",
                        "APPROVED",
                        "REJECTED",
                        "CONTACTED",
                    ][i % 6]
                    candidate.notes = (
                        "Fictional demonstration record. Status is seeded for exploring the UI."
                    )
        db.commit()
    print("Seed complete. Existing users and requests were preserved.")


if __name__ == "__main__":
    seed()
