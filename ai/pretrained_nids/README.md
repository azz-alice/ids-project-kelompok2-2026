# Pretrained NIDS model adapter

This package adapts the pretrained three-class Random Forest from `betuldanismaz/Network_Anomaly_Detection` for the existing FastAPI IDS project.

It is an inference adapter, not a new dashboard or a second backend. It keeps the existing rule-based detections for the visitor's three exhibition scenarios and adds an optional CICIDS2017 flow-level ML signal.

## Before using

The model expects exactly 20 CICFlowMeter-style bidirectional flow features. The current IDS packet sensor output is not enough by itself. The backend must first produce those 20 features per flow. Missing features are rejected rather than filled with fake zeros.

## Setup

Use Python 3.11 for compatibility with the versions pinned from the upstream project:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-ai.txt
backend\.venv\Scripts\python.exe ai\pretrained_nids\download_assets.py
backend\.venv\Scripts\python.exe ai\pretrained_nids\smoke_test.py
backend\.venv\Scripts\python.exe -m unittest discover -s ai\pretrained_nids\tests -v
```

The model/scaler binaries are downloaded from the upstream Git LFS storage and checked against pinned SHA-256 digests. The binary artifacts are not embedded in this ZIP because the file transfer from the upstream LFS host was not available in the preparation environment.

## Outputs

The model predicts one of:

- `Benign`
- `Volumetric`
- `Semantic`

These categories are not the same as the visitor scenarios `volume_spike`, `large_payload`, and `high_request_rate`. Keep ML and rule results as separate detection sources.

## Source and license

See `THIRD_PARTY_NOTICES.md` and `LICENSE-UPSTREAM-MIT.txt`.
