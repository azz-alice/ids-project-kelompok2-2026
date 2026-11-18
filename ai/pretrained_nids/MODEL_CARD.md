# Model card: CICIDS2017 Random Forest 3-Class

## Source

- Upstream repository: https://github.com/betuldanismaz/Network_Anomaly_Detection
- Upstream license: MIT. See `LICENSE-UPSTREAM-MIT.txt`.
- Upstream model config: `models/rf_3class_config.json`.
- Upstream feature definition: `src/config.py`.
- Upstream inference pipeline uses CICFlowMeter-derived flow features.

## Model

- Type: Random Forest classifier
- Input: exactly 20 CICIDS2017 flow features, in the order recorded in `model_config.json`
- Preprocessing: upstream MinMaxScaler (`scaler_ml_3class.pkl`)
- Classes: `Benign`, `Volumetric`, `Semantic`
- Runtime: CPU inference; no GPU required by this Random Forest artifact

## Upstream-reported evaluation

The source repository's config reports accuracy 0.9734, macro precision 0.9443, macro recall 0.9778, and macro F1 0.9591 on 283,078 test samples. These are upstream-reported results. They have not been reproduced or independently validated in this adaptation.

## Intended use in this project

Use this model as an additional flow-level classification signal. Keep the existing rule-based detection as the authoritative detector for the exhibition scenarios:

- `volume_spike`
- `large_payload`
- `high_request_rate`

Do not map `Volumetric` to one of those exact scenario labels. Do not map `Semantic` to `large_payload` or `high_request_rate`. The taxonomies are different.

## Important input limitation

The model expects CICFlowMeter/CICIDS2017-style bidirectional flow statistics, not raw Scapy packet dictionaries and not the project's current aggregate `packet_rate` / `request_rate` window. All 20 input features must be extracted from a flow using a compatible feature extractor. Missing fields are rejected; this wrapper never fills missing values with zero.

Until the project's traffic pipeline produces a valid 20-feature flow record, this model must report `waiting_for_flow_features` and must not create ML detections.

## Output interpretation

The predictor returns the class label and class probability values emitted by the estimator. The top probability is not guaranteed to be calibrated confidence. The result is advisory and must not trigger automatic blocking.

## Security

The upstream artifacts are joblib/pickle files. Loading pickle-based artifacts can execute code. The downloader pins exact SHA-256 digests and file sizes from the upstream Git LFS pointers, and the loader verifies them before calling `joblib.load`. The pretrained binary files are not embedded in this ZIP because the Git LFS binary payload could not be retrieved and independently verified in the build environment. Run the downloader from the integration guide to fetch them. Do not replace artifacts with files from other sources.
