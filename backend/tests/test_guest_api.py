from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.guest import routes as guest_routes
from app.guest_app import app as guest_app
from app.management_app import app as management_app
from app.config import settings
from app.modules.alerts.service import alert_service
from app.modules.incidents.service import incident_service
from app.modules.logs.service import log_service
from app.modules.database.service import Database, from_iso
from app.modules.network_sensor import service as sensor_module
from app.modules.sessions.service import session_service
from app.modules.telemetry_pipeline import telemetry_pipeline


def test_guest_probes_are_logged_as_application_events(database: Database) -> None:
    with TestClient(guest_app) as client:
        created = client.post(
            "/api/session/create",
            json={"client_ip": "203.0.113.99", "user_agent": "pytest-agent"},
        )
        assert created.status_code == 200, created.text
        session = created.json()
        token = session["session_token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert session["client_ip"] == "testclient"
        assert session["server_time"]

        plan_response = client.post(
            "/api/activity",
            headers=headers,
            json={"scenario": "volume_spike"},
        )
        assert plan_response.status_code == 200, plan_response.text
        plan = plan_response.json()
        assert plan["planned_request_count"] == 10

        probe_response = client.post(
            "/api/activity/probe",
            headers={**headers, "X-IDS-Activity-Id": plan["activity_id"]},
            json={
                "activity_id": plan["activity_id"],
                "payload": "x" * plan["payload_sizes"][0],
            },
        )
        assert probe_response.status_code == 200, probe_response.text
        assert probe_response.json()["completed_request_count"] == 1

        heartbeat = client.post("/api/session/heartbeat", headers=headers)
        assert heartbeat.status_code == 200, heartbeat.text
        assert heartbeat.json()["cooldown_until"]

    probes = database.fetch_all(
        "SELECT client_ip, session_id, activity_id, request_bytes FROM application_events "
        "WHERE path = '/api/activity/probe'"
    )
    assert len(probes) == 1
    assert probes[0]["client_ip"] == "testclient"
    assert probes[0]["session_id"] == session["session_id"]
    assert probes[0]["activity_id"] == plan["activity_id"]
    assert probes[0]["request_bytes"] > plan["payload_sizes"][0]
    assert database.scalar("SELECT COUNT(*) FROM packet_events") == 0
    latest_event = from_iso(database.scalar(
        "SELECT MAX(observed_at) FROM application_events WHERE path IN "
        "('/api/activity/probe', '/api/session/heartbeat')"
    ))
    assert latest_event is not None
    window_seconds = max(1, settings.analysis_window_seconds)
    window_end = datetime.fromtimestamp(
        (int(latest_event.timestamp()) // window_seconds + 1) * window_seconds,
        timezone.utc,
    )
    features = telemetry_pipeline.analyze_window(window_end)
    assert features is not None
    assert features["request_count"] == 1
    assert features["heartbeat_count"] == 1
    assert features["internal_request_count"] == 0
    assert features["packet_count"] == 0
    assert features["request_size_mean"] > plan["payload_sizes"][0]
    assert features["baseline_status"] == "warming_up"


def test_all_demo_scenarios_have_bounded_real_request_plans() -> None:
    from app.modules.traffic_tests.service import traffic_generator

    plans = {name: traffic_generator.build_activity(name) for name in (
        "volume_spike", "payload_size_variation", "request_frequency"
    )}
    assert set(traffic_generator.scenarios) == set(plans)
    assert plans["volume_spike"]["planned_count"] == 10
    assert len(set(plans["payload_size_variation"]["payload_sizes"])) > 1
    assert plans["request_frequency"]["interval_seconds"] < plans["volume_spike"]["interval_seconds"]
    for plan in plans.values():
        assert len(plan["payload_sizes"]) == plan["planned_count"]
        assert max(plan["payload_sizes"]) <= settings.max_activity_payload_bytes
        assert plan["planned_count"] <= settings.max_activity_requests
        assert (plan["planned_count"] - 1) * plan["interval_seconds"] <= settings.max_activity_duration_seconds


def test_session_cooldown_is_reported_and_enforced(database: Database) -> None:
    with TestClient(guest_app) as client:
        created = client.post("/api/session/create", json={})
        token = created.json()["session_token"]
        session_id = created.json()["session_id"]
        session_service.apply_cooldown(session_id, seconds=20)
        headers = {"Authorization": f"Bearer {token}"}

        current = client.get("/api/session/current", headers=headers)
        assert current.status_code == 200
        assert current.json()["cooldown_until"]
        assert current.json()["server_time"]

        heartbeat = client.post("/api/session/heartbeat", headers=headers)
        assert heartbeat.status_code == 200
        assert heartbeat.json()["cooldown_until"] == current.json()["cooldown_until"]

        blocked = client.post(
            "/api/activity",
            headers=headers,
            json={"scenario": "request_frequency"},
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0

        normal = client.post(
            "/api/activity",
            headers=headers,
            json={"scenario": "normal"},
        )
        assert normal.status_code == 429


def test_normal_scenario_is_not_available_to_visitors(database: Database) -> None:
    with TestClient(guest_app) as client:
        created = client.post("/api/session/create", json={})
        headers = {"Authorization": f"Bearer {created.json()['session_token']}"}
        rejected = client.post("/api/activity", headers=headers, json={"scenario": "normal"})
        assert rejected.status_code == 400
        assert database.scalar("SELECT COUNT(*) FROM activities") == 0


def test_guest_api_does_not_expose_all_active_sessions(database: Database) -> None:
    with TestClient(guest_app) as client:
        response = client.get("/api/session/active")
    assert response.status_code == 404


def test_guest_status_does_not_disclose_management_sensor_details(database: Database) -> None:
    with TestClient(guest_app) as client:
        response = client.get("/api/guest/status")
    assert response.status_code == 200
    data = response.json()
    assert "sensor" not in data
    assert "threat_intel" not in data
    assert data["max_active_sessions"] == settings.max_active_sessions


def test_active_anomaly_plan_applies_cooldown_but_its_probes_can_finish(database: Database) -> None:
    with TestClient(guest_app) as client:
        created = client.post("/api/session/create", json={})
        token = created.json()["session_token"]
        headers = {"Authorization": f"Bearer {token}"}
        plan_response = client.post("/api/activity", headers=headers, json={"scenario": "volume_spike"})
        assert plan_response.status_code == 200, plan_response.text
        plan = plan_response.json()
        assert plan["cooldown_until"]

        probe = client.post(
            "/api/activity/probe",
            headers={**headers, "X-IDS-Activity-Id": plan["activity_id"]},
            json={"activity_id": plan["activity_id"], "payload": "x" * plan["payload_sizes"][0]},
        )
        assert probe.status_code == 200, probe.text

        next_plan = client.post("/api/activity", headers=headers, json={"scenario": "request_frequency"})
        assert next_plan.status_code == 429


def test_management_websocket_reads_persisted_events(database: Database) -> None:
    with TestClient(management_app) as client:
        with client.websocket_connect("/ws/dashboard") as websocket:
            snapshot = websocket.receive_json()
            assert snapshot["type"] == "snapshot"
            assert snapshot["data"]["health"]["database_status"] == "connected"

            telemetry_pipeline.publish_event("test_event", {"value": "persisted"})
            event = websocket.receive_json()
            for _ in range(5):
                if event.get("type") == "test_event":
                    break
                event = websocket.receive_json()
            assert event["type"] == "test_event"
            assert event["data"] == {"value": "persisted"}


def test_sensor_does_not_claim_running_without_npcap(monkeypatch) -> None:
    monkeypatch.setattr(sensor_module.sys, "platform", "win32")
    monkeypatch.setattr(sensor_module, "conf", SimpleNamespace(use_pcap=False))
    monkeypatch.setattr(sensor_module, "AsyncSniffer", lambda **_kwargs: None)
    monkeypatch.setattr(
        telemetry_pipeline,
        "set_component_status",
        lambda *_args, **_kwargs: None,
    )

    with TestClient(management_app) as client:
        response = client.post(
            "/api/sensor/start",
            json={"interface_name": r"\Device\NPF_{test}"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "not_available"
    assert "Npcap" in response.json()["detail"]["message"]


def test_packet_correlation_checks_both_traffic_directions(database: Database) -> None:
    session = session_service.create_session("192.0.2.25", "pytest-agent")

    telemetry_pipeline.record_packet({
        "timestamp": session["started_at"],
        "source_ip": "192.0.2.1",
        "destination_ip": "192.0.2.25",
        "protocol": "TCP",
        "packet_length": 128,
    })

    packet = database.fetch_one("SELECT session_id, correlation_method FROM packet_events")
    assert packet["session_id"] == session["session_id"]
    assert packet["correlation_method"] == "client_ip_session_time"


def test_management_logs_and_incidents_are_persisted(database: Database) -> None:
    session = session_service.create_session("192.0.2.40", "pytest-agent")
    detection_id = "detection-test-001"
    created_at = "2026-11-18T00:00:00.000Z"
    database.execute(
        "INSERT INTO detections (id, session_id, activity_id, created_at, source, rule_id, label, severity, score, model_version, rules_version, feature_json, reason, status) "
        "VALUES (?, ?, NULL, ?, 'rule', 'packet-rate-spike', 'Peningkatan packet rate', 'high', 12.0, NULL, 'test', '{}', 'Packet rate melewati batas.', 'open')",
        (detection_id, session["session_id"], created_at),
    )
    incident = incident_service.create_for_detection({
        "id": detection_id,
        "severity": "high",
    })
    assert incident is not None
    assert incident["ticket_code"] == session["ticket_code"]

    log_service.info("pytest", "integration_test", "Log integration tersimpan.", {"test": True})

    with TestClient(management_app) as client:
        logs_response = client.get("/api/logs?component=pytest")
        incidents_response = client.get("/api/incidents")
        assert logs_response.status_code == 200
        assert logs_response.json()["total"] == 1
        assert logs_response.json()["items"][0]["details"] == {"test": True}
        assert incidents_response.status_code == 200
        assert any(row["detection_id"] == detection_id for row in incidents_response.json()["items"])

        updated = client.patch(f"/api/incidents/{incident['id']}", json={"status": "investigating"})
        assert updated.status_code == 200
        assert updated.json()["status"] == "investigating"

        invalid = client.patch(f"/api/incidents/{incident['id']}", json={"status": "closed"})
        assert invalid.status_code == 400


def test_management_api_returns_dashboard_snapshot_without_placeholder_values(database: Database) -> None:
    session = session_service.create_session("192.0.2.41", "pytest-agent")
    with TestClient(management_app) as client:
        response = client.get("/api/dashboard/snapshot")
        assert response.status_code == 200
        snapshot = response.json()
        assert snapshot["overview"]["active_sessions"] == 1
        assert snapshot["health"]["database_status"] == "connected"
        assert snapshot["ai"]["status"] in {"disabled", "model_unavailable", "assets_missing_or_invalid", "not_configured", "waiting_for_flow_features", "assets_ready"}
        assert isinstance(snapshot["traffic"], list)
        assert isinstance(snapshot["windows"], list)


def test_ai_service_respects_disabled_configuration() -> None:
    from app.modules.ai_integration.service import Service

    status = Service().status()
    assert status["enabled"] is False
    assert status["status"] == "disabled"
    result = Service().predict_flow({})
    assert result["status"] == "disabled"


def test_maximum_active_sessions_is_enforced(database: Database) -> None:
    with TestClient(guest_app) as client:
        created = [client.post("/api/session/create", json={}) for _ in range(settings.max_active_sessions)]
        assert all(response.status_code == 200 for response in created)
        rejected = client.post("/api/session/create", json={})
        assert rejected.status_code == 409
        assert "Maksimal sesi aktif" in rejected.json()["detail"]


def test_analyzer_creates_session_linked_detection_from_probe_events(database: Database) -> None:
    session = session_service.create_session("192.0.2.55", "pytest-agent")
    activity_id = "activity-frequency-001"
    now = datetime.now(timezone.utc)
    window_seconds = max(1, settings.analysis_window_seconds)
    end_epoch = int(now.timestamp() // window_seconds) * window_seconds
    window_end = datetime.fromtimestamp(end_epoch, timezone.utc)
    window_start = window_end.timestamp() - window_seconds
    start_iso = datetime.fromtimestamp(window_start, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    end_iso = window_end.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    database.execute(
        "INSERT INTO activities (id, session_id, scenario, status, created_at, started_at, finished_at, request_count, planned_count, metadata_json) "
        "VALUES (?, ?, 'request_frequency', 'completed', ?, ?, ?, 12, 12, '{}')",
        (activity_id, session["session_id"], start_iso, start_iso, end_iso),
    )

    for index in range(12):
        observed = datetime.fromtimestamp(window_start + 1 + index * 0.08, timezone.utc)
        database.execute(
            "INSERT INTO application_events (observed_at, method, path, status_code, client_ip, request_bytes, response_bytes, duration_ms, origin, session_id, activity_id) "
            "VALUES (?, 'POST', '/api/activity/probe', 200, ?, 512, 24, 5.0, 'guest', ?, ?)",
            (observed.isoformat(timespec="milliseconds").replace("+00:00", "Z"), session["client_ip"], session["session_id"], activity_id),
        )

    features = telemetry_pipeline.analyze_window(window_end)
    assert features is not None
    assert features["request_count"] == 12
    assert features["request_rate"] >= 2.5

    detections = database.fetch_all(
        "SELECT session_id, activity_id, rule_id, severity FROM detections WHERE session_id = ?",
        (session["session_id"],),
    )
    assert any(row["activity_id"] == activity_id and row["rule_id"] == "request-rate-spike" and row["severity"] == "high" for row in detections)
    assert database.scalar("SELECT COUNT(*) FROM alerts") >= 1
    assert database.scalar("SELECT COUNT(*) FROM incidents") >= 1


def test_activity_status_and_cancel_are_scoped_to_owner(database: Database) -> None:
    with TestClient(guest_app) as client:
        first = client.post("/api/session/create", json={}).json()
        second = client.post("/api/session/create", json={}).json()
        first_headers = {"Authorization": f"Bearer {first['session_token']}"}
        second_headers = {"Authorization": f"Bearer {second['session_token']}"}

        plan = client.post(
            "/api/activity",
            headers=first_headers,
            json={"scenario": "volume_spike"},
        )
        assert plan.status_code == 200
        activity_id = plan.json()["activity_id"]

        own_status = client.get(f"/api/activity/{activity_id}", headers=first_headers)
        assert own_status.status_code == 200
        assert own_status.json()["status"] == "running"

        foreign_status = client.get(f"/api/activity/{activity_id}", headers=second_headers)
        assert foreign_status.status_code == 404

        foreign_cancel = client.post(f"/api/activity/{activity_id}/cancel", headers=second_headers)
        assert foreign_cancel.status_code == 404

        own_cancel = client.post(f"/api/activity/{activity_id}/cancel", headers=first_headers)
        assert own_cancel.status_code == 200
        assert own_cancel.json()["status"] == "cancelled"

        final_status = client.get(f"/api/activity/{activity_id}", headers=first_headers)
        assert final_status.status_code == 200
        assert final_status.json()["status"] == "cancelled"
