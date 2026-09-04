import hashlib

import pytest

from app.approval import ProductFactApprovalService
from app.ingestion.loaders import load_approved_sources
from app.ingestion.pipeline import IngestionPipeline
from app.knowledge_admin import KnowledgeAdminService, ProductMasterService
from app.retrieval.bm25 import BM25Encoder
from app.retrieval.embedding import DomainHashEmbedder, physical_collection_name
from app.security.filter import SensitiveContentError
from tests.conftest import SOURCE


def test_clean_ingestion_idempotency_metadata(service):
    before = service.retrieval.database.counts()
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.iterdir()}
    result = IngestionPipeline(
        service.retrieval.database,
        service.retrieval.vector_store,
        service.retrieval.embedder,
        chunking_strategy="source_aware",
    ).run(SOURCE)
    assert result.source_hashes_unchanged
    assert result.products == 10 and result.source_documents == 5
    assert service.retrieval.database.counts()["products"] == before["products"]
    assert result.chunks == before["indexed_chunks"]
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.iterdir()}
    hit = service.retrieval.search("NSITEM-V731").hits[0]
    assert hit.chunk.source_file == "northstar-products.csv"
    assert hit.chunk.row_start == 2 and hit.chunk.model == "NSTR-VESSEL-731"
    assert hit.dense_score is not None and hit.bm25_score is not None


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("NSTR-VESSEL-731 material?", "18/8 stainless steel"),
        ("NSITEM-M963 dimensions?", "680 x 320 x 3 mm"),
        ("NSTR-VESSEL-731 的材质和起订量?", "144 units"),
        ("Compare NSTR-VESSEL-731 and NSTR-VESSEL-732 capacity.", "800 ml"),
        ("Historical NSTR-VESSEL-731 payment terms and Incoterms?", "40% prepayment"),
        ("Company sample policy?", "seven calendar days"),
        ("SOP release gate and quality inspection?", "reviewer signs"),
    ],
)
def test_grounded_claims(service, question, expected):
    result = service.query(question, debug=True)
    assert expected in result.answer
    assert result.sources
    for claim in result.claims:
        if claim.supported:
            assert claim.sources
    assert "ranking" in result.debug and "context_sent_to_answerer" in result.debug


@pytest.mark.parametrize(
    "question",
    [
        "NSTR-LANTERN-864 current lead time?",
        "NSTR-VESSEL-731 current inventory?",
        "What is the current certificate for NSTR-LANTERN-864?",
        "NSTR-VESSEL-739 MOQ?",
    ],
)
def test_missing_and_near_identifier_refusal(service, question):
    result = service.query(question)
    assert not result.sufficient_information
    assert any(not c.supported for c in result.claims)


def test_duplicate_model_is_ambiguous(service):
    result = service.query("NSTR-POD-452 dimensions?")
    assert not result.sufficient_information and "ambiguous" in result.answer
    assert "NSITEM-P452A" in result.answer and "NSITEM-P452B" in result.answer


def test_approval_pending_reindex_provenance(service, settings):
    admin = KnowledgeAdminService(service.retrieval.database, service, settings)
    uploaded = admin.stage_source(
        filename="northstar-proposed-update.csv",
        data=(SOURCE.parent / "updates/northstar-proposed-update.csv").read_bytes(),
        actor="admin",
    )
    change = admin.propose_staged_facts(uploaded["id"], actor="admin")["changes"][0]
    assert change["status"] == "pending" and change["existing_value"] == "144 units"
    assert "144 units" in service.query("NSTR-VESSEL-731 MOQ?").answer
    approval = ProductFactApprovalService(service.retrieval.database)
    approval.approve(change["id"], reviewer_id="reviewer", reason="Synthetic revision verified")
    master = ProductMasterService(service.retrieval.database).get_product("NSITEM-V731")
    assert master["supported_attributes"]["moq"] == "180 units"
    admin.ingest_configured_source()
    result = service.query("NSTR-VESSEL-731 MOQ?")
    assert "180 units" in result.answer and "144 units" not in result.answer
    cited = service.retrieval.database.get_chunks([s.chunk_id for s in result.sources])
    assert any("180 units" in c.content for c in cited.values())
    assert result.sources[0].approval_change_id == change["id"]
    history = service.retrieval.database.product_fact_history("NSITEM-V731", field_name="moq")
    assert {"approved", "superseded"} <= {f["status"] for f in history}


def test_reject_and_historical_authority(service):
    approval = ProductFactApprovalService(service.retrieval.database)
    change = approval.propose(
        product_id="NSITEM-V731",
        field_name="moq",
        proposed_value="360 units",
        source_file="northstar-historical-rfqs.md",
        source_row=9,
        evidence={"context": "Synthetic archive"},
        actor="admin",
    )
    with pytest.raises(ValueError, match="Historical"):
        approval.approve(change["id"], reviewer_id="reviewer", reason="This must fail")
    approval.reject(change["id"], reviewer_id="reviewer", reason="Historical, not current")
    assert approval.inspect(change["id"])["status"] == "rejected"
    assert "144 units" in service.query("NSTR-VESSEL-731 MOQ?").answer


def test_new_source_conflict_stays_pending(service, tmp_path):
    import shutil

    target = tmp_path / "changed"
    shutil.copytree(SOURCE, target)
    path = target / "northstar-products.csv"
    path.write_text(path.read_text().replace("144 units", "288 units"))
    IngestionPipeline(
        service.retrieval.database,
        service.retrieval.vector_store,
        service.retrieval.embedder,
        chunking_strategy="source_aware",
    ).run(target)
    assert any(c["field_name"] == "moq" for c in service.retrieval.database.list_fact_changes())
    assert "144 units" in service.query("NSTR-VESSEL-731 MOQ?").answer


def test_embedder_and_bm25():
    first, second = DomainHashEmbedder(384), DomainHashEmbedder(128)
    assert first.embed_query("example") == first.embed_query("example")
    assert physical_collection_name("public", first) != physical_collection_name("public", second)
    bm25 = BM25Encoder.fit(["synthetic steel bottle", "synthetic cotton tote"])
    assert bm25.encode_query("steel").indices


def test_parser_rejects_sensitive_source(tmp_path):
    import shutil

    target = tmp_path / "bad"
    shutil.copytree(SOURCE, target)
    path = target / "northstar-company-knowledge.md"
    path.write_text(path.read_text() + "\nEmail: qa@example.invalid\n")
    with pytest.raises(SensitiveContentError):
        load_approved_sources(target)
