"""Clean rebuild and write-once evaluation of the synthetic public corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from app.config import Settings
from app.evaluation.runner import run_evaluation
from app.ingestion.pipeline import IngestionPipeline
from app.runtime import build_rag_service

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "held_out", "blind"], required=True)
    parser.add_argument("--provider", choices=["domain_hash", "fastembed"], default="domain_hash")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing benchmark result")
    questions = ROOT / f"evaluation/public_{args.split}_questions.json"
    definition = json.loads((ROOT / "evaluation/definition.json").read_text())
    digest = hashlib.sha256(questions.read_bytes()).hexdigest()
    if digest != definition["datasets"][questions.name]["sha256"]:
        raise SystemExit("Dataset hash differs from the frozen definition")
    with tempfile.TemporaryDirectory(prefix="northstar-benchmark-") as directory:
        runtime = Path(directory)
        settings = Settings(
            _env_file=None,
            environment="test",
            database_path=runtime / "knowledge.db",
            qdrant_path=str(runtime / "qdrant"),
            ingestion_source_path=ROOT / "data/demo/source",
            embedding_provider=args.provider,
            embedding_allow_hash_fallback=False,
            chunking_strategy="source_aware",
            embedding_cache_path=ROOT / "data/private/models",
        )
        service = build_rag_service(settings)
        try:
            ingestion = IngestionPipeline(
                service.retrieval.database,
                service.retrieval.vector_store,
                service.retrieval.embedder,
                chunking_strategy="source_aware",
            ).run(settings.ingestion_source_path)
            result = run_evaluation(service, questions).to_dict()
            result.update(
                {
                    "benchmark": "Synthetic Public Demo Benchmark",
                    "split": args.split,
                    "dataset_sha256": digest,
                    "embedding_provider": args.provider,
                    "embedding_model": service.retrieval.embedder.model_name,
                    "embedding_dimension": service.retrieval.embedder.dimension,
                    "ingestion": asdict(ingestion),
                    "method": (
                        "Developer-authored synthetic source/claim checks; "
                        "not human-blind validation"
                    ),
                }
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            print(json.dumps(result["summary"], indent=2))
        finally:
            service.retrieval.vector_store.close()


if __name__ == "__main__":
    main()
