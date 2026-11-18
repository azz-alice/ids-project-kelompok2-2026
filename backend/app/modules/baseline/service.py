from __future__ import annotations

from typing import Any

from app.config import settings
from app.modules.database.service import Database, default_database, dumps, loads, to_iso, utc_now


class BaselineService:
    FEATURE_KEYS = (
        "internal_request_rate", "internal_bytes_per_second", "packet_rate", "packet_size_cv",
    )

    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database
        self.database.connect()

    def state(self, scope: str = "global") -> dict[str, Any]:
        row = self.database.fetch_one("SELECT * FROM baseline_state WHERE scope = ?", (scope,))
        if row is None or row["version"] != settings.rules_version:
            return {"scope": scope, "version": settings.rules_version, "sample_count": 0, "features": {}, "status": "warming_up"}
        samples = int(row["sample_count"])
        return {
            "scope": scope,
            "version": row["version"],
            "sample_count": samples,
            "features": loads(row["feature_json"]),
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "updated_at": row["updated_at"],
            "status": "ready" if samples >= settings.baseline_warmup_windows else "warming_up",
        }

    def observe(self, features: dict[str, Any], window_start: str, window_end: str, scope: str = "global") -> dict[str, Any]:
        current = self.state(scope)
        if (
            int(features.get("internal_request_count", 0)) <= 0
            and int(features.get("packet_count", 0)) <= 0
        ):
            return current
        sample_count = current["sample_count"] + 1
        previous = current["features"]
        averages: dict[str, float] = {}
        for key in self.FEATURE_KEYS:
            value = float(features.get(key, 0.0) or 0.0)
            old_average = float(previous.get(key, 0.0) or 0.0)
            averages[key] = old_average + (value - old_average) / sample_count
        self.database.execute(
            "INSERT INTO baseline_state (scope, version, sample_count, feature_json, window_start, window_end, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(scope) DO UPDATE SET version=excluded.version, "
            "sample_count=excluded.sample_count, feature_json=excluded.feature_json, window_start=excluded.window_start, "
            "window_end=excluded.window_end, updated_at=excluded.updated_at",
            (scope, settings.rules_version, sample_count, dumps(averages), window_start, window_end, to_iso(utc_now())),
        )
        return self.state(scope)


baseline_service = BaselineService()
