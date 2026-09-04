"""Create ignored local demo users with Argon2 password hashes."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from pwdlib import PasswordHash

DEMO_USERS = (
    ("employee", "employee", "Demo Employee"),
    ("reviewer", "reviewer", "Demo Reviewer"),
    ("admin", "admin", "Demo Admin"),
)


def bootstrap(output_dir: Path, *, force: bool = False) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    users_path = output_dir / "demo-auth.json"
    credentials_path = output_dir / "demo-credentials.txt"
    if users_path.exists() and not force:
        return users_path, credentials_path

    hasher = PasswordHash.recommended()
    credentials: list[str] = []
    users = []
    for username, role, display_name in DEMO_USERS:
        password = secrets.token_urlsafe(14)
        credentials.append(f"{username}: {password}")
        users.append(
            {
                "username": username,
                "display_name": display_name,
                "role": role,
                "password_hash": hasher.hash(password),
            }
        )
    users_path.write_text(
        json.dumps({"users": users}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    credentials_path.write_text("\n".join(credentials) + "\n", encoding="utf-8")
    users_path.chmod(0o600)
    credentials_path.chmod(0o600)
    return users_path, credentials_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/private"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    users_path, credentials_path = bootstrap(args.output_dir, force=args.force)
    print(f"Demo user hashes: {users_path}")
    print(f"Local demo credentials: {credentials_path}")


if __name__ == "__main__":
    main()
