import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_clean_rights_overrides import apply_overrides


class ApplyCleanRightsOverridesTests(unittest.TestCase):
    def _manifest(self, root: Path) -> Path:
        path = root / "manifest.jsonl"
        rows = [
            {
                "source_key": "pilot:one", "audio_path": "/private/one.wav",
                "source_sha256": "old", "metadata": {"creator": "A"},
                "rights": {"review_status": "pending", "provenance_approved": False},
            },
            {
                "source_key": "pilot:two", "audio_path": "/private/two.wav",
                "rights": {"review_status": "pending"},
            },
        ]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def _approved(self, key: str = "pilot:one") -> dict:
        return {
            "media_key": key, "review_status": "approved", "reviewer": "R",
            "evidence_date": "2026-10-30", "license_label": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "Artist", "evidence_url": "https://example.test/evidence",
            "allow_commercial": False, "allow_redistribution": True,
            "allow_derivatives": True, "share_alike": False,
            "provenance_approved": True, "redistribution_approved": True,
            "source_sha256": "a" * 64,
        }

    def test_applies_rights_only_and_records_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            overrides = root / "overrides.jsonl"
            overrides.write_text(json.dumps(self._approved()) + "\n", encoding="utf-8")
            out, report = root / "out.jsonl", root / "report.json"
            result = apply_overrides(manifest, overrides, out, report, applied_at="2026-10-30T00:00:00+00:00")
            self.assertEqual(result["applied_rows"], 1)
            rows = [json.loads(line) for line in out.read_text().splitlines()]
            first = rows[0]
            self.assertEqual(first["audio_path"], "/private/one.wav")
            self.assertEqual(first["metadata"], {"creator": "A"})
            self.assertEqual(first["source_sha256"], "a" * 64)
            self.assertEqual(first["rights"]["review_status"], "approved")
            self.assertEqual(len(first["rights"]["rights_review_history"]), 1)
            self.assertEqual(first["rights"]["rights_review_history"][0]["previous_review_status"], "pending")
            self.assertEqual(rows[1]["rights"]["review_status"], "pending")

    def test_duplicate_and_unknown_overrides_fail_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            out, report = root / "out.jsonl", root / "report.json"
            duplicate = root / "duplicate.jsonl"
            item = self._approved()
            duplicate.write_text("".join(json.dumps(item) + "\n" for _ in range(2)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate override"):
                apply_overrides(manifest, duplicate, out, report)
            self.assertFalse(out.exists())
            unknown = root / "unknown.jsonl"
            unknown.write_text(json.dumps(self._approved("pilot:missing")) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not in manifest"):
                apply_overrides(manifest, unknown, out, report)
            self.assertFalse(out.exists())

    def test_reapplying_same_override_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            overrides = root / "overrides.jsonl"
            overrides.write_text(json.dumps(self._approved()) + "\n", encoding="utf-8")
            first, first_report = root / "first.jsonl", root / "first.json"
            second, second_report = root / "second.jsonl", root / "second.json"
            apply_overrides(manifest, overrides, first, first_report, applied_at="2026-10-30T00:00:00+00:00")
            result = apply_overrides(first, overrides, second, second_report,
                                     applied_at="2026-10-31T00:00:00+00:00")
            self.assertEqual(result["applied_rows"], 0)
            self.assertEqual(result["idempotent_rows"], 1)
            row = json.loads(second.read_text().splitlines()[0])
            self.assertEqual(len(row["rights"]["rights_review_history"]), 1)

    def test_approved_override_requires_verified_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            overrides = root / "bad.jsonl"
            item = self._approved()
            item["source_sha256"] = "not-a-sha256"
            overrides.write_text(json.dumps(item) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "64-character"):
                apply_overrides(manifest, overrides, root / "out.jsonl", root / "report.json")


if __name__ == "__main__":
    unittest.main()
