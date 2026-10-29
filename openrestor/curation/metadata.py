"""Cross-dataset metadata hints; never a truth label or hard rejection.

Patterns mirror the existing IAMD pilot cues. In particular, electronic,
ambient, experimental, live and chiptune are not automatic exclusions.
"""

from __future__ import annotations

import re


PATTERNS = {
    "synthetic_render_cues": r"\b(?:midi|soundfont|sf2|tracker|mod(?:ule)? file|sequence(?:d|r|s)?|gm[ -]?render|test tone|sine[ -]?wave|oscillator demo)\b",
    "production_context_cues": r"\b(?:type beat|ai[ -]?generated|generative|beat remake)\b",
    "real_recording_cues": r"\b(?:live recording|recorded live|live concert|live performance|field recordings?|recorded at|taped at|microphone|mic'd|studio session)\b",
    "speech_cues": r"\b(?:spoken word|podcast|interview|audiobook|radio talk|speech)\b",
    "sound_effect_cues": r"\b(?:sound effects?|sfx|foley|test tone|field recordings?|white noise)\b",
    "capture_context_cues": r"\b(?:internal microphone|built-in microphone|recorded live|live performance|audience recording|stage banter|bootleg|rehearsal)\b",
    "stylized_content_cues": r"\b(?:8[ -]?bit|chiptune|game soundtrack|oscillator patches?|soundfont|tracker|vgm)\b",
}


def asset_creator(dataset: str | None, archive_key: str | None = None,
                  member_name: str | None = None) -> str | None:
    """Return an interpreter/group only when the path exposes one explicitly.

    Dataset authors are attribution metadata, not necessarily performers.  At
    present Guitar-TECHS is the only supported Zenodo source whose member path
    names a performer (P1/P2/P3); all other cases deliberately remain unknown
    instead of assigning the record creators to every audio asset.
    """
    if str(dataset or "") != "guitar_techs":
        return None
    text = f"{archive_key or ''}/{member_name or ''}"
    match = re.search(r"(?:^|[/_])(P[1-3])(?:[/_.-]|$)", text, re.IGNORECASE)
    return f"Guitar-TECHS {match.group(1).upper()}" if match else None


def asset_role(dataset: str | None, archive_key: str | None = None,
               member_name: str | None = None) -> str | None:
    """Classify an archive member's production role from its path only.

    This is a selection hint, not a content or rights label. An isolated stem
    can be perfectly lossless while not being a complete music reference.
    """
    archive = str(archive_key or "").lower()
    if "masters_stereo" in archive:
        return "full_mix_stereo_master"
    if "masters_7.1.4" in archive:
        return "full_mix_immersive_master"
    if "example_usage" in archive:
        return "full_mix_example"
    if "stems_raw" in archive:
        return "isolated_stem_raw"
    if "stems_mixed_dry" in archive:
        return "isolated_stem_mixed_dry"
    if "stems_mixed" in archive:
        return "isolated_stem_mixed"
    return None


def metadata_cues(metadata: dict) -> dict[str, list[str]]:
    fields = ("title", "description", "subject", "collection", "creator", "filename", "tags")
    text = " ; ".join(str(value) for field in fields
                      if (value := metadata.get(field)) not in (None, ""))
    return {name: sorted({match.group(0).lower() for match in re.finditer(pattern, text, re.I)})
            for name, pattern in PATTERNS.items()}
