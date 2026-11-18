from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

CONFIG_PATH = Path(__file__).resolve().parents[2] / "model_config.json"

with CONFIG_PATH.open("r", encoding="utf-8") as handle:
    MODEL_CONFIG = json.load(handle)

FEATURE_NAMES = tuple(MODEL_CONFIG["feature_names"])
CLASS_LABELS = {int(key): value for key, value in MODEL_CONFIG["classes"].items()}
MODEL_VERSION = str(MODEL_CONFIG["model_version"])

SNAKE_CASE_ALIASES = {
    "Bwd Packet Length Std": "bwd_pkt_len_std",
    "Bwd Packet Length Mean": "bwd_pkt_len_mean",
    "Packet Length Std": "pkt_len_std",
    "Packet Length Variance": "pkt_len_var",
    "Bwd Packet Length Max": "bwd_pkt_len_max",
    "Subflow Bwd Bytes": "subflow_bwd_byts",
    "Avg Bwd Segment Size": "bwd_seg_size_avg",
    "Packet Length Mean": "pkt_len_mean",
    "Average Packet Size": "pkt_size_avg",
    "Max Packet Length": "pkt_len_max",
    "Total Length of Bwd Packets": "totlen_bwd_pkts",
    "Fwd IAT Std": "fwd_iat_std",
    "Total Fwd Packets": "tot_fwd_pkts",
    "Total Backward Packets": "tot_bwd_pkts",
    "Bwd Packets/s": "bwd_pkts_s",
    "Idle Min": "idle_min",
    "Fwd IAT Mean": "fwd_iat_mean",
    "Subflow Fwd Packets": "subflow_fwd_pkts",
    "Total Length of Fwd Packets": "totlen_fwd_pkts",
    "Fwd IAT Max": "fwd_iat_max"
}

NORMALIZED_ALIASES = {
    canonical.casefold(): canonical for canonical in FEATURE_NAMES
}
NORMALIZED_ALIASES.update({alias.casefold(): canonical for canonical, alias in SNAKE_CASE_ALIASES.items()})


class FeatureValidationError(ValueError):
    pass


def normalize_feature_row(features: Mapping[str, Any]) -> list[float]:
    if not isinstance(features, Mapping):
        raise FeatureValidationError("Feature input harus berupa mapping/dictionary.")

    values: dict[str, Any] = {}
    for raw_key, raw_value in features.items():
        key = str(raw_key).strip().casefold()
        canonical = NORMALIZED_ALIASES.get(key)
        if canonical is None:
            continue
        if canonical in values and values[canonical] != raw_value:
            raise FeatureValidationError(f"Dua alias memiliki nilai berbeda untuk fitur '{canonical}'.")
        values[canonical] = raw_value

    missing = [name for name in FEATURE_NAMES if name not in values]
    if missing:
        joined = ", ".join(missing)
        raise FeatureValidationError(f"Fitur model belum lengkap. Fitur yang hilang: {joined}")

    ordered: list[float] = []
    for name in FEATURE_NAMES:
        value = values[name]
        if isinstance(value, bool) or value is None:
            raise FeatureValidationError(f"Nilai fitur '{name}' harus berupa angka finite.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise FeatureValidationError(f"Nilai fitur '{name}' bukan angka yang valid.") from exc
        if not __import__("math").isfinite(number):
            raise FeatureValidationError(f"Nilai fitur '{name}' harus finite, bukan NaN atau infinity.")
        if number < 0:
            raise FeatureValidationError(f"Nilai fitur '{name}' tidak boleh negatif.")
        ordered.append(number)

    return ordered
