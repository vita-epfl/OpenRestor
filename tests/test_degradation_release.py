from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np

from openrestore.degradations.core import sha256_file, write_audio, write_jsonl
from openrestore.degradations.release import (
    create_partition_plan,
    merge_release,
    render_partition,
    validate_clean_release,
    validate_release,
)

SAMPLE_RATE = 44_100


class ProductionReleaseTests(TestCase):
    def _write_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        clean_root = root / "clean"
        rows = []
        audio = np.zeros((SAMPLE_RATE * 30, 2), dtype=np.float32)
        for clean_id in ("source-c", "source-a", "source-b"):
            relative = Path("train") / "sonicmaster_clean" / f"{clean_id}.wav"
            path = clean_root / relative
            write_audio(path, audio)
            rows.append(
                {
                    "id": clean_id,
                    "clean_path": relative.as_posix(),
                    "source_id": clean_id,
                    "dataset": "sonicmaster_clean",
                    "split": "train",
                    "duration_seconds": 30,
                    "sample_rate": SAMPLE_RATE,
                    "channels": 2,
                    "audio_sha256": sha256_file(path),
                }
            )
        manifest = root / "clean.jsonl"
        write_jsonl(manifest, rows)
        recipe = root / "recipes.yaml"
        recipe.write_text(
            """version: test
recipes:
  - id: single_gain_test
    severity: test
    operations:
      - primitive: gain_level
        variant: low_volume
        parameters: {gain_db: -3}
""",
            encoding="utf-8",
        )
        split = root / "split.jsonl"
        write_jsonl(split, [{"source_id": row["source_id"], "split": "train"} for row in rows])
        assets = root / "assets.sha256"
        assets.write_text("test-assets\n", encoding="utf-8")
        release_root = root / "private-release"
        config = root / "release.yaml"
        config.write_text(
            f"""release_id: miniature-private-v0.1
private_output_root: {release_root}
expected_degraded_examples: 3
seed: 20260714
recipe_config: {recipe}
asset_checksums: {assets}
frozen_split_manifest: {split}
frozen_split_sha256: {sha256_file(split)}
clips_per_source: 1
clip_seconds: 30
sources_per_partition: 2
shard_size: 2
partitions:
  - {{dataset: sonicmaster_clean, split: train, expected_sources: 3}}
""",
            encoding="utf-8",
        )
        return clean_root, manifest, config, release_root

    def test_partition_release_resume_failure_and_merge(self) -> None:
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            clean_root, manifest, config, release_root = self._write_fixture(tmp)
            self.assertEqual(validate_clean_release(manifest, clean_root, config), {"sonicmaster_clean/train": 3})
            plan_path = tmp / "plan.json"
            first_plan = create_partition_plan(manifest, config, plan_path, clean_root)
            second_plan = create_partition_plan(manifest, config, tmp / "plan-repeat.json", clean_root)
            self.assertEqual(first_plan, second_plan)
            self.assertEqual([item["clean_ids"] for item in first_plan["partitions"]], [["source-a", "source-b"], ["source-c"]])

            first = first_plan["partitions"][0]["id"]
            second = first_plan["partitions"][1]["id"]
            work_root = tmp / "work"
            first_receipt = render_partition(plan_path, first, manifest, clean_root, config, work_root, release_root)
            self.assertEqual(first_receipt["status"], "complete")
            self.assertFalse((work_root / first / "wav").exists())
            self.assertEqual(render_partition(plan_path, first, manifest, clean_root, config, work_root, release_root), first_receipt)

            with self.assertRaisesRegex(ValueError, "Missing or invalid partition receipt"):
                merge_release(plan_path, release_root, release_root / "index.jsonl", release_root / "receipt.json")

            changed = clean_root / "train" / "sonicmaster_clean" / "source-c.wav"
            write_audio(changed, np.ones((SAMPLE_RATE * 30, 2), dtype=np.float32) * 0.1)
            with self.assertRaisesRegex(ValueError, "Frozen clean audio"):
                render_partition(plan_path, second, manifest, clean_root, config, work_root, release_root)
            failed = json.loads((release_root / "receipts" / f"{second}.json").read_text())
            self.assertEqual(failed["status"], "failed")

            write_audio(changed, np.zeros((SAMPLE_RATE * 30, 2), dtype=np.float32))
            render_partition(plan_path, second, manifest, clean_root, config, work_root, release_root)
            receipt = merge_release(plan_path, release_root, release_root / "index.jsonl", release_root / "receipt.json")
            self.assertEqual(receipt["item_count"], 3)
            self.assertEqual(validate_release(plan_path, release_root, release_root / "receipt.json"), receipt)
