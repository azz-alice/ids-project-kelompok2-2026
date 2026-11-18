# Traffic Analyzer

Menjadi entry point analyzer berkala yang mendelegasikan pemrosesan window ke `telemetry_pipeline.py`. Pipeline memisahkan HTTP/application events dari packet metadata, menghitung request rate, packet rate, bytes per second, variasi ukuran request, dan fitur terkait.

Fitur agregat ini belum sama dengan 20 fitur bidirectional CICFlowMeter. Jangan mengirimkannya ke pretrained AI model yang membutuhkan skema 20 fitur.
