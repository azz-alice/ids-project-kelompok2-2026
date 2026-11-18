from __future__ import annotations

import hashlib
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
ARTIFACTS = {
    "model": {
        "filename": "rf_3class_model.pkl",
        "sha256": "35287335aefad3fcee9779fbcfb22daf2e8c9d5edfd826b712060acd40c7ef7b",
        "size_bytes": 16990577,
    },
    "scaler": {
        "filename": "scaler_ml_3class.pkl",
        "sha256": "0bbf1565be27b5bdb90fa595ec53089c052fc14cfe76360cafcc910580fb0958",
        "size_bytes": 1463,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(path: Path, metadata: dict) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != metadata["size_bytes"]:
        return False
    return sha256_file(path) == metadata["sha256"]
