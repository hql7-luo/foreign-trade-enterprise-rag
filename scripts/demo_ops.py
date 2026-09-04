"""Offline operator-only backup/restore/reset for the isolated public demo runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.demo_safety import demo_manifest, runtime_lease, verify_demo_database
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.bm25 import BM25Encoder
from app.retrieval.qdrant_store import VectorPoint
from app.runtime import build_rag_service
from scripts.bootstrap_demo import bootstrap


def backup_database(settings: Settings, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    output = destination / "knowledge.db"
    with sqlite3.connect(settings.database_path) as source, sqlite3.connect(output) as target:
        source.backup(target)
    output.chmod(0o600)
    manifest = {
        "format": 1,
        "sources": demo_manifest(),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (destination / "manifest.json").chmod(0o600)
    return manifest


def validate_backup(source: Path) -> Path:
    database = source / "knowledge.db"
    manifest_path = source / "manifest.json"
    if source.is_symlink() or database.is_symlink() or manifest_path.is_symlink():
        raise ValueError("Backup cannot contain symlinks")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or manifest.get("sources") != demo_manifest():
        raise ValueError("Backup does not match the fictional demo manifest")
    if hashlib.sha256(database.read_bytes()).hexdigest() != manifest.get("sha256"):
        raise ValueError("Backup checksum mismatch")
    verify_demo_database(database.absolute())
    with sqlite3.connect(f"{database.absolute().as_uri()}?mode=ro", uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup integrity check failed")
    return database


def rebuild_vectors(settings: Settings) -> None:
    """Regenerate only the derived index; preserve master facts, decisions and audit tables."""
    service = build_rag_service(settings)
    retrieval = service.retrieval
    try:
        with retrieval.database.connect() as connection:
            ids = [
                row[0] for row in connection.execute("SELECT id FROM indexed_chunks ORDER BY id")
            ]
        chunks = list(retrieval.database.get_chunks(ids).values())
        bm25 = BM25Encoder.fit([chunk.content for chunk in chunks])
        vectors = retrieval.embedder.embed_documents([chunk.content for chunk in chunks])
        retrieval.vector_store.rebuild(
            [
                VectorPoint(chunk, vector, bm25.encode_document(chunk.content))
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        embedding = {
            "provider": retrieval.embedder.provider_name,
            "model": retrieval.embedder.model_name,
            "dimension": retrieval.embedder.dimension,
            "fingerprint": retrieval.embedder.fingerprint,
            "implementation_version": retrieval.embedder.implementation_version,
            "collection": retrieval.vector_store.collection,
        }
        with retrieval.database.connect() as connection:
            for key, value in {"bm25": bm25.to_dict(), "embedding": embedding}.items():
                connection.execute(
                    "INSERT OR REPLACE INTO retrieval_state(key,value_json) VALUES (?,?)",
                    (key, json.dumps(value)),
                )
            connection.commit()
    finally:
        retrieval.vector_store.close()


def forget_sessions_and_uploads(settings: Settings) -> None:
    # Exact configured targets, validated by runtime_lease; never broad home/workspace deletion.
    session = settings.auth_session_database_path
    for path in (session, Path(str(session) + "-wal"), Path(str(session) + "-shm")):
        path.unlink(missing_ok=True)
    if settings.staging_path.exists():
        shutil.rmtree(settings.staging_path)


def run_operation(settings: Settings, action: str, backup_path: Path | None = None) -> dict:
    with runtime_lease(settings) as root:
        if action == "backup":
            if backup_path is None:
                raise ValueError("Backup destination is required")
            backup_database(settings, backup_path)
        elif action == "restore":
            if backup_path is None:
                raise ValueError("Backup source is required")
            validated = validate_backup(backup_path)
            recovery = root / "recovery" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            backup_database(settings, recovery)
            with (
                sqlite3.connect(validated) as source,
                sqlite3.connect(settings.database_path) as dest,
            ):
                source.backup(dest)
            forget_sessions_and_uploads(settings)
            rebuild_vectors(settings)
        elif action == "reset":
            forget_sessions_and_uploads(settings)
            for suffix in ("", "-wal", "-shm"):
                Path(str(settings.database_path) + suffix).unlink(missing_ok=True)
            bootstrap(settings.auth_users_file.parent, force=True)
            service = build_rag_service(settings)
            try:
                IngestionPipeline(
                    service.retrieval.database,
                    service.retrieval.vector_store,
                    service.retrieval.embedder,
                    chunking_strategy=settings.chunking_strategy,
                ).run(settings.ingestion_source_path)
            finally:
                service.retrieval.vector_store.close()
        elif action == "rebuild":
            rebuild_vectors(settings)
        else:
            raise ValueError("Unknown maintenance action")
        return {"operation": action, "status": "completed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore", "reset", "rebuild"])
    parser.add_argument("--backup-path", type=Path)
    parser.add_argument("--confirm-public-demo", action="store_true", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run_operation(Settings(), args.action, args.backup_path)))
    except Exception as exc:
        raise SystemExit(
            f"Maintenance refused/failed ({type(exc).__name__}); verify demo paths, "
            "backup integrity, configuration, and that the backend is stopped."
        ) from None


if __name__ == "__main__":
    main()
