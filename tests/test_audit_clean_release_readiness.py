import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_clean_release_readiness import audit


def write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class CleanReleaseReadinessTests(unittest.TestCase):
    def _manifest_row(self, **overrides):
        row = {
            "dataset": "test", "source_id": "one", "audio_path": "/tmp/one.wav",
            "source_sha256": "abc", "technical_candidate": True,
            "lossless_status": "clean_lossless", "rights_profile": "public_research",
            "rights": {
                "provenance_approved": True, "review_status": "approved",
                "redistribution_approved": True,
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "attribution": "Artist", "evidence_url": "https://example.test/item",
                "evidence_date": "2026-10-29", "allow_redistribution": True,
                "allow_derivatives": True, "allow_commercial": False,
            },
        }
        row.update(overrides)
        return row

    def test_metadata_only_profiles_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            row = self._manifest_row(audio_path=None, lossless_status="archive_declared_original_unverified",
                                     rights_profile="blocked", rights={"provenance_approved": False})
            write_jsonl(manifest, [row])
            for profile in ("public_research", "public_commercial", "internal_research"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            write_jsonl(profiles / "blocked.jsonl", [{**row, "rights_profile": "blocked"}])
            result = audit(manifest, profiles)
            self.assertEqual(result["verdict"], "NO-GO")
            self.assertEqual(result["public_sources"], 0)
            self.assertFalse(result["audio_uploaded"])
            self.assertIn("no_public_sources", {w["code"] for w in result["warnings"]})

    def test_approved_public_research_manifest_can_pass_mechanical_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "one.wav"
            audio.write_bytes(b"audio")
            import hashlib
            row = self._manifest_row(audio_path=str(audio), source_sha256=hashlib.sha256(b"audio").hexdigest())
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            write_jsonl(manifest, [row])
            write_jsonl(profiles / "public_research.jsonl", [{**row, "rights_profile": "public_research"}])
            for profile in ("public_commercial", "internal_research", "blocked"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            result = audit(manifest, profiles, verify_local_checksums=True)
            self.assertEqual(result["verdict"], "GO")
            self.assertEqual(result["public_sources"], 1)
            self.assertEqual(result["errors"], [])

    def test_public_commercial_requires_commercial_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = self._manifest_row(rights_profile="public_commercial")
            row["rights"]["allow_commercial"] = False
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            write_jsonl(manifest, [row])
            write_jsonl(profiles / "public_commercial.jsonl", [{**row, "rights_profile": "public_commercial"}])
            for profile in ("public_research", "internal_research", "blocked"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            result = audit(manifest, profiles)
            self.assertEqual(result["verdict"], "NO-GO")
            self.assertIn("commercial_use_not_allowed", result["error_counts"])
            self.assertIn("commercial_without_research_profile", result["error_counts"])

    def test_commercial_asset_can_appear_in_both_public_views_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = self._manifest_row()
            row["rights"]["allow_commercial"] = True
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            write_jsonl(manifest, [row])
            write_jsonl(profiles / "public_research.jsonl", [{**row, "rights_profile": "public_research"}])
            write_jsonl(profiles / "public_commercial.jsonl", [{**row, "rights_profile": "public_commercial"}])
            for profile in ("internal_research", "blocked"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            result = audit(manifest, profiles)
            self.assertEqual(result["verdict"], "GO")
            self.assertEqual(result["public_sources"], 1)
            self.assertEqual(result["public_profile_overlap"], 1)
            self.assertTrue(result["profile_partition_complete"])

    def test_commercial_view_must_match_research_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = self._manifest_row()
            row["rights"]["allow_commercial"] = True
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            write_jsonl(manifest, [row])
            write_jsonl(profiles / "public_research.jsonl", [{**row, "rights_profile": "public_research"}])
            write_jsonl(profiles / "public_commercial.jsonl", [
                {**row, "rights_profile": "public_commercial", "source_sha256": "different"}])
            for profile in ("internal_research", "blocked"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            result = audit(manifest, profiles)
            self.assertEqual(result["verdict"], "NO-GO")
            self.assertIn("public_profile_row_mismatch", result["error_counts"])

    def test_public_profile_requires_redistribution_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = self._manifest_row()
            row["rights"].pop("redistribution_approved")
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            write_jsonl(manifest, [row])
            write_jsonl(profiles / "public_research.jsonl", [{**row, "rights_profile": "public_research"}])
            for profile in ("public_commercial", "internal_research", "blocked"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            result = audit(manifest, profiles)
            self.assertEqual(result["verdict"], "NO-GO")
            self.assertIn("redistribution_not_approved", result["error_counts"])

    def test_profile_cannot_grant_rights_absent_from_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = self._manifest_row(rights_profile="blocked")
            row["rights"]["provenance_approved"] = False
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            write_jsonl(manifest, [row])
            forged = {**row, "rights_profile": "public_research",
                      "rights": {**row["rights"], "provenance_approved": True}}
            write_jsonl(profiles / "public_research.jsonl", [forged])
            for profile in ("public_commercial", "internal_research", "blocked"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            result = audit(manifest, profiles)
            self.assertEqual(result["verdict"], "NO-GO")
            self.assertIn("profile_row_differs_from_manifest", result["error_counts"])

    def test_manifest_sources_must_be_partitioned_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = self._manifest_row()
            second = {**row, "source_id": "missing-from-profiles"}
            manifest = root / "manifest.jsonl"
            profiles = root / "profiles"
            profiles.mkdir()
            write_jsonl(manifest, [row, second])
            write_jsonl(profiles / "public_research.jsonl", [{**row, "rights_profile": "public_research"}])
            for profile in ("public_commercial", "internal_research", "blocked"):
                write_jsonl(profiles / f"{profile}.jsonl", [])
            result = audit(manifest, profiles)
            self.assertFalse(result["profile_partition_complete"])
            self.assertIn("manifest_source_missing_from_profiles", result["error_counts"])
            self.assertEqual(result["verdict"], "NO-GO")


if __name__ == "__main__":
    unittest.main()
