const angka = new Intl.NumberFormat("id-ID");

export function formatWaktu(nilai, denganMilidetik = false) {
  if (!nilai) return "—";
  const tanggal = new Date(nilai);
  if (Number.isNaN(tanggal.getTime())) return "—";
  const waktu = tanggal.toLocaleTimeString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
  if (!denganMilidetik) return waktu;
  return `${waktu}.${String(tanggal.getMilliseconds()).padStart(3, "0")}`;
}

export function formatByte(nilai) {
  const byte = Number(nilai || 0);
  if (byte < 1024) return `${angka.format(byte)} B`;
  if (byte < 1024 * 1024) return `${(byte / 1024).toFixed(1).replace(".", ",")} KB`;
  return `${(byte / (1024 * 1024)).toFixed(2).replace(".", ",")} MB`;
}

export function formatAngka(nilai, desimal = 0) {
  const num = Number(nilai || 0);
  if (!Number.isFinite(num)) return "0";
  return num.toLocaleString("id-ID", {
    minimumFractionDigits: desimal,
    maximumFractionDigits: desimal
  });
}

export function sisaWaktu(expiresAt) {
  if (!expiresAt) return "—";
  const selisih = Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 1000));
  return `${String(Math.floor(selisih / 60)).padStart(2, "0")}:${String(selisih % 60).padStart(2, "0")}`;
}

export function dariPacket(item) {
  const ts = item.timestamp || item.observed_at || "";
  return {
    kunci: `pkt-${item.id ?? `${ts}-${item.source_port ?? ""}-${item.destination_port ?? ""}-${item.size_bytes ?? ""}`}`,
    jenis: "packet",
    asal: "sensor",
    timestamp: ts,
    sourceIp: item.source || item.source_ip || "—",
    destinationIp: item.destination || item.destination_ip || "—",
    sourcePort: item.source_port ?? "—",
    destinationPort: item.destination_port ?? "—",
    protocol: String(item.protocol || "OTHER").toUpperCase(),
    length: Number(item.size_bytes ?? item.packet_length ?? 0),
    method: "—",
    path: "—",
    statusCode: "—",
    sourceType: "Packet capture",
    ticket: item.ticket || item.ticket_code || null,
    tcpFlags: item.tcp_flags || null,
    correlationMethod: item.correlation_method || null,
    responseBytes: null,
    durationMs: null
  };
}

export function dariAplikasi(item) {
  const ts = item.observed_at || item.timestamp || "";
  const internal = item.origin === "internal_baseline";
  return {
    kunci: `app-${item.id ?? `${ts}-${item.path ?? ""}-${item.source_port ?? ""}`}`,
    jenis: "aplikasi",
    asal: internal ? "internal" : "pengunjung",
    timestamp: ts,
    sourceIp: item.client_ip || "—",
    destinationIp: item.destination_ip || "127.0.0.1",
    sourcePort: item.source_port ?? "—",
    destinationPort: item.destination_port ?? 8000,
    protocol: "HTTP",
    length: Number(item.request_bytes || 0),
    method: item.method || "—",
    path: item.path || "—",
    statusCode: item.status_code ?? "—",
    sourceType: internal ? "Application event · internal_baseline" : "Application event · pengunjung",
    ticket: item.ticket || item.ticket_code || null,
    tcpFlags: null,
    correlationMethod: null,
    responseBytes: item.response_bytes ?? null,
    durationMs: item.duration_ms ?? null
  };
}
