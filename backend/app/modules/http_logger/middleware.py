from __future__ import annotations

import logging
import time
from typing import Any, Callable

from app.config import GUEST_ORIGIN, INTERNAL_BASELINE_PATH, INTERNAL_ORIGIN
from app.modules.lalu_lintas_internal.pembangkit import pembangkit_baseline
from app.modules.telemetry_pipeline import telemetry_pipeline

logger = logging.getLogger(__name__)

TRUSTED_PROXIES = {"127.0.0.1", "::1", "localhost"}


def _ekstrak_ip_klien(direct_ip: str | None, headers: dict[str, str]) -> str | None:
    if not direct_ip:
        return None
    if direct_ip in TRUSTED_PROXIES:
        xff = headers.get("x-forwarded-for")
        if xff:
            bagian = [ip.strip() for ip in xff.split(",") if ip.strip()]
            for ip in reversed(bagian):
                if ip not in TRUSTED_PROXIES:
                    return ip
            if bagian:
                return bagian[0]
        x_real_ip = headers.get("x-real-ip")
        if x_real_ip and x_real_ip.strip():
            return x_real_ip.strip()
    return direct_ip


class ApplicationEventMiddleware:
    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        session_token = headers.get("authorization", "")
        if session_token.lower().startswith("bearer "):
            session_token = session_token[7:].strip()
        else:
            session_token = headers.get("x-ids-session-token")
        activity_id = headers.get("x-ids-activity-id")
        client = scope.get("client")
        direct_client_ip = client[0] if client else None
        client_port = client[1] if client and len(client) > 1 else None
        client_ip = _ekstrak_ip_klien(direct_client_ip, headers)

        server = scope.get("server")
        server_ip = server[0] if server else None
        server_port = server[1] if server and len(server) > 1 else None
        path = str(scope.get("path", "/"))
        origin = (
            INTERNAL_ORIGIN
            if path == INTERNAL_BASELINE_PATH and pembangkit_baseline.permintaan_sah(direct_client_ip, headers)
            else GUEST_ORIGIN
        )
        request_bytes = 0
        response_bytes = 0
        status_code = 500
        started = time.perf_counter()
        original_receive = receive

        async def receive_with_size() -> dict[str, Any]:
            nonlocal request_bytes
            message = await original_receive()
            if message["type"] == "http.request":
                request_bytes += len(message.get("body", b""))
            return message

        async def send_with_size(message: dict[str, Any]) -> None:
            nonlocal response_bytes, status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            elif message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive_with_size, send_with_size)
        finally:
            try:
                telemetry_pipeline.record_application_event(
                    method=str(scope.get("method", "GET")),
                    path=path,
                    status_code=status_code,
                    client_ip=client_ip,
                    request_bytes=request_bytes,
                    response_bytes=response_bytes,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    session_token=session_token,
                    activity_id=activity_id,
                    origin=origin,
                    client_port=client_port,
                    server_ip=server_ip,
                    server_port=server_port,
                )
            except Exception:
                logger.exception("Gagal menyimpan application event")
