import unittest

from scripts.resolve_choralebricks_zenodo import summarize


class ChoraleBricksZenodoTests(unittest.TestCase):
    def test_summarize_keeps_archive_metadata_and_fails_closed(self):
        row = summarize({
            "id": 20849469, "conceptrecid": "15081740", "doi": "10.5281/zenodo.20849469",
            "submitted": True, "status": "published",
            "metadata": {"title": "ChoraleBricks", "version": "1.1.0",
                         "access_right": "open", "license": {"id": "cc-by-4.0"},
                         "creators": [{"name": "Balke, Stefan"}]},
            "files": [{"key": "01_AudioAndAnnotations.zip", "size": 123,
                       "checksum": "md5:abc", "links": {"self": "https://example/file"}}],
        })
        self.assertEqual(row["record_id"], 20849469)
        self.assertEqual(row["license_id"], "cc-by-4.0")
        self.assertEqual(row["files"][0]["checksum"], "md5:abc")
        self.assertTrue(row["provenance_candidate"])
        self.assertFalse(row["technical_candidate"])
        self.assertFalse(row["redistributable_candidate"])
        self.assertFalse(row["audio_downloaded"])


if __name__ == "__main__":
    unittest.main()
