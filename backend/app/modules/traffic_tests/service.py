from __future__ import annotations

from typing import Any

from app.config import SCENARIOS, settings


class TrafficGenerator:
    def __init__(self) -> None:
        self.scenarios = SCENARIOS

    def build_activity(self, scenario_name: str) -> dict[str, Any]:
        profile = self.scenarios.get(scenario_name)
        if profile is None:
            raise ValueError(f"Skenario '{scenario_name}' tidak dikenal.")
        if profile.request_count > settings.max_activity_requests:
            raise ValueError("Jumlah request skenario melebihi batas konfigurasi.")
        if max(profile.body_sizes) > settings.max_activity_payload_bytes:
            raise ValueError("Ukuran payload skenario melebihi batas konfigurasi.")
        duration = max(0.0, (profile.request_count - 1) * profile.interval_seconds)
        if duration > settings.max_activity_duration_seconds:
            raise ValueError("Durasi skenario melebihi batas konfigurasi.")

        payload_sizes = [profile.body_sizes[index % len(profile.body_sizes)] for index in range(profile.request_count)]
        return {
            "scenario": profile.name,
            "scenario_label": profile.label,
            "planned_count": profile.request_count,
            "interval_seconds": profile.interval_seconds,
            "payload_sizes": payload_sizes,
            "planned_bytes": sum(payload_sizes),
        }


traffic_generator = TrafficGenerator()
