"""Role-scoped HTTP routes delegating business logic to application services."""

from __future__ import annotations

import threading
import weakref
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import get_rag_service
from app.api.schemas import (
    CitationResponse,
    ClaimResponse,
    EvidenceResponse,
    FactChangeProposalRequest,
    FactChangeResponse,
    FactReviewDecisionRequest,
    HealthResponse,
    IngestionJobResponse,
    LoginRequest,
    LoginResponse,
    ProductHistoryResponse,
    ProductMasterResponse,
    QueryRequest,
    QueryResponse,
    RetrievedContextResponse,
    SourceSummaryResponse,
    StagedProposalResponse,
    StagedSourceResponse,
    StructuredMatchResponse,
    UserResponse,
)
from app.approval import ProductFactApprovalService
from app.auth import (
    AdminDependency,
    AuthenticatedDependency,
    DemoAuthService,
    ReviewerDependency,
    bearer_scheme,
    get_auth_service,
)
from app.config import get_settings
from app.ingestion.jobs import IngestionJobService
from app.ingestion.staging import upload_media_type_allowed
from app.knowledge_admin import KnowledgeAdminService, ProductMasterService
from app.observability import event, snapshot
from app.rag.service import RagService

router = APIRouter(prefix="/api")
RagServiceDependency = Annotated[RagService, Depends(get_rag_service)]
FactStatus = Literal["pending", "approved", "rejected", "superseded"]
_job_service_lock = threading.Lock()
_job_services: weakref.WeakKeyDictionary[RagService, IngestionJobService] = (
    weakref.WeakKeyDictionary()
)


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Minimal unauthenticated container health probe without enterprise metadata."""

    return {"status": "ok"}


@router.get("/health/ready")
def readiness(service: RagServiceDependency) -> dict[str, str]:
    """Check the minimum dependencies needed to answer without exposing internals."""

    try:
        counts = service.retrieval.database.counts()
        vector_count = service.retrieval.vector_store.count()
        state = service.retrieval.database.get_retrieval_state("embedding")
        if state.get("fingerprint") != service.retrieval.embedder.fingerprint:
            raise RuntimeError("Embedding fingerprint mismatch")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge services are unavailable",
        ) from exc
    if counts["indexed_chunks"] == 0 or vector_count == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo knowledge has not been initialized",
        )
    return {"status": "ready"}


@router.get("/admin/diagnostics")
def diagnostics(
    service: RagServiceDependency,
    user: AdminDependency,
    auth: Annotated[DemoAuthService, Depends(get_auth_service)],
) -> dict:
    del user
    dependencies = {"database": False, "qdrant": False}
    try:
        service.retrieval.database.counts()
        dependencies["database"] = True
        dependencies["qdrant"] = service.retrieval.vector_store.count() > 0
    except Exception:
        pass
    return {
        **snapshot(),
        "dependencies": dependencies,
        "active_sessions": auth.session_store.active_count(),
    }


@router.get("/demo-policy")
def demo_policy() -> dict:
    settings = get_settings()
    return {
        "demo_mode": settings.demo_mode,
        "read_only": settings.demo_mode and settings.public_demo_read_only,
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    service: Annotated[DemoAuthService, Depends(get_auth_service)],
) -> LoginResponse:
    try:
        token, user, expires_at = service.login(request.username, request.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable",
        ) from exc
    return LoginResponse(
        access_token=token,
        expires_at=expires_at.isoformat(),
        user=UserResponse.model_validate(user, from_attributes=True),
    )


@router.get("/auth/me", response_model=UserResponse)
def current_user(user: AuthenticatedDependency) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: AuthenticatedDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[DemoAuthService, Depends(get_auth_service)],
) -> None:
    del user
    if credentials:
        service.logout(credentials.credentials)


@router.get("/health", response_model=HealthResponse)
def health(service: RagServiceDependency, user: AdminDependency) -> HealthResponse:
    del user
    database = service.retrieval.database
    counts = database.counts()
    indexed = counts["indexed_chunks"] > 0
    return HealthResponse(
        status="ok" if indexed else "not_ingested",
        indexed=indexed,
        database_counts=counts,
        latest_ingestion=database.latest_ingestion_run(),
    )


def _knowledge_status(record_type: str, category: str) -> str:
    if record_type == "approved_product_fact" or category == "current_product_listing":
        return "current_approved"
    if category in {"quotation_evidence", "market_analytics"}:
        return "historical_or_dated"
    return "authoritative"


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    service: RagServiceDependency,
    user: AuthenticatedDependency,
) -> QueryResponse:
    settings = get_settings()
    if request.debug and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Retrieval debug mode is restricted to administrators",
        )
    debug_enabled = user.role == "admin" and (request.debug or settings.debug)
    try:
        result = service.query(
            request.question.strip(),
            debug=debug_enabled,
            limit=request.top_k,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge base is not ready. Run ingestion first.",
        ) from exc

    retrieved_context = []
    structured_matches = []
    if debug_enabled:
        retrieved_context = [
            RetrievedContextResponse(
                chunk_id=hit.chunk.id,
                content=hit.chunk.content,
                source_file=hit.chunk.source_file,
                source_type=hit.chunk.source_type,
                section=hit.chunk.section,
                row_number=hit.chunk.row_start,
                product_sku=hit.chunk.model,
                product_id=hit.chunk.product_id,
                category=hit.chunk.category,
                authority_class=hit.chunk.authority_class,
                dense_score=hit.dense_score,
                bm25_score=hit.bm25_score,
                dense_rank=hit.dense_rank,
                bm25_rank=hit.bm25_rank,
                rrf_score=hit.fused_score,
                fused_rank=hit.fused_rank,
                structured_boost=hit.structured_score,
                heuristic_score=hit.heuristic_score,
                cross_encoder_score=hit.cross_encoder_score,
                reranker_score=hit.reranker_score,
                final_rank=hit.final_rank,
            )
            for hit in result.retrieved_context
        ]
        structured_matches = [
            StructuredMatchResponse(
                product_id=match.product.product_id,
                model=match.product.model,
                title=match.product.title,
                product_group=match.product.product_group,
                match_score=match.score,
                match_reason=match.reason,
            )
            for match in result.structured_matches
        ]
    return QueryResponse(
        answer=result.answer,
        sufficient_information=result.sufficient_information,
        sources=[CitationResponse.model_validate(source) for source in result.sources],
        retrieved_context=retrieved_context,
        structured_matches=structured_matches,
        claims=[
            ClaimResponse(
                text=claim.text,
                supported=claim.supported,
                sources=[CitationResponse.model_validate(source) for source in claim.sources],
                claim_type=claim.claim_type,
                support_state=claim.support_state,
            )
            for claim in result.claims
        ],
        answer_context_chars=result.answer_context_chars,
        answer_context_chunks=result.answer_context_chunks,
        conflicts=result.conflicts,
        debug=result.debug if debug_enabled else None,
    )


@router.get("/evidence/{chunk_id}", response_model=EvidenceResponse)
def evidence(
    chunk_id: str,
    service: RagServiceDependency,
    user: AuthenticatedDependency,
) -> EvidenceResponse:
    del user
    chunk = service.retrieval.database.get_chunks([chunk_id]).get(chunk_id)
    if chunk is None or chunk.confidentiality not in {
        "synthetic_public",
        "internal",
        "commercial_internal",
    }:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return EvidenceResponse(
        chunk_id=chunk.id,
        source_file=chunk.source_file,
        source_type=chunk.source_type,
        row_start=chunk.row_start,
        row_end=chunk.row_end,
        section=chunk.section,
        sheet=chunk.sheet,
        product_sku=chunk.model,
        product_id=chunk.product_id,
        excerpt=chunk.content[:4000],
        authority_class=chunk.authority_class,
        knowledge_status=_knowledge_status(chunk.record_type, chunk.category),
        source_date=chunk.source_date,
        source_modified_at=chunk.source_modified_at,
        source_version=chunk.metadata.get("source_version"),
        approval_change_id=chunk.metadata.get("approval_change_id"),
    )


def _product_service(service: RagService) -> ProductMasterService:
    return ProductMasterService(service.retrieval.database)


@router.get("/products", response_model=list[ProductMasterResponse])
def list_products(
    service: RagServiceDependency,
    user: AuthenticatedDependency,
    search: Annotated[str | None, Query(max_length=200)] = None,
    category: Annotated[str | None, Query(max_length=200)] = None,
) -> list[ProductMasterResponse]:
    del user
    return [
        ProductMasterResponse.model_validate(item)
        for item in _product_service(service).list_products(query=search, category=category)
    ]


@router.get("/products/{product_id}", response_model=ProductMasterResponse)
def inspect_product(
    product_id: str,
    service: RagServiceDependency,
    user: AuthenticatedDependency,
) -> ProductMasterResponse:
    del user
    try:
        item = _product_service(service).get_product(product_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    return ProductMasterResponse.model_validate(item)


@router.get("/products/{product_id}/history", response_model=ProductHistoryResponse)
def product_history(
    product_id: str,
    service: RagServiceDependency,
    user: AuthenticatedDependency,
    field_name: Annotated[str | None, Query(max_length=64)] = None,
) -> ProductHistoryResponse:
    del user
    try:
        item = _product_service(service).history(product_id, field_name=field_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    return ProductHistoryResponse.model_validate(item)


def _approval_service(service: RagService) -> ProductFactApprovalService:
    return ProductFactApprovalService(service.retrieval.database)


def _review_action(action, change_id: str, request: FactReviewDecisionRequest, reviewer: str):
    try:
        result = action(
            change_id,
            reviewer_id=reviewer,
            reason=request.reason.strip(),
        )
        event("approval_action", operation=action.__name__, status="completed")
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Fact change not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/knowledge/fact-changes", response_model=list[FactChangeResponse])
def list_fact_changes(
    service: RagServiceDependency,
    user: ReviewerDependency,
    review_status: Annotated[FactStatus | None, Query(alias="status")] = "pending",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FactChangeResponse]:
    del user
    items = _approval_service(service).list_changes(
        status=review_status,
        limit=limit,
        offset=offset,
    )
    return [FactChangeResponse.model_validate(item) for item in items]


@router.get("/knowledge/fact-changes/{change_id}", response_model=FactChangeResponse)
def inspect_fact_change(
    change_id: str,
    service: RagServiceDependency,
    user: ReviewerDependency,
) -> FactChangeResponse:
    del user
    try:
        item = _approval_service(service).inspect(change_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Fact change not found") from exc
    return FactChangeResponse.model_validate(item)


@router.post(
    "/knowledge/fact-changes",
    response_model=FactChangeResponse,
    status_code=status.HTTP_201_CREATED,
)
def propose_fact_change(
    request: FactChangeProposalRequest,
    service: RagServiceDependency,
    user: AdminDependency,
) -> FactChangeResponse:
    try:
        item = _approval_service(service).propose(
            product_id=request.product_id.strip(),
            field_name=request.field_name.strip(),
            proposed_value=request.proposed_value,
            source_file=request.source_file.strip(),
            source_row=request.source_row,
            evidence=request.evidence,
            actor=f"user:{user.username}",
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FactChangeResponse.model_validate(item)


@router.post(
    "/knowledge/fact-changes/{change_id}/approve",
    response_model=FactChangeResponse,
)
def approve_fact_change(
    change_id: str,
    request: FactReviewDecisionRequest,
    service: RagServiceDependency,
    user: ReviewerDependency,
) -> FactChangeResponse:
    item = _review_action(
        _approval_service(service).approve,
        change_id,
        request,
        f"user:{user.username}",
    )
    return FactChangeResponse.model_validate(item)


@router.post(
    "/knowledge/fact-changes/{change_id}/reject",
    response_model=FactChangeResponse,
)
def reject_fact_change(
    change_id: str,
    request: FactReviewDecisionRequest,
    service: RagServiceDependency,
    user: ReviewerDependency,
) -> FactChangeResponse:
    item = _review_action(
        _approval_service(service).reject,
        change_id,
        request,
        f"user:{user.username}",
    )
    return FactChangeResponse.model_validate(item)


@router.post(
    "/knowledge/fact-changes/{change_id}/supersede",
    response_model=FactChangeResponse,
)
def supersede_fact_change(
    change_id: str,
    request: FactReviewDecisionRequest,
    service: RagServiceDependency,
    user: ReviewerDependency,
) -> FactChangeResponse:
    item = _review_action(
        _approval_service(service).supersede,
        change_id,
        request,
        f"user:{user.username}",
    )
    return FactChangeResponse.model_validate(item)


def _admin_service(service: RagService) -> KnowledgeAdminService:
    return KnowledgeAdminService(service.retrieval.database, service, get_settings())


def _ingestion_job_service(service: RagService) -> IngestionJobService:
    existing = _job_services.get(service)
    if existing is not None:
        return existing
    with _job_service_lock:
        existing = _job_services.get(service)
        if existing is None:
            existing = IngestionJobService(
                service.retrieval.database,
                _admin_service(service),
            )
            _job_services[service] = existing
    return existing


@router.get("/admin/sources", response_model=list[SourceSummaryResponse])
def list_sources(
    service: RagServiceDependency,
    user: AdminDependency,
) -> list[SourceSummaryResponse]:
    del user
    return [
        SourceSummaryResponse(
            id=item["id"],
            filename=item["filename"],
            source_type=item["source_type"],
            version=item["sha256"][:12],
            source_modified_at=item["source_modified_at"],
            source_date=item["source_date"],
            authority_class=item["authority_class"],
            confidentiality=item["confidentiality"],
            version_status=item["version_status"],
            is_current=bool(item["is_current"]) if item["is_current"] is not None else None,
            record_count=item["record_count"],
            chunk_count=item["chunk_count"],
            indexed=item["chunk_count"] > 0,
        )
        for item in _admin_service(service).list_sources()
    ]


@router.post(
    "/admin/ingestions",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_ingestion(
    background_tasks: BackgroundTasks,
    service: RagServiceDependency,
    user: AdminDependency,
) -> IngestionJobResponse:
    jobs = _ingestion_job_service(service)
    try:
        job = jobs.create(actor=f"user:{user.username}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(jobs.run, job["id"])
    return IngestionJobResponse.model_validate(job)


@router.get("/admin/ingestion-jobs", response_model=list[IngestionJobResponse])
def list_ingestion_jobs(
    service: RagServiceDependency,
    user: AdminDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[IngestionJobResponse]:
    del user
    return [
        IngestionJobResponse.model_validate(item)
        for item in _ingestion_job_service(service).list(limit=limit)
    ]


@router.get("/admin/ingestion-jobs/{job_id}", response_model=IngestionJobResponse)
def inspect_ingestion_job(
    job_id: str,
    service: RagServiceDependency,
    user: AdminDependency,
) -> IngestionJobResponse:
    del user
    try:
        item = _ingestion_job_service(service).get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found") from exc
    return IngestionJobResponse.model_validate(item)


@router.post(
    "/admin/ingestion-jobs/{job_id}/cancel",
    response_model=IngestionJobResponse,
)
def cancel_ingestion_job(
    job_id: str,
    service: RagServiceDependency,
    user: AdminDependency,
) -> IngestionJobResponse:
    del user
    try:
        item = _ingestion_job_service(service).cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestionJobResponse.model_validate(item)


@router.get("/admin/staged-sources", response_model=list[StagedSourceResponse])
def list_staged_sources(
    service: RagServiceDependency,
    user: AdminDependency,
) -> list[StagedSourceResponse]:
    del user
    return [
        StagedSourceResponse.model_validate(item)
        for item in service.retrieval.database.list_staged_sources()
    ]


@router.post(
    "/admin/staged-sources",
    response_model=StagedSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def stage_source(
    service: RagServiceDependency,
    user: AdminDependency,
    file: Annotated[UploadFile, File(...)],
) -> StagedSourceResponse:
    if not upload_media_type_allowed(file.filename or "", file.content_type):
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload media type does not match an allowed source format",
        )
    data = await file.read(get_settings().max_upload_bytes + 1)
    await file.close()
    try:
        item = _admin_service(service).stage_source(
            filename=file.filename or "",
            data=data,
            actor=f"user:{user.username}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StagedSourceResponse.model_validate(item)


@router.post(
    "/admin/staged-sources/{source_id}/propose",
    response_model=StagedProposalResponse,
)
def propose_staged_source(
    source_id: str,
    service: RagServiceDependency,
    user: AdminDependency,
) -> StagedProposalResponse:
    try:
        item = _admin_service(service).propose_staged_facts(
            source_id,
            actor=f"user:{user.username}",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Staged source not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return StagedProposalResponse.model_validate(item)
