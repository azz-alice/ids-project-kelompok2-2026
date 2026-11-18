# Backend

Guest API: `0.0.0.0:8000`. Management API: `127.0.0.1:8001`.

Jalankan satu file `RUN_IDS.bat` di root proyek. Dependensi backend diatur melalui `requirements.txt`; dependensi AI bersifat opsional dan berada di `requirements-ai.txt`.

Konfigurasi lokal berada di `.env`, dibuat dari `.env.example`. Guest API menerima sesi dan request pengujian. Management API melayani dashboard, WebSocket, sensor, alert, serta threat intelligence.

Pada Windows, install Npcap dengan dukungan loopback capture jika dibutuhkan, jalankan aplikasi dengan hak yang sesuai, pilih interface yang benar, dan buktikan packet capture aktual. Sensor tidak aktif otomatis kecuali `SENSOR_ENABLED=true` dan `SENSOR_INTERFACE` sudah dikonfigurasi.
