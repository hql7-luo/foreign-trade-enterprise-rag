"""Schema-led claim planning for synthetic public knowledge, with no benchmark bindings.

Every value is copied from an approved, entity-scoped evidence field. Missing
fields do not borrow authority from related product descriptions or old quotes.
"""

from __future__ import annotations

import json
import re

from app.domain import RetrievalHit
from app.rag.answerer import ExtractiveAnswer
from app.rag.models import GroundedClaim
from app.text import meaningful_terms

FIELD_ALIASES = {
    "material": r"material|材质|材料",
    "dimensions": r"dimension|\bsize\b|尺寸",
    "moq": r"\bmoq\b|minimum order|起订",
    "lead_time": r"lead[ -]?time|\beta\b|交期|货期",
    "packaging": r"packaging|packing|包装",
    "certificates": r"certificat|compliance|证书|认证",
    "logistics_or_freight": r"logistics|freight|shipping cost|运费|物流",
    "current_price": (
        r"(?:current|today|final|binding).{0,25}(?:price|quote|quotation)"
        r"|当前.{0,8}(?:价格|报价)"
    ),
    "quoted_price": r"quoted price|historical price|历史.{0,8}价格",
    "payment_terms": r"payment|付款",
    "incoterms": r"incoterm|trade term|贸易条款",
    "capacity": r"capacity|容量",
    "color": r"colou?r|颜色",
    "inventory": r"inventory|\bstock\b|库存|现货",
    "required_fields": r"required field|mandatory field|必填",
    "release_gate": r"release gate|release order|放行|放单",
    "quality_check": r"quality check|inspection|质检|检验",
    "exception_handling": r"exception|damage|damaged|异常|破损",
    "sample_policy": r"sample|样品",
    "revision_policy": r"revision|revision policy|版本",
    "business_scope": r"business scope|company do|business|业务|主营",
    "response_target": r"response|reply|回复",
    "quote_validity": r"quote valid|quotation valid|有效期",
    "handover": r"handover|交接",
    "category": r"categor|分类|品类",
    "inquiries": r"inquir|demand|询盘|需求",
    "date": r"\bdate\b|\bwhen\b|日期|何时",
}
HIGH_RISK = {
    "moq",
    "lead_time",
    "dimensions",
    "packaging",
    "certificates",
    "logistics_or_freight",
    "current_price",
    "payment_terms",
    "incoterms",
    "inventory",
}
HISTORY = re.compile(r"historic|previous|\bold\b|\bpast\b|历史|旧报价", re.I)
CURRENT = re.compile(r"\bcurrent\b|\btoday\b|\bnow\b|当前|现在", re.I)
UNKNOWN = re.compile(r"not verified|unknown|unverified|not confirmed|未核实|未知", re.I)


def mentions(value: str | None, question: str) -> bool:
    return bool(
        value and re.search(r"(?<![\w-])" + re.escape(value) + r"(?![\w-])", question, re.I)
    )


def evidence_fields(hit: RetrievalHit) -> dict:
    fields = dict(hit.chunk.metadata.get("fields", {}))
    if hit.chunk.record_type == "approved_product_fact":
        key = hit.chunk.metadata.get("field_name")
        prefix = f"Approved {key}: "
        for line in hit.chunk.content.splitlines():
            if line.startswith(prefix):
                fields[key] = json.loads(line[len(prefix) :])
    return fields


def render(claims: list[GroundedClaim]) -> ExtractiveAnswer:
    if not claims:
        claims = [
            GroundedClaim(
                "The approved knowledge base does not contain enough "
                "verified information to answer this question.",
                False,
                [],
                "missing",
            )
        ]
    hits, lines, unique = [], [], []
    seen = set()
    for claim in claims:
        key = (claim.text, claim.supported)
        if key in seen:
            continue
        seen.add(key)
        unique.append(claim)
        for hit in claim.evidence_hits:
            if not any(item.chunk.id == hit.chunk.id for item in hits):
                hits.append(hit)
        citations = " ".join(
            f"[{next(i for i, item in enumerate(hits, 1) if item.chunk.id == hit.chunk.id)}]"
            for hit in claim.evidence_hits
        )
        lines.append(f"- {claim.text}" + (f" {citations}" if citations else ""))
    return ExtractiveAnswer("\n".join(lines), all(c.supported for c in unique), hits, unique)


class ClaimLevelAnswerer:
    def __init__(
        self, _fallback=None, *, diversity_selection_enabled=True, concept_completion_enabled=False
    ):
        self.diversity = diversity_selection_enabled

    def answer(self, question, matches, hits, conflicts):
        del conflicts
        normalized = question.casefold()
        fields = [name for name, pattern in FIELD_ALIASES.items() if re.search(pattern, normalized)]
        historical = bool(HISTORY.search(question))
        current = bool(CURRENT.search(question))
        exact_ids = {
            m.product.product_id for m in matches if mentions(m.product.product_id, question)
        }
        exact_models = {m.product.model for m in matches if mentions(m.product.model, question)}
        exact = [
            m
            for m in matches
            if m.product.product_id in exact_ids
            or (not exact_ids and m.product.model in exact_models)
        ]
        # Explicit mismatched ID/SKU requests cannot inherit one identifier's truth.
        if exact_ids and exact_models and any(m.product.model not in exact_models for m in exact):
            return render(
                [
                    GroundedClaim(
                        "The product ID and SKU conflict. Please clarify the "
                        "intended product before using these facts.",
                        False,
                        [],
                        "identity",
                        "conflicting",
                    )
                ]
            )
        if len(exact) > 1 and len(exact_models) == 1 and not exact_ids:
            options = ", ".join(m.product.product_id for m in exact)
            evidence = [
                hit
                for hit in hits
                if hit.chunk.product_id in {m.product.product_id for m in exact}
                and hit.chunk.record_type == "product"
            ]
            return render(
                [
                    GroundedClaim(
                        f"This SKU is ambiguous: {options}. Specify a product ID.",
                        False,
                        evidence,
                        "identity",
                        "ambiguous",
                    )
                ]
            )
        document_intent = bool(
            re.search(
                r"company|policy|sop|procedure|production order|handover|inspection|release gate|"
                r"公司|政策|生产单|操作流程|质检|询盘|demand|analytics",
                normalized,
            )
        )
        if historical:
            candidates = [
                h
                for h in hits
                if h.chunk.category == "quotation_evidence"
                and (not exact or h.chunk.product_id in {m.product.product_id for m in exact})
            ]
            claims = self._document_claims(question, fields, candidates, historical=True)
            if current:
                claims.extend(
                    GroundedClaim(
                        f"Current {key.replace('_', ' ')} is not verified by historical evidence.",
                        False,
                        [],
                        key,
                    )
                    for key in fields
                    if key in HIGH_RISK
                )
            return render(claims)
        if exact and not document_intent:
            claims = []
            for match in exact:
                product_hits = [
                    h
                    for h in hits
                    if h.chunk.product_id == match.product.product_id
                    and h.chunk.record_type in {"product", "approved_product_fact"}
                ]
                claims.extend(self._product_claims(match.product.model, fields, product_hits))
            return render(claims)
        if document_intent:
            category = (
                "operational_knowledge"
                if re.search(
                    r"sop|procedure|production order|handover|inspection|release gate"
                    r"|生产单|操作流程|质检",
                    normalized,
                )
                else "rfq_market_analytics"
                if re.search(r"analytics|demand|inquiries|询盘", normalized)
                else "company_knowledge"
            )
            return render(
                self._document_claims(
                    question, fields, [h for h in hits if h.chunk.category == category]
                )
            )
        identifiers = re.findall(r"\b(?:nstr-[a-z0-9-]+|nsitem-[a-z0-9-]+)\b", normalized)
        if identifiers and not any(
            m.product.model.casefold().startswith(identifiers[0]) for m in matches
        ):
            return render(
                [
                    GroundedClaim(
                        "No exact approved product matches that identifier. "
                        "Check the SKU or product ID.",
                        False,
                        [],
                        "identity",
                    )
                ]
            )
        # Open discovery reports several relevant identities; it never asserts a guessed SKU.
        candidates = []
        query_terms = meaningful_terms(question)
        for hit in hits:
            if hit.chunk.record_type != "product":
                continue
            if query_terms & meaningful_terms(hit.chunk.content):
                if hit.chunk.product_id not in {h.chunk.product_id for h in candidates}:
                    candidates.append(hit)
        if not candidates:
            return render([])
        claims = []
        if identifiers:
            claims.append(
                GroundedClaim(
                    "Partial identifier: possible matches follow. Provide "
                    "the full SKU or product ID to confirm.",
                    False,
                    [],
                    "identity",
                    "ambiguous",
                )
            )
        for hit in candidates[: 3 if self.diversity else 1]:
            facts = evidence_fields(hit)
            text = f"{hit.chunk.model} ({hit.chunk.product_id}): {facts.get('name', '')}"
            if facts.get("material"):
                text += f"; material: {facts['material']}"
            claims.append(GroundedClaim(text + ".", True, [hit], "product_option"))
        return render(claims)

    @staticmethod
    def _product_claims(
        sku: str, requested: list[str], hits: list[RetrievalHit]
    ) -> list[GroundedClaim]:
        claims = []
        fields = requested or [
            "name",
            "category",
            "material",
            "dimensions",
            "capacity",
            "moq",
            "packaging",
        ]
        for key in fields:
            candidates = [(evidence_fields(h)[key], h) for h in hits if key in evidence_fields(h)]
            # A human-approved single-field chunk takes precedence over a consolidated catalog.
            approved = [
                (v, h) for v, h in candidates if h.chunk.record_type == "approved_product_fact"
            ]
            if approved:
                candidates = approved
            candidates = [(v, h) for v, h in candidates if not UNKNOWN.search(str(v))]
            values = list(dict.fromkeys(str(value) for value, _ in candidates))
            label = key.replace("_", " ")
            if len(values) > 1:
                claims.append(
                    GroundedClaim(
                        f"{sku}: conflicting {label}; requires review.",
                        False,
                        [h for _, h in candidates],
                        key,
                        "conflicting",
                    )
                )
            elif values:
                claims.append(
                    GroundedClaim(f"{sku} — {label}: {values[0]}.", True, [candidates[0][1]], key)
                )
            elif requested:
                claims.append(
                    GroundedClaim(
                        f"{sku}: {label} is not verified in the approved knowledge base.",
                        False,
                        [],
                        key,
                    )
                )
        return claims

    @staticmethod
    def _document_claims(question, requested, hits, *, historical=False):
        if not hits:
            return []
        prefix = "Historical evidence (not current policy)" if historical else "Approved knowledge"
        ignored = {"sku", "product_id", "status", "notice"}
        if requested:
            keys = requested
        else:
            keys = [key for key in evidence_fields(hits[0]) if key not in ignored][:5]
        claims = []
        for key in keys:
            matches = [
                (value, h)
                for h in hits
                if (value := evidence_fields(h).get(key)) and not UNKNOWN.search(str(value))
            ]
            if matches:
                # Separate differing dated quotations; never merge their values into one price.
                chosen = matches[:1]
                for value, hit in chosen:
                    date = evidence_fields(hit).get("date", hit.chunk.source_date)
                    claims.append(
                        GroundedClaim(
                            f"{prefix} — {key.replace('_', ' ')}: {value}"
                            + (f" (dated {date})." if historical else "."),
                            True,
                            [hit],
                            key,
                        )
                    )
            else:
                claims.append(
                    GroundedClaim(
                        f"{key.replace('_', ' ')} is not verified by "
                        "the retrieved approved evidence.",
                        False,
                        [],
                        key,
                    )
                )
        return claims
