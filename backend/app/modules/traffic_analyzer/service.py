from __future__ import annotations

from datetime import datetime
from typing import Any


class TrafficAnalyzerService:
    def analyze_window(self, now: datetime | None = None) -> dict[str, Any] | None:
        from app.modules.telemetry_pipeline import telemetry_pipeline
        return telemetry_pipeline.analyze_window(now)


traffic_analyzer_service = TrafficAnalyzerService()
