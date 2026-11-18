# Management API

Menyediakan snapshot dashboard, deret waktu per detik (`/api/dashboard/series`), penelusuran bukti deteksi (`/api/detections/{id}`), histori window, kontrol sensor, status layanan, logs, alerts, incidents, threat intelligence, status AI, dan WebSocket dashboard.

Management API wajib bind hanya ke `127.0.0.1:8001`. Jangan membuka listener ini ke jaringan pengunjung.

File utama: `dashboard.py`. Server dijalankan sebagai `app.management_app:app`.
