"""Core configuration module for the Side-Scan Sonar backend."""

import os
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ALLOWED_ORIGINS = [
    "https://side-scan-sonar-sigma.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    APP_NAME: str = "sonar-backend"
    APP_ENV: str = "production"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS configuration
    CORS_ORIGINS: Union[List[str], str] = DEFAULT_ALLOWED_ORIGINS

    # Database configuration (PostgreSQL / Supabase / SQLite)
    DATABASE_URL: str = "sqlite:///./sonarops.db"

    # Storage configuration ('local' or 'supabase')
    STORAGE_PROVIDER: str = "local"
    LOCAL_STORAGE_DIR: str = "storage/sonar-evidence"

    # Supabase storage configuration (optional)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: str = "sonar-evidence"

    # Optional custom paths and admin key
    MODELS_DIR: Optional[str] = None
    MODEL_CACHE_DIR: Optional[str] = None
    ADMIN_API_KEY: Optional[str] = None

    # Hugging Face Remote ZeroGPU Inference Engine
    HF_SPACE_ID: Optional[str] = "Ksh508/SSS"
    HF_TOKEN: Optional[str] = None
    USE_REMOTE_INFERENCE: bool = True

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            clean = v.strip()
            # Map postgres:// and plain postgresql:// to postgresql+psycopg2:// for SQLAlchemy 2.1+ compatibility
            if clean.startswith("postgres://"):
                return clean.replace("postgres://", "postgresql+psycopg2://", 1)
            elif clean.startswith("postgresql://") and not clean.startswith("postgresql+"):
                return clean.replace("postgresql://", "postgresql+psycopg2://", 1)
            return clean
        return v

    @field_validator("PORT", mode="before")
    @classmethod
    def parse_port(cls, v: Union[str, int]) -> int:
        if isinstance(v, str):
            return int(v.strip())
        return v

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        configured: List[str] = []
        if isinstance(v, str):
            configured = [i.strip().rstrip("/") for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            configured = [i.strip().rstrip("/") for i in v if isinstance(i, str) and i.strip()]

        # Retain default production and local origins so connectivity is never broken
        combined = list(configured)
        for origin in DEFAULT_ALLOWED_ORIGINS:
            if origin not in combined:
                combined.append(origin)
        return combined

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
