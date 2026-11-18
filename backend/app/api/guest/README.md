# Guest API

Menangani akses Web Pengunjung dari jaringan lokal. Route utama mencakup pembuatan dan pemulihan sesi, heartbeat, rencana aktivitas, penerimaan probe HTTP, status aktivitas, dan pembatalan aktivitas.

Batas penting: validasi token, waktu sesi, cooldown, jumlah sesi, jumlah request, dan ukuran payload dilakukan di backend. Jangan menambahkan endpoint yang mengungkap daftar seluruh sesi ke jaringan pengunjung.

File utama: `routes.py` dan `rute_internal.py`. Server dijalankan sebagai `app.guest_app:app` pada port 8000 dengan host jaringan yang dikonfigurasi, serta membangkitkan traffic normal internal (`internal_baseline`) secara otomatis selama layanan aktif.
