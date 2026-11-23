from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.modules.database.service import Database, default_database, dumps, loads, to_iso, utc_now
from app.modules.logs.service import log_service

STATUS_NORMAL = "NORMAL"
STATUS_ABOVE_BASELINE = "DEVIASI BASELINE"
STATUS_ANOMALOUS = "ANOMALI TRAFFIC"
STATUS_RECOVERING = "STABILISASI"

CODE_MAP = {
    STATUS_NORMAL: "normal",
    STATUS_ABOVE_BASELINE: "above_baseline",
    STATUS_ANOMALOUS: "anomalous",
    STATUS_RECOVERING: "recovering",
}

HYSTERESIS_RECOVERING = 2
HYSTERESIS_NORMAL = 3


class PengelolaKondisiTraffic:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database

    def inisialisasi_tabel(self) -> None:
        self.database.execute(
            "CREATE TABLE IF NOT EXISTS traffic_condition_state ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), "
            "status TEXT NOT NULL, "
            "normal_started_at TEXT, "
            "anomaly_started_at TEXT, "
            "anomaly_type TEXT, "
            "anomaly_details_json TEXT, "
            "recovery_started_at TEXT, "
            "recovery_completed_at TEXT, "
            "recovery_duration_seconds REAL, "
            "clean_windows_count INTEGER NOT NULL DEFAULT 0, "
            "updated_at TEXT NOT NULL"
            ")"
        )
        now = to_iso(utc_now())
        self.database.execute(
            "INSERT OR IGNORE INTO traffic_condition_state "
            "(id, status, normal_started_at, anomaly_started_at, anomaly_type, anomaly_details_json, "
            "recovery_started_at, recovery_completed_at, recovery_duration_seconds, clean_windows_count, updated_at) "
            "VALUES (1, ?, ?, NULL, NULL, '{}', NULL, NULL, NULL, 0, ?)",
            (STATUS_NORMAL, now, now),
        )

    def ambil_keadaan(self) -> dict[str, Any]:
        self.inisialisasi_tabel()
        row = self.database.fetch_one("SELECT * FROM traffic_condition_state WHERE id = 1")
        if not row:
            now = to_iso(utc_now())
            return {
                "status": STATUS_NORMAL,
                "code": "normal",
                "normal_started_at": now,
                "anomaly_started_at": None,
                "anomaly_type": None,
                "anomaly_details": {},
                "recovery_started_at": None,
                "recovery_completed_at": None,
                "recovery_duration_seconds": None,
                "clean_windows_count": 0,
                "updated_at": now,
            }
        details = {}
        if row["anomaly_details_json"]:
            try:
                details = loads(row["anomaly_details_json"])
            except Exception:
                details = {}
        return {
            "status": row["status"],
            "code": CODE_MAP.get(row["status"], "normal"),
            "normal_started_at": row["normal_started_at"],
            "anomaly_started_at": row["anomaly_started_at"],
            "anomaly_type": row["anomaly_type"],
            "anomaly_details": details,
            "recovery_started_at": row["recovery_started_at"],
            "recovery_completed_at": row["recovery_completed_at"],
            "recovery_duration_seconds": row["recovery_duration_seconds"],
            "clean_windows_count": int(row["clean_windows_count"]),
            "updated_at": row["updated_at"],
        }

    def _simpan_keadaan(self, state: dict[str, Any]) -> None:
        self.database.execute(
            "UPDATE traffic_condition_state SET "
            "status = ?, "
            "normal_started_at = ?, "
            "anomaly_started_at = ?, "
            "anomaly_type = ?, "
            "anomaly_details_json = ?, "
            "recovery_started_at = ?, "
            "recovery_completed_at = ?, "
            "recovery_duration_seconds = ?, "
            "clean_windows_count = ?, "
            "updated_at = ? "
            "WHERE id = 1",
            (
                state["status"],
                state["normal_started_at"],
                state["anomaly_started_at"],
                state["anomaly_type"],
                dumps(state["anomaly_details"]),
                state["recovery_started_at"],
                state["recovery_completed_at"],
                state["recovery_duration_seconds"],
                state["clean_windows_count"],
                state["updated_at"],
            ),
        )

    def perbarui_kondisi(
        self,
        raw_status: str,
        anomaly_type: str | None = None,
        anomaly_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.ambil_keadaan()
        current_status = state["status"]
        now_dt = utc_now()
        now_iso = to_iso(now_dt)
        status_berubah = False
        status_lama = current_status

        if raw_status == STATUS_ANOMALOUS:
            state["clean_windows_count"] = 0
            if current_status != STATUS_ANOMALOUS:
                state["status"] = STATUS_ANOMALOUS
                state["anomaly_started_at"] = now_iso
                state["anomaly_type"] = anomaly_type or "Anomali terdeteksi"
                state["anomaly_details"] = anomaly_details or {}
                status_berubah = True
            else:
                if anomaly_type:
                    state["anomaly_type"] = anomaly_type
                if anomaly_details:
                    state["anomaly_details"] = anomaly_details

        elif raw_status == STATUS_ABOVE_BASELINE:
            if current_status == STATUS_ANOMALOUS:
                state["clean_windows_count"] += 1
                if state["clean_windows_count"] >= HYSTERESIS_RECOVERING:
                    state["status"] = STATUS_RECOVERING
                    state["recovery_started_at"] = now_iso
                    status_berubah = True
            elif current_status == STATUS_RECOVERING:
                state["clean_windows_count"] += 1
            elif current_status == STATUS_NORMAL:
                state["status"] = STATUS_ABOVE_BASELINE
                state["clean_windows_count"] = 0
                status_berubah = True

        else:
            if current_status == STATUS_ANOMALOUS:
                state["clean_windows_count"] += 1
                if state["clean_windows_count"] >= HYSTERESIS_RECOVERING:
                    state["status"] = STATUS_RECOVERING
                    state["recovery_started_at"] = now_iso
                    status_berubah = True
            elif current_status == STATUS_RECOVERING:
                state["clean_windows_count"] += 1
                if state["clean_windows_count"] >= HYSTERESIS_NORMAL:
                    state["status"] = STATUS_NORMAL
                    state["recovery_completed_at"] = now_iso
                    if state["recovery_started_at"]:
                        try:
                            mulai_rec = datetime.fromisoformat(state["recovery_started_at"].replace("Z", "+00:00"))
                            durasi = round((now_dt - mulai_rec).total_seconds(), 2)
                        except Exception:
                            durasi = 0.0
                        state["recovery_duration_seconds"] = durasi
                    state["normal_started_at"] = now_iso
                    state["anomaly_type"] = None
                    state["clean_windows_count"] = 0
                    status_berubah = True
            elif current_status == STATUS_ABOVE_BASELINE:
                state["clean_windows_count"] += 1
                if state["clean_windows_count"] >= HYSTERESIS_RECOVERING:
                    state["status"] = STATUS_NORMAL
                    state["normal_started_at"] = now_iso
                    state["clean_windows_count"] = 0
                    status_berubah = True
            else:
                state["clean_windows_count"] = 0
                if not state["normal_started_at"]:
                    state["normal_started_at"] = now_iso

        state["updated_at"] = now_iso
        self._simpan_keadaan(state)

        if status_berubah:
            from app.modules.telemetry_pipeline import telemetry_pipeline

            payload = {
                "previous_status": status_lama,
                "current_status": state["status"],
                "code": CODE_MAP.get(state["status"], "normal"),
                "normal_started_at": state["normal_started_at"],
                "anomaly_started_at": state["anomaly_started_at"],
                "anomaly_type": state["anomaly_type"],
                "anomaly_details": state["anomaly_details"],
                "recovery_started_at": state["recovery_started_at"],
                "recovery_completed_at": state["recovery_completed_at"],
                "recovery_duration_seconds": state["recovery_duration_seconds"],
                "timestamp": now_iso,
            }
            telemetry_pipeline.publish_event("traffic_condition", payload)
            level = "error" if state["status"] == STATUS_ANOMALOUS else "warning" if state["status"] in (STATUS_ABOVE_BASELINE, STATUS_RECOVERING) else "info"
            log_service.write(
                level,
                "traffic_condition",
                "state_change",
                f"Status traffic beralih dari {status_lama} ke {state['status']}",
                payload,
            )

        return self.status_lengkap(state)

    def status_lengkap(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        data = state or self.ambil_keadaan()
        now_dt = utc_now()
        durasi_normal = 0
        if data["normal_started_at"] and data["status"] == STATUS_NORMAL:
            try:
                mulai = datetime.fromisoformat(data["normal_started_at"].replace("Z", "+00:00"))
                durasi_normal = max(0, int((now_dt - mulai).total_seconds()))
            except Exception:
                durasi_normal = 0

        durasi_anomali = 0
        if data["anomaly_started_at"] and data["status"] == STATUS_ANOMALOUS:
            try:
                mulai = datetime.fromisoformat(data["anomaly_started_at"].replace("Z", "+00:00"))
                durasi_anomali = max(0, int((now_dt - mulai).total_seconds()))
            except Exception:
                durasi_anomali = 0

        durasi_pemulihan = 0
        if data["recovery_started_at"] and data["status"] == STATUS_RECOVERING:
            try:
                mulai = datetime.fromisoformat(data["recovery_started_at"].replace("Z", "+00:00"))
                durasi_pemulihan = max(0, int((now_dt - mulai).total_seconds()))
            except Exception:
                durasi_pemulihan = 0

        pesan = "Traffic berada dalam batas normal."
        if data["status"] == STATUS_ABOVE_BASELINE:
            pesan = "Traffic mengalami peningkatan di atas baseline normal."
        elif data["status"] == STATUS_ANOMALOUS:
            pesan = f"Anomali terdeteksi: {data['anomaly_type'] or 'Penyimpangan traffic'}."
        elif data["status"] == STATUS_RECOVERING:
            pesan = "Traffic mulai stabil dan sedang dalam proses pemulihan menuju normal."

        label = "Normal" if data["status"] == STATUS_NORMAL else data["status"]
        return {
            "status": data["status"],
            "code": CODE_MAP.get(data["status"], "normal"),
            "label": label,
            "condition": data["status"],
            "message": pesan,
            "normal_started_at": data["normal_started_at"],
            "normal_duration_seconds": durasi_normal,
            "anomaly_started_at": data["anomaly_started_at"],
            "anomaly_duration_seconds": durasi_anomali,
            "anomaly_type": data["anomaly_type"],
            "anomaly_details": data["anomaly_details"],
            "recovery_started_at": data["recovery_started_at"],
            "recovery_duration_seconds": data["recovery_duration_seconds"] or durasi_pemulihan,
            "recovery_completed_at": data["recovery_completed_at"],
            "clean_windows_count": data["clean_windows_count"],
            "updated_at": data["updated_at"],
        }


pengelola_kondisi = PengelolaKondisiTraffic()
