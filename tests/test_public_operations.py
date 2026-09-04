import hashlib
import json
from pathlib import Path

import pytest

from app.demo_safety import prepare_runtime, verify_demo_sources
from scripts.demo_ops import run_operation, validate_backup
from scripts.local_demo import settings_for


def test_manifest_and_runtime_boundaries(tmp_path):
    root = Path(__file__).resolve().parents[1]
    verify_demo_sources(root / "data/demo/source")
    with pytest.raises(ValueError):
        verify_demo_sources(tmp_path)
    with pytest.raises(ValueError):
        prepare_runtime(settings_for(tmp_path / "not-a-demo-runtime"))
    settings = settings_for(tmp_path / "public-demo-runtime")
    with pytest.raises(ValueError):
        prepare_runtime(settings.model_copy(update={"database_path": tmp_path / "outside.db"}))


def test_isolated_backup_restore_reset(tmp_path):
    settings = settings_for(tmp_path / "public-demo-runtime")
    assert run_operation(settings, "reset")["status"] == "completed"
    backup = tmp_path / "backup"
    assert run_operation(settings, "backup", backup)["status"] == "completed"
    assert validate_backup(backup).exists()
    assert run_operation(settings, "restore", backup)["status"] == "completed"
    assert run_operation(settings, "reset")["status"] == "completed"
    settings.auth_session_database_path.write_bytes(b"not a real session database")
    assert run_operation(settings, "reset")["status"] == "completed"
    assert not settings.auth_session_database_path.exists()


def test_eval_labels_have_distinct_ids_and_are_frozen():
    root = Path(__file__).resolve().parents[1]
    definition = json.loads((root / "evaluation/definition.json").read_text())
    ids = []
    questions = []
    for name, entry in definition["datasets"].items():
        path = root / "evaluation" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        rows = json.loads(path.read_text())["questions"]
        ids.extend(row["id"] for row in rows)
        questions.extend(row["question"] for row in rows)
    assert len(ids) == len(set(ids)) == 70
    assert len(questions) == len(set(questions))
