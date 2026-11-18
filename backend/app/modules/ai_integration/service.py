from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.pretrained_nids.src.ids_pretrained.loader import ModelAssetsMissing, ModelCompatibilityError
from ai.pretrained_nids.src.ids_pretrained.predictor import PretrainedNIDS
from app.config import settings


class Service:
    def __init__(self) -> None:
        self._predictor = PretrainedNIDS(PROJECT_ROOT / "ai" / "pretrained_nids" / "models")

    def status(self) -> dict[str, Any]:
        status = self._predictor.status()
        status["enabled"] = settings.ml_enabled
        if not settings.ml_enabled:
            status["status"] = "disabled"
            status["message"] = "AI dinonaktifkan. Aktifkan ML_ENABLED setelah artifact dan flow feature extractor siap."
        elif status["status"] == "assets_ready":
            status["message"] = "Artifact terverifikasi; inference live menunggu flow feature extractor 20 fitur CICFlowMeter."
        else:
            status["message"] = "Artifact model belum tersedia atau gagal diverifikasi."
        return status

    def predict_flow(self, flow_features: Mapping[str, Any]) -> dict[str, Any]:
        if not settings.ml_enabled:
            return {"status": "disabled", "source": "ml", "reason": "ML_ENABLED belum diaktifkan."}
        try:
            return self._predictor.predict(flow_features)
        except ModelAssetsMissing as exc:
            return {"status": "model_unavailable", "source": "ml", "reason": str(exc)}
        except ModelCompatibilityError as exc:
            return {"status": "model_error", "source": "ml", "reason": str(exc)}
        except ValueError as exc:
            return {"status": "feature_input_invalid", "source": "ml", "reason": str(exc)}
