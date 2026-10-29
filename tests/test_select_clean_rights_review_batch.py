import unittest

from scripts.select_clean_rights_review_batch import select


def row(key, dataset, license_label, collection, creator, *, technical=True,
        review_status="pending"):
    return {
        "source_key": key,
        "dataset": dataset,
        "license_label": license_label,
        "collection": collection,
        "creator": creator,
        "technical_candidate": technical,
        "review_status": review_status,
        "audio_path_omitted": True,
        "audio_path": None,
        "redistribution_approved": None,
        "provenance_approved": None,
    }


class RightsReviewBatchTests(unittest.TestCase):
    def test_selection_is_deterministic_balanced_and_fail_closed(self):
        rows = [
            row("a:1", "a", "CC BY", "ca", "one"),
            row("a:2", "a", "CC BY", "ca", "two"),
            row("a:3", "a", "CC0", "cb", "three"),
            row("b:1", "b", "CC BY", "cb", "four"),
            row("b:2", "b", "CC0", "cc", "five"),
            row("c:1", "c", "CC BY", None, None),
            row("c:2", "c", "CC BY", None, None, technical=False),
            row("d:1", "d", "CC BY", "cd", "six", review_status="approved"),
        ]
        selected, report = select(rows, 5)
        self.assertEqual([item["source_key"] for item in selected],
                         ["a:1", "b:2", "c:1", "a:3", "b:1"])
        self.assertEqual(report["selected_sources"], 5)
        self.assertEqual(report["skipped"], {"already_approved": 1})
        self.assertFalse(report["audio_paths_included"])
        self.assertTrue(report["rights_are_not_inferred"])
        selected_again, report_again = select(rows, 5)
        self.assertEqual(selected, selected_again)
        self.assertEqual(report["selected_source_keys_sha256"],
                         report_again["selected_source_keys_sha256"])

    def test_filters_do_not_turn_unknowns_into_approvals(self):
        rows = [row("a:1", "a", "CC BY", None, None, technical=False)]
        selected, report = select(rows, 1, technical_only=False, licenses={"CC BY"})
        self.assertEqual(selected[0]["redistribution_approved"], None)
        self.assertEqual(selected[0]["provenance_approved"], None)
        self.assertEqual(report["selected_by_collection"], {"[unknown]": 1})
        with self.assertRaisesRegex(ValueError, "no eligible"):
            select(rows, 1, technical_only=True)

    def test_duplicate_and_audio_path_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate source_key"):
            select([row("a:1", "a", "CC BY", "c", "x"),
                    row("a:1", "a", "CC BY", "c", "x")], 1)
        bad = row("a:1", "a", "CC BY", "c", "x")
        bad["audio_path"] = "/private/audio.wav"
        with self.assertRaisesRegex(ValueError, "audio path"):
            select([bad], 1)


if __name__ == "__main__":
    unittest.main()
