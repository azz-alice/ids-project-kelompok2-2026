from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import ARTIFACTS, MODEL_DIR, verify_artifact


class ModelAssetsMissing(RuntimeError):
    pass


class ModelCompatibilityError(RuntimeError):
    pass


def load_model_assets(model_dir: Path | None = None) -> tuple[Any, Any]:
    directory = model_dir or MODEL_DIR
    model_path = directory / ARTIFACTS["model"]["filename"]
    scaler_path = directory / ARTIFACTS["scaler"]["filename"]
    missing = [path.name for path in (model_path, scaler_path) if not path.is_file()]
    if missing:
        raise ModelAssetsMissing(
            "Artifact model belum tersedia: " + ", ".join(missing) + ". Jalankan ai/pretrained_nids/download_assets.py."
        )

    for path, key in ((model_path, "model"), (scaler_path, "scaler")):
        if not verify_artifact(path, ARTIFACTS[key]):
            raise ModelCompatibilityError(
                f"Checksum atau ukuran {path.name} tidak cocok dengan artifact upstream yang dipatok. File tidak dimuat."
            )

    try:
        import joblib
    except ImportError as exc:
        raise ModelCompatibilityError("joblib belum terpasang. Instal backend/requirements-ai.txt ke environment backend.") from exc

    try:
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
    except Exception as exc:
        raise ModelCompatibilityError(f"Artifact tidak dapat dimuat: {exc}") from exc

    model_features = getattr(model, "n_features_in_", None)
    scaler_features = getattr(scaler, "n_features_in_", None)
    if model_features != 20 or scaler_features != 20:
        raise ModelCompatibilityError(
            f"Feature count tidak cocok. Model={model_features}, scaler={scaler_features}, diharapkan=20."
        )
    if not hasattr(model, "predict") or not hasattr(model, "predict_proba"):
        raise ModelCompatibilityError("Model tidak menyediakan predict() dan predict_proba().")

    model_classes = {int(value) for value in getattr(model, "classes_", [])}
    if model_classes != {0, 1, 2}:
        raise ModelCompatibilityError(f"Kelas model tidak cocok: {sorted(model_classes)}; diharapkan [0, 1, 2].")

    return model, scaler
