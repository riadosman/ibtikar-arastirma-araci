from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

CandidateStatus = Literal["NEW", "REVIEW", "APPROVED", "REJECTED", "CONTACTED", "ARCHIVED"]
ResearchStatus = Literal[
    "CREATED",
    "SEARCHING",
    "COLLECTING",
    "PROCESSING",
    "READY_FOR_REVIEW",
    "COMPLETED",
    "FAILED",
    "NO_RESULTS",
]
Role = Literal["USER", "ADMIN", "VIEWER"]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class Login(Schema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserCreate(Login):
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)
    role: Role = "USER"


class RoleChange(Schema):
    role: Role


class PasswordChange(Schema):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class UserOut(Schema):
    id: str
    email: str
    name: str
    role: str
    active: bool


class ResearchCreate(Schema):
    search_language: Literal["auto", "tr", "en", "de", "fr", "es", "ar"] = "auto"
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    field: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    target_type: str = Field(min_length=1, max_length=100)
    requested_quantity: int = Field(ge=1, le=1000)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=10000)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value):
        if any(not x.strip() or len(x) > 200 for x in value):
            raise ValueError("Keywords must contain 1–200 characters.")
        return list(dict.fromkeys(x.strip() for x in value))


class ResearchUpdate(ResearchCreate):
    status: ResearchStatus


def valid_url(value):
    if value is None:
        return value
    parsed = urlparse(value)
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use a public http or https URL without embedded credentials.")
    return value


class SourceIn(Schema):
    url: str = Field(max_length=2000)
    name: str = Field(min_length=1, max_length=200)
    source_type: str = Field(default="website", max_length=100)
    source_date: datetime | None = None
    evidence: str | None = Field(default=None, max_length=2000)
    _url = field_validator("url")(valid_url)


class CandidateFields(Schema):
    headline: str | None = Field(default=None, max_length=2000)
    job_title: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    organization_type: str | None = Field(default=None, max_length=100)
    field: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=2000)
    linkedin_url: str | None = Field(default=None, max_length=2000)
    twitter_url: str | None = Field(default=None, max_length=2000)
    instagram_url: str | None = Field(default=None, max_length=2000)
    public_email: EmailStr | None = None
    public_phone: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=20000)
    expertise: list[str] = Field(default_factory=list, max_length=100)
    relevance_score: int | None = Field(default=None, ge=0, le=100)
    confidence_score: int | None = Field(default=None, ge=0, le=100)
    notes: str = Field(default="", max_length=10000)
    _urls = field_validator("website", "linkedin_url", "twitter_url", "instagram_url")(valid_url)

    @field_validator("expertise")
    @classmethod
    def validate_expertise(cls, values):
        if any(not value or len(value) > 200 for value in values):
            raise ValueError("Expertise entries must contain 1–200 characters.")
        return values


class CandidateCreate(CandidateFields):
    full_name: str = Field(min_length=1, max_length=200)
    sources: list[SourceIn] = Field(default_factory=list, max_length=30)
    source_url: str | None = Field(default=None, max_length=2000)
    source_name: str | None = Field(default=None, max_length=200)
    source_type: str = Field(default="website", max_length=100)
    source_date: datetime | None = None
    source_evidence: str | None = Field(default=None, max_length=2000)
    _source_url = field_validator("source_url")(valid_url)

    @model_validator(mode="after")
    def require_source(self):
        if not self.sources and not self.source_url:
            raise ValueError("At least one source URL is required.")
        return self


class CandidateUpdate(CandidateFields):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    status: CandidateStatus | None = None
    sources: list[SourceIn] | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def nonnullable(self):
        for field in (
            "full_name",
            "status",
            "expertise",
            "notes",
            "relevance_score",
            "confidence_score",
            "sources",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        if self.sources == []:
            raise ValueError("At least one source is required.")
        return self


class BulkCandidates(Schema):
    candidates: list[CandidateCreate] = Field(min_length=1, max_length=500)


class ExportInput(Schema):
    format: Literal["csv", "xlsx", "json", "sheets"] = "csv"
    include_all: bool = False
