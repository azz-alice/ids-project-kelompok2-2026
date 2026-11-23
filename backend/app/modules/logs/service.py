from __future__ import annotations

import logging
from typing import Any

from app.modules.database.service import Database, default_database, dumps, loads, to_iso, utc_now

SENSITIVE_KEYS = ("token", "secret", "api_key", "apikey", "password", "authorization")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if any(word in str(key).lower() for word in SENSITIVE_KEYS):
                continue
            clean[key] = sanitize(item)
        return clean
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value

LEVELS = ("debug", "info", "warning", "error")

console = logging.getLogger("ids")


class LogService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def write(
        self,
        level: str,
        component: str,
        event_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        level = level if level in LEVELS else "info"
        clean = sanitize(details or {})
        getattr(console, level)("[%s] %s: %s", component, event_type, message)
        try:
            self.database.execute(
                "INSERT INTO system_logs (created_at, level, component, event_type, message, details_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (to_iso(utc_now()), level, component, event_type, message, dumps(clean)),
            )
        except Exception as error:
            console.error("Gagal menulis log: %s", error)

    def info(self, component: str, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.write("info", component, event_type, message, details)

    def warning(self, component: str, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.write("warning", component, event_type, message, details)

    def error(self, component: str, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.write("error", component, event_type, message, details)

    def list(
        self,
        level: str | None = None,
        component: str | None = None,
        since: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if level:
            clauses.append("level = ?")
            params.append(level)
        if component:
            clauses.append("component = ?")
            params.append(component)
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = self.database.scalar(f"SELECT COUNT(*) FROM system_logs {where}", tuple(params))
        rows = self.database.fetch_all(
            f"SELECT * FROM system_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            tuple(params + [limit, offset]),
        )
        for row in rows:
            row["details"] = loads(row.pop("details_json"))
        components = [
            row["component"] for row in self.database.fetch_all("SELECT DISTINCT component FROM system_logs ORDER BY component")
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": rows, "components": components}


log_service = LogService(default_database)
