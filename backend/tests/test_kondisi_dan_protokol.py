from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.guest_app import app as guest_app
from app.management_app import app as management_app
from app.modules.database.service import Database
from app.modules.kondisi_traffic import (
    STATUS_ABOVE_BASELINE,
    STATUS_ANOMALOUS,
    STATUS_NORMAL,
    STATUS_RECOVERING,
    pengelola_kondisi,
)
from app.modules.pengirim_protokol import pengirim_protokol


def test_kondisi_traffic_state_machine_and_hysteresis(database: Database) -> None:
    pengelola_kondisi.database = database
    status = pengelola_kondisi.ambil_keadaan()
    assert status["status"] == STATUS_NORMAL
    assert status["normal_started_at"] is not None

    anom = pengelola_kondisi.perbarui_kondisi(
        STATUS_ANOMALOUS,
        anomaly_type="Peningkatan frekuensi request",
        anomaly_details={"score": 12.5, "ticket": "T-123"},
    )
    assert anom["status"] == STATUS_ANOMALOUS
    assert anom["code"] == "anomalous"
    assert anom["anomaly_started_at"] is not None
    assert anom["anomaly_type"] == "Peningkatan frekuensi request"

    rec1 = pengelola_kondisi.perbarui_kondisi(STATUS_NORMAL)
    assert rec1["status"] == STATUS_ANOMALOUS
    assert rec1["clean_windows_count"] == 1

    rec2 = pengelola_kondisi.perbarui_kondisi(STATUS_NORMAL)
    assert rec2["status"] == STATUS_RECOVERING
    assert rec2["code"] == "recovering"
    assert rec2["recovery_started_at"] is not None

    pengelola_kondisi.perbarui_kondisi(STATUS_NORMAL)
    pengelola_kondisi.perbarui_kondisi(STATUS_NORMAL)
    norm = pengelola_kondisi.perbarui_kondisi(STATUS_NORMAL)
    assert norm["status"] == STATUS_NORMAL
    assert norm["code"] == "normal"
    assert norm["recovery_completed_at"] is not None
    assert norm["recovery_duration_seconds"] is not None

    logs = database.fetch_all("SELECT * FROM system_logs WHERE component = 'traffic_condition'")
    assert len(logs) >= 3


def test_pengirim_protokol_support_and_safety() -> None:
    http_cek = pengirim_protokol.cek_dukungan("HTTP")
    assert http_cek["didukung"] is True

    tcp_cek = pengirim_protokol.cek_dukungan("TCP")
    assert tcp_cek["didukung"] is True

    udp_cek = pengirim_protokol.cek_dukungan("UDP")
    assert udp_cek["didukung"] is True

    icmp_cek = pengirim_protokol.cek_dukungan("ICMP")
    assert "didukung" in icmp_cek

    bad_target = pengirim_protokol.kirim_tcp(host="8.8.8.8", port=80)
    assert bad_target["status"] == "rejected"

    bad_udp = pengirim_protokol.kirim_udp(host="1.1.1.1", port=53)
    assert bad_udp["status"] == "rejected"


def test_guest_protocols_and_activity_options(database: Database) -> None:
    with TestClient(guest_app) as client:
        proto_res = client.get("/api/activity/protocols")
        assert proto_res.status_code == 200
        daftar = proto_res.json()["protocols"]
        assert len(daftar) >= 4
        assert any(item["protokol"] == "HTTP" for item in daftar)
        assert any(item["protokol"] == "TCP" for item in daftar)
        assert any(item["protokol"] == "RANDOM" for item in daftar)

        sesi_res = client.post("/api/session/create", json={})
        assert sesi_res.status_code == 200
        token = sesi_res.json()["session_token"]

        act_res = client.post(
            "/api/activity",
            headers={"Authorization": f"Bearer {token}"},
            json={"scenario": "volume_spike", "batch_count": 5, "mode": "burst", "protocol": "TCP"},
        )
        assert act_res.status_code == 200
        act_data = act_res.json()
        assert act_data["planned_request_count"] == 5
        assert act_data["protocol"] == "TCP"
        assert act_data["mode"] == "burst"


def test_series_includes_pps_bps_rps(database: Database) -> None:
    with TestClient(management_app) as client:
        res = client.get("/api/dashboard/series?seconds=30")
        assert res.status_code == 200
        data = res.json()
        assert "points" in data
        assert len(data["points"]) == 30
        first = data["points"][0]
        assert "pps" in first
        assert "bps" in first
        assert "rps" in first
