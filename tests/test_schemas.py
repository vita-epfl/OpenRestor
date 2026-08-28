from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from openrestore.validation.core import validate_file


class SchemaValidationTests(TestCase):
    def _write(self, root: Path, name: str, value: object) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_all_artifact_schemas_accept_minimal_documents(self) -> None:
        documents = {
            "index": {"id": "item", "dataset": "clean", "split": "train", "clean_path": "train/item.wav"},
            "degradation_tracking": {
                "recipe_id": "single_noise",
                "severity": "random",
                "item_seed": 1,
                "operations": [{"primitive": "noise_interference", "seed": 2, "summary": {}}],
            },
            "submission_manifest": {"submission_id": "submission", "image": "registry/model@sha256:abc", "inference_command": "run"},
            "scores": {"benchmark_version": "v0.1", "submission_id": "submission", "metrics": {"l1": 0.1}},
            "leaderboard_entry": {"submission_id": "submission", "track": "main", "status": "valid"},
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind, document in documents.items():
                self.assertEqual(validate_file(kind, self._write(root, f"{kind}.json", document)), 1)

    def test_invalid_document_reports_schema_error(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._write(Path(directory), "bad.json", {"id": "missing-required-fields"})
            with self.assertRaises(ValueError):
                validate_file("index", path)
