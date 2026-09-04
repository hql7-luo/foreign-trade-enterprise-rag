"""Fail-closed boundaries for the public fictional corpus and operator maintenance."""

from __future__ import annotations

import fcntl
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import Settings

DEMO_ROOT = Path(__file__).resolve().parent.parent / "data" / "demo"
MARKER = ".public-demo.json"


def demo_manifest() -> dict[str, str]:
    return json.loads((DEMO_ROOT / "manifest.json").read_text(encoding="utf-8"))


def verify_demo_sources(source: Path) -> None:
    if source.absolute() != DEMO_ROOT / "source" or source.resolve() != source.absolute():
        raise ValueError("Public demo accepts only the packaged fictional source directory")
    expected = demo_manifest()
    if {path.name for path in source.iterdir()} != set(expected):
        raise ValueError("Public demo source allowlist mismatch")
    for name, digest in expected.items():
        path = source / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Public demo source integrity mismatch")


def verify_demo_database(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink():
        raise ValueError("Public demo database cannot be a symlink")
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT filename, sha256 FROM source_documents").fetchall()
    expected = demo_manifest()
    if any(expected.get(name) != digest for name, digest in rows):
        raise ValueError("Database contains a source outside the fictional demo manifest")


def prepare_runtime(settings: Settings) -> Path:
    if not settings.demo_mode:
        raise ValueError("Operator maintenance requires explicit demo mode")
    verify_demo_sources(settings.ingestion_source_path.absolute())
    root = settings.runtime_root.absolute()
    if root.name != "public-demo-runtime" or root.resolve() != root or "private" in root.parts[2:]:
        raise ValueError("Unsafe demo runtime target")
    for path in (
        settings.database_path,
        settings.auth_users_file,
        settings.auth_session_database_path,
        settings.staging_path,
        settings.embedding_cache_path,
        settings.reranker_cache_path,
    ):
        if (
            path.absolute() == root
            or not path.absolute().is_relative_to(root)
            or path.resolve() != path.absolute()
        ):
            raise ValueError("State path escapes the isolated demo runtime")
    if not settings.qdrant_collection.startswith("public_demo_"):
        raise ValueError("Demo maintenance requires a public_demo_ collection namespace")
    if not settings.qdrant_url:
        vector_path = Path(settings.qdrant_path).absolute()
        if (
            vector_path == root
            or not vector_path.is_relative_to(root)
            or vector_path.resolve() != vector_path
        ):
            raise ValueError("Local vector storage escapes the isolated demo runtime")
    marker = root / MARKER
    if root.exists() and not marker.exists() and any(root.iterdir()):
        raise ValueError("Refusing an existing runtime without the public-demo marker")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if marker.exists():
        if marker.is_symlink() or json.loads(marker.read_text()) != {"public_demo": 1}:
            raise ValueError("Invalid public-demo marker")
    else:
        marker.write_text('{"public_demo": 1}\n', encoding="utf-8")
        marker.chmod(0o600)
    verify_demo_database(settings.database_path.absolute())
    return root


@contextmanager
def runtime_lease(settings: Settings):
    root = prepare_runtime(settings)
    lock = root / ".runtime.lock"
    if lock.is_symlink():
        raise ValueError("Unsafe runtime lock")
    with lock.open("a") as handle:
        lock.chmod(0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Stop the backend before demo maintenance") from exc
        try:
            yield root
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
