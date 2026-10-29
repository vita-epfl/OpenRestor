#!/usr/bin/env python3
"""Write the metadata-only ChoraleBricks pilot manifest.

The table is transcribed from the official dataset page. No audio is fetched;
the output remains a provenance candidate until the Zenodo files, checksums and
record-level notice are independently verified.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


OFFICIAL_URL = "https://www.audiolabs-erlangen.de/resources/MIR/2025-ChoraleBricks"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
ZENODO_URL = "https://doi.org/10.5281/zenodo.20849469"

WORKS = (
    ("AN1", "Anonymous: Aus meines Herzens Grunde", 1598, 57),
    ("BA1", "Bach, J. S.: Ich steh' an Deiner Krippe hier", 1736, 45),
    ("CR1", "Crüger, J.: Auf, auf, mein Herz, mit Freuden", 1647, 48),
    ("DR1", "Drese, A.: Jesu, geh voran", 1698, 32),
    ("GE1", "Gesius, B.: Befiehl Du Deine Wege", 1603, 45),
    ("GE2", "Gesius, B.: Du Friedensfürst, Herr Jesu Christ", 1601, 34),
    ("JA1", "Jan, M.: Du großer Schmerzensmann", 1668, 40),
    ("TE1", "Telemann, G. P.: Der lieben Sonne Licht und Pracht", 1730, 59),
    ("VU1", "Vulpuis, M.: Die helle Sonn leucht' jetzt herfür", 1609, 16),
    ("VU2", "Vulpuis, M.: Christus, der ist mein Leben", 1609, 26),
)


def build_rows() -> list[dict]:
    rows = []
    for identifier, title, year, duration in WORKS:
        rows.append({
            "dataset": "choralebricks",
            "source_id": identifier,
            "source_key": f"choralebricks:{identifier}",
            "audio_path": None,
            "metadata": {"title": title, "year": year, "genre": "wind_chorale",
                         "collection": "ChoraleBricks", "content_type": "music",
                         "parts": ["soprano", "alto", "tenor", "bass"]},
            "duration_seconds": duration,
            "original_format": "unknown_until_zenodo_resolution",
            "technical_candidate": False,
            "provenance_candidate": True,
            "redistributable_candidate": False,
            "rights": {
                "license_label": "CC BY 4.0 (dataset website statement)",
                "license_url": LICENSE_URL,
                "evidence_url": OFFICIAL_URL,
                "source_record_url": ZENODO_URL,
                "review_status": "pending",
                "allow_commercial": None,
                "allow_redistribution": None,
                "allow_derivatives": None,
                "attribution": "Stefan Balke, Axel Berndt, and Meinard Müller; ChoraleBricks",
            },
            "notes": "Metadata-only pilot; do not treat as audio or release approval.",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = build_rows()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                       for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} metadata-only ChoraleBricks sources: {args.out}")


if __name__ == "__main__":
    main()
