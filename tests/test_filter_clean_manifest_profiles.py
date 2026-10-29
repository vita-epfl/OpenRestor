import tempfile
import unittest
from pathlib import Path

from scripts.filter_clean_manifest_profiles import filter_rows


def row(source_id, url, *, provenance=True, technical=True, audio=True):
    code = url.rstrip("/").split("/")[-2] if "creativecommons.org/licenses/" in url else "by"
    label = "CC " + code.upper() + " 4.0"
    return {
        "dataset": "test", "source_id": source_id, "audio_path": "/tmp/audio.flac" if audio else None,
        "technical_candidate": technical,
        "rights": {"license_label": label, "license_url": url,
                    "attribution": "Artist", "evidence_url": "https://example.test/evidence",
                    "evidence_date": "2026-10-29", "review_status": "approved",
                    "reviewer": "reviewer", "provenance_approved": provenance,
                    "redistribution_approved": provenance,
                    "allow_commercial": "nc" not in url, "allow_redistribution": True,
                    "allow_derivatives": "nd" not in url, "share_alike": "sa" in url},
    }


class CleanRightsProfileTests(unittest.TestCase):
    def test_profiles_are_strict_and_nc_is_research_only(self):
        rows = [
            row("by", "https://creativecommons.org/licenses/by/4.0/"),
            row("nc", "https://creativecommons.org/licenses/by-nc/4.0/"),
            row("nd", "https://creativecommons.org/licenses/by-nd/4.0/"),
            row("unknown", "https://example.test/license", provenance=False),
        ]
        outputs, report = filter_rows(rows)
        self.assertEqual([r["source_id"] for r in outputs["public_commercial"]], ["by"])
        self.assertEqual([r["source_id"] for r in outputs["public_research"]], ["by", "nc"])
        self.assertEqual([r["source_id"] for r in outputs["internal_research"]], ["nd"])
        self.assertEqual({r["source_id"] for r in outputs["blocked"]}, {"unknown"})
        self.assertEqual(report["unique_public_sources"], 2)
        self.assertEqual(report["public_profile_overlap"], 1)
        self.assertFalse(report["audio_copied"])

    def test_share_alike_family_is_preserved_in_both_public_views(self):
        outputs, _ = filter_rows([row("sa", "https://creativecommons.org/licenses/by-sa/4.0/")])
        self.assertEqual(outputs["public_research"][0]["rights_family"],
                         "sa:https://creativecommons.org/licenses/by-sa/4.0/")
        self.assertEqual(outputs["public_commercial"][0]["rights_family"],
                         "sa:https://creativecommons.org/licenses/by-sa/4.0/")

    def test_technical_gate_is_independent(self):
        outputs, report = filter_rows([row("x", "https://creativecommons.org/licenses/by/4.0/",
                                           technical=False)], require_technical=True)
        self.assertEqual(outputs["public_commercial"], [])
        self.assertEqual(outputs["blocked"][0]["blocked_reason"], "technical_candidate_false")
        self.assertTrue(report["require_technical"])

    def test_technical_gate_is_fail_closed_by_default(self):
        outputs, report = filter_rows([row("x", "https://creativecommons.org/licenses/by/4.0/",
                                           technical=False)])
        self.assertEqual(outputs["public_commercial"], [])
        self.assertEqual(outputs["blocked"][0]["blocked_reason"], "technical_candidate_false")
        self.assertTrue(report["require_technical"])

    def test_redistribution_approval_has_its_own_block_reason(self):
        candidate = row("x", "https://creativecommons.org/licenses/by/4.0/", audio=False)
        candidate["rights"]["redistribution_approved"] = False
        outputs, report = filter_rows([candidate])
        self.assertEqual(outputs["blocked"][0]["blocked_reason"], "redistribution_not_approved")
        self.assertEqual(report["blocked_reasons"], {"redistribution_not_approved": 1})

    def test_duplicate_keys_fail(self):
        with self.assertRaises(ValueError):
            filter_rows([row("x", "https://creativecommons.org/licenses/by/4.0/"),
                         row("x", "https://creativecommons.org/licenses/by/4.0/")])


if __name__ == "__main__":
    unittest.main()
