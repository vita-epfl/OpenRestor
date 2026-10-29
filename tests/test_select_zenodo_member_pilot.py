import unittest

from scripts.select_zenodo_member_pilot import select


def row(key, archive, member, compressed=10):
    return {
        "source_key": key,
        "metadata": {
            "archive_member": member,
            "collection": f"zenodo:1/{archive}",
            "member_compressed_size_bytes": compressed,
            "member_uncompressed_size_bytes": compressed * 2,
        },
        "zenodo": {"archive_key": archive},
    }


class SelectZenodoMemberPilotTests(unittest.TestCase):
    def test_round_robin_covers_archives_and_never_downloads(self):
        rows = [
            row("a1", "masters_stereo.zip", "01 - A.wav"),
            row("a2", "masters_stereo.zip", "02 - B.wav"),
            row("b1", "stems_raw.zip", "01 A/bass.wav"),
            row("b2", "stems_raw.zip", "02 B/bass.wav"),
            row("c1", "example_usage.zip", "song01_raw.wav"),
        ]
        selected, report = select(rows, max_items=3, max_total_compressed_bytes=100)
        self.assertEqual({item["source_key"] for item in selected}, {"a1", "b1", "c1"})
        self.assertEqual(report["selected_rows"], 3)
        self.assertTrue(all(not item["pilot_selection"]["audio_downloaded"] for item in selected))

    def test_budget_defers_large_member(self):
        rows = [row("a1", "masters_stereo.zip", "01 - A.wav", compressed=101)]
        selected, report = select(rows, max_items=1, max_total_compressed_bytes=100)
        self.assertEqual(selected, [])
        self.assertEqual(report["deferred_for_budget"], 1)

    def test_duplicate_source_key_fails(self):
        rows = [row("same", "masters_stereo.zip", "01 - A.wav"),
                row("same", "masters_stereo.zip", "02 - B.wav")]
        with self.assertRaises(ValueError):
            select(rows, max_items=2, max_total_compressed_bytes=100)


if __name__ == "__main__":
    unittest.main()

