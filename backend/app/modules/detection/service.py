from __future__ import annotations

from typing import Any

from app.config import settings

RULES_WITHOUT_BASELINE = {"request-rate-spike", "request-size-variation", "bytes-rate-spike"}


class DetectionService:
    def evaluate(
        self,
        features: dict[str, Any],
        baseline: dict[str, Any],
        allowed_rules: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        baseline_ready = baseline.get("status") == "ready"
        base = (baseline.get("features") or {}) if baseline_ready else {}
        findings: list[dict[str, Any]] = []

        def allowed(rule_id: str) -> bool:
            if allowed_rules is not None and rule_id not in allowed_rules:
                return False
            return baseline_ready or rule_id in RULES_WITHOUT_BASELINE

        def append(rule_id: str, label: str, severity: str, score: float, reason: str, values: dict[str, Any]) -> None:
            findings.append({"rule_id": rule_id, "label": label, "severity": severity, "score": score, "reason": reason, "features": values})

        request_count = int(features.get("request_count", 0) or 0)

        request_rate = float(features.get("request_rate", 0.0) or 0.0)
        if allowed("request-rate-spike") and request_count >= 2 and request_rate >= settings.rule_request_rate_warning:
            severity = "high" if request_rate >= settings.rule_request_rate_abnormal else "warning"
            append("request-rate-spike", "Peningkatan frekuensi request", severity, request_rate,
                f"Terukur {request_rate:.2f} request/detik dari {request_count} request pengunjung; batas wajar {settings.rule_request_rate_warning:.2f} request/detik.",
                {"request_rate": request_rate, "request_count": request_count, "threshold_warning": settings.rule_request_rate_warning, "threshold_abnormal": settings.rule_request_rate_abnormal})

        size_cv = float(features.get("request_size_cv", 0.0) or 0.0)
        size_range = int(features.get("request_size_range", 0) or 0)
        if allowed("request-size-variation") and request_count >= settings.rule_size_min_samples and size_range >= settings.rule_size_min_range and size_cv >= settings.rule_size_cv_warning:
            severity = "high" if size_cv >= settings.rule_size_cv_abnormal else "warning"
            append("request-size-variation", "Perbedaan ukuran data", severity, size_cv,
                f"Koefisien variasi ukuran request {size_cv:.2f} dengan rentang {size_range} byte dari {request_count} request.",
                {"request_size_cv": size_cv, "request_size_range": size_range, "request_size_min": features.get("request_size_min"), "request_size_max": features.get("request_size_max"), "request_count": request_count})

        byte_rate = float(features.get("bytes_per_second", 0.0) or 0.0)
        if allowed("bytes-rate-spike") and byte_rate >= settings.rule_bytes_warning:
            severity = "high" if byte_rate >= settings.rule_bytes_abnormal else "warning"
            append("bytes-rate-spike", "Kenaikan volume data", severity, byte_rate,
                f"Terukur {byte_rate:.0f} byte/detik dari {int(features.get('request_bytes', 0))} byte request pengunjung; batas wajar {settings.rule_bytes_warning} byte/detik.",
                {"bytes_per_second": byte_rate, "request_bytes": int(features.get("request_bytes", 0)), "request_count": request_count, "threshold_warning": settings.rule_bytes_warning, "threshold_abnormal": settings.rule_bytes_abnormal})

        packet_rate = float(features.get("packet_rate", 0.0) or 0.0)
        packet_base = float(base.get("packet_rate", 0.0) or 0.0)
        if allowed("packet-rate-spike") and packet_rate >= settings.rule_packet_rate_warning and packet_rate > max(packet_base * settings.baseline_multiplier, packet_base + 10.0):
            severity = "high" if packet_rate >= settings.rule_packet_rate_abnormal else "warning"
            append("packet-rate-spike", "Peningkatan packet rate", severity, packet_rate,
                f"Terukur {packet_rate:.1f} paket/detik; baseline {packet_base:.1f} paket/detik.",
                {"packet_rate": packet_rate, "baseline_packet_rate": packet_base, "packet_count": int(features.get("packet_count", 0))})
        return findings


detection_service = DetectionService()
