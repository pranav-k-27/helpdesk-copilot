import os
import json
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration.
    All values loaded from environment variables or .env file.
    No secrets hardcoded — SAST compliant.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Application ────────────────────────────────────────────
    ENV:          str = Field(default="local")
    LOG_LEVEL:    str = Field(default="INFO")
    BACKEND_HOST: str = Field(default="0.0.0.0")
    BACKEND_PORT: int = Field(default=8000)

    # ── CORS ───────────────────────────────────────────────────
    FRONTEND_URL:  Optional[str] = Field(default=None)
    CORS_ORIGINS:  List[str]     = Field(default_factory=list)

    # ── OpenAI ─────────────────────────────────────────────────
    OPENAI_API_KEY:         Optional[str] = Field(default=None)
    OPENAI_API_BASE:        Optional[str] = Field(default=None)
    OPENAI_MODEL:           str           = Field(default="gpt-4o")
    OPENAI_EMBEDDING_MODEL: str           = Field(default="text-embedding-3-small")

    # ── Qdrant ─────────────────────────────────────────────────
    QDRANT_HOST:              str           = Field(default="localhost")
    QDRANT_PORT:              int           = Field(default=6333)
    QDRANT_GRPC_PORT:         int           = Field(default=6334)
    QDRANT_API_KEY:           Optional[str] = Field(default=None)
    QDRANT_COLLECTION_KB:     str           = Field(default="helpdesk_kb")
    QDRANT_COLLECTION_SCHEMA: str           = Field(default="ticket_schema")

    # ── Data Paths ─────────────────────────────────────────────
    DATA_DIR:            str = Field(default="data")
    SQLITE_DB_FILENAME:  str = Field(default="tickets.db")
    KB_JSON_FILENAME:    str = Field(default="kb_articles.json")

    # ── Auth — NO hardcoded defaults for secrets ───────────────
    JWT_SECRET_KEY:              str = Field(default="")
    JWT_ALGORITHM:               str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)

    # ── Guardrails ─────────────────────────────────────────────
    MAX_QUERY_LENGTH:    int = Field(default=2000)
    RATE_LIMIT_PER_MINUTE: int = Field(default=20)

    # ── RAG Tuning ─────────────────────────────────────────────
    RAG_TOP_K:             int   = Field(default=10)
    RAG_TOP_N_RERANK:      int   = Field(default=3)
    CONFIDENCE_THRESHOLD:  float = Field(default=0.5)
    CHUNK_SIZE:            int   = Field(default=600)
    CHUNK_OVERLAP:         int   = Field(default=60)

    # ── Observability ──────────────────────────────────────────
    AUDIT_LOG_PATH: str = Field(default="logs/audit.log")

    # ── Derived Properties ─────────────────────────────────────
    @property
    def sqlite_db_url(self) -> str:
        return f"sqlite:///{self.sqlite_db_path}"

    @property
    def sqlite_db_path(self) -> str:
        return os.path.join(self.DATA_DIR, self.SQLITE_DB_FILENAME)

    @property
    def kb_json_path(self) -> str:
        return os.path.join(self.DATA_DIR, self.KB_JSON_FILENAME)

    @property
    def audit_log_file(self) -> str:
        return self.AUDIT_LOG_PATH

    # ── Validators ─────────────────────────────────────────────
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if not v:
            return ["*"]
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return ["*"]
            if v.startswith("["):
                try:
                    return json.loads(v)
                except Exception:
                    return ["*"]
            return [o.strip() for o in v.split(",") if o.strip()]
        return ["*"]

    @model_validator(mode="after")
    def validate_required_secrets(self):
        """
        In production: require all secrets to be explicitly set.
        In local/dev: use fallback values for convenience.
        """
        if self.ENV == "prod":
            if not self.JWT_SECRET_KEY:
                raise ValueError("JWT_SECRET_KEY must be set in production")
            if not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY must be set in production")
        else:
            # Local dev only — never use these in production
            if not self.JWT_SECRET_KEY:
                object.__setattr__(self, "JWT_SECRET_KEY", "local-dev-only-not-for-production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()