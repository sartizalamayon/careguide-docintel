"""Application settings, read from environment variables (see .env.example and docs/SPEC.md §4)."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # infrastructure
    DATABASE_URL: str = "postgresql+psycopg://docintel:docintel@db:5432/docintel"
    REDIS_URL: str = "redis://redis:6379/0"
    STORAGE_DIR: str = "/data/uploads"
    CORS_ORIGINS: str = "http://localhost:3000"
    LOG_LEVEL: str = "INFO"

    # security / limits
    API_KEY: str = Field(..., min_length=16)
    MAX_FILE_MB: int = 200
    MAX_FILES_PER_UPLOAD: int = 50
    MAX_PDF_PAGES: int = 2000

    # LLM (any OpenAI-compatible endpoint)
    LLM_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.5-flash-lite"
    LLM_FALLBACK_MODEL: str = "gemini-3.1-flash-lite"  # empty = no fallback
    LLM_FALLBACK_BASE_URL: str = ""  # empty = LLM_BASE_URL
    LLM_FALLBACK_API_KEY: str = ""  # empty = LLM_API_KEY
    LLM_JSON_MODE: str = "schema"  # schema | object
    LLM_CONCURRENCY: int = 4
    LLM_TIMEOUT_S: int = 60
    LLM_CACHE_ENABLED: bool = True

    # per-user Groq keys (added in the UI after Google sign-in)
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODELS: str = "openai/gpt-oss-120b,llama-3.3-70b-versatile,openai/gpt-oss-20b,llama-3.1-8b-instant"
    CREDENTIALS_SECRET: str = ""  # encrypts stored keys; empty = derived from API_KEY

    # OCR / embeddings
    OCR_THREADS: int = 4
    OCR_DPI: int = 300
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_CACHE_DIR: str = "/models"
    # local = fastembed in-process (about 200 MB of memory); api = the LLM provider's /embeddings (small hosts)
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_API_MODEL: str = "gemini-embedding-2"

    # validation
    REVIEW_CONFIDENCE: float = 0.6

    # celery
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # small hosts: run jobs in the API process and keep originals in Postgres (disk may be wiped)
    WORKER_MODE: str = "celery"  # celery | inline
    STORAGE_BACKEND: str = "disk"  # disk | database

    @field_validator("DATABASE_URL")
    @classmethod
    def _psycopg_driver(cls, url: str) -> str:
        """Accept connection strings as hosted Postgres providers show them (postgres://, postgresql://)."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def groq_models(self) -> list[str]:
        return [m.strip() for m in self.GROQ_MODELS.split(",") if m.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
