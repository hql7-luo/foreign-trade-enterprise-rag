"""Generic bilingual business terms; no source-specific product vocabulary."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_GROUPS = {
    "moq": ("minimum order quantity", "minimum order", "moq", "起订量", "最小订购量"),
    "sop": ("standard operating procedure", "production order", "sop", "生产单", "操作流程"),
    "required": ("required field", "mandatory", "必填"),
    "material": ("material", "材质", "材料"),
    "dimension": ("dimension", "尺寸"),
    "lead_time": ("lead time", "lead-time", "交期"),
    "price": ("price", "pricing", "价格", "报价"),
    "incoterm": ("incoterm", "trade terms", "贸易条款"),
    "certificate": ("certificate", "certification", "证书", "认证"),
    "packaging": ("packaging", "packing", "包装"),
    "payment": ("payment", "付款"),
    "history": ("historical", "历史"),
    "company": ("company", "公司"),
}
DOMAIN_PHRASES = {term: f" domain_{key} " for key, terms in _GROUPS.items() for term in terms}
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/-]*|[\u3400-\u9fff]+")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    aliases = "".join(tag for term, tag in DOMAIN_PHRASES.items() if term in normalized)
    return re.sub(r"\s+", " ", normalized + aliases).strip()


def tokenize(text: str) -> list[str]:
    tokens = []
    for term in TOKEN_PATTERN.findall(normalize_text(text)):
        if re.fullmatch(r"[\u3400-\u9fff]+", term):
            tokens.extend(term)
            tokens.extend(term[i : i + 2] for i in range(len(term) - 1))
        else:
            tokens.append(term)
    return tokens


def meaningful_terms(text: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "about",
        "can",
        "do",
        "does",
        "for",
        "from",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "our",
        "the",
        "this",
        "to",
        "we",
        "what",
        "which",
        "with",
        "please",
        "tell",
        "show",
        "know",
        "current",
        "verified",
    }
    return {term for term in tokenize(text) if len(term) > 1 and term not in stopwords}


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in normalize_text(text) for term in terms)
