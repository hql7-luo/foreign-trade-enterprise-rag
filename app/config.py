from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RAG_",
        extra="ignore",
    )

    app_name: str = "Foreign Trade Enterprise RAG"
    app_version: str = "1.0.0"
    environment: Literal["development", "test", "production"] = "development"
    public_origin: str = ""
    allowed_origins: str = ""
    demo_mode: bool = False
    public_demo_read_only: bool = True
    runtime_root: Path = Path("data/public-demo-runtime")
    log_level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    rate_limit_enabled: bool = False
    login_limit_per_minute: int = Field(default=5, ge=1, le=60)
    query_limit_per_minute: int = Field(default=20, ge=1, le=120)
    mutation_limit_per_minute: int = Field(default=5, ge=1, le=30)
    read_limit_per_minute: int = Field(default=120, ge=10, le=600)
    global_limit_per_minute: int = Field(default=300, ge=10, le=3000)
    trusted_proxy_ips: str = ""
    auth_enabled: bool = True
    auth_users_file: Path = Path("data/private/demo-auth.json")
    auth_session_database_path: Path = Path("data/private/demo-sessions.db")
    auth_session_hours: int = Field(default=8, ge=1, le=24)
    enable_docs: bool = False
    allowed_hosts: str = "localhost,127.0.0.1,testserver,backend"
    ingestion_source_path: Path = Path("data/demo/source")
    staging_path: Path = Path("data/private/staging")
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    database_path: Path = Path("data/private/knowledge.db")
    qdrant_path: str = "data/private/qdrant"
    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "foreign_trade_knowledge"
    embedding_provider: str = "domain_hash"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = Field(default=384, ge=64, le=4096)
    embedding_cache_path: Path = Path("data/private/models")
    embedding_allow_hash_fallback: bool = True
    reranker_mode: str = "heuristic"
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_cache_path: Path = Path("data/private/models")
    reranker_candidate_limit: int = Field(default=16, ge=8, le=50)
    chunking_strategy: str = "source_aware"
    answer_mode: str = "claim_level"
    parent_context_enabled: bool = False
    diversity_selection_enabled: bool = True
    sibling_evidence_enabled: bool = False
    sibling_max_chunks: int = Field(default=3, ge=1, le=6)
    debug: bool = False

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str | None = None

    @model_validator(mode="after")
    def validate_production(self):
        if self.environment != "production":
            return self
        origin = urlsplit(self.public_origin)
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
        ):
            raise ValueError("Production requires an HTTPS RAG_PUBLIC_ORIGIN without a path")
        if not self.auth_enabled or self.enable_docs or self.debug:
            raise ValueError("Production requires authentication and disabled docs/debug")
        if not self.demo_mode or not self.public_demo_read_only or not self.rate_limit_enabled:
            raise ValueError("Production requires read-only demo mode and rate limiting")
        if "*" in self.allowed_hosts or origin.hostname not in self.allowed_hosts.split(","):
            raise ValueError("Production requires an explicit public host allowlist")
        if self.allowed_origins and self.allowed_origins != self.public_origin:
            raise ValueError("Production CORS may only allow the configured public origin")
        if (
            not self.qdrant_url
            or not self.qdrant_api_key
            or len(self.qdrant_api_key.get_secret_value()) < 32
        ):
            raise ValueError(
                "Production requires Qdrant URL and a random API key of 32+ characters"
            )
        if not self.qdrant_collection.startswith("public_demo_"):
            raise ValueError("Production requires a public_demo_ collection namespace")
        if self.embedding_allow_hash_fallback or self.llm_api_key or self.llm_model:
            raise ValueError("Production must use explicit local embeddings and no external LLM")
        root = self.runtime_root.absolute()
        if root.name != "public-demo-runtime" or "private" in root.parts[2:]:
            raise ValueError(
                "Production runtime must use a dedicated public-demo-runtime directory"
            )
        for path in (
            self.database_path,
            self.auth_users_file,
            self.auth_session_database_path,
            self.staging_path,
            self.embedding_cache_path,
            self.reranker_cache_path,
        ):
            if not path.absolute().is_relative_to(root) or path.absolute() == root:
                raise ValueError("All production state must be inside the isolated demo runtime")
            if path.resolve() != path.absolute():
                raise ValueError("Production state paths must not contain symlinks or traversal")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
