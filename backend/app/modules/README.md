# Backend Modules

Modul backend membentuk pipeline IDS. `telemetry_pipeline.py` dan `fitur_traffic.py` menghubungkan event aplikasi dan packet capture, menghitung fitur per window, memperbarui baseline, menjalankan rule detection, menyimpan event, serta menerbitkan pembaruan dashboard. Modul `lalu_lintas_internal` membangkitkan traffic normal internal otomatis, dan `deret_waktu` menyediakan deret metrik per detik serta penelusuran bukti deteksi.

Modul lain memisahkan tanggung jawab database, sesi, sensor, traffic generator, analyzer, baseline, detection, alerts, incidents, logs, threat intelligence, dan adapter AI. Pertahankan pemisahan sumber application events dan packet events.
