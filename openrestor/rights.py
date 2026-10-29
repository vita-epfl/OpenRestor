"""Fail-closed, per-media redistribution decisions for release candidates.

The registry is private. A Creative Commons label describes candidate permissions,
not provenance approval or permission to publish the OpenRestor software.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

PROFILES = ("commercial_compatible", "academic_noncommercial")
REQUIRED = {
    "media_key", "dataset", "source_id", "license_label", "license_url",
    "attribution", "evidence_url", "evidence_date", "review_status",
    "allow_commercial", "allow_redistribution", "allow_derivatives", "share_alike",
}


def cc_terms(url: str | None) -> dict[str, Any]:
    """Parse only official, versioned CC URLs; other terms remain unknown."""
    result = {"license_label": None, "allow_commercial": None,
              "allow_redistribution": None, "allow_derivatives": None,
              "share_alike": None}
    if not url:
        return result
    match = re.fullmatch(
        r"https?://creativecommons\.org/licenses/(by(?:-nc)?(?:-nd|-sa)?)/(\d+\.\d+)/?",
        url.strip(), re.IGNORECASE,
    )
    if match:
        code, version = match.group(1).lower(), match.group(2)
        result.update(license_label=f"CC {code.upper()} {version}",
                      allow_commercial="nc" not in code,
                      allow_redistribution=True, allow_derivatives="nd" not in code,
                      share_alike="sa" in code)
    elif re.fullmatch(r"https?://creativecommons\.org/publicdomain/zero/1\.0/?",
                       url.strip(), re.IGNORECASE):
        result.update(license_label="CC0 1.0", allow_commercial=True,
                      allow_redistribution=True, allow_derivatives=True, share_alike=False)
    return result


def validate_record(record: dict[str, Any]) -> None:
    missing = REQUIRED - record.keys()
    if missing:
        raise ValueError(f"Rights record missing fields: {sorted(missing)}")
    if not record["media_key"] or not record["dataset"] or not record["source_id"]:
        raise ValueError("Rights record needs a media_key, dataset and source_id")
    if record["review_status"] not in {"pending", "approved", "rejected"}:
        raise ValueError("Invalid review_status")
    for field in ("allow_commercial", "allow_redistribution", "allow_derivatives", "share_alike"):
        if record[field] is not True and record[field] is not False and record[field] is not None:
            raise ValueError(f"{field} must be true, false or null")
    if record["review_status"] == "approved":
        if not all(record.get(field) for field in
                   ("license_label", "attribution", "evidence_url", "evidence_date", "reviewer")):
            raise ValueError("Approved media require exact licence, credit, dated evidence and reviewer")
        if record["license_label"] != "Public Domain" and not record.get("license_url"):
            raise ValueError("Approved licensed media require the exact licence URL")
        claimed = cc_terms(record.get("license_url"))
        if claimed["license_label"] is not None:
            for field in ("license_label", "allow_commercial", "allow_redistribution",
                          "allow_derivatives", "share_alike"):
                if record[field] != claimed[field]:
                    raise ValueError(f"Approved CC record contradicts its licence URL: {field}")


def pack_family(record: dict[str, Any], profile: str) -> str | None:
    """Return base or a distinct SA family, never a silent permission guess."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown rights profile: {profile}")
    validate_record(record)
    # A licence and permission flags do not prove that this exact asset has
    # been provenance-reviewed.  Keep the publication pack fail-closed when
    # the explicit asset-level approval is absent.
    if record.get("provenance_approved") is not True:
        return None
    if record.get("redistribution_approved") is not True:
        return None
    if record["review_status"] != "approved":
        return None
    if record["allow_redistribution"] is not True or record["allow_derivatives"] is not True:
        return None
    commercial = record["allow_commercial"]
    if commercial is None or (profile == "commercial_compatible" and commercial is not True):
        return None
    if record["share_alike"] is None:
        return None
    if record["share_alike"]:
        # Separate by exact SA licence URL, including version/jurisdiction.
        return "sa:" + str(record["license_url"])
    return "base" if commercial else "nc_extension"


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            validate_record(row)
            key = str(row["media_key"])
            if key in records:
                raise ValueError(f"Duplicate rights key: {key}")
            records[key] = row
    return records


def public_summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate only; never expose blocked IDs, titles, paths or evidence URLs."""
    rows = list(records)
    by_dataset = Counter(str(row["dataset"]) for row in rows)
    approved = Counter(str(row["dataset"]) for row in rows if row["review_status"] == "approved")
    profiles = {}
    families = {}
    for profile in PROFILES:
        counts: Counter = Counter()
        family_counts: Counter = Counter()
        for row in rows:
            family = pack_family(row, profile)
            if family is not None:
                counts[str(row["dataset"])] += 1
                family_counts[family] += 1
        profiles[profile] = dict(sorted(counts.items()))
        families[profile] = dict(sorted(family_counts.items()))
    return {"total_media": len(rows), "counts_by_dataset": dict(sorted(by_dataset.items())),
            "approved_by_dataset": dict(sorted(approved.items())),
            "profiles": profiles, "profile_families": families,
            "note": "Counts are not permission to download; software and release approval are separate."}


def media_key(dataset: str, source_id: str) -> str:
    return f"{dataset}:{source_id}"
