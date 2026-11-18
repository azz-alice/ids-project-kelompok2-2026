# Threat Intelligence

Menyediakan pemeriksaan reputasi IP melalui AbuseIPDB, cache hasil, timeout, dan batas request. Fitur memerlukan `ABUSEIPDB_ENABLED=true` serta API key pada `backend/.env`.

API key tidak boleh dikirim ke browser. Kegagalan layanan eksternal tidak boleh menghentikan sensor, analyzer, atau rule detection lokal.
