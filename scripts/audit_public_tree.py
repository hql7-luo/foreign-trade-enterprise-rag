"""Release hygiene checks; complements, but cannot replace, a source-provenance review."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {".venv", "node_modules", "__pycache__", "runtime", "dist", "build"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".onnx", ".pyc", ".ses"}
SECRET_PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{25,}"),
    # A bare header is an intentional scanner-rejection fixture, not key material.
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{32,}"),
    re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/(?:Documents|Desktop|Downloads|\.codex)/"),
]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def check_bytes(name: str, content: bytes) -> None:
    if content.startswith(b"SQLite format 3"):
        raise ValueError(f"Database in publication content: {name}")
    if any(pattern.search(content) for pattern in SECRET_PATTERNS):
        raise ValueError(f"Potential secret or personal path: {name}")


def main() -> None:
    if not (ROOT / ".git").is_dir():
        raise SystemExit("Run after independently initializing and staging the public tree")
    if (ROOT / ".git/objects/info/alternates").exists():
        raise SystemExit("Shared Git object storage is not permitted for this public edition")
    names = [name for name in git("ls-files", "-z").decode().split("\0") if name]
    if not names:
        raise SystemExit("No staged/tracked release files")
    for name in names:
        path = Path(name)
        if path.suffix in FORBIDDEN_SUFFIXES or FORBIDDEN_PARTS.intersection(path.parts):
            raise ValueError(f"Generated/runtime file tracked: {name}")
        if name.startswith("data/private/") and name != "data/private/.gitkeep":
            raise ValueError("Runtime data tracked")
        if name.startswith("data/public-demo-runtime/") or name.startswith(".coverage"):
            raise ValueError("Runtime artifact tracked")
        if path.name.startswith(".env") and name not in {".env.example", ".env.production.example"}:
            raise ValueError("Local environment tracked")
        if (ROOT / name).is_symlink():
            raise ValueError("Publication symlinks require an explicit independent review")
        check_bytes(name, (ROOT / name).read_bytes())
        check_bytes("staged:" + name, git("show", ":" + name))
    objects = git("cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)")
    count = 0
    for line in objects.decode().splitlines():
        oid, kind = line.split()
        check_bytes("object:" + oid, git("cat-file", kind, oid))
        count += 1
    print(json.dumps({"tracked_files": len(names), "git_objects_scanned": count, "passed": True}))


if __name__ == "__main__":
    main()
