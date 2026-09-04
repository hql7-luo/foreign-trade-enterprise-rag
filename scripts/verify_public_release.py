"""Verify frozen synthetic artifacts and run regression checks without overwriting evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from app.config import Settings
from app.evaluation.runner import run_evaluation
from app.ingestion.pipeline import IngestionPipeline
from app.runtime import build_rag_service

ROOT = Path(__file__).resolve().parents[1]


def verify_frozen():
    definition = json.loads((ROOT / "evaluation/definition.json").read_text())
    for name, entry in definition["datasets"].items():
        assert (
            hashlib.sha256((ROOT / "evaluation" / name).read_bytes()).hexdigest() == entry["sha256"]
        )
    for name, digest in definition["sources"].items():
        assert hashlib.sha256((ROOT / "data/demo/source" / name).read_bytes()).hexdigest() == digest
    for name, digest in definition["implementation"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    if (ROOT / ".git").exists():
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        for name in filter(None, tracked):
            path = Path(name)
            assert not (name.startswith("data/private/") and name != "data/private/.gitkeep")
            assert not name.startswith("data/public-demo-runtime/")
            assert path.suffix not in {".db", ".sqlite", ".log", ".pyc", ".onnx"}
            assert not any(part in {".venv", "node_modules", "__pycache__"} for part in path.parts)
    return definition


def main():
    verify_frozen()
    with tempfile.TemporaryDirectory(prefix="northstar-regression-") as directory:
        runtime = Path(directory)
        service = build_rag_service(
            Settings(
                _env_file=None,
                environment="test",
                database_path=runtime / "knowledge.db",
                qdrant_path=str(runtime / "qdrant"),
                embedding_provider="domain_hash",
                embedding_allow_hash_fallback=False,
                chunking_strategy="source_aware",
            )
        )
        try:
            IngestionPipeline(
                service.retrieval.database,
                service.retrieval.vector_store,
                service.retrieval.embedder,
                chunking_strategy="source_aware",
            ).run(ROOT / "data/demo/source")
            for split in ["dev", "held_out", "blind"]:
                result = run_evaluation(service, ROOT / f"evaluation/public_{split}_questions.json")
                baseline = json.loads(
                    (ROOT / f"evaluation/results/{split}_first_run.json").read_text()
                )["summary"]
                for metric in [
                    "recall_at_1",
                    "recall_at_3",
                    "recall_at_5",
                    "recall_at_8",
                    "mrr",
                    "answer_correctness",
                    "citation_correctness",
                    "sufficiency_correctness",
                    "claim_coverage",
                    "multi_fact_completeness",
                ]:
                    assert result.summary[metric] >= baseline[metric] - 1e-9, (split, metric)
                assert (
                    result.summary["unsupported_hallucination_rate"]
                    <= baseline["unsupported_hallucination_rate"]
                )
                print(f"{split}: frozen synthetic regression passed, N={result.summary['n']}")
        finally:
            service.retrieval.vector_store.close()


if __name__ == "__main__":
    main()
