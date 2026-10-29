from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from openrestor.validation.core import validate_clean_manifest, validate_file


class SchemaValidationTests(TestCase):
    def _write(self, root: Path, name: str, value: object) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_all_artifact_schemas_accept_minimal_documents(self) -> None:
        documents = {
            "index": {
                "id": "item",
                "dataset": "clean",
                "split": "train",
                "clean_path": "train/item.wav",
            },
            "clean_manifest": {
                "dataset": "clean",
                "source_id": "item",
                "source_key": "clean:item",
                "audio_path": None,
                "metadata": {},
                "rights": {"review_status": "pending"},
            },
            "degradation_tracking": {
                "recipe_id": "single_noise",
                "severity": "random",
                "item_seed": 1,
                "operations": [{"primitive": "noise_interference", "seed": 2, "summary": {}}],
            },
            "submission_manifest": {
                "submission_id": "submission",
                "image": "registry/model@sha256:abc",
                "inference_command": "run",
            },
            "restoration_outputs": {"id": "item", "restored_audio_path": "outputs/item.wav"},
            "restoration_metadata": {
                "id": "item",
                "degraded_audio_path": "degraded/item.wav",
                "clean_audio_path": "clean/item.wav",
                "degradation_type": "noise",
                "source_id": "source",
                "restored_audio_path": "outputs/item.wav",
            },
            "scores": {
                "benchmark_version": "v0.1",
                "submission_id": "submission",
                "metric_pack": "cpu_core_v0_1",
                "ranking": "diagnostic_only_no_aggregate",
                "items": {"scored": 1, "failures": 0},
                "metric_definitions": {"l1": {"direction": "lower"}},
                "overall": {},
                "by_category": {},
                "by_effect": {},
                "by_severity": {},
                "by_split": {},
                "by_dataset": {},
                "artifacts": {},
            },
            "leaderboard_entry": {
                "submission_id": "submission",
                "track": "main",
                "status": "valid",
            },
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind, document in documents.items():
                path = self._write(root, f"{kind}.json", document)
                count = (validate_clean_manifest(path) if kind == "clean_manifest"
                         else validate_file(kind, path))
                self.assertEqual(count, 1)

    def test_clean_manifest_requires_consistent_source_key_and_unique_rows(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "manifest.jsonl"
            rows = [
                {"dataset": "clean", "source_id": "one", "source_key": "wrong:one",
                 "audio_path": None, "metadata": {}, "rights": {}},
                {"dataset": "clean", "source_id": "one", "source_key": "clean:one",
                 "audio_path": None, "metadata": {}, "rights": {}},
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_key"):
                validate_clean_manifest(path)

    def test_invalid_document_reports_schema_error(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._write(Path(directory), "bad.json", {"id": "missing-required-fields"})
            with self.assertRaises(ValueError):
                validate_file("index", path)
