from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ingestion.pipeline import IngestionPipeline, IngestionResult

__all__ = ["IngestionPipeline", "IngestionResult"]


def __getattr__(name: str) -> Any:
    """Keep the package convenience imports without an eager approval/pipeline cycle."""

    if name in __all__:
        from app.ingestion.pipeline import IngestionPipeline, IngestionResult

        return {"IngestionPipeline": IngestionPipeline, "IngestionResult": IngestionResult}[name]
    raise AttributeError(name)
