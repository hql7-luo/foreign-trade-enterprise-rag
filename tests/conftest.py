from pathlib import Path

import pytest

from app.config import Settings
from app.ingestion.pipeline import IngestionPipeline
from app.runtime import build_rag_service

SOURCE = Path(__file__).resolve().parents[1] / "data/demo/source"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        environment="test",
        ingestion_source_path=SOURCE,
        database_path=tmp_path / "knowledge.db",
        qdrant_path=str(tmp_path / "qdrant"),
        embedding_provider="domain_hash",
        chunking_strategy="source_aware",
        embedding_cache_path=tmp_path / "models",
        staging_path=tmp_path / "staging",
        auth_users_file=tmp_path / "demo-auth.json",
        auth_session_database_path=tmp_path / "sessions.db",
    )


@pytest.fixture
def service(settings):
    result = build_rag_service(settings)
    IngestionPipeline(
        result.retrieval.database,
        result.retrieval.vector_store,
        result.retrieval.embedder,
        chunking_strategy="source_aware",
    ).run(SOURCE)
    yield result
    result.retrieval.vector_store.close()


@pytest.fixture
def client(service, settings, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_rag_service
    from app.auth import DemoAuthService, get_auth_service
    from app.config import get_settings
    from app.main import create_app
    from scripts.bootstrap_demo import bootstrap

    bootstrap(settings.auth_users_file.parent)
    auth = DemoAuthService(
        settings.auth_users_file, session_database_path=settings.auth_session_database_path
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    application = create_app()
    application.dependency_overrides[get_rag_service] = lambda: service
    application.dependency_overrides[get_auth_service] = lambda: auth
    application.dependency_overrides[get_settings] = lambda: settings
    with TestClient(application) as result:
        passwords = dict(
            line.split(": ", 1)
            for line in (settings.auth_users_file.parent / "demo-credentials.txt")
            .read_text()
            .splitlines()
        )
        headers = {}
        for username, password in passwords.items():
            response = result.post(
                "/api/auth/login", json={"username": username, "password": password}
            )
            assert response.status_code == 200
            headers[username] = {"Authorization": "Bearer " + response.json()["access_token"]}
        yield result, headers
