# Integration guide for the existing IDS project

## What this package adds

1. A pretrained CICIDS2017 Random Forest classifier with three classes.
2. Its paired MinMaxScaler.
3. A strict 20-feature input contract.
4. A checksum-verified model downloader.
5. A FastAPI-backend service facade at `backend/app/modules/ai_integration/service.py`.

The archive does not replace the existing sensor, analyzer, detection engine, database, dashboard, or rules. It does not add Kafka, Streamlit, Android, or firewall blocking.

## Extraction location

Extract this ZIP at the project root. It contains two paths:

- `ai/` — model package, configuration, downloader, and tests.
- `backend/app/modules/ai_integration/service.py` — provides the lazy-loading inference adapter used by the backend AI status and prediction interface.

Make a Git commit or copy of the current project before overlaying the files.

## Python environment

The model package uses scikit-learn 1.7.2, NumPy 1.26.4, and joblib 1.5.2. The project uses one Python 3.11 x64 environment at `backend\.venv` for the backend and optional inference dependencies.

From the project root, install the optional AI dependencies into the existing backend environment:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-ai.txt
```

Download the upstream model artifacts and verify their SHA-256 checksums:

```powershell
backend\.venv\Scripts\python.exe ai\pretrained_nids\download_assets.py
```

Verify model availability and loading:

```powershell
backend\.venv\Scripts\python.exe ai\pretrained_nids\smoke_test.py
```

Run the feature-contract tests:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s ai\pretrained_nids\tests -v
```

Do not install unrelated upstream requirements such as TensorFlow, Kafka, Streamlit, or Docker just to use this Random Forest model.

## Backend service interface

The replacement `Service` exposes:

- `status()` — returns readiness and artifact verification state.
- `predict_flow(flow_features)` — accepts one complete mapping containing all 20 CICFlowMeter features and returns a prediction object.

The service loads the model lazily on its first prediction. It never generates or substitutes fake feature rows. `status()` reports the configured switch, artifact verification, `integration_status=waiting_for_flow_features`, and `live_inference_ready=false`; this package does not claim the current backend flow extractor is already connected.

## Required upstream feature bridge

The current project's sensor emits packet metadata. That metadata is not the same thing as the 20 bidirectional flow features required by this model.

Before enabling calls to `predict_flow`, the backend must add a flow feature extraction stage compatible with CICFlowMeter's CICIDS2017 definitions. It must produce these exact 20 features per flow:

1. Bwd Packet Length Std
2. Bwd Packet Length Mean
3. Packet Length Std
4. Packet Length Variance
5. Bwd Packet Length Max
6. Subflow Bwd Bytes
7. Avg Bwd Segment Size
8. Packet Length Mean
9. Average Packet Size
10. Max Packet Length
11. Total Length of Bwd Packets
12. Fwd IAT Std
13. Total Fwd Packets
14. Total Backward Packets
15. Bwd Packets/s
16. Idle Min
17. Fwd IAT Mean
18. Subflow Fwd Packets
19. Total Length of Fwd Packets
20. Fwd IAT Max

The strict adapter accepts the canonical CICIDS column names or the snake_case names used by the upstream live bridge. If any required feature is missing, non-numeric, non-finite, or negative, prediction is rejected.

Do not map aggregate window metrics such as `packet_rate`, `request_rate`, `bytes_per_second`, or a single packet's length to these flow features. Do not fill missing flow fields with zero. Do not call the model once per packet. It predicts one bidirectional flow record at a time.

## How the output should be integrated

Keep ML output separate from rule output:

- Rule source remains responsible for the three exhibition scenarios.
- ML source returns only `Benign`, `Volumetric`, or `Semantic`.
- Store `source=ml`, the model version, class probabilities, and the original 20 features.
- Do not set an automatic firewall block action based on this model.
- Do not reinterpret `Volumetric` as a precise `volume_spike` diagnosis.

If flow feature extraction is not ready, keep the module status as `waiting_for_flow_features` and leave the model disconnected from live detections.

## Current known integration gap

In the upgraded project, `backend/app/modules/traffic_analyzer/service.py` is a façade over the telemetry pipeline that builds packet-level and HTTP-application windows. It does not yet produce the full 20 bidirectional CICFlowMeter features required by this pretrained model. This package supplies the model adapter and strict inference boundary; it does not claim that the missing flow-feature extractor already exists.
