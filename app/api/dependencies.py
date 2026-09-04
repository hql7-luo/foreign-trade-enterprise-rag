"""Runtime service composition kept outside route handlers."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.rag.service import RagService
from app.runtime import build_rag_service


@lru_cache
def get_rag_service() -> RagService:
    return build_rag_service(get_settings())
