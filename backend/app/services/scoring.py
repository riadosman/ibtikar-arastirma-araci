"""Deterministic, explainable scores. A score is a reviewer hint, never an approval."""

from app.models import as_utc
from app.services.matching import decide, reasons
from app.services.platforms import LEAD_SOURCE
from app.services.requirements import build_spec

PROFILE_FIELDS = ("job_title", "organization", "field", "location", "bio", "expertise")
LEAD_CONFIDENCE = 15


def lead_only(candidate):
    """Known only from a profile platform's search result; no page was read."""
    return bool(candidate.sources) and all(s.source_type == LEAD_SOURCE for s in candidate.sources)


def analyze(candidate, research, spec=None):
    """Relevance from per-requirement decisions (see matching) plus evidence points."""
    spec = spec or build_spec(research)
    # Source names are page titles ("Akademik Kadro - TOBB ETÜ"): page-level topic and role.
    page_text = " ".join(s.name or "" for s in candidate.sources)
    # Evidence quotes are about this person (their record, bio or sentence).
    own_text = " ".join(s.evidence or "" for s in candidate.sources)[:5000]
    details = decide(candidate, spec, page_text, own_text)
    evidence = []
    if any(s.source_type != LEAD_SOURCE for s in candidate.sources):
        evidence.append(("kaynak sayfası var", 5))
    if candidate.bio or candidate.expertise:
        evidence.append(("biyografi/uzmanlık bilgisi var", 5))
    if candidate.organization:
        evidence.append(("kurum bilgisi var", 5))
    details["points"]["evidence"] = sum(points for _, points in evidence)
    details["score"] = max(0, min(100, sum(details["points"].values())))
    candidate.match_details = details
    candidate.relevance_score = details["score"]
    reason = "; ".join([reasons(details)] + [f"{label} (+{points})" for label, points in evidence])
    candidate.relevance_reason = reason[:1].upper() + reason[1:] + ". İnsan değerlendirmesi gerekir."
    populated = sum(bool(getattr(candidate, k)) for k in PROFILE_FIELDS)
    candidate.confidence_score = (
        min(90, 15 * min(len(candidate.sources), 3) + populated * 7) if candidate.sources else 0
    )
    if lead_only(candidate):
        candidate.confidence_score = min(candidate.confidence_score, LEAD_CONFIDENCE)
        candidate.relevance_reason += (" Yalnızca platform arama sonucu başlığından; profil sayfası "
                                       "açılmadı, doğrulanmadı.")
    if candidate.is_demo:
        candidate.confidence_score = 0
        candidate.relevance_reason += " Kurgusal demo profili; doğrulanmadı."


def quality(candidate):
    """Where the data came from, when it was seen and how much of the profile is known."""
    sources = candidate.sources
    populated = [k for k in PROFILE_FIELDS if getattr(candidate, k)]
    seen = [as_utc(s.created_at) for s in sources if s.created_at]
    if candidate.status in ("APPROVED", "CONTACTED"):
        verification = "HUMAN_APPROVED"
    elif candidate.status == "REJECTED":
        verification = "HUMAN_REJECTED"
    else:
        verification = "UNVERIFIED"
    if candidate.is_demo:
        explanation = "Kurgusal demo kaydı; güven puanı 0."
    elif not sources:
        explanation = "Kaynak yok; güven puanı 0."
    elif lead_only(candidate):
        explanation = (f"Yalnızca platform arama sonucu (profil sayfası açılmadı); güven puanı en fazla "
                       f"{LEAD_CONFIDENCE}. Kişinin kimliği ve bilgileri doğrulanmadı.")
    else:
        counted = min(len(sources), 3)
        explanation = (
            f"{len(sources)} kaynak ({counted} × 15 puan) ve "
            f"{len(populated)}/{len(PROFILE_FIELDS)} profil alanı ({len(populated)} × 7 puan); "
            "en fazla 90. Kişinin kimliği veya iletişim izni otomatik doğrulanmaz."
        )
    return {
        "source_count": len(sources),
        "source_domains": sorted({s.url.split("/")[2] for s in sources if "//" in s.url}),
        "first_seen_at": min(seen) if seen else None,
        "last_seen_at": max(seen) if seen else None,
        "verification_status": verification,
        "populated_fields": populated,
        "confidence_reason": explanation,
    }
