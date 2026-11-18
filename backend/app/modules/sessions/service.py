from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.config import settings
from app.modules.database.service import Database, default_database, from_iso, to_iso, utc_now


class SessionService:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database
        self.database.connect()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_ticket() -> str:
        return f"IDS-{uuid4().hex[:6].upper()}"

    def _ticket_available(self, ticket_code: str) -> bool:
        row = self.database.fetch_one(
            "SELECT 1 FROM sessions WHERE ticket_code = ?",
            (ticket_code,),
        )
        return row is None

    def create_session(self, client_ip: str | None, user_agent: str | None, display_name: str | None = None) -> dict[str, Any]:
        now = utc_now()
        session_id = uuid4().hex
        session_token = secrets.token_urlsafe(24)
        started_at = now
        expires_at = now + timedelta(seconds=settings.session_duration_seconds)
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE sessions SET status = 'expired', ended_at = ?, end_reason = 'expired' "
                "WHERE status = 'active' AND expires_at <= ?",
                (to_iso(now), to_iso(now)),
            )
            active_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE status = 'active' AND expires_at > ?",
                    (to_iso(now),),
                ).fetchone()[0]
            )
            if active_count >= settings.max_active_sessions:
                raise RuntimeError("Maksimal sesi aktif telah tercapai.")

            ticket_code = self._generate_ticket()
            while connection.execute(
                "SELECT 1 FROM sessions WHERE ticket_code = ?",
                (ticket_code,),
            ).fetchone():
                ticket_code = self._generate_ticket()
            display_label = display_name or f"Pengunjung {ticket_code[-3:]}"
            values = (
                session_id,
                ticket_code,
                self._hash_token(session_token),
                client_ip or "unknown",
                user_agent or "unknown",
                display_label,
                to_iso(started_at),
                to_iso(expires_at),
                None,
                None,
                "active",
                None,
                to_iso(started_at),
            )
            connection.execute(
                "INSERT INTO sessions (id, ticket_code, session_token_hash, client_ip, user_agent, display_name, started_at, expires_at, ended_at, end_reason, status, cooldown_until, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

        return {
            "session_id": session_id,
            "session_token": session_token,
            "ticket_code": ticket_code,
            "display_name": display_label,
            "client_ip": client_ip or "unknown",
            "user_agent": user_agent or "unknown",
            "started_at": to_iso(started_at),
            "expires_at": to_iso(expires_at),
            "status": "active",
            "cooldown_until": None,
            "session_duration_seconds": settings.session_duration_seconds,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.database.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(row) if row else None

    def get_session_by_ticket(self, ticket_code: str) -> dict[str, Any] | None:
        row = self.database.fetch_one("SELECT * FROM sessions WHERE ticket_code = ?", (ticket_code,))
        return dict(row) if row else None

    def count_active_sessions(self, now: datetime | None = None) -> int:
        current = now or utc_now()
        return int(
            self.database.scalar(
                "SELECT COUNT(*) FROM sessions WHERE status = 'active' AND expires_at > ?",
                (to_iso(current),),
            )
            or 0
        )

    def expire_sessions(self, now: datetime | None = None) -> list[str]:
        current = now or utc_now()
        rows = self.database.fetch_all(
            "SELECT id, ticket_code FROM sessions WHERE status = 'active' AND expires_at <= ?",
            (to_iso(current),),
        )
        if not rows:
            return []

        expired_ids = [row["id"] for row in rows]
        self.database.execute(
            "UPDATE sessions SET status = 'expired', ended_at = ?, end_reason = 'expired' WHERE status = 'active' AND expires_at <= ?",
            (to_iso(current), to_iso(current)),
        )
        return expired_ids

    def close_session(self, session_id: str, reason: str = "closed") -> dict[str, Any] | None:
        now = to_iso(utc_now())
        self.database.execute(
            "UPDATE sessions SET status = 'closed', ended_at = ?, end_reason = ? WHERE id = ?",
            (now, reason, session_id),
        )
        return self.get_session(session_id)

    def validate_session(self, session_token: str | None, enforce_cooldown: bool = True) -> dict[str, Any]:
        if not session_token:
            raise ValueError("Token sesi tidak tersedia.")

        self.expire_sessions(utc_now())
        row = self.database.fetch_one(
            "SELECT * FROM sessions WHERE session_token_hash = ?",
            (self._hash_token(session_token),),
        )
        if row is None:
            raise ValueError("Token sesi tidak valid.")

        session = dict(row)
        expires_at = from_iso(session["expires_at"])
        if expires_at is None or expires_at <= utc_now():
            self.database.execute(
                "UPDATE sessions SET status = 'expired', ended_at = ?, end_reason = 'expired' WHERE id = ?",
                (to_iso(utc_now()), session["id"]),
            )
            raise ValueError("Sesi telah berakhir.")

        if session["status"] != "active":
            raise ValueError("Sesi tidak aktif.")

        cooldown_until = from_iso(session.get("cooldown_until")) if session.get("cooldown_until") else None
        if enforce_cooldown and cooldown_until and cooldown_until > utc_now():
            remaining = int((cooldown_until - utc_now()).total_seconds())
            raise PermissionError(f"Cooldown aktif. Coba kembali dalam {remaining} detik.")

        return session

    def apply_cooldown(self, session_id: str, seconds: int | None = None) -> str | None:
        seconds = seconds if seconds is not None else settings.anomaly_cooldown_seconds
        cooldown_until = to_iso(utc_now() + timedelta(seconds=seconds))
        self.database.execute(
            "UPDATE sessions SET cooldown_until = ? WHERE id = ?",
            (cooldown_until, session_id),
        )
        return cooldown_until

    def clear_cooldown(self, session_id: str) -> None:
        self.database.execute(
            "UPDATE sessions SET cooldown_until = NULL WHERE id = ?",
            (session_id,),
        )



session_service = SessionService()
