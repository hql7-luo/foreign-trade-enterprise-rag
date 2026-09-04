"""Record synthetic dataset/source/code hashes before first evaluation; never overwrite."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination = ROOT / "evaluation/definition.json"
    if destination.exists():
        raise SystemExit("Definition already frozen; refusing to overwrite")
    datasets = {}
    for path in sorted((ROOT / "evaluation").glob("public_*_questions.json")):
        questions = json.loads(path.read_text())["questions"]
        if len({q["id"] for q in questions}) != len(questions):
            raise ValueError("Duplicate question IDs")
        datasets[path.name] = {
            "sha256": sha(path),
            "n": len(questions),
            "categories": dict(Counter(q["category"] for q in questions)),
            "languages": dict(Counter(q["language"] for q in questions)),
        }
    definition = {
        "benchmark": "Synthetic Public Demo Benchmark",
        "method": "Developer-authored synthetic cases, frozen before first execution. "
        "Not independently human-authored or a real-world blind benchmark.",
        "datasets": datasets,
        "sources": {p.name: sha(p) for p in sorted((ROOT / "data/demo/source").iterdir())},
        "implementation": {
            p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT / "app").rglob("*.py"))
        },
    }
    with destination.open("x") as stream:
        json.dump(definition, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    manifest = ROOT / "data/demo/manifest.json"
    with manifest.open("x") as stream:
        json.dump(definition["sources"], stream, indent=2)
        stream.write("\n")
    print({key: value["n"] for key, value in datasets.items()})


if __name__ == "__main__":
    main()
