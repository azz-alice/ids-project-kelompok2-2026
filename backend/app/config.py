from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
GUEST_SITE_DIR = PROJECT_DIR / "web pengunjung"
MANAGEMENT_SITE_DIR = PROJECT_DIR / "web utama"

load_dotenv(BACKEND_DIR / ".env")


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def _float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value is not None else default


def _database_path() -> Path:
    url = _str("DATABASE_URL", "sqlite:///./data/ids.db")
    raw = url.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


@dataclass(frozen=True)
class ScenarioProfile:
    name: str
    label: str
    request_count: int
    interval_seconds: float
    body_sizes: tuple[int, ...]


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: _str("APP_ENV", "local"))
    guest_host: str = field(default_factory=lambda: _str("GUEST_HOST", "0.0.0.0"))
    guest_port: int = field(default_factory=lambda: _int("GUEST_PORT", 8000))
    management_host: str = field(default_factory=lambda: _str("MANAGEMENT_HOST", "127.0.0.1"))
    management_port: int = field(default_factory=lambda: _int("MANAGEMENT_PORT", 8001))
    database_path: Path = field(default_factory=_database_path)
    session_duration_seconds: int = field(default_factory=lambda: _int("SESSION_DURATION_SECONDS", 120))
    max_active_sessions: int = field(default_factory=lambda: _int("MAX_ACTIVE_SESSIONS", 5))
    anomaly_cooldown_seconds: int = field(default_factory=lambda: _int("ANOMALY_COOLDOWN_SECONDS", 30))
    max_activities_per_session: int = field(default_factory=lambda: _int("MAX_ACTIVITIES_PER_SESSION", 12))
    live_traffic_buffer_size: int = field(default_factory=lambda: _int("LIVE_TRAFFIC_BUFFER_SIZE", 500))
    max_request_body_bytes: int = field(default_factory=lambda: _int("MAX_REQUEST_BODY_BYTES", 65536))
    max_activity_requests: int = field(default_factory=lambda: _int("MAX_ACTIVITY_REQUESTS", 16))
    max_activity_payload_bytes: int = field(default_factory=lambda: _int("MAX_ACTIVITY_PAYLOAD_BYTES", 16384))
    max_activity_duration_seconds: int = field(default_factory=lambda: _int("MAX_ACTIVITY_DURATION_SECONDS", 15))
    guest_rate_limit_per_minute: int = field(default_factory=lambda: _int("GUEST_RATE_LIMIT_PER_MINUTE", 120))
    session_create_limit_per_minute: int = field(default_factory=lambda: _int("SESSION_CREATE_LIMIT_PER_MINUTE", 6))
    sensor_enabled: bool = field(default_factory=lambda: _bool("SENSOR_ENABLED", False))
    sensor_interface: str = field(default_factory=lambda: _str("SENSOR_INTERFACE", ""))
    analysis_window_seconds: int = field(default_factory=lambda: _int("ANALYSIS_WINDOW_SECONDS", 10))
    analysis_interval_seconds: float = field(default_factory=lambda: _float("ANALYSIS_INTERVAL_SECONDS", 2.0))
    baseline_warmup_windows: int = field(default_factory=lambda: _int("BASELINE_WARMUP_WINDOWS", 3))
    baseline_multiplier: float = field(default_factory=lambda: _float("BASELINE_MULTIPLIER", 3.0))
    rule_request_rate_warning: float = field(default_factory=lambda: _float("RULE_REQUEST_RATE_WARNING", 2.0))
    rule_request_rate_abnormal: float = field(default_factory=lambda: _float("RULE_REQUEST_RATE_ABNORMAL", 4.0))
    rule_bytes_warning: int = field(default_factory=lambda: _int("RULE_BYTES_WARNING", 60000))
    rule_bytes_abnormal: int = field(default_factory=lambda: _int("RULE_BYTES_ABNORMAL", 150000))
    rule_size_cv_warning: float = field(default_factory=lambda: _float("RULE_SIZE_CV_WARNING", 0.6))
    rule_size_cv_abnormal: float = field(default_factory=lambda: _float("RULE_SIZE_CV_ABNORMAL", 1.0))
    rule_size_min_range: int = field(default_factory=lambda: _int("RULE_SIZE_MIN_RANGE", 4000))
    rule_size_min_samples: int = field(default_factory=lambda: _int("RULE_SIZE_MIN_SAMPLES", 4))
    rule_packet_rate_warning: float = field(default_factory=lambda: _float("RULE_PACKET_RATE_WARNING", 200.0))
    rule_packet_rate_abnormal: float = field(default_factory=lambda: _float("RULE_PACKET_RATE_ABNORMAL", 600.0))
    alert_dedup_seconds: int = field(default_factory=lambda: _int("ALERT_DEDUP_SECONDS", 30))
    retention_hours: int = field(default_factory=lambda: _int("RETENTION_HOURS", 24))
    log_retention_days: int = field(default_factory=lambda: _int("LOG_RETENTION_DAYS", 7))
    abuseipdb_enabled: bool = field(default_factory=lambda: _bool("ABUSEIPDB_ENABLED", False))
    abuseipdb_api_key: str = field(default_factory=lambda: _str("ABUSEIPDB_API_KEY", ""))
    abuseipdb_cache_hours: int = field(default_factory=lambda: _int("ABUSEIPDB_CACHE_HOURS", 24))
    abuseipdb_timeout_seconds: float = field(default_factory=lambda: _float("ABUSEIPDB_TIMEOUT_SECONDS", 6.0))
    abuseipdb_requests_per_hour: int = field(default_factory=lambda: _int("ABUSEIPDB_REQUESTS_PER_HOUR", 60))
    internal_baseline_enabled: bool = field(default_factory=lambda: _bool("INTERNAL_BASELINE_ENABLED", True))
    internal_baseline_rate: float = field(default_factory=lambda: _float("INTERNAL_BASELINE_RATE", 3.0))
    internal_baseline_payload_bytes: int = field(default_factory=lambda: _int("INTERNAL_BASELINE_PAYLOAD_BYTES", 128))
    ml_enabled: bool = field(default_factory=lambda: _bool("ML_ENABLED", False))
    ml_model_path: str = field(default_factory=lambda: _str("ML_MODEL_PATH", ""))

    @property
    def rules_version(self) -> str:
        return (
            f"rules-v2:rr{self.rule_request_rate_warning}/{self.rule_request_rate_abnormal}"
            f":b{self.rule_bytes_warning}/{self.rule_bytes_abnormal}"
            f":cv{self.rule_size_cv_warning}/{self.rule_size_cv_abnormal}"
            f":pr{self.rule_packet_rate_warning}/{self.rule_packet_rate_abnormal}"
            f":w{self.analysis_window_seconds}:m{self.baseline_multiplier}"
        )


INTERNAL_BASELINE_PATH = "/api/internal/baseline"
INTERNAL_ORIGIN = "internal_baseline"
GUEST_ORIGIN = "guest"
PROBE_PATH = "/api/activity/probe"
HEARTBEAT_PATH = "/api/session/heartbeat"

SCENARIOS: dict[str, ScenarioProfile] = {
    "volume_spike": ScenarioProfile("volume_spike", "Kenaikan volume traffic", 10, 0.4, (1024,)),
    "payload_size_variation": ScenarioProfile(
        "payload_size_variation", "Perbedaan ukuran data", 6, 0.8, (64, 4096, 128, 8192, 256, 16384)
    ),
    "request_frequency": ScenarioProfile("request_frequency", "Peningkatan frekuensi request", 12, 0.2, (128,)),
}

settings = Settings()
