from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest

from app.api.guest import routes as guest_routes
from app.modules.alerts.service import alert_service
from app.modules.baseline.service import baseline_service
from app.modules.database.service import Database
from app.modules.deret_waktu.layanan import layanan_deret_waktu
from app.modules.incidents.service import incident_service
from app.modules.lalu_lintas_internal.pembangkit import pembangkit_baseline
from app.modules.logs.service import log_service
from app.modules.sessions.service import session_service
from app.modules.telemetry_pipeline import telemetry_pipeline


@pytest.fixture(autouse=True)
def tanpa_generator_otomatis(monkeypatch) -> None:
    monkeypatch.setattr(pembangkit_baseline, "mulai", lambda port=None: False)


@pytest.fixture
def database(tmp_path, monkeypatch) -> Iterator[Database]:
    db = Database(tmp_path / "ids-test.db")
    db.connect()
    monkeypatch.setattr(guest_routes, "default_database", db)
    monkeypatch.setattr(session_service, "database", db)
    monkeypatch.setattr(telemetry_pipeline, "database", db)
    monkeypatch.setattr(baseline_service, "database", db)
    monkeypatch.setattr(alert_service, "database", db)
    monkeypatch.setattr(incident_service, "database", db)
    monkeypatch.setattr(log_service, "database", db)
    monkeypatch.setattr(layanan_deret_waktu, "database", db)
    yield db
    db.close()
