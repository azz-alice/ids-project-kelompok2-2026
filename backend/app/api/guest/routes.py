from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.config import settings
from app.modules.database.service import default_database, dumps, to_iso, utc_now
from app.modules.pengirim_protokol import pengirim_protokol
from app.modules.sessions.service import session_service
from app.modules.telemetry_pipeline import telemetry_pipeline
from app.modules.traffic_tests.service import traffic_generator

logger = logging.getLogger(__name__)
router = APIRouter()


def _session_token(
    payload: dict[str, Any] | None,
    authorization: str | None,
    header_token: str | None,
) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if header_token:
        return header_token
    return str(payload.get("session_token")) if payload and payload.get("session_token") else None


def _validated_session(token: str | None, enforce_cooldown: bool = True) -> dict[str, Any]:
    try:
        return session_service.validate_session(token, enforce_cooldown=enforce_cooldown)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(settings.anomaly_cooldown_seconds)},
        ) from exc


def _check_guest_rate(request: Request, path: str) -> None:
    client = request.client
    if client is None:
        return
    cutoff = to_iso(utc_now() - timedelta(minutes=1))
    count = default_database.scalar(
        "SELECT COUNT(*) FROM application_events WHERE client_ip = ? AND path = ? AND observed_at >= ?",
        (client.host, path, cutoff),
    )
    limit = settings.session_create_limit_per_minute if path == "/api/session/create" else settings.guest_rate_limit_per_minute
    if int(count or 0) >= limit:
        raise HTTPException(status_code=429, detail="Batas request sementara tercapai. Coba kembali sebentar lagi.")


@router.get("/api/guest/status")
async def guest_status() -> dict[str, Any]:
    return {
        "status": "running",
        "max_active_sessions": settings.max_active_sessions,
        "session_duration_seconds": settings.session_duration_seconds,
        "anomaly_cooldown_seconds": settings.anomaly_cooldown_seconds,
        "active_sessions": session_service.count_active_sessions(),
    }


@router.post("/api/session/create")
async def create_session(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _check_guest_rate(request, "/api/session/create")
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    display_name = payload.get("display_name") if payload else None
    try:
        session = session_service.create_session(
            client_ip=client_ip,
            user_agent=user_agent,
            display_name=display_name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("Gagal membuat sesi pengunjung")
        raise HTTPException(status_code=500, detail="Sesi tidak dapat dibuat saat ini.") from None
    telemetry_pipeline.publish_event("session", {
        "ticket": session["ticket_code"],
        "ip_address": session["client_ip"],
        "status": "active",
        "started_at": session["started_at"],
        "expires_at": session["expires_at"],
    })
    session["server_time"] = to_iso(utc_now())
    return session


@router.get("/api/session/current")
async def current_session(
    authorization: str | None = Header(default=None),
    x_ids_session_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = _validated_session(_session_token(None, authorization, x_ids_session_token), enforce_cooldown=False)
    return {
        "session_id": session["id"],
        "ticket_code": session["ticket_code"],
        "client_ip": session["client_ip"],
        "started_at": session["started_at"],
        "expires_at": session["expires_at"],
        "status": session["status"],
        "cooldown_until": session.get("cooldown_until"),
        "session_duration_seconds": settings.session_duration_seconds,
        "server_time": to_iso(utc_now()),
    }


@router.post("/api/session/heartbeat")
async def session_heartbeat(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    x_ids_session_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_guest_rate(request, "/api/session/heartbeat")
    session = _validated_session(_session_token(None, authorization, x_ids_session_token), enforce_cooldown=False)
    session["expires_at"] = session_service.extend_session(session["id"])
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "active",
        "ticket_code": session["ticket_code"],
        "expires_at": session["expires_at"],
        "cooldown_until": session.get("cooldown_until"),
        "server_time": to_iso(utc_now()),
    }


@router.get("/api/activity/protocols")
async def activity_protocols() -> dict[str, Any]:
    return {
        "protocols": [
            pengirim_protokol.cek_dukungan("HTTP"),
            pengirim_protokol.cek_dukungan("TCP"),
            pengirim_protokol.cek_dukungan("UDP"),
            pengirim_protokol.cek_dukungan("ICMP"),
            pengirim_protokol.cek_dukungan("RANDOM"),
        ]
    }


@router.post("/api/activity")
async def submit_activity(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
    x_ids_session_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_guest_rate(request, "/api/activity")
    scenario_name = str(payload.get("scenario") or "")
    protocol = str(payload.get("protocol") or "HTTP").upper()
    custom_count = payload.get("batch_count")
    mode = payload.get("mode")
    token = _session_token(payload, authorization, x_ids_session_token)
    session = _validated_session(token, enforce_cooldown=True)
    try:
        plan = traffic_generator.build_activity(scenario_name, custom_count=custom_count, mode=mode, protocol=protocol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    activity_id = uuid4().hex
    created_at = to_iso(utc_now())
    metadata = {
        "interval_seconds": plan["interval_seconds"],
        "payload_sizes": plan["payload_sizes"],
        "scenario_label": plan["scenario_label"],
        "protocol": protocol,
        "mode": plan["mode"],
    }
    with default_database.transaction() as connection:
        activity_count = int(connection.execute(
            "SELECT COUNT(*) FROM activities WHERE session_id = ?",
            (session["id"],),
        ).fetchone()[0])
        if settings.max_activities_per_session > 0 and activity_count >= settings.max_activities_per_session:
            raise HTTPException(status_code=429, detail="Batas aktivitas untuk sesi ini telah tercapai.")
        connection.execute(
            "INSERT INTO activities "
            "(id, session_id, scenario, status, created_at, started_at, request_count, planned_count, metadata_json) "
            "VALUES (?, ?, ?, 'running', ?, ?, 0, ?, ?)",
            (
                activity_id,
                session["id"],
                scenario_name,
                created_at,
                created_at,
                plan["planned_count"],
                dumps(metadata),
            ),
        )
    durasi_burst = max(0, plan["planned_count"] - 1) * plan["interval_seconds"]
    cooldown_until = session_service.apply_cooldown(session["id"], int(durasi_burst + 0.999) + settings.anomaly_cooldown_seconds)
    telemetry_pipeline.publish_event("activity", {
        "activity_id": activity_id,
        "ticket": session["ticket_code"],
        "scenario": scenario_name,
        "status": "running",
        "planned_request_count": plan["planned_count"],
        "protocol": protocol,
    })
    return {
        "status": "started",
        "activity_id": activity_id,
        "scenario": scenario_name,
        "scenario_label": plan["scenario_label"],
        "planned_request_count": plan["planned_count"],
        "payload_sizes": plan["payload_sizes"],
        "interval_seconds": plan["interval_seconds"],
        "max_payload_bytes": settings.max_activity_payload_bytes,
        "cooldown_until": cooldown_until,
        "protocol": protocol,
        "mode": plan["mode"],
        "message": f"Aktivitas {protocol} dikirim ke target lab lokal; jumlah selesai dihitung dari data aktual yang diterima.",
    }


@router.post("/api/activity/probe-protocol")
async def activity_probe_protocol(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
    x_ids_session_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_guest_rate(request, "/api/activity/probe")
    token = _session_token(payload, authorization, x_ids_session_token)
    session = _validated_session(token, enforce_cooldown=False)
    activity_id = str(payload.get("activity_id") or "")
    protocol = str(payload.get("protocol") or "TCP").upper()
    data_text = str(payload.get("payload") or "x" * 64)
    data_bytes = data_text.encode("utf-8")
    if len(data_bytes) > settings.max_activity_payload_bytes:
        raise HTTPException(status_code=413, detail="Ukuran payload melebihi batas konfigurasi.")

    if protocol == "RANDOM":
        import random
        protocol = random.choice(["HTTP", "TCP", "UDP"])

    if protocol == "ICMP":
        hasil = pengirim_protokol.kirim_icmp("127.0.0.1")
        if not hasil.get("didukung", False):
            raise HTTPException(status_code=501, detail=hasil.get("pesan", "Protokol ICMP belum didukung di lingkungan ini."))
        return hasil

    timed_out = False
    with default_database.transaction() as connection:
        activity = connection.execute(
            "SELECT * FROM activities WHERE id = ? AND session_id = ?",
            (activity_id, session["id"]),
        ).fetchone()
        if activity is None:
            raise HTTPException(status_code=404, detail="Aktivitas tidak ditemukan.")
        if activity["status"] != "running":
            raise HTTPException(status_code=409, detail="Aktivitas tidak lagi berjalan.")
        start_time = datetime.fromisoformat(activity["started_at"].replace("Z", "+00:00"))
        if (utc_now() - start_time).total_seconds() > settings.max_activity_duration_seconds:
            connection.execute(
                "UPDATE activities SET status = 'timed_out', finished_at = ?, error_code = 'duration_exceeded' WHERE id = ?",
                (to_iso(utc_now()), activity_id),
            )
            timed_out = True
        else:
            completed = int(activity["request_count"]) + 1
            planned = int(activity["planned_count"])
            metadata = json.loads(activity["metadata_json"] or "{}")
            actual_bytes = int(metadata.get("actual_payload_bytes", 0)) + len(data_bytes)
            metadata["actual_payload_bytes"] = actual_bytes
            status = "completed" if completed >= planned else "running"
            finished_at = to_iso(utc_now()) if status == "completed" else None
            connection.execute(
                "UPDATE activities SET request_count = ?, status = ?, finished_at = ?, metadata_json = ? WHERE id = ?",
                (completed, status, finished_at, dumps(metadata), activity_id),
            )

    if timed_out:
        telemetry_pipeline.publish_event("activity", {
            "activity_id": activity_id,
            "ticket": session["ticket_code"],
            "status": "timed_out",
        })
        raise HTTPException(status_code=408, detail="Durasi aktivitas melebihi batas.")

    if protocol == "TCP":
        hasil = pengirim_protokol.kirim_tcp("127.0.0.1", port=settings.guest_port, payload_bytes=data_bytes, session_id=session["id"], activity_id=activity_id)
    elif protocol == "UDP":
        hasil = pengirim_protokol.kirim_udp("127.0.0.1", port=settings.guest_port, payload_bytes=data_bytes, session_id=session["id"], activity_id=activity_id)
    else:
        hasil = {"status": "sent", "protocol": "HTTP", "bytes_sent": len(data_bytes)}

    return {
        "status": "accepted",
        "activity_id": activity_id,
        "protocol": protocol,
        "completed_request_count": completed,
        "planned_request_count": planned,
        "probe_result": hasil,
        "activity_status": status,
    }


@router.post("/api/activity/probe")
async def activity_probe(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
    x_ids_session_token: str | None = Header(default=None),
    x_ids_activity_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_guest_rate(request, "/api/activity/probe")
    token = _session_token(payload, authorization, x_ids_session_token)
    session = _validated_session(token, enforce_cooldown=False)
    activity_id = str(payload.get("activity_id") or x_ids_activity_id or "")
    data_payload = payload.get("payload")
    if not isinstance(data_payload, str):
        raise HTTPException(status_code=400, detail="Payload aktivitas harus berupa teks.")
    payload_size = len(data_payload.encode("utf-8"))
    if payload_size > settings.max_activity_payload_bytes:
        raise HTTPException(status_code=413, detail="Ukuran payload melebihi batas konfigurasi.")
    if len(await request.body()) > settings.max_request_body_bytes:
        raise HTTPException(status_code=413, detail="Ukuran request melebihi batas konfigurasi.")

    timed_out = False
    with default_database.transaction() as connection:
        activity = connection.execute(
            "SELECT * FROM activities WHERE id = ? AND session_id = ?",
            (activity_id, session["id"]),
        ).fetchone()
        if activity is None:
            raise HTTPException(status_code=404, detail="Aktivitas tidak ditemukan.")
        if activity["status"] != "running":
            raise HTTPException(status_code=409, detail="Aktivitas tidak lagi berjalan.")
        metadata = json.loads(activity["metadata_json"] or "{}")
        planned_sizes = metadata.get("payload_sizes", [])
        completed = int(activity["request_count"])
        if completed >= int(activity["planned_count"]):
            raise HTTPException(status_code=409, detail="Jumlah request aktivitas sudah terpenuhi.")
        expected_size = int(planned_sizes[completed])
        if payload_size != expected_size:
            raise HTTPException(status_code=400, detail="Ukuran payload tidak sesuai dengan rencana aktivitas.")
        start_time = datetime.fromisoformat(activity["started_at"].replace("Z", "+00:00"))
        if (utc_now() - start_time).total_seconds() > settings.max_activity_duration_seconds:
            connection.execute(
                "UPDATE activities SET status = 'timed_out', finished_at = ?, error_code = 'duration_exceeded' WHERE id = ?",
                (to_iso(utc_now()), activity_id),
            )
            timed_out = True
        else:
            completed += 1
            actual_bytes = int(metadata.get("actual_payload_bytes", 0)) + payload_size
            metadata["actual_payload_bytes"] = actual_bytes
            status = "completed" if completed >= int(activity["planned_count"]) else "running"
            finished_at = to_iso(utc_now()) if status == "completed" else None
            connection.execute(
                "UPDATE activities SET request_count = ?, status = ?, finished_at = ?, metadata_json = ? WHERE id = ?",
                (completed, status, finished_at, dumps(metadata), activity_id),
            )

    if timed_out:
        telemetry_pipeline.publish_event("activity", {
            "activity_id": activity_id,
            "ticket": session["ticket_code"],
            "status": "timed_out",
        })
        raise HTTPException(status_code=408, detail="Durasi aktivitas melebihi batas.")

    return {
        "status": "accepted",
        "activity_id": activity_id,
        "scenario": activity["scenario"],
        "completed_request_count": completed,
        "planned_request_count": int(activity["planned_count"]),
        "request_bytes": payload_size,
        "actual_payload_bytes": actual_bytes,
        "activity_status": status,
    }


@router.get("/api/activity/{activity_id}")
async def activity_status(
    activity_id: str,
    authorization: str | None = Header(default=None),
    x_ids_session_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = _validated_session(_session_token(None, authorization, x_ids_session_token), enforce_cooldown=False)
    activity = default_database.fetch_one(
        "SELECT id, scenario, status, created_at, started_at, finished_at, request_count, planned_count, metadata_json "
        "FROM activities WHERE id = ? AND session_id = ?",
        (activity_id, session["id"]),
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Aktivitas tidak ditemukan.")
    metadata = json.loads(activity["metadata_json"] or "{}")
    return {
        "activity_id": activity["id"],
        "scenario": activity["scenario"],
        "status": activity["status"],
        "created_at": activity["created_at"],
        "started_at": activity["started_at"],
        "finished_at": activity["finished_at"],
        "request_count": int(activity["request_count"]),
        "planned_count": int(activity["planned_count"]),
        "actual_payload_bytes": int(metadata.get("actual_payload_bytes", 0)),
    }


@router.post("/api/activity/{activity_id}/cancel")
async def cancel_activity(
    activity_id: str,
    payload: dict[str, Any] | None = None,
    authorization: str | None = Header(default=None),
    x_ids_session_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = _validated_session(_session_token(payload, authorization, x_ids_session_token), enforce_cooldown=False)
    now = to_iso(utc_now())
    cursor = default_database.execute(
        "UPDATE activities SET status = 'cancelled', finished_at = ? "
        "WHERE id = ? AND session_id = ? AND status = 'running'",
        (now, activity_id, session["id"]),
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Aktivitas berjalan tidak ditemukan.")
    telemetry_pipeline.publish_event("activity", {
        "activity_id": activity_id,
        "ticket": session["ticket_code"],
        "status": "cancelled",
    })
    return {"status": "cancelled", "activity_id": activity_id}

