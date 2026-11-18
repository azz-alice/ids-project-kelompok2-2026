from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any, Mapping

import httpx

from app.config import INTERNAL_BASELINE_PATH, settings

logger = logging.getLogger(__name__)

HEADER_KUNCI = "x-ids-internal-key"
HOST_LOOPBACK = {"127.0.0.1", "::1"}


class PembangkitBaseline:
    def __init__(self) -> None:
        self.kunci = secrets.token_urlsafe(32)
        self.berhasil = 0
        self.gagal = 0
        self._task: asyncio.Task[None] | None = None

    @property
    def aktif(self) -> bool:
        return self._task is not None and not self._task.done()

    def permintaan_sah(self, client_host: str | None, headers: Mapping[str, str]) -> bool:
        if client_host not in HOST_LOOPBACK:
            return False
        return secrets.compare_digest(str(headers.get(HEADER_KUNCI) or ""), self.kunci)

    def mulai(self, port: int | None = None) -> bool:
        if not settings.internal_baseline_enabled or self.aktif:
            return False
        self._task = asyncio.create_task(self._jalankan(port or settings.guest_port))
        return True

    async def henti(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _jalankan(self, port: int) -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / max(0.1, settings.internal_baseline_rate)
        padding = "x" * max(0, settings.internal_baseline_payload_bytes)
        urutan = 0
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            timeout=2.0,
            trust_env=False,
            headers={HEADER_KUNCI: self.kunci},
        ) as client:
            jadwal = loop.time() + interval
            while True:
                urutan += 1
                try:
                    response = await client.post(INTERNAL_BASELINE_PATH, json={"seq": urutan, "payload": padding})
                    if response.status_code == 200:
                        self.berhasil += 1
                    else:
                        self.gagal += 1
                except httpx.HTTPError:
                    self.gagal += 1
                except Exception:
                    logger.exception("Pembangkit baseline internal gagal mengirim request")
                    self.gagal += 1
                jadwal += interval
                jeda = jadwal - loop.time()
                if jeda < -1.0:
                    jadwal = loop.time() + interval
                    jeda = interval
                await asyncio.sleep(max(0.0, jeda))

    def ringkasan(self) -> dict[str, Any]:
        return {"aktif": self.aktif, "berhasil": self.berhasil, "gagal": self.gagal}


pembangkit_baseline = PembangkitBaseline()
