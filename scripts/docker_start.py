"""Bootstrap the safe demo corpus and start the single-worker FastAPI service."""

from __future__ import annotations

import time
from contextlib import nullcontext
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import uvicorn

from app.api.dependencies import get_rag_service
from app.config import Settings, get_settings
from app.demo_safety import runtime_lease, verify_demo_database
from app.ingestion.pipeline import IngestionPipeline
from app.observability import configure_logging, event
from scripts.bootstrap_demo import bootstrap


def _wait_for_qdrant(base_url: str, *, attempts: int = 30, api_key: str | None = None) -> None:
    for _ in range(attempts):
        try:
            request = Request(f"{base_url.rstrip('/')}/readyz")
            if api_key:
                request.add_header("api-key", api_key)
            with urlopen(request, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(1)
    raise RuntimeError(
        "STARTUP ERROR: Qdrant is unavailable after the startup retry budget. "
        "Inspect `docker compose logs qdrant` and retry."
    )


def _classify_startup_failure(error: Exception) -> str:
    """Return an actionable public message without logging exception contents."""

    message = str(error).casefold()
    if "demo data not initialized" in message:
        return (
            "Demo data is not initialized; verify RAG_INGESTION_SOURCE_PATH "
            "and approved demo files."
        )
    if "qdrant" in message or "connection" in message:
        return "Qdrant is unavailable; inspect the qdrant service health."
    if "embedding" in message or "fastembed" in message or "model" in message:
        return "The embedding model is unavailable; verify RAG_EMBEDDING_* configuration."
    if "sqlite" in message or "database" in message or "readonly" in message:
        return "The knowledge database is unavailable or its runtime volume is not writable."
    if "validation" in message or "configuration" in message:
        return "Runtime configuration is invalid; compare the matching environment example."
    return "Demo initialization failed; check sanitized logs and the deployment runbook."


def initialize_demo(settings: Settings) -> None:
    with runtime_lease(settings) if settings.demo_mode else nullcontext():
        if not settings.auth_users_file.exists():
            bootstrap(settings.auth_users_file.parent)
        if settings.qdrant_url:
            _wait_for_qdrant(
                settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key
                else None,
            )
        if not settings.ingestion_source_path.is_dir():
            raise RuntimeError("Demo data not initialized: source directory is absent")
        rag_service = get_rag_service()
        try:
            try:
                state = rag_service.retrieval.database.get_retrieval_state("embedding")
                needs_ingestion = (
                    state.get("fingerprint") != rag_service.retrieval.embedder.fingerprint
                    or rag_service.retrieval.vector_store.count() == 0
                )
            except Exception:
                needs_ingestion = True
            if needs_ingestion:
                result = IngestionPipeline(
                    rag_service.retrieval.database,
                    rag_service.retrieval.vector_store,
                    rag_service.retrieval.embedder,
                    chunking_strategy=settings.chunking_strategy,
                ).run(Path(settings.ingestion_source_path))
                if result.chunks == 0:
                    raise RuntimeError("Demo data not initialized: no approved chunks")
            if settings.demo_mode:
                verify_demo_database(settings.database_path.absolute())
            event("demo_initialized")
        except BaseException:
            rag_service.retrieval.vector_store.close()
            get_rag_service.cache_clear()
            raise


def main() -> None:
    try:
        settings = get_settings()
        configure_logging(settings.log_level)
        initialize_demo(settings)
    except Exception as exc:
        event("startup_failed", error_type=type(exc).__name__)
        if str(exc).startswith("STARTUP ERROR:"):
            raise SystemExit(str(exc)) from None
        raise SystemExit(f"STARTUP ERROR: {_classify_startup_failure(exc)}") from None
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
        access_log=False,
        proxy_headers=False,
        limit_concurrency=32,
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()
