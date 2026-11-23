from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.config import GUEST_ORIGIN, HEARTBEAT_PATH, INTERNAL_ORIGIN, PROBE_PATH, settings
from app.modules.alerts.service import alert_service
from app.modules.baseline.service import baseline_service
from app.modules.database.service import Database, default_database, dumps, from_iso, loads, to_iso, utc_now
from app.modules.detection.service import detection_service
from app.modules.fitur_traffic import bangun_fitur
from app.modules.incidents.service import incident_service
from app.modules.kondisi_traffic import (
    STATUS_ABOVE_BASELINE,
    STATUS_ANOMALOUS,
    STATUS_NORMAL,
    STATUS_RECOVERING,
    pengelola_kondisi,
)
from app.modules.logs.service import log_service

PUBLISHED_PATH_PREFIX = "/api/"
UNPUBLISHED_PATHS = {"/api/health", "/api/guest/status"}


class TelemetryPipeline:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database
        self._last_retention_ts = 0.0
        self.database.connect()

    def _publish_locked(self, connection: Any, event_type: str, data: dict[str, Any]) -> int:
        cursor = connection.execute(
            "INSERT INTO dashboard_events (created_at, event_type, data_json) VALUES (?, ?, ?)",
            (to_iso(utc_now()), event_type, dumps(data)),
        )
        return int(cursor.lastrowid)

    def _publish(self, event_type: str, data: dict[str, Any]) -> int:
        with self.database.transaction() as connection:
            return self._publish_locked(connection, event_type, data)

    def publish_event(self, event_type: str, data: dict[str, Any]) -> int:
        return self._publish(event_type, data)

    def set_component_status(self, component: str, status: str, message: str) -> None:
        previous = self.database.fetch_one(
            "SELECT status, message FROM component_status WHERE component = ?",
            (component,),
        )
        self.database.execute(
            "INSERT INTO component_status (component, status, message, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(component) DO UPDATE SET status = excluded.status, message = excluded.message, "
            "updated_at = excluded.updated_at",
            (component, status, message, to_iso(utc_now())),
        )
        if previous is None or previous["status"] != status or previous["message"] != message:
            level = "error" if status == "error" else "warning" if status in {"stopped", "not_configured", "not_available"} else "info"
            log_service.write(level, component, "component_status", message, {"status": status})
        self._publish("health", {"component": component, "status": status, "message": message})

    def record_application_event(
        self,
        method: str,
        path: str,
        status_code: int,
        client_ip: str | None,
        request_bytes: int,
        response_bytes: int,
        duration_ms: float,
        session_token: str | None = None,
        activity_id: str | None = None,
        origin: str = GUEST_ORIGIN,
        client_port: int | None = None,
        server_ip: str | None = None,
        server_port: int | None = None,
    ) -> int:
        session = None
        if origin == INTERNAL_ORIGIN:
            session_token = None
        if session_token:
            import hashlib

            session = self.database.fetch_one(
                "SELECT id FROM sessions WHERE session_token_hash = ? AND status = 'active' AND expires_at > ?",
                (
                    hashlib.sha256(session_token.encode("utf-8")).hexdigest(),
                    to_iso(utc_now()),
                ),
            )
        session_id = session["id"] if session else None
        if activity_id and session_id:
            activity = self.database.fetch_one(
                "SELECT id FROM activities WHERE id = ? AND session_id = ?",
                (activity_id, session_id),
            )
            if activity is None:
                activity_id = None
        else:
            activity_id = None

        observed_at = to_iso(utc_now())
        data = {
            "id": None,
            "timestamp": observed_at,
            "method": method,
            "path": path,
            "status_code": int(status_code),
            "client_ip": client_ip,
            "source_port": client_port,
            "destination_ip": server_ip,
            "destination_port": server_port,
            "request_bytes": max(0, int(request_bytes)),
            "response_bytes": max(0, int(response_bytes)),
            "duration_ms": round(max(0.0, float(duration_ms)), 3),
            "origin": origin,
            "ticket": None,
        }
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO application_events "
                "(observed_at, method, path, status_code, client_ip, request_bytes, response_bytes, duration_ms, "
                "origin, session_id, activity_id, source_port, destination_ip, destination_port) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    observed_at,
                    method,
                    path,
                    int(status_code),
                    client_ip,
                    data["request_bytes"],
                    data["response_bytes"],
                    data["duration_ms"],
                    origin,
                    session_id,
                    activity_id,
                    client_port,
                    server_ip,
                    server_port,
                ),
            )
            event_id = int(cursor.lastrowid)
            if path.startswith(PUBLISHED_PATH_PREFIX) and path not in UNPUBLISHED_PATHS:
                data["id"] = event_id
                if session_id:
                    row = connection.execute("SELECT ticket_code FROM sessions WHERE id = ?", (session_id,)).fetchone()
                    data["ticket"] = row[0] if row else None
                self._publish_locked(connection, "application_event", data)
        return event_id

    def record_packet(self, packet: dict[str, Any]) -> int:
        observed_at = packet.get("timestamp") or to_iso(utc_now())
        session_id = packet.get("session_id")
        activity_id = packet.get("activity_id")
        correlation_method = "direct_probe_correlation" if session_id else None
        if not session_id:
            candidate_ips = {
                ip for ip in (packet.get("source_ip"), packet.get("destination_ip")) if ip
            }
            if candidate_ips:
                placeholders = ",".join("?" for _ in candidate_ips)
                sessions = self.database.fetch_all(
                    f"SELECT id FROM sessions WHERE client_ip IN ({placeholders}) "
                    "AND status = 'active' AND started_at <= ? AND expires_at > ?",
                    (*candidate_ips, observed_at, observed_at),
                )
                if len(sessions) == 1:
                    session_id = sessions[0]["id"]
                    correlation_method = "client_ip_session_time"
                    activities = self.database.fetch_all(
                        "SELECT id FROM activities WHERE session_id = ? AND status = 'running' "
                        "AND started_at <= ? ORDER BY started_at DESC LIMIT 2",
                        (session_id, observed_at),
                    )
                    if len(activities) == 1:
                        activity_id = activities[0]["id"]
                        correlation_method = "client_ip_active_activity_time"

        values = (
            observed_at,
            packet.get("interface_name"),
            packet.get("source_ip"),
            packet.get("destination_ip"),
            str(packet.get("protocol") or "OTHER").upper(),
            packet.get("source_port"),
            packet.get("destination_port"),
            max(0, int(packet.get("packet_length") or 0)),
            packet.get("tcp_flags"),
            session_id,
            activity_id,
            correlation_method,
        )
        row = {
            "timestamp": observed_at,
            "source": packet.get("source_ip") or "-",
            "destination": packet.get("destination_ip") or "-",
            "protocol": str(packet.get("protocol") or "OTHER").upper(),
            "source_port": packet.get("source_port"),
            "destination_port": packet.get("destination_port"),
            "size_bytes": values[7],
            "ticket": None,
            "correlation_method": correlation_method,
        }
        if session_id:
            session = self.database.fetch_one("SELECT ticket_code FROM sessions WHERE id = ?", (session_id,))
            row["ticket"] = session["ticket_code"] if session else None
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO packet_events "
                "(observed_at, interface_name, source_ip, destination_ip, protocol, source_port, destination_port, "
                "packet_length, tcp_flags, session_id, activity_id, correlation_method) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            row["id"] = int(cursor.lastrowid)
            row["tcp_flags"] = packet.get("tcp_flags")
            self._publish_locked(connection, "packet", row)
        return 1

    def _persist_findings(
        self,
        findings: list[dict[str, Any]],
        window_start: str,
        window_end: str,
        session_id: str | None,
        activity_ids: set[str],
    ) -> list[dict[str, Any]]:
        if not findings:
            return []
        linked_activity = next(iter(activity_ids)) if len(activity_ids) == 1 else None
        rows: list[dict[str, Any]] = []
        with self.database.transaction() as connection:
            for finding in findings:
                detection_id = uuid4().hex
                evidence = {**finding["features"], "window_start": window_start, "window_end": window_end}
                detection = {
                    "id": detection_id,
                    "session_id": session_id,
                    "activity_id": linked_activity,
                    "created_at": window_end,
                    "source": "rule",
                    "rule_id": finding["rule_id"],
                    "label": finding["label"],
                    "severity": finding["severity"],
                    "score": finding["score"],
                    "model_version": None,
                    "rules_version": settings.rules_version,
                    "feature_json": dumps(evidence),
                    "reason": finding["reason"],
                    "status": "open",
                }
                connection.execute(
                    "INSERT INTO detections (id, session_id, activity_id, created_at, source, rule_id, label, severity, score, model_version, rules_version, feature_json, reason, status) "
                    "VALUES (?, ?, ?, ?, 'rule', ?, ?, ?, ?, NULL, ?, ?, ?, 'open')",
                    (detection_id, session_id, linked_activity, window_end, finding["rule_id"], finding["label"], finding["severity"], finding["score"], settings.rules_version, detection["feature_json"], finding["reason"]),
                )
                ticket = None
                if session_id:
                    session_row = connection.execute("SELECT ticket_code FROM sessions WHERE id = ?", (session_id,)).fetchone()
                    ticket = session_row[0] if session_row else None
                self._publish_locked(connection, "detection", {
                    "id": detection_id,
                    "timestamp": window_end,
                    "title": finding["label"],
                    "category": finding["rule_id"],
                    "severity": finding["severity"],
                    "reason": finding["reason"],
                    "ticket": ticket,
                    "source": "rule",
                })
                rows.append(detection)
        for row in rows:
            alert = alert_service.create_for_detection(row)
            if alert:
                self._publish("alert", alert)
            incident = incident_service.create_for_detection(row)
            if incident:
                self._publish("incident", incident)
            log_service.write(
                "error" if row["severity"] == "high" else "warning",
                "detection",
                row["rule_id"],
                row["reason"],
                {"detection_id": row["id"], "session_id": row["session_id"], "activity_id": row["activity_id"]},
            )
        return rows

    def analyze_window(self, now: datetime | None = None) -> dict[str, Any] | None:
        self.expire_sessions()
        current = now or utc_now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        window_seconds = max(1, settings.analysis_window_seconds)
        end_epoch = math.floor(current.timestamp() / window_seconds) * window_seconds
        end = datetime.fromtimestamp(end_epoch, timezone.utc)
        start = end - timedelta(seconds=window_seconds)
        start_iso = to_iso(start)
        end_iso = to_iso(end)
        existing = self.database.fetch_one(
            "SELECT feature_json FROM traffic_windows WHERE scope = 'global' AND window_start = ?",
            (start_iso,),
        )
        if existing:
            return loads(existing["feature_json"])

        app_events = self.database.fetch_all(
            "SELECT * FROM application_events "
            "WHERE (path LIKE '/api/activity/probe%' OR path = ? OR origin = ?) AND observed_at >= ? AND observed_at < ? ORDER BY observed_at",
            (HEARTBEAT_PATH, INTERNAL_ORIGIN, start_iso, end_iso),
        )
        packets = self.database.fetch_all(
            "SELECT * FROM packet_events WHERE observed_at >= ? AND observed_at < ? ORDER BY observed_at",
            (start_iso, end_iso),
        )
        features = bangun_fitur(app_events, packets, start_iso, end_iso, window_seconds)
        visitor_events = [row for row in app_events if row.get("origin") != INTERNAL_ORIGIN]
        session_ids = {
            row["session_id"] for row in visitor_events + packets if row.get("session_id")
        }
        features["session_count"] = len(session_ids)
        global_baseline = baseline_service.state("global")
        global_findings = detection_service.evaluate(features, global_baseline, allowed_rules={"packet-rate-spike"})
        if not global_findings and features["request_count"] == 0:
            global_baseline = baseline_service.observe(features, start_iso, end_iso, "global")
        features["baseline_status"] = global_baseline["status"]
        features["baseline_samples"] = global_baseline["sample_count"]
        features["baseline_version"] = global_baseline["version"]

        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO traffic_windows (window_start, window_end, scope, session_id, status, feature_json, baseline_version) VALUES (?, ?, 'global', NULL, ?, ?, ?)",
                (start_iso, end_iso, "analyzed" if app_events or packets else "waiting_for_data", dumps(features), global_baseline["version"]),
            )
            self._publish_locked(connection, "traffic_window", features)

        self._persist_findings(global_findings, start_iso, end_iso, None, set())

        for session_id in sorted(session_ids):
            session_app = [row for row in visitor_events if row.get("session_id") == session_id]
            session_packets = [row for row in packets if row.get("session_id") == session_id]
            if not session_app and not session_packets:
                continue
            session_features = bangun_fitur(session_app, session_packets, start_iso, end_iso, window_seconds)
            session_features["session_id"] = session_id
            session_findings = detection_service.evaluate(
                session_features,
                {},
                allowed_rules={"request-rate-spike", "request-size-variation", "bytes-rate-spike"},
            )
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO traffic_windows (window_start, window_end, scope, session_id, status, feature_json, baseline_version) VALUES (?, ?, 'session', ?, ?, ?, ?)",
                    (start_iso, end_iso, session_id, "analyzed", dumps(session_features), global_baseline["version"]),
                )
            activity_ids = {row["activity_id"] for row in session_app if row.get("activity_id")}
            self._persist_findings(session_findings, start_iso, end_iso, session_id, activity_ids)

        if current.timestamp() - self._last_retention_ts >= 300:
            self._last_retention_ts = current.timestamp()
            self.database.apply_retention(settings.retention_hours, settings.log_retention_days)
        return features

    def events_after(self, event_id: int, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            "SELECT id, created_at, event_type, data_json FROM dashboard_events WHERE id > ? ORDER BY id LIMIT ?",
            (max(0, int(event_id)), max(1, min(int(limit), 500))),
        )
        return [
            {
                "event_id": row["id"],
                "timestamp": row["created_at"],
                "type": row["event_type"],
                "data": loads(row["data_json"]),
            }
            for row in rows
        ]

    def expire_sessions(self) -> int:
        now = utc_now()
        expired = self.database.fetch_all(
            "SELECT id, ticket_code FROM sessions WHERE status = 'active' AND expires_at <= ?",
            (to_iso(now),),
        )
        if not expired:
            return 0
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE sessions SET status = 'expired', ended_at = ?, end_reason = 'expired' "
                "WHERE status = 'active' AND expires_at <= ?",
                (to_iso(now), to_iso(now)),
            )
            for session in expired:
                self._publish_locked(connection, "session", {
                    "ticket": session["ticket_code"],
                    "status": "expired",
                })
        return len(expired)

    def latest_event_id(self) -> int:
        return int(self.database.scalar("SELECT COALESCE(MAX(id), 0) FROM dashboard_events") or 0)

    def history(self, minutes: int = 60) -> list[dict[str, Any]]:
        cutoff = to_iso(utc_now() - timedelta(minutes=max(1, min(minutes, 1440))))
        rows = self.database.fetch_all(
            "SELECT window_start, window_end, status, feature_json, baseline_version "
            "FROM traffic_windows WHERE scope = 'global' AND window_end >= ? ORDER BY window_end",
            (cutoff,),
        )
        return [
            {
                "window_start": row["window_start"],
                "window_end": row["window_end"],
                "status": row["status"],
                "baseline_version": row["baseline_version"],
                "features": loads(row["feature_json"]),
            }
            for row in rows
        ]

    def internal_baseline_status(self, component: dict[str, Any] | None = None) -> dict[str, Any]:
        cutoff = to_iso(utc_now() - timedelta(seconds=10))
        row = self.database.fetch_one(
            "SELECT COUNT(*) AS total, MAX(observed_at) AS last_at FROM application_events "
            "WHERE origin = ? AND status_code < 400 AND observed_at >= ?",
            (INTERNAL_ORIGIN, cutoff),
        ) or {"total": 0, "last_at": None}
        total = int(row["total"] or 0)
        return {
            "status": (component or {}).get("status", "stopped"),
            "target_rate": settings.internal_baseline_rate,
            "measured_rate": round(total / 10, 2),
            "received_10s": total,
            "last_event_at": row["last_at"],
        }

    @staticmethod
    def _ai_status() -> dict[str, Any]:
        try:
            from app.modules.ai_integration.service import Service
            return Service().status()
        except Exception as exc:
            return {"status": "not_configured", "integration_status": "waiting_for_flow_features", "message": str(exc)}

    def snapshot(self) -> dict[str, Any]:
        self.database.connect()
        self.expire_sessions()
        now = to_iso(utc_now())
        recent_cutoff = to_iso(utc_now() - timedelta(seconds=10))
        total_packets = int(self.database.scalar("SELECT COUNT(*) FROM packet_events") or 0)
        recent_packets = int(
            self.database.scalar("SELECT COUNT(*) FROM packet_events WHERE observed_at >= ?", (recent_cutoff,)) or 0
        )
        active_sessions = self.database.fetch_all(
            "SELECT ticket_code, client_ip, started_at, expires_at, status FROM sessions "
            "WHERE status = 'active' AND expires_at > ? ORDER BY started_at DESC",
            (now,),
        )
        packets = self.database.fetch_all(
            "SELECT p.id, p.observed_at, p.source_ip, p.destination_ip, p.protocol, p.source_port, "
            "p.destination_port, p.packet_length, p.tcp_flags, p.session_id, p.correlation_method, s.ticket_code "
            "FROM packet_events p LEFT JOIN sessions s ON s.id = p.session_id "
            "ORDER BY p.id DESC LIMIT ?",
            (settings.live_traffic_buffer_size,),
        )
        application_events = self.database.fetch_all(
            "SELECT ae.id, ae.observed_at, ae.method, ae.path, ae.status_code, ae.client_ip, ae.source_port, "
            "ae.destination_ip, ae.destination_port, ae.request_bytes, ae.response_bytes, ae.duration_ms, ae.origin, "
            "ae.session_id, ae.activity_id, s.ticket_code "
            "FROM application_events ae LEFT JOIN sessions s ON s.id = ae.session_id "
            "WHERE ae.path LIKE '/api/%' AND ae.path NOT IN ('/api/health', '/api/guest/status') "
            "ORDER BY ae.id DESC LIMIT ?",
            (settings.live_traffic_buffer_size,),
        )
        detections = self.database.fetch_all(
            "SELECT d.id, d.created_at, d.rule_id, d.label, d.severity, d.reason, d.score, d.session_id, d.activity_id, d.source, s.ticket_code "
            "FROM detections d LEFT JOIN sessions s ON s.id = d.session_id ORDER BY d.created_at DESC LIMIT 100",
        )
        alerts = alert_service.list_recent(100)
        windows = self.history(60)
        components = {
            row["component"]: {"status": row["status"], "message": row["message"], "updated_at": row["updated_at"]}
            for row in self.database.fetch_all("SELECT * FROM component_status")
        }
        active_activity_count = int(
            self.database.scalar("SELECT COUNT(*) FROM activities WHERE status = 'running'") or 0
        )
        all_application_events = int(
            self.database.scalar("SELECT COUNT(*) FROM application_events WHERE observed_at >= ?", (recent_cutoff,)) or 0
        )
        latest_window = windows[-1]["features"] if windows else {}
        baseline = baseline_service.state("global")
        condition_cutoff = to_iso(utc_now() - timedelta(seconds=settings.analysis_window_seconds * 3))
        recent_detections = self.database.fetch_all(
            "SELECT d.label, d.severity, d.reason, d.score, s.ticket_code "
            "FROM detections d LEFT JOIN sessions s ON s.id = d.session_id "
            "WHERE d.created_at >= ? ORDER BY d.created_at DESC",
            (condition_cutoff,),
        )
        severities = {r["severity"] for r in recent_detections}
        recent_10s = to_iso(utc_now() - timedelta(seconds=10))
        recent_visitor_10s = int(self.database.scalar(
            "SELECT COUNT(*) FROM application_events WHERE origin != ? AND path LIKE '/api/activity/probe%' AND observed_at >= ?",
            (INTERNAL_ORIGIN, recent_10s),
        ) or 0)
        recent_visitor_bytes_10s = int(self.database.scalar(
            "SELECT COALESCE(SUM(request_bytes), 0) FROM application_events WHERE origin != ? AND path LIKE '/api/activity/probe%' AND observed_at >= ?",
            (INTERNAL_ORIGIN, recent_10s),
        ) or 0)

        anomaly_type = None
        anomaly_details = None
        if severities & {"high", "critical"} or recent_visitor_10s >= 5 or recent_visitor_bytes_10s >= 10000:
            raw_status = STATUS_ANOMALOUS
            latest_det = next((r for r in recent_detections if r["severity"] in {"high", "critical"}), recent_detections[0] if recent_detections else None)
            if latest_det:
                anomaly_type = latest_det["label"]
                anomaly_details = {
                    "reason": latest_det["reason"],
                    "ticket": latest_det.get("ticket_code"),
                    "severity": latest_det["severity"],
                }
            else:
                anomaly_type = "Peningkatan frekuensi request" if recent_visitor_10s >= 5 else "Kenaikan volume data"
                anomaly_details = {
                    "reason": f"Terukur {recent_visitor_10s} request pengunjung dalam 10 detik terakhir.",
                    "severity": "high",
                }
        elif severities or recent_visitor_10s >= 1 or recent_visitor_bytes_10s >= 1000:
            raw_status = STATUS_ABOVE_BASELINE
            latest_det = recent_detections[0] if recent_detections else None
            if latest_det:
                anomaly_type = latest_det["label"]
                anomaly_details = {
                    "reason": latest_det["reason"],
                    "ticket": latest_det.get("ticket_code"),
                    "severity": latest_det["severity"],
                }
            else:
                anomaly_type = "Deviasi volume traffic"
                anomaly_details = {
                    "reason": f"Terukur {recent_visitor_10s} request pengunjung di atas baseline.",
                    "severity": "warning",
                }
        else:
            raw_status = STATUS_NORMAL

        condition = pengelola_kondisi.perbarui_kondisi(raw_status, anomaly_type, anomaly_details)
        system_logs = log_service.list(limit=100)["items"]
        incidents = incident_service.list_recent(100)
        return {
            "overview": {
                "active_sessions": len(active_sessions),
                "active_activities": active_activity_count,
                "total_packets": total_packets,
                "packets_per_second": round(recent_packets / 10, 2),
                "total_bytes": int(self.database.scalar("SELECT COALESCE(SUM(packet_length), 0) FROM packet_events") or 0),
                "application_requests_10s": int(self.database.scalar(
                    "SELECT COUNT(*) FROM application_events WHERE path LIKE '/api/activity/probe%' AND observed_at >= ?", (recent_cutoff,)
                ) or 0),
                "application_events_10s": all_application_events,
                "warnings_total": int(self.database.scalar("SELECT COUNT(*) FROM detections WHERE severity = 'warning'") or 0),
                "detections_total": int(self.database.scalar("SELECT COUNT(*) FROM detections") or 0),
                "abnormal_total": int(self.database.scalar("SELECT COUNT(*) FROM detections WHERE severity IN ('high', 'critical')") or 0),
                "last_packet_at": packets[0]["observed_at"] if packets else None,
            },
            "health": {
                "sensor_status": components.get("sensor", {}).get("status", "stopped"),
                "analyzer_status": components.get("analyzer", {}).get("status", "stopped"),
                "database_status": "connected" if self.database.is_healthy() else "error",
                "guest_api_status": components.get("guest_api", {}).get("status", "unknown"),
                "management_api_status": components.get("management_api", {}).get("status", "unknown"),
                "websocket_status": components.get("websocket", {}).get("status", "waiting"),
                "message": "Status berasal dari proses layanan dan data yang tersimpan.",
                "components": components,
            },
            "traffic": [
                {
                    "id": row["id"],
                    "timestamp": row["observed_at"],
                    "ticket": row["ticket_code"],
                    "source": row["source_ip"] or "-",
                    "destination": row["destination_ip"] or "-",
                    "protocol": row["protocol"],
                    "source_port": row["source_port"],
                    "destination_port": row["destination_port"],
                    "size_bytes": row["packet_length"],
                    "tcp_flags": row["tcp_flags"],
                    "correlation_method": row["correlation_method"],
                }
                for row in packets
            ],
            "application_events": application_events,
            "detections": [
                {
                    "id": row["id"],
                    "timestamp": row["created_at"],
                    "title": row["label"],
                    "category": row["rule_id"],
                    "severity": row["severity"],
                    "reason": row["reason"],
                    "ticket": row.get("ticket_code"),
                    "source": row["source"],
                    "session_id": row["session_id"],
                    "activity_id": row["activity_id"],
                    "score": row["score"],
                }
                for row in detections
            ],
            "alerts": alerts,
            "sessions": [
                {
                    "ticket": row["ticket_code"],
                    "ip_address": row["client_ip"],
                    "started_at": row["started_at"],
                    "expires_at": row["expires_at"],
                    "status": row["status"],
                }
                for row in active_sessions
            ],
            "windows": windows,
            "latest_features": latest_window,
            "baseline": baseline,
            "internal_baseline": self.internal_baseline_status(components.get("baseline_generator")),
            "traffic_condition": condition,
            "system_logs": system_logs,
            "incidents": incidents,
            "ai": self._ai_status(),
        }


telemetry_pipeline = TelemetryPipeline()
