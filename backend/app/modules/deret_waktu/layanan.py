from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import GUEST_ORIGIN, INTERNAL_ORIGIN
from app.modules.database.service import Database, default_database, loads, to_iso, utc_now

JALUR_DIABAIKAN = ("/api/health", "/api/guest/status")
BATAS_DETIK = 600
BATAS_BUKTI = 100


class LayananDeretWaktu:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database

    def deret(self, detik: int = 120, sekarang: datetime | None = None) -> dict[str, Any]:
        jumlah = max(10, min(int(detik), BATAS_DETIK))
        current = sekarang or utc_now()
        akhir = datetime.fromtimestamp(math.floor(current.timestamp()), timezone.utc)
        awal = akhir - timedelta(seconds=jumlah)
        awal_iso, akhir_iso = to_iso(awal), to_iso(akhir)
        aplikasi = self.database.fetch_all(
            "SELECT substr(observed_at, 1, 19) AS detik, origin, COUNT(*) AS jumlah, COALESCE(SUM(request_bytes), 0) AS byte "
            "FROM application_events WHERE observed_at >= ? AND observed_at < ? AND path LIKE '/api/%' "
            "AND path NOT IN (?, ?) GROUP BY detik, origin",
            (awal_iso, akhir_iso, *JALUR_DIABAIKAN),
        )
        paket = self.database.fetch_all(
            "SELECT substr(observed_at, 1, 19) AS detik, COUNT(*) AS jumlah, COALESCE(SUM(packet_length), 0) AS byte "
            "FROM packet_events WHERE observed_at >= ? AND observed_at < ? GROUP BY detik",
            (awal_iso, akhir_iso),
        )
        titik = {
            index: {"internal": 0, "visitor": 0, "app_bytes": 0, "packets": 0, "packet_bytes": 0}
            for index in range(jumlah)
        }
        epoch_awal = int(awal.timestamp())

        def indeks(label: str) -> int:
            parsed = datetime.fromisoformat(label).replace(tzinfo=timezone.utc)
            return int(parsed.timestamp()) - epoch_awal

        for row in aplikasi:
            slot = titik.get(indeks(row["detik"]))
            if slot is None:
                continue
            kunci = "internal" if row["origin"] == INTERNAL_ORIGIN else "visitor"
            slot[kunci] += int(row["jumlah"])
            slot["app_bytes"] += int(row["byte"])
        for row in paket:
            slot = titik.get(indeks(row["detik"]))
            if slot is None:
                continue
            slot["packets"] += int(row["jumlah"])
            slot["packet_bytes"] += int(row["byte"])
        total = sum(slot["internal"] + slot["visitor"] + slot["packets"] for slot in titik.values())
        return {
            "seconds": jumlah,
            "server_time": to_iso(current),
            "has_events": total > 0,
            "points": [
                {"t": to_iso(awal + timedelta(seconds=index)), **titik[index]}
                for index in range(jumlah)
            ],
        }

    def bukti_deteksi(self, detection_id: str) -> dict[str, Any] | None:
        row = self.database.fetch_one(
            "SELECT d.*, s.ticket_code, s.client_ip AS session_ip FROM detections d "
            "LEFT JOIN sessions s ON s.id = d.session_id WHERE d.id = ?",
            (detection_id,),
        )
        if row is None:
            return None
        fitur = loads(row["feature_json"])
        awal, akhir = fitur.get("window_start"), fitur.get("window_end") or row["created_at"]
        peristiwa: list[dict[str, Any]] = []
        paket: list[dict[str, Any]] = []
        if awal and akhir:
            if row["session_id"]:
                peristiwa = self.database.fetch_all(
                    "SELECT id, observed_at, method, path, status_code, client_ip, request_bytes, response_bytes, origin, activity_id "
                    "FROM application_events WHERE session_id = ? AND observed_at >= ? AND observed_at < ? "
                    "AND path = '/api/activity/probe' AND origin = ? ORDER BY observed_at LIMIT ?",
                    (row["session_id"], awal, akhir, GUEST_ORIGIN, BATAS_BUKTI),
                )
                paket = self.database.fetch_all(
                    "SELECT id, observed_at, source_ip, destination_ip, protocol, source_port, destination_port, packet_length "
                    "FROM packet_events WHERE session_id = ? AND observed_at >= ? AND observed_at < ? "
                    "ORDER BY observed_at LIMIT ?",
                    (row["session_id"], awal, akhir, BATAS_BUKTI),
                )
            else:
                paket = self.database.fetch_all(
                    "SELECT id, observed_at, source_ip, destination_ip, protocol, source_port, destination_port, packet_length "
                    "FROM packet_events WHERE observed_at >= ? AND observed_at < ? ORDER BY observed_at LIMIT ?",
                    (awal, akhir, BATAS_BUKTI),
                )
        return {
            "id": row["id"],
            "rule_id": row["rule_id"],
            "label": row["label"],
            "severity": row["severity"],
            "reason": row["reason"],
            "measured_value": row["score"],
            "created_at": row["created_at"],
            "rules_version": row["rules_version"],
            "ticket": row["ticket_code"],
            "client_ip": row["session_ip"],
            "session_id": row["session_id"],
            "activity_id": row["activity_id"],
            "window_start": awal,
            "window_end": akhir,
            "features": fitur,
            "application_events": peristiwa,
            "packet_events": paket,
        }


layanan_deret_waktu = LayananDeretWaktu()
