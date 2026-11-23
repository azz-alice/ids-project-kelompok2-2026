from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.config import settings
from app.modules.alerts.service import alert_service
from app.modules.network_sensor.service import sensor_service
from app.modules.incidents.service import incident_service
from app.modules.logs.service import log_service
from app.modules.deret_waktu.layanan import layanan_deret_waktu
from app.modules.telemetry_pipeline import telemetry_pipeline
from app.modules.threat_intelligence.service import threat_intel_service

logger = logging.getLogger(__name__)
router = APIRouter()
_websocket_connections = 0


@router.get("/api/dashboard/snapshot")
async def dashboard_snapshot() -> dict[str, Any]:
    return await asyncio.to_thread(telemetry_pipeline.snapshot)


@router.get("/api/dashboard/history")
async def dashboard_history(minutes: int = 60) -> dict[str, Any]:
    return {"items": await asyncio.to_thread(telemetry_pipeline.history, minutes)}


@router.get("/api/dashboard/series")
async def dashboard_series(seconds: int = 120) -> dict[str, Any]:
    return await asyncio.to_thread(layanan_deret_waktu.deret, seconds)


@router.get("/api/detections/{detection_id}")
async def detection_evidence(detection_id: str) -> dict[str, Any]:
    evidence = await asyncio.to_thread(layanan_deret_waktu.bukti_deteksi, detection_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Deteksi tidak ditemukan.")
    return evidence


@router.get("/api/sensor/status")
async def sensor_status() -> dict[str, Any]:
    status = sensor_service.status()
    telemetry_pipeline.set_component_status("sensor", status["status"], status["message"])
    return status


@router.get("/api/sensor/interfaces")
async def sensor_interfaces() -> dict[str, Any]:
    return {"items": await asyncio.to_thread(sensor_service.interfaces)}


@router.post("/api/sensor/start")
async def start_sensor(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    interface_name = str((payload or {}).get("interface_name") or "")
    status = await asyncio.to_thread(sensor_service.start, interface_name)
    telemetry_pipeline.set_component_status("sensor", status["status"], status["message"])
    log_service.write("info" if status["status"] == "running" else "warning", "sensor", "start", status["message"], {"interface_name": interface_name})
    if status["status"] != "running":
        raise HTTPException(status_code=503, detail=status)
    return status


@router.post("/api/sensor/stop")
async def stop_sensor() -> dict[str, Any]:
    status = await asyncio.to_thread(sensor_service.stop)
    telemetry_pipeline.set_component_status("sensor", status["status"], status["message"])
    log_service.info("sensor", "stop", status["message"])
    return status


@router.get("/api/logs")
async def list_system_logs(level: str | None = None, component: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, min(int(offset), 100000))
    return await asyncio.to_thread(log_service.list, level, component, None, safe_limit, safe_offset)


@router.get("/api/incidents")
async def list_incidents() -> dict[str, Any]:
    return {"items": await asyncio.to_thread(incident_service.list_recent, 200)}


@router.patch("/api/incidents/{incident_id}")
async def update_incident(incident_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        incident = await asyncio.to_thread(incident_service.update_status, incident_id, str(payload.get("status", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if incident is None:
        raise HTTPException(status_code=404, detail="Insiden tidak ditemukan.")
    log_service.info("incidents", "status_updated", "Status investigasi diperbarui.", {"incident_id": incident_id, "status": incident["status"]})
    telemetry_pipeline.publish_event("incident", incident)
    return incident


@router.get("/api/alerts")
async def list_alerts() -> dict[str, Any]:
    return {"items": await asyncio.to_thread(alert_service.list_recent, 200)}


@router.get("/api/ai/status")
async def ai_status() -> dict[str, Any]:
    from app.modules.ai_integration.service import Service
    return await asyncio.to_thread(Service().status)


@router.get("/api/threat-intelligence/status")
async def threat_intelligence_status() -> dict[str, Any]:
    return threat_intel_service.status()


@router.post("/api/threat-intelligence/check")
async def check_threat_ip(payload: dict[str, Any]) -> dict[str, Any]:
    ip_address = str(payload.get("ip_address") or "").strip()
    if not ip_address:
        raise HTTPException(status_code=400, detail="Alamat IP harus diisi.")
    return await threat_intel_service.check_ip(ip_address)


@router.patch("/api/alerts/{alert_id}")
async def update_alert(alert_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        alert = await asyncio.to_thread(alert_service.set_status, alert_id, str(payload.get("status", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert tidak ditemukan.")
    log_service.info("alerts", "status_updated", "Status alert diperbarui.", {"alert_id": alert_id, "status": alert["status"]})
    telemetry_pipeline.publish_event("alert", alert)
    return alert


@router.websocket("/ws/dashboard")
async def dashboard_stream(websocket: WebSocket) -> None:
    global _websocket_connections
    await websocket.accept()
    _websocket_connections += 1
    telemetry_pipeline.set_component_status("websocket", "connected", "WebSocket management aktif.")
    try:
        last_event_id = await asyncio.to_thread(telemetry_pipeline.latest_event_id)
        snapshot = await asyncio.to_thread(telemetry_pipeline.snapshot)
        await websocket.send_json({"type": "snapshot", "data": snapshot})
        while True:
            events = await asyncio.to_thread(telemetry_pipeline.events_after, last_event_id)
            for event in events:
                await websocket.send_json(event)
                last_event_id = int(event["event_id"])
            await asyncio.sleep(0.15)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Dashboard WebSocket gagal")
        raise
    finally:
        _websocket_connections = max(0, _websocket_connections - 1)
        status = "connected" if _websocket_connections else "waiting"
        message = "WebSocket management aktif." if _websocket_connections else "Belum ada dashboard WebSocket yang tersambung."
        telemetry_pipeline.set_component_status("websocket", status, message)
