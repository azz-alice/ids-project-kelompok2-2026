from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings
from app.modules.database.service import default_database, dumps, loads, to_iso, utc_now

logger = logging.getLogger(__name__)


class ThreatIntelService:
    def __init__(self) -> None:
        self.enabled = bool(settings.abuseipdb_enabled and settings.abuseipdb_api_key)

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "status": "not_configured",
                "provider": "AbuseIPDB",
                "message": "Integrasi belum aktif. Atur ABUSEIPDB_ENABLED dan API key melalui environment.",
            }
        return {
            "status": "configured",
            "provider": "AbuseIPDB",
            "message": "Integrasi siap; pemeriksaan hanya dijalankan untuk IP publik yang diminta.",
        }

    async def check_ip(self, ip_address: str) -> dict[str, Any]:
        try:
            address = ipaddress.ip_address(ip_address)
        except ValueError:
            return {
                "status": "invalid_ip",
                "provider": "AbuseIPDB",
                "ip": ip_address,
                "message": "Alamat IP tidak valid.",
                "score": None,
                "data": None,
            }
        if not address.is_global:
            return {
                "status": "private_ip",
                "provider": "AbuseIPDB",
                "ip": str(address),
                "message": "Alamat privat/lokal tidak diperiksa oleh AbuseIPDB.",
                "score": None,
                "data": None,
            }
        if not self.enabled:
            return {
                "status": "not_configured",
                "provider": "AbuseIPDB",
                "ip": str(address),
                "message": "API key AbuseIPDB belum dikonfigurasi.",
                "score": None,
                "data": None,
            }

        cached = default_database.fetch_one(
            "SELECT result_json, status FROM threat_intel_cache WHERE ip_address = ? AND expires_at > ?",
            (str(address), to_iso(utc_now())),
        )
        if cached:
            result = loads(cached["result_json"])
            result["cached"] = True
            return result
        recent_cutoff = to_iso(utc_now() - timedelta(hours=1))
        request_count = int(default_database.scalar(
            "SELECT COUNT(*) FROM threat_intel_cache WHERE checked_at >= ?",
            (recent_cutoff,),
        ) or 0)
        if request_count >= settings.abuseipdb_requests_per_hour:
            return {
                "status": "rate_limited",
                "provider": "AbuseIPDB",
                "ip": str(address),
                "message": "Batas pemeriksaan AbuseIPDB lokal per jam telah tercapai.",
                "score": None,
                "data": None,
                "cached": False,
            }

        return await asyncio.to_thread(self._request_ip, str(address))

    def _request_ip(self, ip_address: str) -> dict[str, Any]:
        query = urlencode({"ipAddress": ip_address, "maxAgeInDays": 90})
        request = Request(
            f"https://api.abuseipdb.com/api/v2/check?{query}",
            headers={
                "Accept": "application/json",
                "Key": settings.abuseipdb_api_key,
                "User-Agent": "IDS-Local-Demo/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=settings.abuseipdb_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
            data = body.get("data") or {}
            result = {
                "status": "checked",
                "provider": "AbuseIPDB",
                "ip": ip_address,
                "message": "Pemeriksaan AbuseIPDB berhasil.",
                "score": data.get("abuseConfidenceScore"),
                "data": {
                    "countryCode": data.get("countryCode"),
                    "totalReports": data.get("totalReports"),
                    "lastReportedAt": data.get("lastReportedAt"),
                    "usageType": data.get("usageType"),
                    "isWhitelisted": data.get("isWhitelisted"),
                },
                "cached": False,
            }
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Pemeriksaan AbuseIPDB gagal untuk %s: %s", ip_address, exc)
            result = {
                "status": "not_available",
                "provider": "AbuseIPDB",
                "ip": ip_address,
                "message": "Layanan AbuseIPDB tidak dapat dijangkau; monitoring lokal tetap berjalan.",
                "score": None,
                "data": None,
                "cached": False,
            }

        now = utc_now()
        default_database.execute(
            "INSERT INTO threat_intel_cache (ip_address, provider, checked_at, expires_at, result_json, status) "
            "VALUES (?, 'AbuseIPDB', ?, ?, ?, ?) "
            "ON CONFLICT(ip_address) DO UPDATE SET provider = excluded.provider, checked_at = excluded.checked_at, "
            "expires_at = excluded.expires_at, result_json = excluded.result_json, status = excluded.status",
            (
                ip_address,
                to_iso(now),
                to_iso(now + timedelta(hours=settings.abuseipdb_cache_hours)),
                dumps(result),
                result["status"],
            ),
        )
        return result


threat_intel_service = ThreatIntelService()
