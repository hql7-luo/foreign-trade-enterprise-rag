from __future__ import annotations

import re


class SensitiveContentError(ValueError):
    """Raised when approved-source extraction still contains blocked content."""


BLOCKED_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "credential_assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|password|passwd|pwd)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}"
    ),
    "email": re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "bank_account": re.compile(
        r"(?i)\b(?:bank\s+account|account\s+(?:number|no\.?))\b[^\n]{0,40}\d{6,}"
    ),
    "phone": re.compile(
        r"(?i)\b(?:tel(?:ephone)?|mobile|phone|whatsapp|wechat)\b[^\n]{0,30}"
        r"\+?[\d ()-]{7,}"
    ),
    "absolute_user_path": re.compile(r"/Users/[^\s`\"']+"),
    "network_path": re.compile(r"\\\\[^\s\\]+\\[^\s]+"),
}


def blocked_findings(text: str) -> list[str]:
    """Return finding types without exposing the matched values."""

    return [name for name, pattern in BLOCKED_PATTERNS.items() if pattern.search(text)]


def ensure_safe_for_general_index(text: str, *, source_file: str) -> None:
    findings = blocked_findings(text)
    if findings:
        kinds = ", ".join(sorted(findings))
        raise SensitiveContentError(f"Blocked content in {source_file}: {kinds}")
