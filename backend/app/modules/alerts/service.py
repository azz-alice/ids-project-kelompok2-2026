from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from app.config import settings
from app.modules.database.service import Database, default_database, to_iso, utc_now


class AlertService:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database
        self.database.connect()

    def create_for_detection(self, detection: dict[str, Any]) -> dict[str, Any] | None:
        cutoff = to_iso(utc_now())
        recent_cutoff = to_iso(utc_now() - timedelta(seconds=settings.alert_dedup_seconds))
        existing = self.database.fetch_one(
            "SELECT a.* FROM alerts a JOIN detections d ON d.id = a.detection_id "
            "WHERE d.rule_id = ? AND a.status = 'open' AND a.created_at >= ? "
            "ORDER BY a.created_at DESC LIMIT 1",
            (
                detection["rule_id"],
                recent_cutoff,
            ),
        )
        if existing:
            return None

        alert = {
            "id": uuid4().hex,
            "detection_id": detection["id"],
            "created_at": cutoff,
            "severity": detection["severity"],
            "title": detection["label"],
            "description": detection["reason"],
            "status": "open",
        }
        self.database.execute(
            "INSERT INTO alerts (id, detection_id, created_at, severity, title, description, status, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'open', NULL)",
            (
                alert["id"],
                alert["detection_id"],
                alert["created_at"],
                alert["severity"],
                alert["title"],
                alert["description"],
            ),
        )
        return alert

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.database.fetch_all(
            "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        )

    def set_status(self, alert_id: str, status: str) -> dict[str, Any] | None:
        if status not in {"open", "acknowledged", "resolved"}:
            raise ValueError("Status alert tidak valid.")
        resolved_at = to_iso(utc_now()) if status == "resolved" else None
        self.database.execute(
            "UPDATE alerts SET status = ?, resolved_at = ? WHERE id = ?",
            (status, resolved_at, alert_id),
        )
        return self.database.fetch_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))


alert_service = AlertService()
