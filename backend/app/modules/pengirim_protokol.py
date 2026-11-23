from __future__ import annotations

import os
import socket
import time
from typing import Any

from app.config import settings
from app.modules.database.service import to_iso, utc_now

TARGET_LAB_DIIZINKAN = {"127.0.0.1", "localhost", "::1"}
PORT_LAB_DIIZINKAN = {8000, 8001}


def _target_aman(host: str, port: int) -> bool:
    h = (host or "").strip().lower()
    return h in TARGET_LAB_DIIZINKAN and port in PORT_LAB_DIIZINKAN


class PengirimProtokol:
    def cek_dukungan(self, protokol: str) -> dict[str, Any]:
        p = (protokol or "").strip().upper()
        if p == "HTTP":
            return {"protokol": "HTTP", "didukung": True, "pesan": "Didukung langsung via HTTP client browser/backend."}
        if p == "TCP":
            return {"protokol": "TCP", "didukung": True, "pesan": "Didukung via socket TCP lokal backend."}
        if p == "UDP":
            return {"protokol": "UDP", "didukung": True, "pesan": "Didukung via socket UDP datagram backend."}
        if p == "ICMP":
            bisa_raw = False
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
                s.close()
                bisa_raw = True
            except (PermissionError, OSError):
                bisa_raw = False
            if bisa_raw:
                return {"protokol": "ICMP", "didukung": True, "pesan": "Didukung via raw socket ICMP."}
            return {
                "protokol": "ICMP",
                "didukung": False,
                "pesan": "Protokol ICMP memerlukan hak akses raw socket administrator pada sistem operasi lokal; belum didukung di lingkungan saat ini.",
            }
        if p == "RANDOM":
            return {"protokol": "RANDOM", "didukung": True, "pesan": "Pemilihan otomatis protokol yang didukung per pengiriman."}
        return {"protokol": p, "didukung": False, "pesan": f"Protokol '{p}' belum didukung oleh sistem."}

    def kirim_tcp(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
        payload_bytes: bytes = b"",
        session_id: str | None = None,
        activity_id: str | None = None,
    ) -> dict[str, Any]:
        target_port = port or settings.guest_port
        if not _target_aman(host, target_port):
            return {"status": "rejected", "error": "Target di luar konfigurasi lab lokal yang diizinkan."}
        mulai = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        try:
            sock.connect((host, target_port))
            data = payload_bytes or b"PING_TCP"
            sock.sendall(data)
            durasi_ms = (time.perf_counter() - mulai) * 1000
            local_ip, local_port = sock.getsockname()
            sock.close()
            from app.modules.telemetry_pipeline import telemetry_pipeline

            telemetry_pipeline.record_packet({
                "timestamp": to_iso(utc_now()),
                "source_ip": local_ip,
                "destination_ip": host,
                "protocol": "TCP",
                "source_port": local_port,
                "destination_port": target_port,
                "packet_length": len(data),
                "tcp_flags": "PSH,ACK",
                "session_id": session_id,
                "activity_id": activity_id,
            })
            return {
                "status": "sent",
                "protocol": "TCP",
                "target": f"{host}:{target_port}",
                "bytes_sent": len(data),
                "duration_ms": round(durasi_ms, 2),
            }
        except Exception as exc:
            try:
                sock.close()
            except Exception:
                pass
            return {"status": "error", "protocol": "TCP", "error": str(exc)}

    def kirim_udp(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
        payload_bytes: bytes = b"",
        session_id: str | None = None,
        activity_id: str | None = None,
    ) -> dict[str, Any]:
        target_port = port or settings.guest_port
        if not _target_aman(host, target_port):
            return {"status": "rejected", "error": "Target di luar konfigurasi lab lokal yang diizinkan."}
        mulai = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        try:
            data = payload_bytes or b"PING_UDP"
            sock.sendto(data, (host, target_port))
            durasi_ms = (time.perf_counter() - mulai) * 1000
            local_ip, local_port = sock.getsockname()
            sock.close()
            from app.modules.telemetry_pipeline import telemetry_pipeline

            telemetry_pipeline.record_packet({
                "timestamp": to_iso(utc_now()),
                "source_ip": local_ip,
                "destination_ip": host,
                "protocol": "UDP",
                "source_port": local_port,
                "destination_port": target_port,
                "packet_length": len(data),
                "tcp_flags": None,
                "session_id": session_id,
                "activity_id": activity_id,
            })
            return {
                "status": "sent",
                "protocol": "UDP",
                "target": f"{host}:{target_port}",
                "bytes_sent": len(data),
                "duration_ms": round(durasi_ms, 2),
            }
        except Exception as exc:
            try:
                sock.close()
            except Exception:
                pass
            return {"status": "error", "protocol": "UDP", "error": str(exc)}

    def kirim_icmp(self, host: str = "127.0.0.1") -> dict[str, Any]:
        cek = self.cek_dukungan("ICMP")
        if not cek["didukung"]:
            return {"status": "unsupported", "protocol": "ICMP", "message": cek["pesan"]}
        return {"status": "error", "protocol": "ICMP", "message": "Raw socket ICMP belum diinisialisasi."}


pengirim_protokol = PengirimProtokol()
