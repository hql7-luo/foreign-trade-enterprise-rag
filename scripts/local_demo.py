"""Start a fresh or existing isolated, synthetic-only local operator demo."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from app.config import Settings, get_settings
from app.demo_safety import prepare_runtime
from scripts.docker_start import initialize_demo

ROOT = Path(__file__).resolve().parents[1]


def settings_for(root: Path) -> Settings:
    root = root.absolute()
    return Settings(
        _env_file=None,
        environment="test",
        demo_mode=True,
        runtime_root=root,
        database_path=root / "knowledge.db",
        llm_api_key=None,
        llm_model=None,
        auth_enabled=True,
        qdrant_api_key=None,
        auth_users_file=root / "demo-auth.json",
        auth_session_database_path=root / "sessions.db",
        staging_path=root / "staging",
        qdrant_path=str(root / "qdrant"),
        qdrant_collection="public_demo_northstar",
        qdrant_url=None,
        embedding_provider="domain_hash",
        embedding_allow_hash_fallback=False,
        embedding_cache_path=root / "models",
        reranker_cache_path=root / "models",
        ingestion_source_path=ROOT / "data/demo/source",
        rate_limit_enabled=False,
        chunking_strategy="source_aware",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=ROOT / "data/public-demo-runtime")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = settings_for(args.runtime)
    prepare_runtime(settings)
    for key in list(os.environ):
        if key.startswith("RAG_"):
            del os.environ[key]
    # Mutation is allowed only for this explicit loopback operator process.
    settings = settings.model_copy(update={"demo_mode": False})
    for key, value in settings.model_dump().items():
        if value is not None:
            os.environ["RAG_" + key.upper()] = (
                str(value).lower() if isinstance(value, bool) else str(value)
            )
    get_settings.cache_clear()
    initialize_demo(settings)
    print(
        "Local demo ready. Read generated credentials from the isolated runtime; "
        "never publish them."
    )
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
