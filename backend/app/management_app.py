from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.management.dashboard import router as dashboard_router
from app.config import settings
from app.modules.network_sensor.service import sensor_service
from app.modules.telemetry_pipeline import telemetry_pipeline
from app.modules.traffic_analyzer.service import traffic_analyzer_service

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[2]
SITE_DIR = ROOT_DIR / "web utama"


async def _analyzer_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(traffic_analyzer_service.analyze_window)
        except Exception as exc:
            logger.exception("Traffic Analyzer gagal memproses window")
            telemetry_pipeline.set_component_status("analyzer", "error", str(exc))
        await asyncio.sleep(max(0.25, settings.analysis_interval_seconds))


@asynccontextmanager
async def lifespan(_: FastAPI):
    telemetry_pipeline.set_component_status("management_api", "running", "Management API berjalan di listener lokal.")
    if settings.sensor_enabled and settings.sensor_interface:
        sensor_status = await asyncio.to_thread(sensor_service.start, settings.sensor_interface)
    else:
        sensor_status = sensor_service.status()
        sensor_status["status"] = "not_configured"
        sensor_status["message"] = "Pilih interface lokal dan mulai sensor dari panel sensor."
    telemetry_pipeline.set_component_status("sensor", sensor_status["status"], sensor_status["message"])
    telemetry_pipeline.set_component_status("analyzer", "running", "Analyzer memproses window secara berkala.")
    analyzer_task = asyncio.create_task(_analyzer_loop())
    try:
        yield
    finally:
        analyzer_task.cancel()
        try:
            await analyzer_task
        except asyncio.CancelledError:
            pass
        sensor_status = await asyncio.to_thread(sensor_service.stop)
        telemetry_pipeline.set_component_status("sensor", "stopped", sensor_status["message"])
        telemetry_pipeline.set_component_status("analyzer", "stopped", "Analyzer telah dihentikan.")
        telemetry_pipeline.set_component_status("management_api", "stopped", "Management API telah dihentikan.")


app = FastAPI(title="IDS Management Service", lifespan=lifespan)
app.include_router(dashboard_router)
app.mount("/assets", StaticFiles(directory=SITE_DIR / "assets"), name="assets")


@app.get("/")
def index():
    return FileResponse(SITE_DIR / "index.html")


@app.get("/api/health")
async def health():
    status = await asyncio.to_thread(telemetry_pipeline.snapshot)
    return {
        "status": "ok",
        "service": "management",
        "listener_scope": "localhost",
        "database": status["health"]["database_status"],
        "sensor": status["health"]["sensor_status"],
        "analyzer": status["health"]["analyzer_status"],
    }
