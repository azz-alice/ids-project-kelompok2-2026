from __future__ import annotations

import statistics
from typing import Any

from app.config import HEARTBEAT_PATH, INTERNAL_ORIGIN, PROBE_PATH
from app.modules.database.service import from_iso


def koefisien_variasi(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if mean <= 0:
        return 0.0
    return statistics.pstdev(values) / mean


def rentang_pengamatan(timestamps: list[str], window_seconds: float) -> float:
    values = [parsed.timestamp() for value in timestamps if (parsed := from_iso(value)) is not None]
    if len(values) < 2:
        return max(1.0, float(window_seconds))
    return max(1.0, min(float(window_seconds), max(values) - min(values)))


def laju(count: int, timestamps: list[str], window_seconds: float) -> float:
    if count <= 0:
        return 0.0
    return count / rentang_pengamatan(timestamps, window_seconds)


def _berhasil(row: dict[str, Any]) -> bool:
    return int(row.get("status_code", 0)) < 400


def bangun_fitur(
    app_events: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    window_start: str,
    window_end: str,
    window_seconds: int,
) -> dict[str, Any]:
    internal = [row for row in app_events if row.get("origin") == INTERNAL_ORIGIN and _berhasil(row)]
    visitor_events = [row for row in app_events if row.get("origin") != INTERNAL_ORIGIN]
    probes = [row for row in visitor_events if str(row.get("path") or "").startswith("/api/activity/probe") and _berhasil(row)]
    heartbeats = [row for row in visitor_events if row.get("path") == HEARTBEAT_PATH and _berhasil(row)]

    request_sizes = [float(row.get("request_bytes") or 0) for row in probes]
    packet_sizes = [float(row.get("packet_length") or 0) for row in packets]
    request_timestamps = [row["observed_at"] for row in probes]
    heartbeat_timestamps = [row["observed_at"] for row in heartbeats]
    packet_timestamps = [row["observed_at"] for row in packets]
    request_bytes = sum(int(row.get("request_bytes") or 0) for row in probes)
    packet_bytes = sum(int(row.get("packet_length") or 0) for row in packets)
    internal_bytes = sum(int(row.get("request_bytes") or 0) for row in internal)
    window = max(1, int(window_seconds))
    request_span = rentang_pengamatan(request_timestamps, window)
    packet_span = rentang_pengamatan(packet_timestamps, window)

    protocols: dict[str, int] = {}
    flows: set[tuple[Any, ...]] = set()
    for packet in packets:
        protocol = str(packet.get("protocol") or "OTHER").upper()
        protocols[protocol] = protocols.get(protocol, 0) + 1
        flows.add((packet.get("source_ip"), packet.get("destination_ip"), packet.get("source_port"), packet.get("destination_port"), protocol))

    return {
        "window_start": window_start,
        "window_end": window_end,
        "request_count": len(probes),
        "request_rate": round(laju(len(probes), request_timestamps, window), 4),
        "request_bytes": request_bytes,
        "bytes_per_second": round(request_bytes / request_span, 2),
        "request_size_mean": round(statistics.fmean(request_sizes), 2) if request_sizes else 0.0,
        "request_size_cv": round(koefisien_variasi(request_sizes), 4),
        "request_size_min": min(request_sizes) if request_sizes else 0,
        "request_size_max": max(request_sizes) if request_sizes else 0,
        "request_size_range": (max(request_sizes) - min(request_sizes)) if request_sizes else 0,
        "heartbeat_count": len(heartbeats),
        "heartbeat_rate": round(laju(len(heartbeats), heartbeat_timestamps, window), 4),
        "internal_request_count": len(internal),
        "internal_request_rate": round(len(internal) / window, 4),
        "internal_request_bytes": internal_bytes,
        "internal_bytes_per_second": round(internal_bytes / window, 2),
        "packet_count": len(packets),
        "packet_rate": round(laju(len(packets), packet_timestamps, window), 4),
        "packet_bytes": packet_bytes,
        "packet_bytes_per_second": round(packet_bytes / packet_span, 2),
        "packet_size_mean": round(statistics.fmean(packet_sizes), 2) if packet_sizes else 0.0,
        "packet_size_cv": round(koefisien_variasi(packet_sizes), 4),
        "total_observed_bytes": request_bytes + internal_bytes + packet_bytes,
        "protocol_distribution": protocols,
        "flow_count": len(flows),
    }
