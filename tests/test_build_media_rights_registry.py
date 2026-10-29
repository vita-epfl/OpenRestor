import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_media_rights_registry import merge_clean_manifest


class CleanManifestRightsRegistryTests(unittest.TestCase):
    def test_source_specific_pending_status_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.jsonl"
            path.write_text(json.dumps({
                "dataset": "guitarset", "source_id": "member-1",
                "rights": {
                    "license_label": "cc-by-4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "review_status": "metadata_confirmed_pending_asset_review",
                    "allow_commercial": None, "allow_redistribution": None,
                    "allow_derivatives": None,
                },
            }) + "\n", encoding="utf-8")
            records = {}
            merge_clean_manifest(records, path)
            row = records["guitarset:member-1"]
            self.assertEqual(row["review_status"], "pending")
            self.assertIsNone(row["allow_commercial"])
            self.assertIn("metadata_confirmed_pending_asset_review", row["provenance_note"])

    def test_later_review_override_can_approve_imported_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.jsonl"
            path.write_text(json.dumps({"dataset": "guitarset", "source_id": "member-1",
                                        "rights": {"review_status": "pending"}}) + "\n",
                            encoding="utf-8")
            records = {}
            merge_clean_manifest(records, path)
            records["guitarset:member-1"].update({
                "license_label": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "Creator", "evidence_url": "https://example.org/evidence",
                "evidence_date": "2026-10-29", "reviewer": "Reviewer",
                "review_status": "approved", "allow_commercial": True,
                "allow_redistribution": True, "allow_derivatives": True,
                "share_alike": False,
            })
            self.assertEqual(records["guitarset:member-1"]["review_status"], "approved")

    def test_review_history_survives_registry_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.jsonl"
            history = [{"label": "rights_review_override", "override_sha256": "a" * 64}]
            path.write_text(json.dumps({
                "dataset": "guitarset", "source_id": "member-1",
                "rights": {"review_status": "pending", "rights_review_history": history},
            }) + "\n", encoding="utf-8")
            records = {}
            merge_clean_manifest(records, path)
            self.assertEqual(records["guitarset:member-1"]["rights_review_history"], history)


if __name__ == "__main__":
    unittest.main()
