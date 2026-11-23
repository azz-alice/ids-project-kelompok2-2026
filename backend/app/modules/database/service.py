from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    ticket_code TEXT NOT NULL UNIQUE,
    session_token_hash TEXT NOT NULL UNIQUE,
    client_ip TEXT,
    user_agent TEXT,
    display_name TEXT,
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'expired', 'closed', 'rejected')),
    cooldown_until TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);

CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    scenario TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    request_count INTEGER NOT NULL DEFAULT 0,
    planned_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_session ON activities(session_id);
CREATE INDEX IF NOT EXISTS idx_activities_created ON activities(created_at);
CREATE INDEX IF NOT EXISTS idx_activities_scenario ON activities(scenario);

CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    client_ip TEXT,
    request_bytes INTEGER NOT NULL DEFAULT 0,
    response_bytes INTEGER,
    duration_ms REAL,
    origin TEXT NOT NULL,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    activity_id TEXT REFERENCES activities(id) ON DELETE SET NULL,
    source_port INTEGER,
    destination_ip TEXT,
    destination_port INTEGER
);
CREATE INDEX IF NOT EXISTS idx_app_events_time ON application_events(observed_at);
CREATE INDEX IF NOT EXISTS idx_app_events_session ON application_events(session_id);
CREATE INDEX IF NOT EXISTS idx_app_events_path_time ON application_events(path, observed_at);

CREATE TABLE IF NOT EXISTS packet_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    interface_name TEXT,
    source_ip TEXT,
    destination_ip TEXT,
    protocol TEXT NOT NULL,
    source_port INTEGER,
    destination_port INTEGER,
    packet_length INTEGER NOT NULL,
    tcp_flags TEXT,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    activity_id TEXT REFERENCES activities(id) ON DELETE SET NULL,
    correlation_method TEXT
);
CREATE INDEX IF NOT EXISTS idx_packets_time ON packet_events(observed_at);
CREATE INDEX IF NOT EXISTS idx_packets_session ON packet_events(session_id);

CREATE TABLE IF NOT EXISTS traffic_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'session')),
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    feature_json TEXT NOT NULL,
    baseline_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_windows_end ON traffic_windows(window_end);
CREATE INDEX IF NOT EXISTS idx_windows_session ON traffic_windows(session_id);

CREATE TABLE IF NOT EXISTS detections (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    activity_id TEXT REFERENCES activities(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('rule', 'ml', 'combined')),
    rule_id TEXT,
    label TEXT NOT NULL,
    severity TEXT NOT NULL,
    score REAL,
    model_version TEXT,
    rules_version TEXT,
    feature_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_detections_created ON detections(created_at);
CREATE INDEX IF NOT EXISTS idx_detections_session ON detections(session_id);
CREATE INDEX IF NOT EXISTS idx_detections_severity ON detections(severity);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    detection_id TEXT NOT NULL UNIQUE REFERENCES detections(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'resolved'))
);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    detection_id TEXT REFERENCES detections(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'acknowledged', 'resolved')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);

CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_logs_created ON system_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_level ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_component ON system_logs(component);

CREATE TABLE IF NOT EXISTS threat_intel_cache (
    ip_address TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    result_json TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dashboard_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dashboard_events_created ON dashboard_events(created_at);

CREATE TABLE IF NOT EXISTS component_status (
    component TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baseline_state (
    scope TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    feature_json TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_global_window_unique
ON traffic_windows(window_start) WHERE scope = 'global';
"""


APPLICATION_EVENT_EXTRA_COLUMNS = (
    ("source_port", "INTEGER"),
    ("destination_ip", "TEXT"),
    ("destination_port", "INTEGER"),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None) -> Any:
    if not value:
        return {}
    return json.loads(value)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        if self._connection is not None:
            return
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA wal_autocheckpoint = 1000")
        connection.execute("PRAGMA cache_size = -8000")
        connection.executescript(SCHEMA)
        self._add_missing_columns(connection)
        self._connection = connection

    @staticmethod
    def _add_missing_columns(connection: sqlite3.Connection) -> None:
        existing = {row["name"] for row in connection.execute("PRAGMA table_info(application_events)")}
        for column, column_type in APPLICATION_EVENT_EXTRA_COLUMNS:
            if column not in existing:
                try:
                    connection.execute(f"ALTER TABLE application_events ADD COLUMN {column} {column_type}")
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Database belum terhubung")
        return self._connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self.connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.connection.execute(sql, params)

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        if not rows:
            return
        with self.transaction() as connection:
            connection.executemany(sql, rows)

    def fetch_one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        with self._lock:
            row = self.connection.execute(sql, params).fetchone()
        return row[0] if row else None

    def is_healthy(self) -> bool:
        try:
            return self.scalar("SELECT 1") == 1
        except Exception:
            return False

    def apply_retention(self, retention_hours: int, log_retention_days: int) -> dict[str, int]:
        cutoff = to_iso(utc_now() - timedelta(hours=retention_hours))
        log_cutoff = to_iso(utc_now() - timedelta(days=log_retention_days))
        removed: dict[str, int] = {}
        with self.transaction() as connection:
            removed["packet_events"] = connection.execute(
                "DELETE FROM packet_events WHERE observed_at < ?", (cutoff,)
            ).rowcount
            removed["application_events"] = connection.execute(
                "DELETE FROM application_events WHERE observed_at < ?", (cutoff,)
            ).rowcount
            removed["traffic_windows"] = connection.execute(
                "DELETE FROM traffic_windows WHERE window_end < ?", (cutoff,)
            ).rowcount
            removed["system_logs"] = connection.execute(
                "DELETE FROM system_logs WHERE created_at < ?", (log_cutoff,)
            ).rowcount
            removed["threat_intel_cache"] = connection.execute(
                "DELETE FROM threat_intel_cache WHERE expires_at < ?", (to_iso(utc_now()),)
            ).rowcount
            removed["dashboard_events"] = connection.execute(
                "DELETE FROM dashboard_events WHERE created_at < ?", (cutoff,)
            ).rowcount
        return removed


default_database = Database(settings.database_path)
