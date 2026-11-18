# Realtime Data Sanitization

Menyediakan fungsi sanitasi recursive untuk membuang key sensitif seperti token, secret, API key, password, dan authorization sebelum detail event disimpan atau diteruskan.

WebSocket dashboard dikelola oleh Management API dan event disimpan pada tabel dashboard_events.
