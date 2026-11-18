from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.modules.database.service import Database, default_database, to_iso, utc_now


class IncidentService:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database
        self.database.connect()

    def create_for_detection(self, detection: dict[str, Any]) -> dict[str, Any] | None:
        if str(detection.get("severity", "")).lower() not in {"high", "critical"}:
            return None
        incident_id = uuid4().hex
        now = to_iso(utc_now())
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO incidents (id, detection_id, created_at, updated_at, status) "
                "VALUES (?, ?, ?, ?, 'open')",
                (incident_id, detection["id"], now, now),
            )
        return self.database.fetch_one(
            "SELECT i.id, i.detection_id, i.created_at, i.updated_at, i.status, "
            "d.label, d.severity, d.reason, d.rule_id, s.ticket_code "
            "FROM incidents i JOIN detections d ON d.id = i.detection_id "
            "LEFT JOIN sessions s ON s.id = d.session_id WHERE i.detection_id = ?",
            (detection["id"],),
        )

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.database.fetch_all(
            "SELECT i.id, i.detection_id, i.created_at, i.updated_at, i.status, "
            "d.label, d.severity, d.reason, d.rule_id, s.ticket_code "
            "FROM incidents i JOIN detections d ON d.id = i.detection_id "
            "LEFT JOIN sessions s ON s.id = d.session_id "
            "ORDER BY i.created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        )

    def update_status(self, incident_id: str, status: str) -> dict[str, Any] | None:
        if status not in {"open", "investigating", "resolved"}:
            raise ValueError("Status insiden tidak valid.")
        self.database.execute(
            "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
            (status, to_iso(utc_now()), incident_id),
        )
        return self.database.fetch_one(
            "SELECT i.id, i.detection_id, i.created_at, i.updated_at, i.status, "
            "d.label, d.severity, d.reason, d.rule_id, s.ticket_code "
            "FROM incidents i JOIN detections d ON d.id = i.detection_id "
            "LEFT JOIN sessions s ON s.id = d.session_id WHERE i.id = ?",
            (incident_id,),
        )


incident_service = IncidentService()
