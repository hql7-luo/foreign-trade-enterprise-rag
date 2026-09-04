import hashlib

import pytest

from app.approval import ProductFactApprovalService
from app.auth import DemoAuthService
from app.ingestion.jobs import IngestionJobService
from app.ingestion.staging import parse_staged_source, upload_media_type_allowed
from app.knowledge_admin import KnowledgeAdminService
from app.security.filter import blocked_findings
from app.security.operations import RateLimiter


@pytest.mark.parametrize(
    ("path", "method", "role", "expected"),
    [
        ("/api/products", "get", None, 401),
        ("/api/admin/sources", "get", "employee", 403),
        ("/api/knowledge/fact-changes", "get", "employee", 403),
        ("/api/admin/ingestions", "post", "reviewer", 403),
        ("/api/knowledge/fact-changes/not-a-real-id/approve", "post", "employee", 403),
        ("/api/admin/diagnostics", "get", "admin", 200),
        ("/api/knowledge/fact-changes", "get", "reviewer", 200),
    ],
)
def test_roles(client, path, method, role, expected):
    http, headers = client
    kwargs = {"headers": headers[role]} if role else {}
    if method == "post" and "approve" in path:
        kwargs["json"] = {"reason": "Synthetic test decision"}
    assert getattr(http, method)(path, **kwargs).status_code == expected


def test_evidence_minimal_and_authenticated(client, service):
    http, headers = client
    result = http.post(
        "/api/query", headers=headers["employee"], json={"question": "NSTR-VESSEL-731 material?"}
    ).json()
    assert not result["retrieved_context"] and result["debug"] is None
    chunk = result["sources"][0]["chunk_id"]
    assert http.get(f"/api/evidence/{chunk}").status_code == 401
    evidence = http.get(f"/api/evidence/{chunk}", headers=headers["employee"]).json()
    assert "18/8 stainless steel" in evidence["excerpt"]
    assert not {"stored_path", "absolute_path", "owner"} & evidence.keys()
    with service.retrieval.database.connect() as connection:
        connection.execute(
            "UPDATE indexed_chunks SET confidentiality='restricted' WHERE id=?", (chunk,)
        )
        connection.commit()
    assert http.get(f"/api/evidence/{chunk}", headers=headers["employee"]).status_code == 404
    assert http.get("/data/private/demo-auth.json").status_code == 404
    assert http.get("/data/demo/source/northstar-products.csv").status_code == 404
    assert (
        http.post(
            "/api/query",
            headers=headers["employee"],
            json={"question": "NSTR-VESSEL-731?", "debug": True},
        ).status_code
        == 403
    )


@pytest.mark.parametrize("filename", ["../escape.csv", "/tmp/escape.csv", "folder/unsafe.csv"])
def test_path_traversal(service, settings, filename):
    admin = KnowledgeAdminService(service.retrieval.database, service, settings)
    with pytest.raises(ValueError, match="filename"):
        admin.stage_source(filename=filename, data=b"example", actor="admin")


@pytest.mark.parametrize(
    "text",
    [
        "Email: synthetic-person@example.invalid",
        "Phone: +1 202 555 0175",
        "Bank account number: 000011112222",
        "password: " + "fake-only-" * 3,
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_sensitive_scanner(text):
    assert blocked_findings(text)
    parsed = parse_staged_source("synthetic-sensitive.txt", text.encode())
    assert parsed.findings and not parsed.preview and not parsed.fact_updates


def test_upload_validation(service, settings):
    assert not upload_media_type_allowed("fact.csv", "image/png")
    assert not upload_media_type_allowed("fact.exe", "text/plain")
    for name, content in [
        ("wrong.pdf", b"not a pdf"),
        ("unsafe.txt", b"\x00"),
        ("file.exe", b"unsupported"),
    ]:
        with pytest.raises(ValueError):
            parse_staged_source(name, content)
    admin = KnowledgeAdminService(service.retrieval.database, service, settings)
    with pytest.raises(ValueError, match="size limit"):
        admin.stage_source(
            filename="large.txt", data=b"x" * (settings.max_upload_bytes + 1), actor="admin"
        )


def test_sessions_survive_service_restart(client, settings):
    _, headers = client
    token = headers["employee"]["Authorization"].removeprefix("Bearer ")
    restarted = DemoAuthService(
        settings.auth_users_file, session_database_path=settings.auth_session_database_path
    )
    assert restarted.authenticate(token).role == "employee"
    raw = settings.auth_session_database_path.read_bytes()
    assert token.encode() not in raw
    assert hashlib.sha256(token.encode()).hexdigest().encode() in raw


def test_rate_limit(settings):
    limiter = RateLimiter(
        settings.model_copy(update={"rate_limit_enabled": True, "login_limit_per_minute": 2})
    )
    assert limiter.allow("client", "login", now=1)
    assert limiter.allow("client", "login", now=1)
    assert not limiter.allow("client", "login", now=1)
    assert limiter.allow("client", "login", now=61)


def test_jobs_complete_cancel_and_fail(service, settings, monkeypatch):
    admin = KnowledgeAdminService(service.retrieval.database, service, settings)
    jobs = IngestionJobService(service.retrieval.database, admin)
    job = jobs.create(actor="admin")
    jobs.run(job["id"])
    assert jobs.get(job["id"])["status"] == "completed"
    job = jobs.create(actor="admin")
    jobs.cancel(job["id"])
    jobs.run(job["id"])
    assert jobs.get(job["id"])["status"] == "cancelled"

    def fail(**kwargs):
        raise ConnectionError("private error details must not escape")

    monkeypatch.setattr(admin, "ingest_configured_source", fail)
    job = jobs.create(actor="admin")
    jobs.run(job["id"])
    result = jobs.get(job["id"])
    assert result["status"] == "failed" and "private error" not in str(result)


def test_supersede_retains_history(service, settings):
    approval = ProductFactApprovalService(service.retrieval.database)
    proposal = approval.propose(
        product_id="NSITEM-L864",
        field_name="lead_time",
        proposed_value="30 working days",
        source_file="northstar-products.csv",
        source_row=6,
        evidence={"statement": "Synthetic fixture proposal"},
        actor="admin",
    )
    approval.approve(proposal["id"], reviewer_id="reviewer", reason="Synthetic evidence checked")
    approval.supersede(
        proposal["id"], reviewer_id="reviewer", reason="Withdraw unsupported proposal"
    )
    assert approval.inspect(proposal["id"])["status"] == "superseded"
    admin = KnowledgeAdminService(service.retrieval.database, service, settings)
    admin.ingest_configured_source()
    assert not service.query("NSTR-LANTERN-864 lead time?").sufficient_information
