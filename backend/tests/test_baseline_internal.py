from __future__ import annotations

import asyncio
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.config import INTERNAL_BASELINE_PATH, settings
from app.guest_app import app as guest_app
from app.management_app import app as management_app
from app.modules.baseline.service import baseline_service
from app.modules.database.service import Database, to_iso
from app.modules.lalu_lintas_internal import pembangkit as modul_pembangkit
from app.modules.lalu_lintas_internal.pembangkit import HEADER_KUNCI, PembangkitBaseline, pembangkit_baseline
from app.modules.sessions.service import session_service
from app.modules.telemetry_pipeline import telemetry_pipeline


def _iso(epoch: float) -> str:
    return to_iso(datetime.fromtimestamp(epoch, timezone.utc))


def _sisipkan_internal(database: Database, epoch: float, jumlah: int = 30) -> None:
    for index in range(jumlah):
        database.execute(
            "INSERT INTO application_events (observed_at, method, path, status_code, client_ip, request_bytes, response_bytes, duration_ms, origin) "
            "VALUES (?, 'POST', ?, 200, '127.0.0.1', 160, 30, 2.0, 'internal_baseline')",
            (_iso(epoch + index * 0.3), INTERNAL_BASELINE_PATH),
        )


def _awal_window(offset: int) -> float:
    window = max(1, settings.analysis_window_seconds)
    return (int(time.time() // window) - offset) * window


def test_internal_endpoint_rejects_requests_that_are_not_local(database: Database) -> None:
    with TestClient(guest_app) as client:
        response = client.post(INTERNAL_BASELINE_PATH, json={"seq": 1}, headers={HEADER_KUNCI: pembangkit_baseline.kunci})
    assert response.status_code == 403
    assert database.scalar("SELECT COUNT(*) FROM application_events WHERE origin = 'internal_baseline'") == 0


def test_internal_endpoint_requires_the_process_key(database: Database, monkeypatch) -> None:
    monkeypatch.setattr(modul_pembangkit, "HOST_LOOPBACK", {"testclient"})
    with TestClient(guest_app) as client:
        tanpa_kunci = client.post(INTERNAL_BASELINE_PATH, json={"seq": 1})
        kunci_salah = client.post(INTERNAL_BASELINE_PATH, json={"seq": 1}, headers={HEADER_KUNCI: "salah"})
    assert tanpa_kunci.status_code == 403
    assert kunci_salah.status_code == 403
    assert database.scalar("SELECT COUNT(*) FROM application_events WHERE origin = 'internal_baseline'") == 0


def test_internal_request_is_logged_as_internal_baseline_not_visitor(database: Database, monkeypatch) -> None:
    monkeypatch.setattr(modul_pembangkit, "HOST_LOOPBACK", {"testclient"})
    with TestClient(guest_app) as client:
        response = client.post(INTERNAL_BASELINE_PATH, json={"seq": 7, "payload": "x" * 128}, headers={HEADER_KUNCI: pembangkit_baseline.kunci})
    assert response.status_code == 200
    row = database.fetch_one("SELECT origin, session_id, activity_id, request_bytes, status_code FROM application_events")
    assert row["origin"] == "internal_baseline"
    assert row["session_id"] is None and row["activity_id"] is None
    assert row["request_bytes"] > 128 and row["status_code"] == 200
    assert database.scalar("SELECT COUNT(*) FROM sessions") == 0
    assert session_service.count_active_sessions() == 0


def test_internal_traffic_builds_baseline_without_detection_or_alert(database: Database) -> None:
    for offset in (4, 3, 2):
        _sisipkan_internal(database, _awal_window(offset) + 1)
        telemetry_pipeline.analyze_window(datetime.fromtimestamp(_awal_window(offset - 1) + 1, timezone.utc))
    baseline = baseline_service.state("global")
    assert baseline["status"] == "ready"
    assert baseline["features"]["internal_request_rate"] == pytest.approx(3.0, abs=0.2)
    assert database.scalar("SELECT COUNT(*) FROM detections") == 0
    assert database.scalar("SELECT COUNT(*) FROM alerts") == 0
    window = database.fetch_one("SELECT feature_json FROM traffic_windows WHERE scope = 'global' ORDER BY id DESC")
    assert window is not None
    assert database.scalar("SELECT COUNT(*) FROM traffic_windows WHERE scope = 'session'") == 0


def test_visitor_heartbeats_and_internal_traffic_are_not_anomalies(database: Database) -> None:
    session = session_service.create_session("192.0.2.70", "pytest-agent")
    inicio = _awal_window(2)
    database.execute("UPDATE sessions SET started_at = ?, expires_at = ? WHERE id = ?", (_iso(inicio - 5), _iso(inicio + 300), session["session_id"]))
    _sisipkan_internal(database, inicio + 1)
    for index in range(3):
        database.execute(
            "INSERT INTO application_events (observed_at, method, path, status_code, client_ip, request_bytes, response_bytes, duration_ms, origin, session_id) "
            "VALUES (?, 'POST', '/api/session/heartbeat', 200, '192.0.2.70', 0, 32, 2.0, 'guest', ?)",
            (_iso(inicio + 1 + index * 3), session["session_id"]),
        )
    features = telemetry_pipeline.analyze_window(datetime.fromtimestamp(_awal_window(1) + 1, timezone.utc))
    assert features["heartbeat_count"] == 3
    assert features["internal_request_count"] == 30
    assert features["request_count"] == 0
    assert database.scalar("SELECT COUNT(*) FROM detections") == 0


def _sisipkan_probe(database: Database, session: dict, activity_id: str, awal: float, jumlah: int, jeda: float, ukuran: int) -> None:
    database.execute(
        "INSERT INTO activities (id, session_id, scenario, status, created_at, started_at, request_count, planned_count, metadata_json) "
        "VALUES (?, ?, 'request_frequency', 'completed', ?, ?, ?, ?, '{}')",
        (activity_id, session["session_id"], _iso(awal), _iso(awal), jumlah, jumlah),
    )
    for index in range(jumlah):
        database.execute(
            "INSERT INTO application_events (observed_at, method, path, status_code, client_ip, request_bytes, response_bytes, duration_ms, origin, session_id, activity_id) "
            "VALUES (?, 'POST', '/api/activity/probe', 200, ?, ?, 24, 5.0, 'guest', ?, ?)",
            (_iso(awal + index * jeda), session["client_ip"], ukuran, session["session_id"], activity_id),
        )


def test_concurrent_visitors_keep_separate_detection_identity(database: Database) -> None:
    pelaku = session_service.create_session("192.0.2.81", "pytest-agent")
    tenang = session_service.create_session("192.0.2.82", "pytest-agent")
    awal = _awal_window(2)
    for sesi in (pelaku, tenang):
        database.execute("UPDATE sessions SET started_at = ?, expires_at = ? WHERE id = ?", (_iso(awal - 5), _iso(awal + 300), sesi["session_id"]))
    _sisipkan_probe(database, pelaku, "aktivitas-pelaku", awal + 1, 12, 0.1, 128)
    _sisipkan_probe(database, tenang, "aktivitas-tenang", awal + 1, 1, 1.0, 64)
    _sisipkan_internal(database, awal + 1)

    telemetry_pipeline.analyze_window(datetime.fromtimestamp(_awal_window(1) + 1, timezone.utc))

    rows = database.fetch_all("SELECT session_id, activity_id, rule_id FROM detections")
    assert rows
    assert {row["session_id"] for row in rows} == {pelaku["session_id"]}
    assert {row["activity_id"] for row in rows} == {"aktivitas-pelaku"}


def test_detection_can_be_traced_to_source_events(database: Database) -> None:
    sesi = session_service.create_session("192.0.2.90", "pytest-agent")
    awal = _awal_window(2)
    database.execute("UPDATE sessions SET started_at = ?, expires_at = ? WHERE id = ?", (_iso(awal - 5), _iso(awal + 300), sesi["session_id"]))
    _sisipkan_probe(database, sesi, "aktivitas-jejak", awal + 1, 12, 0.1, 128)
    telemetry_pipeline.analyze_window(datetime.fromtimestamp(_awal_window(1) + 1, timezone.utc))
    detection_id = database.scalar("SELECT id FROM detections WHERE rule_id = 'request-rate-spike'")
    assert detection_id

    with TestClient(management_app) as client:
        response = client.get(f"/api/detections/{detection_id}")
        missing = client.get("/api/detections/tidak-ada")
    assert missing.status_code == 404
    bukti = response.json()
    assert bukti["ticket"] == sesi["ticket_code"]
    assert bukti["activity_id"] == "aktivitas-jejak"
    assert len(bukti["application_events"]) == 12
    assert all(item["origin"] == "guest" for item in bukti["application_events"])
    assert bukti["features"]["window_start"] and bukti["measured_value"] >= settings.rule_request_rate_warning


def test_series_reports_real_counts_per_second(database: Database) -> None:
    sekarang = datetime.fromtimestamp(int(time.time()) + 1, timezone.utc)
    dasar = sekarang.timestamp() - 5
    _sisipkan_internal(database, dasar + 0.05, jumlah=3)
    database.execute(
        "INSERT INTO packet_events (observed_at, source_ip, destination_ip, protocol, packet_length) VALUES (?, '192.0.2.1', '192.0.2.2', 'TCP', 100)",
        (_iso(dasar + 0.5),),
    )
    with TestClient(management_app) as client:
        data = client.get("/api/dashboard/series?seconds=30").json()
    assert data["seconds"] == 30 and len(data["points"]) == 30
    assert data["has_events"] is True
    assert sum(point["internal"] for point in data["points"]) == 3
    assert sum(point["packets"] for point in data["points"]) == 1
    assert sum(point["visitor"] for point in data["points"]) == 0


def test_snapshot_marks_origin_and_reports_normal_condition(database: Database) -> None:
    _sisipkan_internal(database, time.time() - 3, jumlah=3)
    with TestClient(management_app) as client:
        snapshot = client.get("/api/dashboard/snapshot").json()
    assert snapshot["traffic_condition"]["label"] in {"Normal", "Menunggu traffic"}
    assert {item["origin"] for item in snapshot["application_events"]} == {"internal_baseline"}
    assert snapshot["internal_baseline"]["received_10s"] == 3
    assert snapshot["detections"] == []


def _port_bebas() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_generator_sends_about_three_requests_per_second_and_stops_cleanly(database: Database) -> None:
    port = _port_bebas()
    server = uvicorn.Server(uvicorn.Config(guest_app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    batas = time.time() + 10
    while not server.started and time.time() < batas:
        time.sleep(0.05)
    assert server.started

    generator = PembangkitBaseline()
    generator.kunci = pembangkit_baseline.kunci

    async def jalankan() -> tuple[float, int, bool]:
        assert generator.mulai(port) is True
        assert generator.mulai(port) is False
        await asyncio.sleep(2.0)
        awal_hitung, awal_waktu = generator.berhasil, time.monotonic()
        await asyncio.sleep(5.0)
        laju = (generator.berhasil - awal_hitung) / (time.monotonic() - awal_waktu)
        await generator.henti()
        return laju, generator.berhasil, generator.aktif

    try:
        laju, berhasil, aktif = asyncio.run(jalankan())
        diterima = database.scalar("SELECT COUNT(*) FROM application_events WHERE origin = 'internal_baseline' AND status_code = 200")
        time.sleep(0.8)
        setelah_berhenti = database.scalar("SELECT COUNT(*) FROM application_events WHERE origin = 'internal_baseline'")
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    assert aktif is False
    assert 2.7 <= laju <= 3.3
    assert diterima == berhasil
    assert setelah_berhenti == diterima
    assert generator.gagal == 0
    assert database.scalar("SELECT COUNT(*) FROM sessions") == 0
