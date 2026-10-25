"""HTTP API used by the panel and by integrations such as n8n.

Roles: ADMIN (everything), USER (research and review), VIEWER (read and export),
SERVICE (n8n key: import and trigger, never approve), LOCAL (no-login mode).
"""

import logging
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.idempotency import Idempotency
from app.core.logging import log_event
from app.core.ratelimit import limiter
from app.core.security import (
    DUMMY_HASH,
    Actor,
    admin,
    authenticate,
    human,
    manage_research,
    new_session,
    passwords,
    researcher,
    signed_in,
    token_hash,
    writer,
)
from app.models import (
    AuditLog,
    Candidate,
    CandidateSource,
    CollectionJob,
    ExportJob,
    LoginSession,
    ResearchKeyword,
    ResearchRequest,
    SourceDocument,
    User,
    as_utc,
    now,
)
from app.schemas import (
    BulkCandidates,
    CandidateCreate,
    CandidateStatus,
    CandidateUpdate,
    ExportInput,
    Login,
    PasswordChange,
    ResearchCreate,
    ResearchUpdate,
    RoleChange,
    UserCreate,
    UserOut,
)
from app.services.ai import get_ai_service
from app.services.candidates import REVIEWED, CandidateLimitError, audit, import_candidates
from app.services.collection import RUNNING_RESEARCH, active_job, enqueue, request_cancel
from app.services.discovery import query_rounds
from app.services.export import ExportError, get_sheets_service, render_export
from app.services.requirements import build_spec
from app.services.scoring import analyze, quality
from app.services.search import get_search_service

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger("relationships.api")
CSRF_HEADER = ("x-requested-with", "RelationshipPlatform")


def get_entity(db, model, entity_id):
    entity = db.get(model, str(entity_id))
    if not entity:
        raise HTTPException(404, f"{model.__name__} not found.")
    return entity


def serialize(entity):
    return jsonable_encoder(
        {column.name: getattr(entity, column.name) for column in entity.__table__.columns}
    )


def candidate_out(candidate):
    return {
        **serialize(candidate),
        "sources": [serialize(s) for s in candidate.sources],
        "quality": jsonable_encoder(quality(candidate)),
    }


def research_stats(db, research_ids):
    """Candidate counts per research request in one grouped query (no N+1)."""
    stats = {
        rid: {"total": 0, "approved": 0, "rejected": 0, "awaiting_review": 0,
              "high": 0, "medium": 0, "low": 0}
        for rid in research_ids
    }
    if not research_ids:
        return stats
    score = Candidate.relevance_score
    rows = db.execute(
        select(
            Candidate.research_request_id,
            Candidate.status,
            func.count(),
            func.sum(case((score >= 75, 1), else_=0)),
            func.sum(case((and_(score >= 40, score < 75), 1), else_=0)),
            func.sum(case((score < 40, 1), else_=0)),
        )
        .where(Candidate.research_request_id.in_(research_ids))
        .group_by(Candidate.research_request_id, Candidate.status)
    ).all()
    for rid, status, count, high, medium, low in rows:
        entry = stats[rid]
        entry["total"] += count
        entry["high"] += int(high or 0)
        entry["medium"] += int(medium or 0)
        entry["low"] += int(low or 0)
        if status == "APPROVED":
            entry["approved"] += count
        elif status == "REJECTED":
            entry["rejected"] += count
        elif status in ("NEW", "REVIEW"):
            entry["awaiting_review"] += count
    return stats


def research_list_out(db, rows):
    rows = list(rows)
    stats = research_stats(db, [r.id for r in rows])
    creator_ids = {r.created_by for r in rows if r.created_by}
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(creator_ids))).all()) if creator_ids else {}
    return [
        {
            **serialize(r),
            "keywords": [k.value for k in r.keywords],
            "creator_name": names.get(r.created_by, "Araştırma aracı"),
            "stats": stats[r.id],
        }
        for r in rows
    ]


def research_out(db, research):
    return research_list_out(db, [research])[0]


def require_csrf_header(request):
    if request.headers.get(CSRF_HEADER[0]) != CSRF_HEADER[1]:
        raise HTTPException(403, "Missing request protection header.")


@router.post("/auth/login", response_model=UserOut, tags=["Authentication"])
def login(payload: Login, response: Response, request: Request, db: Session = Depends(get_db)):
    require_csrf_header(request)
    settings = get_settings()
    ip = request.client.host if request.client else "unknown"
    # Per account (brute force) and per address (spraying). Behind Docker the address may
    # be shared, so its limit is higher.
    if not limiter.allow(("login-email", payload.email.lower()), settings.login_attempts_per_minute) or (
        not limiter.allow(("login-ip", ip), settings.login_attempts_per_minute * 5)
    ):
        raise HTTPException(429, "Too many sign-in attempts. Try again in a minute.",
                            headers={"Retry-After": "60"})
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    valid = passwords.verify(payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        log_event(logger, "auth.login_failed", logging.WARNING)
        raise HTTPException(401, "Incorrect email or password.")
    old = request.cookies.get("rip_session")
    if old:
        old_session = db.get(LoginSession, token_hash(old))
        if old_session:
            db.delete(old_session)
    token = new_session(db, user)
    audit(db, user.id, "auth.login", user.id)
    db.commit()
    response.set_cookie(
        "rip_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=43200,
        path="/",
    )
    return user


@router.post("/auth/logout", tags=["Authentication"])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    # Works with an expired session too, so the browser cookie is always cleared.
    require_csrf_header(request)
    if request.headers.get("authorization"):
        raise HTTPException(403, "A signed-in reviewer is required.")
    token = request.cookies.get("rip_session")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie("rip_session", path="/")
    return {"message": "Signed out."}


@router.get("/auth/me", response_model=UserOut, tags=["Authentication"])
def me(actor: Actor = Depends(signed_in)):
    return actor.user


@router.post("/auth/password", tags=["Authentication"])
def change_password(
    payload: PasswordChange,
    response: Response,
    actor: Actor = Depends(signed_in),
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not passwords.verify(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise HTTPException(422, "Choose a different password.")
    user.password_hash = passwords.hash(payload.new_password)
    user.updated_by = actor.id
    db.execute(delete(LoginSession).where(LoginSession.user_id == actor.id))
    audit(db, actor, "auth.password_changed", actor.id)
    db.commit()
    response.delete_cookie("rip_session", path="/")
    return {"message": "Password changed. Sign in again on all devices."}


@router.get("/dashboard", tags=["Dashboard"])
def dashboard(actor: Actor = Depends(human), db: Session = Depends(get_db)):
    counts = dict(
        db.execute(select(Candidate.status, func.count()).group_by(Candidate.status)).all()
    )
    recent = db.scalars(
        select(ResearchRequest).order_by(ResearchRequest.created_at.desc()).limit(6)
    )
    return {
        "active_requests": db.scalar(
            select(func.count())
            .select_from(ResearchRequest)
            .where(ResearchRequest.status.notin_(["COMPLETED", "FAILED"]))
        ),
        "candidates_found": sum(counts.values()),
        "awaiting_review": counts.get("NEW", 0) + counts.get("REVIEW", 0),
        "approved": counts.get("APPROVED", 0),
        "rejected": counts.get("REJECTED", 0),
        "recent_requests": research_list_out(db, recent),
    }


@router.post("/research-requests", status_code=201, tags=["Research"])
def create_research(
    payload: ResearchCreate,
    request: Request,
    actor: Actor = Depends(writer),
    db: Session = Depends(get_db),
):
    idempotency = Idempotency(request, actor, payload)
    if replay := idempotency.replay(db):
        return replay
    research = ResearchRequest(
        **payload.model_dump(exclude={"keywords"}), created_by=actor.id, updated_by=actor.id
    )
    research.keywords = [ResearchKeyword(value=k) for k in payload.keywords]
    db.add(research)
    db.flush()
    audit(db, actor, "research.create", research.id)
    return idempotency.commit(db, 201, research_out(db, research))


@router.get("/research-requests", tags=["Research"])
def list_research(
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(authenticate),
    db: Session = Depends(get_db),
):
    query = select(ResearchRequest)
    if q:
        query = query.where(ResearchRequest.title.icontains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(ResearchRequest.created_at.desc(), ResearchRequest.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": research_list_out(db, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/research-requests/{research_id}", tags=["Research"])
def read_research(
    research_id: UUID, actor: Actor = Depends(authenticate), db: Session = Depends(get_db)
):
    return research_out(db, get_entity(db, ResearchRequest, research_id))


@router.patch("/research-requests/{research_id}", tags=["Research"])
def update_research(
    research_id: UUID,
    payload: ResearchUpdate,
    actor: Actor = Depends(researcher),
    db: Session = Depends(get_db),
):
    research = db.scalar(
        select(ResearchRequest).where(ResearchRequest.id == str(research_id)).with_for_update()
    )
    if not research:
        raise HTTPException(404, "ResearchRequest not found.")
    if research.status in RUNNING_RESEARCH or active_job(db, research.id):
        raise HTTPException(409, "Research is currently running.")
    if payload.status in RUNNING_RESEARCH:
        raise HTTPException(422, "Use the collect endpoint to start research.")
    excluded = {"keywords"} | (
        {"search_language"} if "search_language" not in payload.model_fields_set else set()
    )
    for key, value in payload.model_dump(exclude=excluded).items():
        setattr(research, key, value)
    research.keywords = [ResearchKeyword(value=k) for k in payload.keywords]
    research.updated_by = actor.id
    spec = build_spec(research)
    for candidate in db.scalars(
        select(Candidate).where(Candidate.research_request_id == research.id)
    ):
        analyze(candidate, research, spec)
    audit(db, actor, "research.update", research.id)
    db.commit()
    return research_out(db, research)


@router.delete("/research-requests/{research_id}", status_code=204, tags=["Research"])
def delete_research(
    research_id: UUID, actor: Actor = Depends(manage_research), db: Session = Depends(get_db)
):
    research = db.scalar(
        select(ResearchRequest).where(ResearchRequest.id == str(research_id)).with_for_update()
    )
    if not research:
        raise HTTPException(404, "ResearchRequest not found.")
    if research.status in RUNNING_RESEARCH or active_job(db, research.id):
        raise HTTPException(409, "Research is currently running.")
    db.delete(research)
    audit(db, actor, "research.delete", str(research_id))
    db.commit()


@router.post("/research-requests/{research_id}/run", tags=["Research"])
def run_research(research_id: UUID, actor: Actor = Depends(researcher),
                 db: Session = Depends(get_db)):
    """Demo-only: imports fictional profiles synchronously. Live search uses /collect."""
    if not get_settings().demo_mode:
        raise HTTPException(
            409, "Demo search is disabled. Use live collection or the integration API."
        )
    research = db.scalar(
        select(ResearchRequest).where(ResearchRequest.id == str(research_id)).with_for_update()
    )
    if not research:
        raise HTTPException(404, "ResearchRequest not found.")
    if research.status in RUNNING_RESEARCH:
        raise HTTPException(409, "Research is already running.")
    try:
        results = get_search_service().search(
            f"{research.field} {research.location} {research.target_type}"
        )
        result = import_candidates(db, research, results, actor, is_demo=True)
        research.status, research.error = "READY_FOR_REVIEW", None
        research.updated_by = actor.id
        audit(db, actor, "research.run", research.id)
        db.commit()
        return result
    except Exception:
        log_event(logger, "research.run_failed", logging.ERROR, exc_info=True,
                  research_id=research.id)
        db.rollback()
        raise HTTPException(502, "Search failed. Retry or contact an administrator.")


@router.post("/research-requests/{research_id}/collect", status_code=202, tags=["Collection"])
def collect(
    research_id: UUID,
    request: Request,
    actor: Actor = Depends(writer),
    db: Session = Depends(get_db),
):
    if not get_settings().live_search_enabled:
        raise HTTPException(409, "Live collection is disabled by the administrator.")
    idempotency = Idempotency(request, actor)
    if replay := idempotency.replay(db):
        return replay
    research = db.scalar(
        select(ResearchRequest).where(ResearchRequest.id == str(research_id)).with_for_update()
    )
    if not research:
        raise HTTPException(404, "Research request not found.")
    # A concurrent duplicate may have committed while we waited for the row lock.
    if replay := idempotency.replay(db):
        return replay
    try:
        job = enqueue(db, research, actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return idempotency.commit(db, 202, serialize(job))


@router.post("/research-requests/{research_id}/collection/cancel", tags=["Collection"])
def cancel_collection(
    research_id: UUID, actor: Actor = Depends(writer), db: Session = Depends(get_db)
):
    """Queued jobs stop immediately; a running job stops after its current source."""
    research = db.scalar(
        select(ResearchRequest).where(ResearchRequest.id == str(research_id)).with_for_update()
    )
    if not research:
        raise HTTPException(404, "Research request not found.")
    try:
        job = request_cancel(db, research, actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return serialize(job)


@router.get("/research-requests/{research_id}/collection", tags=["Collection"])
def collection_status(
    research_id: UUID,
    actor: Actor = Depends(authenticate),
    db: Session = Depends(get_db),
    summary: bool = False,
):
    research = get_entity(db, ResearchRequest, research_id)
    job = db.scalar(
        select(CollectionJob)
        .where(CollectionJob.research_request_id == str(research_id))
        .order_by(CollectionJob.created_at.desc())
        .limit(1)
    )
    if not job:
        return {"job": None, "sources": [], "research_status": research.status}
    if summary:
        # Lightweight polling payload: no page text.
        sources = db.execute(
            select(SourceDocument.url, SourceDocument.title, SourceDocument.status)
            .where(SourceDocument.collection_job_id == job.id)
            .order_by(SourceDocument.created_at)
        ).all()
        running = job.status in ("QUEUED", "RUNNING")
        end = now() if running else as_utc(job.finished_at or job.updated_at)
        elapsed = max(0, int((end - as_utc(job.created_at)).total_seconds()))
        rows = db.scalars(
            select(Candidate)
            .where(Candidate.research_request_id == research.id)
            .order_by(Candidate.created_at.desc())
            .limit(20)
        )
        counts = dict(
            db.execute(
                select(Candidate.status, func.count())
                .where(Candidate.research_request_id == research.id)
                .group_by(Candidate.status)
            ).all()
        )
        if not running:
            phase = "done"
        elif job.cancel_requested:
            phase = "cancelling"
        elif job.status == "QUEUED":
            phase = "queued"
        elif research.status == "SEARCHING":
            phase = "fallback" if job.processed else "searching"
        else:
            phase = "reading"
        return {
            "job": serialize(job),
            "research_status": research.status,
            "progress": {
                "phase": phase,
                "elapsed_seconds": elapsed,
                "readable": sum(s.status in ("EXTRACTED", "NEEDS_REVIEW") for s in sources),
                "blocked": sum(s.status in ("FAILED", "SKIPPED") for s in sources),
                "current_source": next((s.url for s in sources if s.status == "READING"), None),
                "round": int((job.stats or {}).get("search_rounds", 0)),
                "rounds": len(query_rounds(research)),
                "page": int((job.stats or {}).get("search_pages", 0)) or 1,
            },
            "sources": [{"url": s.url, "title": s.title, "status": s.status} for s in sources],
            "candidates": [
                {"id": c.id, "full_name": c.full_name, "job_title": c.job_title,
                 "status": c.status}
                for c in rows
            ],
            "total_candidates": sum(counts.values()),
            "approved": counts.get("APPROVED", 0),
            "awaiting_review": counts.get("NEW", 0) + counts.get("REVIEW", 0),
        }
    sources = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.collection_job_id == job.id)
        .order_by(SourceDocument.created_at)
    )
    return {
        "job": serialize(job),
        "research_status": research.status,
        "sources": [serialize(source) for source in sources],
    }


@router.post("/research-requests/{research_id}/complete", tags=["n8n"])
def complete(research_id: UUID, actor: Actor = Depends(writer), db: Session = Depends(get_db)):
    research = db.scalar(
        select(ResearchRequest).where(ResearchRequest.id == str(research_id)).with_for_update()
    )
    if not research:
        raise HTTPException(404, "ResearchRequest not found.")
    if active_job(db, research.id):
        raise HTTPException(409, "Collection is still running.")
    # Completion of collection does not imply reviewer approval or completion of review.
    if research.status != "COMPLETED":
        research.status = "READY_FOR_REVIEW"
    research.error = None
    research.updated_by = actor.id
    audit(db, actor, "research.collection_complete", research.id)
    db.commit()
    return research_out(db, research)


def run_import(db, research_id, payloads, actor):
    research = get_entity(db, ResearchRequest, research_id)
    try:
        return import_candidates(db, research, payloads, actor)
    except CandidateLimitError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@router.post("/research-requests/{research_id}/candidates", status_code=201, tags=["n8n"])
def add_candidate(
    research_id: UUID,
    payload: CandidateCreate,
    request: Request,
    actor: Actor = Depends(writer),
    db: Session = Depends(get_db),
):
    idempotency = Idempotency(request, actor, payload)
    if replay := idempotency.replay(db):
        return replay
    result = run_import(db, research_id, [payload], actor)
    candidate = candidate_out(db.get(Candidate, result["candidate_ids"][0]))
    return idempotency.commit(db, 201, {**result, "candidate": candidate})


@router.post("/research-requests/{research_id}/candidates/bulk", tags=["n8n"])
def bulk_candidates(
    research_id: UUID,
    payload: BulkCandidates,
    request: Request,
    actor: Actor = Depends(writer),
    db: Session = Depends(get_db),
):
    idempotency = Idempotency(request, actor, payload)
    if replay := idempotency.replay(db):
        return replay
    result = run_import(db, research_id, payload.candidates, actor)
    return idempotency.commit(db, 200, result)


def candidate_list(
    db,
    research_id=None,
    q="",
    status=None,
    min_score=0,
    sort="relevance_score",
    direction="desc",
    page=1,
    page_size=20,
    awaiting_review=False,
):
    query = select(Candidate)
    if research_id:
        query = query.where(Candidate.research_request_id == str(research_id))
    if q:
        query = query.where(
            or_(
                *(
                    column.icontains(q, autoescape=True)
                    for column in (
                        Candidate.full_name,
                        Candidate.organization,
                        Candidate.job_title,
                        Candidate.location,
                    )
                )
            )
        )
    if awaiting_review:
        query = query.where(Candidate.status.in_(["NEW", "REVIEW"]))
    elif status:
        query = query.where(Candidate.status == status)
    query = query.where(Candidate.relevance_score >= min_score)
    if sort not in (
        "full_name",
        "organization",
        "relevance_score",
        "confidence_score",
        "created_at",
    ) or direction not in ("asc", "desc"):
        raise HTTPException(422, "Invalid sort order.")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    column = getattr(Candidate, sort)
    query = (
        query.order_by(column.asc() if direction == "asc" else column.desc(), Candidate.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [candidate_out(c) for c in db.scalars(query)],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/candidates", tags=["Candidates"])
def all_candidates(
    q: str = Query("", max_length=200),
    status: CandidateStatus | None = None,
    awaiting_review: bool = False,
    min_score: int = Query(0, ge=0, le=100),
    sort: str = "relevance_score",
    direction: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(authenticate),
    db: Session = Depends(get_db),
):
    return candidate_list(
        db,
        q=q,
        status=status,
        min_score=min_score,
        sort=sort,
        direction=direction,
        page=page,
        page_size=page_size,
        awaiting_review=awaiting_review,
    )


@router.get("/research-requests/{research_id}/candidates", tags=["Candidates"])
def request_candidates(
    research_id: UUID,
    q: str = Query("", max_length=200),
    status: CandidateStatus | None = None,
    awaiting_review: bool = False,
    min_score: int = Query(0, ge=0, le=100),
    sort: str = "relevance_score",
    direction: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(authenticate),
    db: Session = Depends(get_db),
):
    get_entity(db, ResearchRequest, research_id)
    return candidate_list(
        db, research_id, q, status, min_score, sort, direction, page, page_size, awaiting_review
    )


@router.get("/candidates/{candidate_id}", tags=["Candidates"])
def read_candidate(
    candidate_id: UUID, actor: Actor = Depends(authenticate), db: Session = Depends(get_db)
):
    return candidate_out(get_entity(db, Candidate, candidate_id))


@router.patch("/candidates/{candidate_id}", tags=["Candidates"])
def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    actor: Actor = Depends(writer),
    db: Session = Depends(get_db),
):
    candidate = db.scalar(
        select(Candidate)
        .where(Candidate.id == str(candidate_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not candidate:
        raise HTTPException(404, "Candidate not found.")
    updates = payload.model_dump(exclude_unset=True, exclude={"sources"})
    if actor.role == "SERVICE":
        if "status" in updates:
            raise HTTPException(403, "Only a human reviewer may change candidate status.")
        # What a person approved is what gets exported; integrations may only add notes.
        if candidate.status in REVIEWED and (set(updates) - {"notes"} or payload.sources):
            raise HTTPException(409, "This candidate was already reviewed; a person must edit it.")
    for key, value in updates.items():
        setattr(candidate, key, value)
    if payload.sources is not None:
        # Reconcile by URL instead of deleting/re-inserting rows with unique constraints.
        old = {s.url: s for s in candidate.sources}
        reconciled = []
        for source in {s.url: s for s in payload.sources}.values():
            entity = old.get(source.url) or CandidateSource(created_by=actor.id)
            for key, value in source.model_dump().items():
                setattr(entity, key, value)
            entity.updated_by = actor.id
            reconciled.append(entity)
        candidate.sources = reconciled
    candidate.updated_by = actor.id
    if set(updates) - {"status", "notes"} or payload.sources is not None:
        analyze(candidate, candidate.research)
    audit(
        db,
        actor,
        "candidate.update",
        candidate.id,
        {"fields": sorted(payload.model_fields_set), "status": candidate.status},
    )
    db.commit()
    return candidate_out(candidate)


@router.delete("/candidates/{candidate_id}", status_code=204, tags=["Candidates"])
def delete_candidate(
    candidate_id: UUID, actor: Actor = Depends(manage_research), db: Session = Depends(get_db)
):
    db.delete(get_entity(db, Candidate, candidate_id))
    audit(db, actor, "candidate.delete", str(candidate_id))
    db.commit()


def export_sheets(db, request, actor, research, candidates, payload):
    """Create or resume a Google Sheet. With an Idempotency-Key, retries reuse one sheet."""
    idempotency = Idempotency(request, actor, payload)
    if replay := idempotency.replay(db):
        return replay
    # The fingerprint covers the research (URL) and options, so a key reused for another
    # export never resumes someone else's sheet.
    key = (
        f"{idempotency.scope}:{idempotency.key}:{idempotency.fingerprint[:16]}"
        if idempotency.key else None
    )
    job = db.scalar(select(ExportJob).where(ExportJob.idempotency_key == key)) if key else None
    if job and job.status == "PENDING" and as_utc(job.updated_at) > now() - timedelta(minutes=10):
        raise HTTPException(409, "This export is still running. Try again shortly.")
    if not job:
        job = ExportJob(research_request_id=research.id, format="sheets", status="PENDING",
                        include_all=payload.include_all, candidate_count=len(candidates),
                        created_by=actor.id, idempotency_key=key)
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "This export is still running. Try again shortly.")
    else:
        job.status = "PENDING"
        db.commit()
    provider = get_sheets_service()
    try:
        if job.external_id:
            sheet = {"provider": provider.provider, "id": job.external_id,
                     "url": job.external_url, "title": research.title}
        else:
            sheet = provider.create_sheet(f"{research.title} - adaylar")
            job.external_id, job.external_url = sheet.get("id"), sheet.get("url")
            db.commit()  # remember the sheet before writing, so a retry reuses it
        result = provider.append_candidates(sheet, candidates)
        if provider.provider == "google" and actor.user is not None:
            result = provider.share_sheet(result, actor.user.email)
    except ExportError as exc:
        db.rollback()
        job.status, job.detail = "FAILED", str(exc)
        db.commit()
        log_event(logger, "export.failed", logging.WARNING, export_id=job.id, format="sheets",
                  retryable=exc.retryable)
        raise HTTPException(503 if exc.retryable else 502, str(exc))
    except Exception:
        db.rollback()
        job.status, job.detail = "FAILED", "Unexpected export error."
        db.commit()
        log_event(logger, "export.failed", logging.ERROR, exc_info=True, export_id=job.id,
                  format="sheets")
        raise HTTPException(500, "Export failed. Please try again.")
    job.status = "MOCK" if provider.provider == "mock" else "COMPLETED"
    job.candidate_count = len(candidates)
    job.detail = result.get("message") or result.get("url")
    audit(db, actor, "export.create", job.id,
          {"format": "sheets", "count": len(candidates), "include_all": payload.include_all})
    log_event(logger, "export.completed", export_id=job.id, format="sheets", rows=len(candidates))
    return idempotency.commit(db, 200, {**result, "export_id": job.id})


@router.post("/research-requests/{research_id}/exports", tags=["Exports"])
def export(
    research_id: UUID,
    payload: ExportInput,
    request: Request,
    actor: Actor = Depends(human),
    db: Session = Depends(get_db),
):
    research = get_entity(db, ResearchRequest, research_id)
    query = (
        select(Candidate)
        .where(Candidate.research_request_id == research.id)
        .order_by(Candidate.full_name, Candidate.id)
    )
    if not payload.include_all:
        query = query.where(Candidate.status == "APPROVED")
    candidates = list(db.scalars(query))
    if payload.format == "sheets":
        return export_sheets(db, request, actor, research, candidates, payload)
    job = ExportJob(
        research_request_id=research.id,
        format=payload.format,
        include_all=payload.include_all,
        candidate_count=len(candidates),
        created_by=actor.id,
    )
    db.add(job)
    try:
        content, media_type = render_export(candidates, payload.format)
    except Exception:
        log_event(logger, "export.failed", logging.ERROR, exc_info=True, format=payload.format)
        db.rollback()
        raise HTTPException(500, "Export failed. Please try again.")
    db.flush()
    audit(
        db,
        actor,
        "export.create",
        job.id,
        {"format": payload.format, "count": len(candidates), "include_all": payload.include_all},
    )
    db.commit()
    log_event(logger, "export.completed", export_id=job.id, format=payload.format,
              rows=len(candidates))
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="candidates-{research.id[:8]}.{payload.format}"'
        },
    )


@router.get("/exports", tags=["Exports"])
def exports(
    page: int = Query(1, ge=1), actor: Actor = Depends(human), db: Session = Depends(get_db)
):
    query = select(ExportJob).order_by(ExportJob.created_at.desc(), ExportJob.id)
    return {
        "items": [serialize(j) for j in db.scalars(query.offset((page - 1) * 20).limit(20))],
        "total": db.scalar(select(func.count()).select_from(ExportJob)),
        "page": page,
        "page_size": 20,
    }


@router.post("/ai/interpret", tags=["AI"])
def interpret(payload: ResearchCreate, actor: Actor = Depends(researcher)):
    try:
        return get_ai_service().interpret(payload.field, payload.description)
    except Exception:
        log_event(logger, "ai.interpret_failed", logging.WARNING, exc_info=True)
        raise HTTPException(
            502, "Unable to connect to the AI provider. You can enter keywords manually."
        )


@router.post("/candidates/{candidate_id}/classify", tags=["AI"])
def classify(candidate_id: UUID, actor: Actor = Depends(researcher),
             db: Session = Depends(get_db)):
    candidate = get_entity(db, Candidate, candidate_id)
    try:
        return get_ai_service().classify(
            {
                k: getattr(candidate, k)
                for k in ("headline", "job_title", "field", "bio", "expertise", "relevance_reason")
            }
        )
    except Exception:
        log_event(logger, "ai.classify_failed", logging.WARNING, exc_info=True)
        raise HTTPException(
            502, "Unable to connect to the AI provider. Deterministic analysis is still available."
        )


@router.get("/settings", tags=["Settings"])
def settings(actor: Actor = Depends(human)):
    config = get_settings()
    return {
        "demo_mode": config.demo_mode,
        "live_search_enabled": config.live_search_enabled,
        "live_search_provider": "Public web search (no user API key)",
        "search_provider": "public_web" if config.live_search_enabled else "disabled",
        "ai_provider": "openai"
        if config.ai_provider == "openai" and config.openai_api_key
        else "mock",
        "sheets_provider": "google" if config.google_sheets_configured else "mock",
        "api_key_configured": bool(config.n8n_api_key),
        "workspace": "Shared internal workspace",
    }


@router.get("/admin/users", response_model=list[UserOut], tags=["Admin"])
def users(actor: Actor = Depends(admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.post("/admin/users", response_model=UserOut, status_code=201, tags=["Admin"])
def create_user(payload: UserCreate, actor: Actor = Depends(admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(409, "A user with this email already exists.")
    user = User(
        email=payload.email.lower(),
        name=payload.name,
        password_hash=passwords.hash(payload.password),
        role=payload.role,
        created_by=actor.id,
    )
    db.add(user)
    db.flush()
    audit(db, actor, "user.create", user.id, {"role": user.role})
    db.commit()
    return user


@router.post("/admin/users/{user_id}/toggle", response_model=UserOut, tags=["Admin"])
def toggle_user(user_id: UUID, actor: Actor = Depends(admin), db: Session = Depends(get_db)):
    user = get_entity(db, User, user_id)
    if user.id == actor.id:
        raise HTTPException(409, "You cannot deactivate your own account.")
    user.active = not user.active
    if not user.active:
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    user.updated_by = actor.id
    audit(db, actor, "user.toggle", user.id, {"active": user.active})
    db.commit()
    return user


@router.post("/admin/users/{user_id}/role", response_model=UserOut, tags=["Admin"])
def change_role(
    user_id: UUID, payload: RoleChange, actor: Actor = Depends(admin),
    db: Session = Depends(get_db),
):
    user = get_entity(db, User, user_id)
    if user.id == actor.id:
        raise HTTPException(409, "You cannot change your own role.")
    previous, user.role = user.role, payload.role
    user.updated_by = actor.id
    # A changed role takes effect immediately: existing sessions must sign in again.
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    audit(db, actor, "user.role", user.id, {"from": previous, "to": user.role})
    db.commit()
    return user


@router.get("/admin/audit", tags=["Admin"])
def audit_log(
    page: int = Query(1, ge=1), actor: Actor = Depends(admin), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).offset((page - 1) * 100).limit(100)
    )
    return [serialize(a) for a in rows]
