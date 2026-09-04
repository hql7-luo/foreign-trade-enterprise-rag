"""Small, explicit authentication and authorization layer for the local enterprise demo."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from app.config import get_settings

Role = Literal["employee", "reviewer", "admin"]
ALL_ROLES: frozenset[Role] = frozenset({"employee", "reviewer", "admin"})
REVIEW_ROLES: frozenset[Role] = frozenset({"reviewer", "admin"})
ADMIN_ROLES: frozenset[Role] = frozenset({"admin"})


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    username: str
    display_name: str
    role: Role


@dataclass(frozen=True, slots=True)
class _StoredUser:
    username: str
    display_name: str
    role: Role
    password_hash: str


class SQLiteSessionStore:
    """Persist only opaque-token digests and usernames in private SQLite storage."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_digest TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at)"
            )
        self.path.chmod(0o600)

    def create(self, token_digest: str, username: str, expires_at: datetime) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            self._purge_expired(connection, now)
            connection.execute(
                """DELETE FROM auth_sessions WHERE username = ? AND token_digest NOT IN (
                SELECT token_digest FROM auth_sessions WHERE username = ?
                ORDER BY created_at DESC LIMIT 19)""",
                (username, username),
            )
            connection.execute(
                """
                INSERT INTO auth_sessions(token_digest, username, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_digest, username, now, expires_at.isoformat()),
            )

    def username_for(self, token_digest: str) -> str | None:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            self._purge_expired(connection, now)
            row = connection.execute(
                "SELECT username FROM auth_sessions WHERE token_digest = ?",
                (token_digest,),
            ).fetchone()
        return str(row["username"]) if row else None

    def delete(self, token_digest: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_digest = ?", (token_digest,))

    def active_count(self) -> int:
        with self._lock, self._connect() as connection:
            self._purge_expired(connection, datetime.now(UTC).isoformat())
            return int(connection.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0])

    @staticmethod
    def _purge_expired(connection: sqlite3.Connection, now: str) -> None:
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))


class DemoAuthService:
    """Environment-backed demo users with opaque, short-lived persistent sessions.

    This intentionally is not an IAM replacement. Raw bearer tokens are returned once and only a
    SHA-256 digest and username are kept in private SQLite storage. Current role/display attributes
    are re-read from the user registry for every authenticated request.
    """

    def __init__(
        self,
        users_file: Path,
        *,
        session_hours: int = 8,
        session_database_path: Path | None = None,
        password_hash: PasswordHash | None = None,
    ) -> None:
        self.users_file = users_file
        self.session_hours = session_hours
        self.password_hash = password_hash or PasswordHash.recommended()
        self._dummy_hash = self.password_hash.hash(secrets.token_urlsafe(32))
        self.session_store = SQLiteSessionStore(
            session_database_path or users_file.with_name("demo-sessions.db")
        )

    def _load_users(self) -> dict[str, _StoredUser]:
        try:
            payload = json.loads(self.users_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Demo users are not configured. Run scripts/bootstrap_demo.py first."
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Demo user configuration is unreadable") from exc

        users: dict[str, _StoredUser] = {}
        for raw in payload.get("users", []):
            role = raw.get("role")
            username = str(raw.get("username", "")).strip()
            password_hash = str(raw.get("password_hash", ""))
            if not username or role not in ALL_ROLES or not password_hash.startswith("$argon2"):
                raise RuntimeError("Demo user configuration is invalid")
            users[username.casefold()] = _StoredUser(
                username=username,
                display_name=str(raw.get("display_name") or username),
                role=role,
                password_hash=password_hash,
            )
        if not users:
            raise RuntimeError("Demo user configuration contains no users")
        return users

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def login(self, username: str, password: str) -> tuple[str, AuthenticatedUser, datetime]:
        users = self._load_users()
        stored = users.get(username.strip().casefold())
        verified = self.password_hash.verify(
            password, stored.password_hash if stored else self._dummy_hash
        )
        if not verified or stored is None:
            raise ValueError("Invalid username or password")

        user = AuthenticatedUser(
            username=stored.username,
            display_name=stored.display_name,
            role=stored.role,
        )
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=self.session_hours)
        self.session_store.create(self._token_digest(token), user.username, expires_at)
        return token, user, expires_at

    def authenticate(self, token: str) -> AuthenticatedUser | None:
        username = self.session_store.username_for(self._token_digest(token))
        if username is None:
            return None
        stored = self._load_users().get(username.casefold())
        if stored is None:
            self.logout(token)
            return None
        return AuthenticatedUser(stored.username, stored.display_name, stored.role)

    def logout(self, token: str) -> None:
        self.session_store.delete(self._token_digest(token))


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_auth_service() -> DemoAuthService:
    settings = get_settings()
    return DemoAuthService(
        settings.auth_users_file,
        session_hours=settings.auth_session_hours,
        session_database_path=settings.auth_session_database_path,
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[DemoAuthService, Depends(get_auth_service)],
) -> AuthenticatedUser:
    settings = get_settings()
    if not settings.auth_enabled:
        return AuthenticatedUser(
            username="local-dev-admin",
            display_name="Local development administrator",
            role="admin",
        )
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = service.authenticate(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*allowed: Role):
    allowed_roles = frozenset(allowed)

    def dependency(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role is not allowed to perform this action",
            )
        return user

    return dependency


AuthenticatedDependency = Annotated[
    AuthenticatedUser,
    Depends(require_roles("employee", "reviewer", "admin")),
]
ReviewerDependency = Annotated[
    AuthenticatedUser,
    Depends(require_roles("reviewer", "admin")),
]
AdminDependency = Annotated[AuthenticatedUser, Depends(require_roles("admin"))]
