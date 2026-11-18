from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.modules.telemetry_pipeline import telemetry_pipeline

logger = logging.getLogger(__name__)

try:
    from scapy.all import AsyncSniffer, ARP, ICMP, IP, IPv6, TCP, UDP, get_if_list
    from scapy.config import conf
except ImportError:
    AsyncSniffer = None
    ARP = ICMP = IP = IPv6 = TCP = UDP = None
    get_if_list = None
    conf = None


class NetworkSensorService:
    def __init__(self) -> None:
        self._sniffer: Any = None
        self._lock = threading.RLock()
        self._interface_name: str | None = None
        self._last_error: str | None = None
        self._last_status: str | None = None
        self._captured_packets = 0

    def interfaces(self) -> list[str]:
        if get_if_list is None:
            return []
        try:
            return sorted({str(item) for item in get_if_list()})
        except Exception as exc:
            logger.exception("Gagal membaca interface Scapy")
            self._last_error = str(exc)
            return []

    def _packet_received(self, packet: Any) -> None:
        try:
            source_ip = None
            destination_ip = None
            source_port = None
            destination_port = None
            tcp_flags = None
            protocol = "OTHER"
            if IP is not None and packet.haslayer(IP):
                ip_layer = packet[IP]
                source_ip = str(ip_layer.src)
                destination_ip = str(ip_layer.dst)
            elif IPv6 is not None and packet.haslayer(IPv6):
                ip_layer = packet[IPv6]
                source_ip = str(ip_layer.src)
                destination_ip = str(ip_layer.dst)

            if TCP is not None and packet.haslayer(TCP):
                layer = packet[TCP]
                source_port = int(layer.sport)
                destination_port = int(layer.dport)
                tcp_flags = str(layer.flags)
                protocol = "TCP"
            elif UDP is not None and packet.haslayer(UDP):
                layer = packet[UDP]
                source_port = int(layer.sport)
                destination_port = int(layer.dport)
                protocol = "UDP"
            elif ICMP is not None and packet.haslayer(ICMP):
                protocol = "ICMP"
            elif ARP is not None and packet.haslayer(ARP):
                protocol = "ARP"
                source_ip = str(packet[ARP].psrc) or None
                destination_ip = str(packet[ARP].pdst) or None

            timestamp = datetime.fromtimestamp(float(packet.time), timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            telemetry_pipeline.record_packet({
                "timestamp": timestamp,
                "interface_name": self._interface_name,
                "source_ip": source_ip,
                "destination_ip": destination_ip,
                "protocol": protocol,
                "source_port": source_port,
                "destination_port": destination_port,
                "packet_length": len(packet),
                "tcp_flags": tcp_flags,
            })
            self._captured_packets += 1
        except Exception as exc:
            logger.exception("Gagal memproses metadata paket")
            self._last_error = str(exc)

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = bool(self._sniffer is not None and getattr(self._sniffer, "running", False))
            if running:
                status = "running"
                message = f"Capture Scapy aktif pada interface {self._interface_name}."
            elif self._last_error:
                status = self._last_status or "error"
                message = self._last_error
            elif not settings.sensor_enabled and not self._interface_name:
                status = "not_configured"
                message = "Pilih interface lokal dan mulai sensor dari panel sensor."
            else:
                status = "stopped"
                message = "Capture belum berjalan. Pilih interface laptop yang sesuai dan mulai sensor."
            return {
                "status": status,
                "interface_name": self._interface_name,
                "available_interfaces": self.interfaces(),
                "provider": "scapy",
                "captured_packets": self._captured_packets,
                "message": message,
            }

    def start(self, interface_name: str | None = None) -> dict[str, Any]:
        if AsyncSniffer is None:
            self._last_error = "Scapy belum terpasang."
            self._last_status = "not_available"
            return self.status()
        if sys.platform == "win32" and (conf is None or not conf.use_pcap):
            self._last_error = "Npcap/libpcap tidak tersedia untuk Scapy (wpcap.dll tidak ditemukan). Instal Npcap lalu mulai ulang layanan."
            self._last_status = "not_available"
            telemetry_pipeline.set_component_status("sensor", "not_available", self._last_error)
            return self.status()
        selected = (interface_name or settings.sensor_interface).strip()
        if not selected:
            self._last_error = "Interface sensor belum dipilih."
            self._last_status = "not_configured"
            return self.status()
        available = self.interfaces()
        if selected not in available:
            self._last_error = f"Interface '{selected}' tidak ditemukan pada Scapy."
            self._last_status = "error"
            return self.status()
        with self._lock:
            if self._sniffer is not None and getattr(self._sniffer, "running", False):
                if self._interface_name == selected:
                    return self.status()
                self._sniffer.stop()
                self._sniffer = None
            self._last_error = None
            self._last_status = None
            self._interface_name = selected
            try:
                self._sniffer = AsyncSniffer(
                    iface=selected,
                    store=False,
                    prn=self._packet_received,
                )
                self._sniffer.start()
            except Exception as exc:
                self._sniffer = None
                self._last_error = str(exc)
                self._last_status = "error"
                logger.exception("Scapy gagal memulai capture pada %s", selected)
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            sniffer = self._sniffer
            if sniffer is not None and getattr(sniffer, "running", False):
                try:
                    sniffer.stop()
                except Exception as exc:
                    self._last_error = str(exc)
                    logger.exception("Scapy gagal menghentikan capture")
            self._sniffer = None
        return self.status()


sensor_service = NetworkSensorService()
