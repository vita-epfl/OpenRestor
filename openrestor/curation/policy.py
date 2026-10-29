"""Conservative, explainable clean-music triage across representative segments."""

from __future__ import annotations

import math
from statistics import median


POLICY_VERSION = "clean-music-v1"
DEFAULTS = {
    "auto_accept_score": .78,
    "min_segment_pq": 6.6,
    "min_segment_pc": 4.5,
    "min_segment_cu": 6.0,
    "min_ast_music": .42,
    "max_ast_speech": .30,
    "min_clap_music_margin": .015,
    "max_clipped_ratio": .005,
    "min_bandwidth_hz_at_44100": 11000,
    "silence_rms_dbfs": -45,
    "silence_ratio": .98,
    "strong_nonmusic_ast_music": .25,
    "strong_nonmusic_ast_speech": .50,
    "strong_nonmusic_clap_margin": .025,
}

POLICY_V2_VERSION = "clean-music-v2"
V2_DEFAULTS = {
    "v2_auto_accept_score": .76,
    "v2_auto_reject_score": .28,
    "v2_max_severe_clipped_ratio": .02,
    "v2_min_bandwidth_hz_at_44100": 7000,
    "v2_max_noise_floor_db": -18.0,
    "v2_max_frame_rms_iqr_db": 28.0,
}
POLICY_V21_VERSION = "clean-music-v2.1"
V21_DEFAULTS = {
    # Conservative gates selected before the independent validation labels exist.
    "v21_auto_accept_score": .82,
    "v21_min_pq": 7.0,
    "v21_min_clap_degraded_margin": .08,
    "v21_max_hiss_proxy": .25,
    "v21_max_spectral_flatness": .35,
    "v21_enable_metadata_guard": 1.0,
    "v21_enable_acoustic_guard": 1.0,
}


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_segment(segment: dict, metadata: dict, sample_rate: int, config: dict | None = None) -> dict:
    cfg = {**DEFAULTS, **(config or {})}
    acoustic = segment.get("acoustic") or {}
    aesthetics = segment.get("aesthetics") or {}
    ast = (segment.get("ast") or {}).get("interest_labels") or {}
    clap = (segment.get("clap") or {}).get("group_scores") or {}
    pq, pc, ce, cu = (_number(aesthetics.get(axis)) for axis in ("PQ", "PC", "CE", "CU"))
    music, speech = _number(ast.get("Music")), _number(ast.get("Speech"))
    required_clap = ("produced_music", "legitimate_electronic_music", "degraded_music",
                     "non_music", "rudimentary_synthetic")
    clap_values = {key: _number(clap.get(key)) for key in required_clap}
    required = {"PQ": pq, "PC": pc, "CE": ce, "CU": cu, "AST Music": music,
                "AST Speech": speech, **{f"CLAP {key}": value for key, value in clap_values.items()}}
    missing = [key for key, value in required.items() if value is None]
    reasons = []
    clip_ratio = _number(acoustic.get("clipped_sample_ratio_channels"))
    near_silent = _number(acoustic.get("near_silent_sample_ratio"))
    rms = _number(acoustic.get("rms_dbfs"))
    bandwidth = _number(acoustic.get("bandwidth_hz"))
    cues = metadata.get("metadata_cues") or {}
    if near_silent is not None and rms is not None and near_silent >= cfg["silence_ratio"] and rms <= cfg["silence_rms_dbfs"]:
        return {"segment_id": segment["segment_id"], "clean_score": 0.0,
                "decision": "auto_reject", "reasons": ["quasi_silence_consensus"],
                "components": {}, "model_signals_complete": not missing}
    if missing:
        return {"segment_id": segment["segment_id"], "clean_score": None,
                "decision": "manual_review", "reasons": ["missing_model_signals:" + ",".join(missing)],
                "components": {}, "model_signals_complete": False}
    positive_music = max(clap_values["produced_music"], clap_values["legitimate_electronic_music"])
    nonmusic_margin = positive_music - clap_values["non_music"]
    rudimentary_margin = positive_music - clap_values["rudimentary_synthetic"]
    degraded_margin = positive_music - clap_values["degraded_music"]
    nonmusic_evidence = (music <= cfg["strong_nonmusic_ast_music"]
                         and nonmusic_margin <= -cfg["strong_nonmusic_clap_margin"]
                         and (speech >= cfg["strong_nonmusic_ast_speech"]
                              or cues.get("speech_cues") or cues.get("sound_effect_cues")))
    if nonmusic_evidence:
        return {"segment_id": segment["segment_id"], "clean_score": 0.0,
                "decision": "auto_reject", "reasons": ["ast_clap_metadata_nonmusic_consensus"],
                "components": {"ast_music": music, "ast_speech": speech,
                               "clap_music_minus_nonmusic": nonmusic_margin},
                "model_signals_complete": True}
    bandwidth_score = 1.0 if bandwidth is None or sample_rate < 44100 else _clamp((bandwidth - 7000) / 10000)
    quality = (.28 * _clamp((pq - 5) / 3) + .24 * _clamp((pc - 3) / 4)
               + .18 * _clamp((ce - 4) / 4) + .18 * _clamp((cu - 5) / 3)
               + .12 * bandwidth_score)
    content = (.50 * _clamp((music - .25) / .6) + .16 * _clamp(1 - speech / .4)
               + .17 * _clamp((nonmusic_margin + .03) / .18)
               + .17 * _clamp((rudimentary_margin + .03) / .18))
    score = round(.55 * quality + .45 * content, 4)
    if pq < cfg["min_segment_pq"]:
        reasons.append("low_audiobox_pq")
    if pc < cfg["min_segment_pc"]:
        reasons.append("low_production_complexity")
    if cu < cfg["min_segment_cu"]:
        reasons.append("low_audiobox_cu")
    if music < cfg["min_ast_music"]:
        reasons.append("weak_ast_music")
    if speech > cfg["max_ast_speech"]:
        reasons.append("ast_speech_signal")
    if min(nonmusic_margin, rudimentary_margin) < cfg["min_clap_music_margin"]:
        reasons.append("clap_music_contrast_weak")
    if clip_ratio is not None and clip_ratio > cfg["max_clipped_ratio"]:
        reasons.append("clipping_review")
    if bandwidth is not None and sample_rate >= 44100 and bandwidth < cfg["min_bandwidth_hz_at_44100"]:
        reasons.append("bandwidth_review")
    if cues.get("synthetic_render_cues") or cues.get("sound_effect_cues") or cues.get("speech_cues"):
        reasons.append("metadata_content_review")
    if degraded_margin < -.05 and (pq < 7 or ce < 5.5):
        reasons.append("clap_degraded_capture_review")
    if score < cfg["auto_accept_score"]:
        reasons.append("clean_score_below_auto_accept")
    return {"segment_id": segment["segment_id"], "clean_score": score,
            "decision": "manual_review" if reasons else "auto_accept",
            "reasons": reasons or ["multi_signal_clean_agreement"],
            "components": {"quality": round(quality, 4), "content": round(content, 4),
                           "ast_music": music, "ast_speech": speech,
                           "clap_music_minus_nonmusic": round(nonmusic_margin, 4),
                           "clap_music_minus_rudimentary": round(rudimentary_margin, 4),
                           "clap_music_minus_degraded": round(degraded_margin, 4)},
            "model_signals_complete": True}


def score_source(record: dict, config: dict | None = None) -> dict:
    """Use all sampled passages; one good passage never certifies a source."""
    segments = record.get("segments") or []
    if not segments:
        raise ValueError(f"source has no segments: {record.get('source_key')}")
    sample_rate = int(record.get("sample_rate") or 0)
    scored = [score_segment(segment, record.get("metadata") or {}, sample_rate, config)
              for segment in segments]
    votes = [row["decision"] for row in scored]
    if all(vote == "auto_accept" for vote in votes):
        decision = "auto_accept"
    elif sum(vote == "auto_reject" for vote in votes) > len(votes) / 2:
        decision = "auto_reject"
    else:
        decision = "manual_review"
    values = [row["clean_score"] for row in scored if row["clean_score"] is not None]
    reasons = sorted({reason for row in scored for reason in row["reasons"]
                      if reason != "multi_signal_clean_agreement"})
    if len(set(votes)) > 1:
        reasons.append("passage_disagreement")
    if len(segments) < 2 and decision == "auto_accept":
        decision = "manual_review"
        reasons.append("single_passage_not_source_validation")
    return {"source_key": record["source_key"], "dataset": record["dataset"],
            "source_id": record["source_id"], "policy_version": POLICY_VERSION,
            "clean_score": round(min(values), 4) if values else None,
            "decision": decision, "reasons": reasons or ["all_sampled_passages_agree"],
            "segments": scored, "rights": record.get("rights") or {},
            "metadata": record.get("metadata") or {}}


def _v2_quality_risks(acoustic: dict, sample_rate: int, cfg: dict) -> tuple[list[str], list[str]]:
    """Return hard risks and review-only acoustic risks.

    These are deliberately proxies. They block automatic acceptance when clearly
    unsafe, but do not declare a musical aesthetic to be defective.
    """
    hard, review = [], []
    clipped = _number(acoustic.get("clipped_sample_ratio_channels"))
    bandwidth = _number(acoustic.get("bandwidth_hz"))
    noise_floor = _number(acoustic.get("noise_floor_db"))
    rms_iqr = _number(acoustic.get("frame_rms_iqr_db"))
    near_silent = _number(acoustic.get("near_silent_sample_ratio"))
    rms = _number(acoustic.get("rms_dbfs"))
    if (near_silent is not None and rms is not None and near_silent >= .995 and rms <= -45):
        hard.append("quasi_silence_consensus")
    if clipped is not None:
        if clipped > cfg["v2_max_severe_clipped_ratio"]:
            hard.append("severe_clipping")
        elif clipped > DEFAULTS["max_clipped_ratio"]:
            review.append("clipping_review")
    if bandwidth is not None and sample_rate >= 44100:
        if bandwidth < cfg["v2_min_bandwidth_hz_at_44100"]:
            hard.append("severe_bandwidth_cutoff")
        elif bandwidth < DEFAULTS["min_bandwidth_hz_at_44100"]:
            review.append("bandwidth_review")
    # Noise-floor and frame-level variability overlap strongly between reviewed
    # positives and negatives in the current calibration. Keep them observable
    # in the feature cache, but do not gate acceptance until more labels exist.
    return hard, review


def score_segment_v2(segment: dict, metadata: dict, sample_rate: int,
                     config: dict | None = None) -> dict:
    """Targeted v2 policy: soft model warnings no longer force review by themselves.

    Content/provenance cues and clear acoustic failures remain independent gates;
    electronic, ambient and live music are not rejected by metadata alone.
    """
    cfg = {**V2_DEFAULTS, **(config or {})}
    base = score_segment(segment, metadata, sample_rate, config)
    acoustic = segment.get("acoustic") or {}
    cues = metadata.get("metadata_cues") or {}
    hard, quality_review = _v2_quality_risks(acoustic, sample_rate, cfg)
    reasons = [reason for reason in base.get("reasons", [])
               if reason not in {"clean_score_below_auto_accept", "low_audiobox_pq",
                                 "low_production_complexity", "low_audiobox_cu",
                                 "weak_ast_music", "ast_speech_signal", "clap_music_contrast_weak",
                                 "multi_signal_clean_agreement"}]
    reasons.extend(quality_review)
    if cues.get("synthetic_render_cues"):
        reasons.append("metadata_synthetic_render_review")
    if cues.get("production_context_cues"):
        reasons.append("metadata_production_context_review")
    if cues.get("sound_effect_cues") or cues.get("speech_cues"):
        reasons.append("metadata_content_review")
    hard.extend(reason for reason in base.get("reasons", [])
                if reason in {"ast_clap_metadata_nonmusic_consensus", "quasi_silence_consensus"})
    if base.get("clean_score") is not None and base["clean_score"] <= cfg["v2_auto_reject_score"]:
        hard.append("very_low_clean_score")
    if base.get("clean_score") is None:
        decision = "manual_review"
        reasons.append("missing_model_signals")
    elif hard:
        decision = "auto_reject"
    elif (base["clean_score"] >= cfg["v2_auto_accept_score"] and not reasons):
        decision = "auto_accept"
    else:
        decision = "manual_review"
    components = dict(base.get("components") or {})
    components.update({"v2_hard_risks": hard, "v2_quality_review": quality_review})
    return {"segment_id": segment["segment_id"], "clean_score": base.get("clean_score"),
            "decision": decision, "reasons": sorted(set(reasons)) or ["v2_multisignal_agreement"],
            "components": components, "model_signals_complete": base.get("model_signals_complete", False)}


def score_source_v2(record: dict, config: dict | None = None) -> dict:
    """Aggregate v2 by source; one good passage never certifies a source."""
    segments = record.get("segments") or []
    if not segments:
        raise ValueError(f"source has no segments: {record.get('source_key')}")
    cfg = {**V2_DEFAULTS, **(config or {})}
    rate = int(record.get("sample_rate") or 0)
    scored = [score_segment_v2(part, record.get("metadata") or {}, rate, cfg) for part in segments]
    votes = [part["decision"] for part in scored]
    if all(vote == "auto_accept" for vote in votes):
        decision = "auto_accept"
    elif sum(vote == "auto_reject" for vote in votes) > len(votes) / 2:
        decision = "auto_reject"
    else:
        decision = "manual_review"
    values = [part["clean_score"] for part in scored if part.get("clean_score") is not None]
    reasons = sorted({reason for part in scored for reason in part.get("reasons", [])
                      if reason != "v2_multisignal_agreement"})
    if len(set(votes)) > 1:
        reasons.append("passage_disagreement")
    return {"source_key": record["source_key"], "dataset": record["dataset"],
            "source_id": record["source_id"], "policy_version": POLICY_V2_VERSION,
            "clean_score": round(min(values), 4) if values else None,
            "decision": decision, "reasons": sorted(set(reasons)) or ["v2_multisignal_agreement"],
            "segments": scored, "rights": record.get("rights") or {},
            "metadata": record.get("metadata") or {}}


def score_segment_v21(segment: dict, metadata: dict, sample_rate: int,
                      config: dict | None = None) -> dict:
    """Conservative acceptance layer on top of v2.

    The additional guards only prevent automatic acceptance. They do not reject
    a source by themselves, so intentional lo-fi, electronic and live material
    remains available for human review. Segment-level acceptance is explicit and
    can be exported without claiming that the whole source is clean.
    """
    cfg = {**V2_DEFAULTS, **V21_DEFAULTS, **(config or {})}
    base = score_segment_v2(segment, metadata, sample_rate, cfg)
    reasons = [reason for reason in base.get("reasons", [])
               if reason != "v2_multisignal_agreement"]
    guards = []
    acoustic = segment.get("acoustic") or {}
    aesthetics = segment.get("aesthetics") or {}
    clap = (segment.get("clap") or {}).get("group_scores") or {}
    pq = _number(aesthetics.get("PQ"))
    hiss = _number(acoustic.get("hiss_proxy"))
    flatness = _number(acoustic.get("spectral_flatness"))
    positive_music = max(_number(clap.get("produced_music")) or -1,
                         _number(clap.get("legitimate_electronic_music")) or -1)
    degraded = _number(clap.get("degraded_music"))
    if cfg["v21_enable_acoustic_guard"] > .5 and pq is not None and pq < cfg["v21_min_pq"]:
        guards.append("v21_low_pq_guard")
    if cfg["v21_enable_acoustic_guard"] > .5 and positive_music >= 0 and degraded is not None and positive_music - degraded < cfg["v21_min_clap_degraded_margin"]:
        guards.append("v21_clap_degraded_capture_guard")
    if cfg["v21_enable_acoustic_guard"] > .5 and hiss is not None and hiss > cfg["v21_max_hiss_proxy"]:
        guards.append("v21_hiss_guard")
    if cfg["v21_enable_acoustic_guard"] > .5 and flatness is not None and flatness > cfg["v21_max_spectral_flatness"]:
        guards.append("v21_noise_like_spectrum_guard")
    cues = metadata.get("metadata_cues") or {}
    if cfg["v21_enable_metadata_guard"] > .5:
        if cues.get("synthetic_render_cues") or cues.get("stylized_content_cues"):
            guards.append("v21_stylized_or_synthetic_metadata_guard")
        if cues.get("production_context_cues"):
            guards.append("v21_production_context_guard")
    reasons.extend(guards)
    if base.get("decision") == "auto_reject":
        decision = "auto_reject"
    elif base.get("clean_score") is None:
        decision = "manual_review"
    elif base.get("clean_score") >= cfg["v21_auto_accept_score"] and not reasons:
        decision = "auto_accept"
    else:
        decision = "manual_review"
    components = dict(base.get("components") or {})
    components["v21_acceptance_guards"] = guards
    return {"segment_id": segment["segment_id"], "clean_score": base.get("clean_score"),
            "decision": decision, "reasons": sorted(set(reasons)) or ["v21_multisignal_agreement"],
            "components": components,
            "model_signals_complete": base.get("model_signals_complete", False)}


def score_source_v21(record: dict, config: dict | None = None) -> dict:
    """Score all passages and expose accepted segments without certifying mixed sources."""
    segments = record.get("segments") or []
    if not segments:
        raise ValueError(f"source has no segments: {record.get('source_key')}")
    cfg = {**V2_DEFAULTS, **V21_DEFAULTS, **(config or {})}
    rate = int(record.get("sample_rate") or 0)
    scored = [score_segment_v21(part, record.get("metadata") or {}, rate, cfg) for part in segments]
    votes = [part["decision"] for part in scored]
    if all(vote == "auto_accept" for vote in votes):
        decision = "auto_accept"
    elif sum(vote == "auto_reject" for vote in votes) > len(votes) / 2:
        decision = "auto_reject"
    else:
        decision = "manual_review"
    values = [part["clean_score"] for part in scored if part.get("clean_score") is not None]
    reasons = sorted({reason for part in scored for reason in part.get("reasons", [])
                      if reason != "v21_multisignal_agreement"})
    if len(set(votes)) > 1:
        reasons.append("passage_disagreement")
    return {"source_key": record["source_key"], "dataset": record["dataset"],
            "source_id": record["source_id"], "policy_version": POLICY_V21_VERSION,
            "clean_score": round(min(values), 4) if values else None,
            "decision": decision, "reasons": sorted(set(reasons)) or ["v21_multisignal_agreement"],
            "segments": scored,
            "accepted_segment_ids": [part["segment_id"] for part in scored if part["decision"] == "auto_accept"],
            "rights": record.get("rights") or {}, "metadata": record.get("metadata") or {}}
