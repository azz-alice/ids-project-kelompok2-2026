# AI IDS

Model pretrained opsional berada di `ai/pretrained_nids`. Model ini memakai 20 fitur CICIDS2017 dan tiga kelas: Benign, Volumetric, dan Semantic.

Model tidak otomatis mengklasifikasikan empat tombol skenario Web Pengunjung. Integrasi live tetap menunggu extractor flow 20 fitur yang kompatibel dengan definisi fitur training. Rule-based detection tetap menjadi mekanisme utama demonstrasi.

Untuk menyiapkan model, ikuti `ai/pretrained_nids/INTEGRATION_GUIDE.md`. Instal dependensi AI ke virtual environment backend dengan `backend/requirements-ai.txt`, lalu unduh dan verifikasi artifact menggunakan script downloader.
