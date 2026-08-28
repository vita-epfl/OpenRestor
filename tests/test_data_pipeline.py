from __future__ import annotations

import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from openrestore.data.core import read_jsonl, sha256_file
from openrestore.data.pipeline import (
    combine_and_split,
    ingest,
    iter_shard,
    segment,
    source_statistics,
    verify_checksums,
    write_shards,
    write_statistics,
)


def _write_tone(path: Path, seconds: int = 31) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = (b"\x00\x10\x00\x10") * (44_100 * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(frames)


def _config(dataset: str, root: Path, fixed_split: str) -> dict[str, str | int]:
    return {
        "dataset": dataset,
        "source_root": str(root),
        "role": "public-transfer-evaluation" if fixed_split == "transfer" else "main-track-training-and-public-evaluation",
        "fixed_split": fixed_split,
        "min_source_seconds": 30,
        "license": "test",
        "redistribution": "test",
        "quality_notes": "test",
    }


class PhaseOnePipelineTests(TestCase):
    def test_pipeline_is_deterministic_and_transfer_separated(self) -> None:
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            sonic_root = tmp_path / "sonic" / "clean"
            sdd_root = tmp_path / "sdd"
            musdb_root = tmp_path / "musdb"
            for number in range(12):
                _write_tone(sonic_root / f"track-{number}.wav")
            _write_tone(sdd_root / "captioned-track.wav")
            _write_tone(musdb_root / "mixture.wav")

            sonic_index = tmp_path / "sonic.jsonl"
            sdd_index = tmp_path / "sdd.jsonl"
            musdb_index = tmp_path / "musdb.jsonl"
            ingest(_config("sonicmaster_clean", sonic_root, "unassigned"), sonic_index)
            ingest(_config("sdd", sdd_root, "transfer"), sdd_index)
            ingest(_config("musdb18_hq", musdb_root, "transfer"), musdb_index)

            source_manifest = tmp_path / "sources.jsonl"
            rows = combine_and_split([sonic_index, sdd_index, musdb_index], source_manifest, 42, 0.7, 0.15)
            self.assertTrue(all(row["split"] == "transfer" for row in rows if row["dataset"] in {"sdd", "musdb18_hq"}))
            self.assertLessEqual({row["split"] for row in rows if row["dataset"] == "sonicmaster_clean"}, {"train", "validation", "test"})
            source_report = source_statistics(rows)
            self.assertEqual(source_report["sources"], len(rows))
            self.assertEqual(source_report["by_dataset"]["sonicmaster_clean"], 12)
            self.assertEqual(source_report["maximum_non_overlapping_30s_clips"], len(rows))

            audio_root = tmp_path / "clips"
            manifest = tmp_path / "index.jsonl"
            checksums = tmp_path / "checksums.jsonl"
            clips = segment(rows, audio_root, manifest, checksums, seed=42, clips_per_source=1, normalize=False, min_rms=0.003)
            self.assertEqual(len(clips), len(rows))
            self.assertTrue(all(row["duration_seconds"] == 30 for row in clips))
            self.assertEqual(verify_checksums(audio_root, checksums), [])

            shards = write_shards(audio_root, clips, tmp_path / "shards", shard_size=5)
            self.assertEqual(len(shards), 3)
            self.assertEqual(sum(1 for shard in shards for _ in iter_shard(shard)), len(clips))

            report_path = tmp_path / "statistics.json"
            report = write_statistics(manifest, report_path)
            self.assertEqual(report["items"], len(clips))
            self.assertEqual(read_jsonl(manifest)[0]["audio_sha256"], sha256_file(audio_root / clips[0]["clean_path"]))
