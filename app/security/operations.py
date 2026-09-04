"""Simple bounded rate limiting for the documented single-worker deployment."""

from __future__ import annotations

import ipaddress
import threading
import time

from fastapi import Request

from app.config import Settings


def operation(method: str, path: str) -> str:
    if path == "/api/auth/login":
        return "login"
    if path == "/api/query":
        return "query"
    if path.startswith("/api/knowledge/") and method != "GET":
        return "review"
    if path.startswith("/api/admin/") and method != "GET":
        return "ingestion" if "ingestion" in path else "upload"
    if path.startswith("/api/health/"):
        return "health"
    return "read"


class RateLimiter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.Lock()
        self.window = -1
        self.counts: dict[tuple[str, str], int] = {}

    def allow(self, client: str, category: str, *, now: float | None = None) -> bool:
        if not self.settings.rate_limit_enabled or category == "health":
            return True
        window = int((now if now is not None else time.monotonic()) // 60)
        limit = {
            "login": self.settings.login_limit_per_minute,
            "query": self.settings.query_limit_per_minute,
            "review": self.settings.mutation_limit_per_minute,
            "upload": self.settings.mutation_limit_per_minute,
            "ingestion": self.settings.mutation_limit_per_minute,
        }.get(category, self.settings.read_limit_per_minute)
        with self.lock:
            if window != self.window:
                self.counts.clear()
                self.window = window
            # A global ceiling also bounds cardinality under spoofed/distributed clients.
            global_key = ("*", "*")
            used = self.counts.get(global_key, 0)
            if used >= self.settings.global_limit_per_minute:
                return False
            key = (client, category)
            if self.counts.get(key, 0) >= limit:
                return False
            self.counts[key] = self.counts.get(key, 0) + 1
            self.counts[global_key] = used + 1
            return True


def client_address(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    # Only the explicitly configured Nginx socket peer can assert the Caddy client address.
    if peer in settings.trusted_proxy_ips.split(","):
        try:
            return str(ipaddress.ip_address(request.headers.get("x-real-ip", "")))
        except ValueError:
            pass
    return peer
