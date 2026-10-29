import unittest

from scripts.audit_clean_rights_license_consistency import audit


def row(key, label, url):
    return {"source_key": key, "dataset": "test", "license_label": label,
            "license_url": url, "review_status": "pending"}


class RightsLicenseConsistencyTests(unittest.TestCase):
    def test_recognizes_http_https_and_normalized_labels(self):
        rows, report = audit([
            row("a", "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
            row("b", "cc-by-4.0", "http://creativecommons.org/licenses/by/4.0/"),
            row("c", "http://creativecommons.org/licenses/by/4.0/",
                "http://creativecommons.org/licenses/by/4.0/"),
        ])
        self.assertEqual(report["consistent_cc"], 3)
        self.assertEqual({item["consistency"] for item in rows}, {"consistent_cc"})

    def test_separates_missing_unknown_and_conflicting_metadata(self):
        rows, report = audit([
            row("missing", "CC BY 4.0", None),
            row("unknown", "Some licence", "https://example.org/licence"),
            row("conflict", "CC BY 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
        ])
        self.assertEqual(report["missing_url"], 1)
        self.assertEqual(report["unknown_url"], 1)
        self.assertEqual(report["contradictory_label_url"], 1)
        self.assertEqual(rows[2]["label_status"], "label_url_conflict")

    def test_duplicate_source_keys_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate source_key"):
            audit([row("a", "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
                   row("a", "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")])


if __name__ == "__main__":
    unittest.main()
