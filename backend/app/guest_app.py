from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.guest.routes import router as guest_router
from app.api.guest.rute_internal import router as internal_router
from app.config import settings
from app.modules.http_logger.middleware import ApplicationEventMiddleware
from app.modules.lalu_lintas_internal.pembangkit import pembangkit_baseline
from app.modules.telemetry_pipeline import telemetry_pipeline

ROOT_DIR = Path(__file__).resolve().parents[2]
SITE_DIR = ROOT_DIR / "web pengunjung"


@asynccontextmanager
async def lifespan(_: FastAPI):
    telemetry_pipeline.set_component_status("guest_api", "running", "Guest API menerima koneksi pada listener yang dikonfigurasi.")
    if pembangkit_baseline.mulai():
        telemetry_pipeline.set_component_status(
            "baseline_generator",
            "running",
            f"Traffic normal internal {settings.internal_baseline_rate:g} request/detik ke 127.0.0.1:{settings.guest_port}.",
        )
    else:
        telemetry_pipeline.set_component_status("baseline_generator", "not_configured", "Generator baseline internal dinonaktifkan.")
    try:
        yield
    finally:
        await pembangkit_baseline.henti()
        telemetry_pipeline.set_component_status("baseline_generator", "stopped", "Generator baseline internal dihentikan.")
        telemetry_pipeline.set_component_status("guest_api", "stopped", "Guest API telah dihentikan.")


app = FastAPI(title="IDS Guest Service", lifespan=lifespan)
app.add_middleware(ApplicationEventMiddleware)
app.include_router(guest_router)
app.include_router(internal_router)
app.mount("/assets", StaticFiles(directory=SITE_DIR / "assets"), name="assets")


@app.get("/")
def index():
    return FileResponse(SITE_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "guest",
        "database": telemetry_pipeline.database.is_healthy(),
    }
