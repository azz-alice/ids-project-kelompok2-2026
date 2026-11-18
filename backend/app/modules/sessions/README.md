# Sessions

Membuat ticket unik, session ID, token acak yang disimpan sebagai hash, durasi sesi 120 detik, maksimal lima sesi aktif, validasi sesi, dan cooldown per sesi.

Aturan sesi wajib divalidasi backend. Frontend hanya menampilkan waktu yang diterima dari server dan tidak boleh memperpanjang sesi secara lokal.
