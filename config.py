"""Typed application settings loaded from the environment.

Every tunable used by retrieval, generation and guardrails lives here so that
behaviour is reproducible and auditable from a single place.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RC_", extra="ignore")

    env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_keys: list[str] = Field(default_factory=lambda: ["change_me_local_key"])
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    data_dir: Path = Path("./data")

    # LLM
    llm_provider: Literal["anthropic", "openai", "ollama", "fake"] = "anthropic"
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = "gpt-4o"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1400
    llm_timeout_seconds: float = 60.0

    # Retrieval
    embedding_backend: Literal["sentence_transformers", "hashing"] = "sentence_transformers"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768
    reranker_backend: Literal["cross_encoder", "none"] = "cross_encoder"
    reranker_model: str = "BAAI/bge-reranker-base"
    vector_backend: Literal["qdrant", "memory"] = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "root_canon_chunks"
    top_k_dense: int = 40
    top_k_sparse: int = 40
    top_k_final: int = 8
    rrf_k: int = 60
    min_evidence_score: float = 0.20
    evidence_weight: float = 0.15
    recency_half_life_years: float = 8.0

    # Cache
    redis_url: str | None = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 86_400

    # Safety
    jurisdiction: Literal["UK"] = "UK"
    max_question_chars: int = 2_000
    rate_limit_per_minute: int = 30

    @field_validator("api_keys", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
