"""Python research panel with optional account login; uses the same API operations."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import collection_status, get_entity, research_list_out, research_out
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import Actor, authenticate
from app.models import Candidate, ResearchRequest, User
from app.services.scoring import quality

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
STATUS_LABELS = {
    "CREATED": "Yeni", "SEARCHING": "Aranıyor", "COLLECTING": "Kaynaklar okunuyor",
    "PROCESSING": "İşleniyor", "READY_FOR_REVIEW": "Değerlendirmeye hazır",
    "COMPLETED": "Tamamlandı", "PARTIAL": "Kısmi sonuç", "FAILED": "Sonuç alınamadı",
    "QUEUED": "Sırada", "RUNNING": "Çalışıyor", "SKIPPED": "Atlandı",
    "NEEDS_REVIEW": "Kişi profili çıkarılamadı", "EXTRACTED": "Aday çıkarıldı",
    "READING": "Okunuyor", "DISCOVERED": "Sırada", "NOT_NEEDED": "Hedefe ulaşıldı",
    "NO_RESULTS": "Aday bulunamadı", "CANCELLED": "İptal edildi",
    "DUPLICATE": "Aynı içerik", "NEW": "Yeni", "REVIEW": "İnceleniyor", "APPROVED": "Onaylı",
    "REJECTED": "Reddedildi", "CONTACTED": "İletişime geçildi", "ARCHIVED": "Arşivlendi",
    "PENDING": "Sürüyor", "MOCK": "Önizleme",
    "HUMAN_APPROVED": "İnsan onaylı", "HUMAN_REJECTED": "İnsan tarafından reddedildi",
    "UNVERIFIED": "Doğrulanmadı",
    "ADMIN": "Yönetici", "USER": "Araştırmacı", "VIEWER": "İzleyici",
}
CANDIDATE_STATUSES = ["NEW", "REVIEW", "APPROVED", "REJECTED", "CONTACTED", "ARCHIVED"]
ERROR_MESSAGES = {
    403: "Bu sayfayı görüntüleme veya bu işlemi yapma yetkiniz yok.",
    404: "Aradığınız kayıt bulunamadı. Silinmiş olabilir.",
    422: "Geçersiz adres veya parametre.",
}
PAGE_KINDS = {
    "people_list": "kişi listesi", "profile": "profil sayfası", "event": "etkinlik", "article": "haber/yazı",
    "page": "genel sayfa", "platform": "kapalı platform", "job_listing": "iş ilanı", "definition": "tanım yazısı",
    "document": "belge", "shop": "ürün sayfası",
}
DECISIONS = {
    "role": {"match": "Uyuyor", "inferred": "Sayfadan çıkarıldı", "any": "Şart yok", "unknown": "Belirtilmemiş",
             "mismatch": "Farklı"},
    "topic": {"match": "Kişinin kaydında geçiyor", "page": "Yalnızca sayfada geçiyor", "unknown": "Doğrulanmadı"},
    "place": {"match": "Uyuyor", "country": "Aynı ülke, şehir yok", "mismatch": "Farklı", "unknown": "Bilinmiyor",
              "any": "Şart yok"},
}
templates.env.filters["status_label"] = lambda value: STATUS_LABELS.get(value, value)
templates.env.filters["page_kind"] = lambda value: PAGE_KINDS.get(value or "", value or "")
templates.env.filters["decision"] = lambda value, kind: DECISIONS.get(kind, {}).get(value or "", value or "—")
templates.env.globals["candidate_statuses"] = CANDIDATE_STATUSES


def panel_actor(request: Request, db: Session = Depends(get_db)):
    try:
        actor = authenticate(request, credentials=None, db=db)
        if actor.role == "SERVICE":
            raise HTTPException(403)
        return actor
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(303, headers={"Location": "/panel/login"})
        raise


def panel_config():
    # Only what templates need; never hand the Settings object (secrets) to templates.
    settings = get_settings()
    return {
        "auth_required": settings.auth_required,
        "live_search_enabled": settings.live_search_enabled,
        "sheets_enabled": settings.google_sheets_configured,
    }


def render(request, template_name, actor=None, status_code=200, **context):
    return templates.TemplateResponse(
        request=request,
        name=template_name + ".html",
        context={
            "user": actor.user if actor else None,
            "can_edit": actor is not None and actor.role not in ("VIEWER",),
            "config": panel_config(),
            **context,
        },
        status_code=status_code,
    )


def render_error(request, status_code, detail):
    message = ERROR_MESSAGES.get(status_code, "İşlem tamamlanamadı. Lütfen yeniden deneyin.")
    return render(request, "error", None, status_code=status_code, message=message,
                  status=status_code)


@router.get("/")
def home():
    return RedirectResponse("/panel", status_code=303)


@router.get("/login")
@router.get("/panel/login")
def login_page(request: Request):
    return render(request, "login")


@router.get("/panel")
def dashboard(
    request: Request,
    q: str = "",
    page: int = 1,
    actor: Actor = Depends(panel_actor),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    query = select(ResearchRequest)
    if q:
        query = query.where(ResearchRequest.title.icontains(q[:200], autoescape=True))
    rows = list(
        db.scalars(
            query.order_by(ResearchRequest.created_at.desc(), ResearchRequest.id)
            .offset((page - 1) * 20)
            .limit(21)
        )
    )
    return render(
        request,
        "dashboard",
        actor,
        research=research_list_out(db, rows[:20]),
        q=q,
        page=page,
        more=len(rows) > 20,
    )


@router.get("/panel/research/new")
def new_research(request: Request, actor: Actor = Depends(panel_actor)):
    if actor.role == "VIEWER":
        raise HTTPException(403)
    return render(request, "research_form", actor, research=None)


@router.get("/panel/research/{rid}/edit")
def edit_research(
    request: Request, rid: UUID, actor: Actor = Depends(panel_actor), db: Session = Depends(get_db)
):
    if actor.role == "VIEWER":
        raise HTTPException(403)
    return render(
        request,
        "research_form",
        actor,
        research=research_out(db, get_entity(db, ResearchRequest, rid)),
    )


@router.get("/panel/research/{rid}")
def research_page(
    request: Request,
    rid: UUID,
    q: str = "",
    status: str = "",
    page: int = 1,
    actor: Actor = Depends(panel_actor),
    db: Session = Depends(get_db),
):
    research = get_entity(db, ResearchRequest, rid)
    query = select(Candidate).where(Candidate.research_request_id == str(rid))
    if q:
        query = query.where(Candidate.full_name.icontains(q[:200], autoescape=True))
    if status in CANDIDATE_STATUSES:
        query = query.where(Candidate.status == status)
    page = max(1, page)
    rows = list(
        db.scalars(
            query.order_by(Candidate.relevance_score.desc(), Candidate.id)
            .offset((page - 1) * 20)
            .limit(21)
        )
    )
    collection = collection_status(rid, actor, db)
    job = collection["job"]
    return render(
        request,
        "research",
        actor,
        research=research_out(db, research),
        candidates=rows[:20],
        collection=collection,
        q=q,
        status=status,
        page=page,
        more=len(rows) > 20,
        running=research.status in ("SEARCHING", "COLLECTING", "PROCESSING")
        or bool(job and job["status"] in ("QUEUED", "RUNNING")),
    )


@router.get("/panel/candidates/{cid}")
def candidate_page(
    request: Request, cid: UUID, actor: Actor = Depends(panel_actor), db: Session = Depends(get_db)
):
    candidate = get_entity(db, Candidate, cid)
    return render(request, "candidate", actor, candidate=candidate, quality=quality(candidate))


@router.get("/panel/settings")
def settings_page(request: Request, actor: Actor = Depends(panel_actor)):
    if actor.user is None:
        return RedirectResponse("/panel", status_code=303)
    return render(request, "settings", actor)


@router.get("/panel/users")
def users_page(
    request: Request, actor: Actor = Depends(panel_actor), db: Session = Depends(get_db)
):
    if actor.role != "ADMIN":
        raise HTTPException(403, "Administrator access required")
    return render(
        request, "users", actor, users=list(db.scalars(select(User).order_by(User.created_at)))
    )
