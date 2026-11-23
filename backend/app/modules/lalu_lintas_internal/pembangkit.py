from __future__ import annotations

import asyncio
import logging
import random
import secrets
from typing import Any, Mapping

import httpx

from app.config import INTERNAL_BASELINE_PATH, settings

logger = logging.getLogger(__name__)

HEADER_KUNCI = "x-ids-internal-key"
HOST_LOOPBACK = {"127.0.0.1", "::1"}
PAYLOAD_PILIHAN = (64, 128, 256, 512, 1024, 1500, 2048)
ACTION_PILIHAN = ("heartbeat", "metric_sync", "probe", "telemetry_ping")
POLA_VARIASI = (2, 4, 1, 5, 3)


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
        urutan = 0
        indeks_pola = 0
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            timeout=2.0,
            trust_env=False,
            headers={HEADER_KUNCI: self.kunci},
        ) as client:
            target_awal = loop.time()
            while True:
                jumlah_detik_ini = POLA_VARIASI[indeks_pola % len(POLA_VARIASI)]
                indeks_pola += 1

                bobot = [random.uniform(0.5, 1.5) for _ in range(jumlah_detik_ini)]
                total_bobot = sum(bobot)
                jeda_list = [round(b / total_bobot, 4) for b in bobot]

                for jeda in jeda_list:
                    target_awal += jeda
                    sisa_tidur = target_awal - loop.time()
                    if sisa_tidur > 0:
                        await asyncio.sleep(sisa_tidur)
                    elif sisa_tidur < -1.0:
                        target_awal = loop.time()

                    urutan += 1
                    ukuran = random.choice(PAYLOAD_PILIHAN)
                    aksi = random.choice(ACTION_PILIHAN)
                    metode = "POST" if (urutan % 3 != 0) else "GET"
                    try:
                        if metode == "POST":
                            response = await client.post(
                                INTERNAL_BASELINE_PATH,
                                json={
                                    "seq": urutan,
                                    "action": aksi,
                                    "payload": "b" * ukuran,
                                    "meta": {"proto": "HTTP/1.1", "source": "system_baseline"},
                                },
                            )
                        else:
                            response = await client.get(
                                INTERNAL_BASELINE_PATH,
                                params={"seq": urutan, "action": aksi, "size": ukuran},
                            )
                        if response.status_code == 200:
                            self.berhasil += 1
                        else:
                            self.gagal += 1
                    except httpx.HTTPError:
                        self.gagal += 1
                    except Exception:
                        logger.exception("Pembangkit baseline internal gagal mengirim request")
                        self.gagal += 1

    def ringkasan(self) -> dict[str, Any]:
        return {"aktif": self.aktif, "berhasil": self.berhasil, "gagal": self.gagal}


pembangkit_baseline = PembangkitBaseline()
