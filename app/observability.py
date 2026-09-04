"""Bounded single-instance metrics and allowlisted JSON events; no content or credentials."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from contextvars import ContextVar
from datetime import UTC, datetime

request_id: ContextVar[str] = ContextVar("request_id", default="")
_lock = threading.Lock()
_counters: Counter = Counter()
_timings: dict[str, dict[str, float]] = {}
_started = time.monotonic()
logger = logging.getLogger("rag.events")


class EventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Deliberately ignore message, args, exception text, headers and body.
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "event": getattr(record, "event", "operational_error"),
                "request_id": getattr(record, "correlation_id", ""),
                **getattr(record, "safe_fields", {}),
            }
        )


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(EventFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False


def event(name: str, **fields) -> None:
    allowed = {"operation", "status", "duration_ms", "job_id", "error_type", "phase"}
    safe = {key: value for key, value in fields.items() if key in allowed}
    level = (
        logging.ERROR
        if name in {"unexpected_error", "startup_failed", "ingestion_failed"}
        else logging.WARNING
        if name == "login_failure"
        else logging.INFO
    )
    logger.log(
        level, "", extra={"event": name, "correlation_id": request_id.get(), "safe_fields": safe}
    )


def count(name: str) -> None:
    with _lock:
        _counters[name] += 1


def timing(name: str, seconds: float) -> None:
    with _lock:
        item = _timings.setdefault(name, {"count": 0, "total_ms": 0, "max_ms": 0})
        item["count"] += 1
        item["total_ms"] += seconds * 1000
        item["max_ms"] = max(item["max_ms"], seconds * 1000)


def snapshot() -> dict:
    with _lock:
        return {
            "uptime_seconds": round(time.monotonic() - _started, 1),
            "counters": dict(_counters),
            "timings": {
                name: {**value, "mean_ms": value["total_ms"] / value["count"]}
                for name, value in _timings.items()
            },
            "scope": "one process; resets on restart; no question or visitor content",
        }
