# AI Integration

Adapter opsional untuk pretrained Random Forest CICIDS2017 tiga kelas: Benign, Volumetric, dan Semantic. Adapter memeriksa artifact, urutan fitur, dan input inference.

Model membutuhkan 20 fitur bidirectional flow CICFlowMeter. Packet metadata atau agregat `packet_rate`, `request_rate`, dan `bytes_per_second` tidak cukup. Live inference tetap menunggu flow feature extractor yang kompatibel. Rule detection tetap menjadi jalur aktif.
