import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.export_clean_rights_review_form import export_form
from scripts.import_clean_rights_review_form import import_form


class CleanRightsReviewFormTests(unittest.TestCase):
    def _row(self):
        return {
            "source_key": "pilot:one", "dataset": "pilot", "source_id": "one",
            "title": "Song", "collection": "collection", "creator": "Artist",
            "original_format": "WAV", "source_status": "ambiguous_original_status",
            "technical_candidate": True, "provenance_candidate": True,
            "license_label": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "evidence_url": "https://example.test/evidence", "audio_path": None,
            "provenance_approved": False, "redistribution_approved": False,
        }

    def test_export_has_blank_decision_and_no_audio_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, report = root / "form.csv", root / "report.json"
            result = export_form([self._row()], out, report)
            with out.open(encoding="utf-8", newline="") as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(result["form_rows"], 1)
            self.assertEqual(saved[0]["source_key"], "pilot:one")
            self.assertEqual(saved[0]["decision"], "")
            self.assertNotIn("audio_path", saved[0])
            self.assertTrue(result["rights_are_not_inferred"])

    def test_import_skips_blank_and_rejects_incomplete_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            form = root / "form.csv"
            fields = ["source_key", "decision", "reviewer", "review_date", "reason"]
            with form.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"source_key": "pilot:blank", "decision": ""})
                writer.writerow({"source_key": "pilot:reject", "decision": "rejected",
                                 "reviewer": "R", "review_date": "2026-10-30",
                                 "reason": "rights unclear"})
            out, report = root / "overrides.jsonl", root / "report.json"
            result = import_form(form, out, report)
            self.assertEqual(result["override_rows"], 1)
            self.assertEqual(result["blank_or_unreviewed_rows"], 1)
            saved = json.loads(out.read_text().strip())
            self.assertEqual(saved["review_status"], "rejected")
            self.assertFalse(saved["provenance_approved"])

    def test_approval_requires_original_checksum_and_explicit_approvals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            form = root / "form.csv"
            fields = [
                "source_key", "decision", "reviewer", "review_date",
                "verified_license_label", "verified_license_url",
                "verified_attribution", "evidence_url", "allow_commercial",
                "allow_redistribution", "allow_derivatives", "share_alike",
                "provenance_approved", "redistribution_approved",
                "source_status_verified", "verified_source_sha256",
            ]
            values = {field: "x" for field in fields}
            values.update({"source_key": "pilot:one", "decision": "approved",
                           "reviewer": "R", "review_date": "2026-10-30",
                           "allow_commercial": "true", "allow_redistribution": "true",
                           "allow_derivatives": "true", "share_alike": "false",
                           "provenance_approved": "true", "redistribution_approved": "true",
                           "source_status_verified": "original_verified",
                           "verified_source_sha256": "0" * 64})
            with form.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow(values)
            result = import_form(form, root / "overrides.jsonl", root / "report.json")
            self.assertEqual(result["override_rows"], 1)
            saved = json.loads((root / "overrides.jsonl").read_text().strip())
            self.assertTrue(saved["provenance_approved"])
            self.assertEqual(saved["source_sha256"], "0" * 64)

    def test_expected_queue_rejects_unknown_or_missing_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = root / "queue.jsonl"
            queue.write_text("".join(json.dumps({"source_key": key}) + "\n"
                                   for key in ("pilot:one", "pilot:two")), encoding="utf-8")
            form = root / "form.csv"
            fields = ["source_key", "decision"]
            with form.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"source_key": "pilot:one", "decision": ""})
            with self.assertRaisesRegex(ValueError, "missing expected"):
                import_form(form, root / "bad.jsonl", root / "bad.json", expected_queue=queue)
            result = import_form(form, root / "subset.jsonl", root / "subset.json",
                                 expected_queue=queue, allow_subset=True)
            self.assertEqual(result["missing_expected_sources"], 1)
            self.assertFalse(result["source_keys_match_expected"])


if __name__ == "__main__":
    unittest.main()
