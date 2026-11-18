from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .artifacts import ARTIFACTS, MODEL_DIR, verify_artifact
from .loader import ModelAssetsMissing, ModelCompatibilityError, load_model_assets
from .schema import CLASS_LABELS, FEATURE_NAMES, MODEL_VERSION, normalize_feature_row


class PretrainedNIDS:
    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir or MODEL_DIR
        self._model: Any = None
        self._scaler: Any = None
        self._lock = RLock()

    def _load(self) -> None:
        if self._model is not None and self._scaler is not None:
            return
        with self._lock:
            if self._model is None or self._scaler is None:
                self._model, self._scaler = load_model_assets(self.model_dir)

    def status(self) -> dict[str, Any]:
        assets = {}
        for key, metadata in ARTIFACTS.items():
            path = self.model_dir / metadata["filename"]
            assets[metadata["filename"]] = {
                "present": path.is_file(),
                "verified": verify_artifact(path, metadata),
            }
        all_verified = all(value["verified"] for value in assets.values())
        return {
            "status": "assets_ready" if all_verified else "assets_missing_or_invalid",
            "integration_status": "waiting_for_flow_features",
            "live_inference_ready": False,
            "model": "RandomForest 3-Class CICIDS2017",
            "model_version": MODEL_VERSION,
            "dataset": "CICIDS2017",
            "feature_count": len(FEATURE_NAMES),
            "classes": list(CLASS_LABELS.values()),
            "assets": assets,
            "inference_loaded": self._model is not None,
        }

    def predict(self, flow_features: Mapping[str, Any]) -> dict[str, Any]:
        ordered = normalize_feature_row(flow_features)
        self._load()
        try:
            import numpy as np
        except ImportError as exc:
            raise ModelCompatibilityError("NumPy belum terpasang.") from exc

        raw = np.asarray([ordered], dtype=np.float64)
        scaled = self._scaler.transform(raw)
        prediction = int(self._model.predict(scaled)[0])
        if prediction not in CLASS_LABELS:
            raise ModelCompatibilityError(f"Model mengembalikan label yang tidak dikenal: {prediction}.")

        probability_row = self._model.predict_proba(scaled)[0]
        model_classes = [int(value) for value in self._model.classes_]
        probabilities = {
            CLASS_LABELS[class_id]: float(probability)
            for class_id, probability in zip(model_classes, probability_row)
        }
        predicted_label = CLASS_LABELS[prediction]

        return {
            "status": "predicted",
            "source": "ml",
            "model": "RandomForest 3-Class CICIDS2017",
            "model_version": MODEL_VERSION,
            "dataset": "CICIDS2017",
            "label": predicted_label,
            "class_id": prediction,
            "probabilities": probabilities,
            "top_probability": probabilities.get(predicted_label),
            "probability_note": "Nilai probabilitas keluaran model; bukan jaminan confidence yang terkalibrasi.",
            "feature_count": len(FEATURE_NAMES),
            "feature_schema": "betuldanismaz-rf-3class-20features-v1",
        }
