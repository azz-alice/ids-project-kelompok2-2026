from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ids_pretrained.predictor import PretrainedNIDS


def main() -> int:
    predictor = PretrainedNIDS(ROOT / "models")
    status = predictor.status()
    print(f"Model: {status['model']}")
    print(f"Status: {status['status']}")
    print(f"Feature count: {status['feature_count']}")
    for filename, details in status["assets"].items():
        print(f"{filename}: present={details['present']} verified={details['verified']}")
    if status["status"] != "assets_ready":
        print("Jalankan download_assets.py sebelum memuat model.")
        return 1
    try:
        predictor._load()
    except Exception as exc:
        print(f"Model load gagal: {exc}")
        return 1
    print("MODEL LOAD OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
