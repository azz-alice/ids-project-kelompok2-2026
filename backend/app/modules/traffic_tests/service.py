from __future__ import annotations

import random
from typing import Any

from app.config import SCENARIOS, settings


class TrafficGenerator:
    def __init__(self) -> None:
        self.scenarios = SCENARIOS

    def build_activity(
        self,
        scenario_name: str,
        custom_count: int | None = None,
        mode: str | None = None,
        protocol: str = "HTTP",
    ) -> dict[str, Any]:
        profile = self.scenarios.get(scenario_name)
        if profile is None:
            raise ValueError(f"Skenario '{scenario_name}' tidak dikenal.")

        req_count = profile.request_count
        if custom_count is not None and int(custom_count) > 0:
            req_count = min(int(custom_count), settings.max_activity_requests)

        interval = profile.interval_seconds
        if mode == "burst":
            interval = max(0.08, interval * 0.5)
        elif mode == "sustained":
            interval = max(0.3, interval * 1.2)

        if req_count > settings.max_activity_requests:
            raise ValueError("Jumlah request skenario melebihi batas konfigurasi.")
        if max(profile.body_sizes) > settings.max_activity_payload_bytes:
            raise ValueError("Ukuran payload skenario melebihi batas konfigurasi.")
        duration = max(0.0, (req_count - 1) * interval)
        if duration > settings.max_activity_duration_seconds:
            raise ValueError("Durasi skenario melebihi batas konfigurasi.")

        payload_sizes = [profile.body_sizes[index % len(profile.body_sizes)] for index in range(req_count)]
        return {
            "scenario": profile.name,
            "scenario_label": profile.label,
            "planned_count": req_count,
            "interval_seconds": round(interval, 3),
            "payload_sizes": payload_sizes,
            "planned_bytes": sum(payload_sizes),
            "protocol": protocol,
            "mode": mode or "normal",
        }


traffic_generator = TrafficGenerator()
