from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./relationships.db"
    secret_key: str = Field(min_length=32)
    n8n_api_key: str = ""
    admin_email: str = "admin@example.com"
    admin_password: str = ""
    demo_mode: bool = True
    cookie_secure: bool = False
    auth_required: bool = False
    # Browser origins allowed to call the API cross-site. The panel is same-origin.
    allowed_origins: str = ""
    # Host headers accepted (DNS-rebinding guard). Add the server name when exposing on a LAN.
    allowed_hosts: str = "localhost,127.0.0.1,backend,host.docker.internal"
    enable_api_docs: bool = True
    # Request guards. One backend process; limits are per process.
    max_request_bytes: int = Field(default=5_000_000, ge=10_000)
    rate_limit_per_minute: int = Field(default=600, ge=10)
    login_attempts_per_minute: int = Field(default=10, ge=1)
    # Collection budgets for one job.
    live_search_enabled: bool = True
    # DDGS engines, tried one at a time in this order until one returns results.
    search_backends: str = "yahoo,duckduckgo,brave,google,mojeek,startpage"
    # Pause before each query for a further result page, so free engines do not block us.
    search_pause_seconds: float = Field(default=2.0, ge=0, le=60)
    # Minimum gap between first-page queries: back-to-back queries came back empty far more often.
    search_query_interval_seconds: float = Field(default=1.0, ge=0, le=30)
    # Same-site people pages ("Ekibimiz", "Akademik Kadro") followed from relevant pages, per job.
    collection_max_followed_links: int = Field(default=30, ge=0, le=200)
    collection_max_sources: int = Field(default=500, ge=1, le=5000)
    # A job searches until it has the requested people, the user stops it or no new source is
    # left. The time budget is only a safety ceiling: the single worker serves one job at a time.
    collection_time_budget_seconds: int = Field(default=3600, ge=10, le=86400)
    collection_stale_after_seconds: int = Field(default=300, ge=60)
    collection_max_attempts: int = Field(default=2, ge=1, le=5)
    discovery_retries: int = Field(default=2, ge=0, le=5)
    fetch_retries: int = Field(default=1, ge=0, le=5)
    fetch_timeout_seconds: float = Field(default=8, gt=0, le=60)
    fetch_document_seconds: float = Field(default=20, gt=0, le=120)
    # Large staff and speaker lists exceed 1 MiB (2 of 30 sampled list pages, Oct 2026).
    fetch_max_bytes: int = Field(default=3 * 1024 * 1024, ge=10_000)
    source_text_retention_days: int = Field(default=90, ge=0)
    max_candidates_per_research: int = Field(default=5000, ge=10)
    retry_backoff_seconds: float = Field(default=1.0, ge=0, le=30)
    # Optional integrations.
    ai_provider: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    ai_max_output_tokens: int = Field(default=800, ge=50, le=8000)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    @property
    def google_sheets_configured(self):
        return bool(self.google_client_id and self.google_client_secret and self.google_refresh_token)

    def production_problems(self):
        """Configuration that is acceptable on a laptop but unsafe for a shared deployment."""
        problems = []
        if self.app_env != "production":
            return problems
        if not self.auth_required:
            problems.append("AUTH_REQUIRED must be true in production.")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL in production.")
        if self.demo_mode:
            problems.append("DEMO_MODE must be false in production.")
        if len(set(self.secret_key)) < 10:
            problems.append("SECRET_KEY must be a random value (python scripts/init_env.py).")
        if "*" in self.allowed_origins:
            problems.append("ALLOWED_ORIGINS must list explicit origins.")
        if self.n8n_api_key and len(self.n8n_api_key) < 32:
            problems.append("N8N_API_KEY must contain at least 32 characters.")
        return problems


@lru_cache
def get_settings():
    return Settings()
