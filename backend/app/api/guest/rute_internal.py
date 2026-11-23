from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import INTERNAL_BASELINE_PATH
from app.modules.lalu_lintas_internal.pembangkit import pembangkit_baseline

router = APIRouter()


@router.post(INTERNAL_BASELINE_PATH)
async def baseline_internal_post(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    client_host = request.client.host if request.client else None
    if not pembangkit_baseline.permintaan_sah(client_host, request.headers):
        raise HTTPException(status_code=403, detail="Endpoint ini hanya untuk proses internal laptop.")
    return {"status": "diterima", "seq": (payload or {}).get("seq")}


@router.get(INTERNAL_BASELINE_PATH)
async def baseline_internal_get(request: Request, seq: int | None = None, action: str | None = None) -> dict[str, Any]:
    client_host = request.client.host if request.client else None
    if not pembangkit_baseline.permintaan_sah(client_host, request.headers):
        raise HTTPException(status_code=403, detail="Endpoint ini hanya untuk proses internal laptop.")
    return {"status": "diterima", "seq": seq, "action": action}
