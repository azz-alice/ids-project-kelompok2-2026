import { request } from "./api.js";
import { formatAngka, formatByte, formatWaktu, sisaWaktu } from "./format.js";

const LABEL_KONDISI_DETEKSI = {
  warning: "Kenaikan di atas batas wajar",
  high: "Traffic tidak normal",
  critical: "Traffic tidak normal"
};

const LABEL_ATURAN = {
  "request-rate-spike": "Peningkatan frekuensi request",
  "request-size-variation": "Perbedaan ukuran data",
  "bytes-rate-spike": "Kenaikan volume data",
  "packet-rate-spike": "Peningkatan laju paket"
};

const STATUS_LAYANAN = {
  running: ["baik", "Aktif"],
  connected: ["baik", "Terhubung"],
  ready: ["baik", "Siap"],
  warming_up: ["peringatan", "Mengumpulkan data"],
  stopped: ["peringatan", "Dihentikan"],
  not_configured: ["peringatan", "Belum dikonfigurasi"],
  not_available: ["peringatan", "Tidak tersedia"],
  waiting: ["peringatan", "Menunggu"],
  disabled: ["peringatan", "Nonaktif"],
  error: ["galat", "Gangguan"],
  disconnected: ["galat", "Terputus"]
};

function barisKosong(tbody, jumlahKolom, pesan) {
  tbody.replaceChildren();
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = jumlahKolom;
  td.className = "kosong";
  td.textContent = pesan;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

export function renderRingkasDeteksi(daftar, panelEl, ulEl, saatPilih) {
  if (!panelEl || !ulEl) return;
  const itemValid = Array.isArray(daftar) ? daftar.slice(0, 8) : [];
  if (!itemValid.length) {
    panelEl.hidden = true;
    ulEl.replaceChildren();
    return;
  }
  panelEl.hidden = false;
  ulEl.replaceChildren();
  itemValid.forEach((item) => {
    const li = document.createElement("li");
    const tingkat = String(item.severity || "warning").toLowerCase();
    const spanTingkat = document.createElement("div");
    spanTingkat.className = "tingkat";
    spanTingkat.dataset.tingkat = tingkat === "critical" ? "high" : tingkat;
    spanTingkat.textContent = LABEL_KONDISI_DETEKSI[tingkat] || "Kenaikan di atas batas wajar";

    const judul = document.createElement("div");
    judul.className = "judul";
    judul.textContent = item.title || LABEL_ATURAN[item.category] || "Aturan deteksi";

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${formatWaktu(item.timestamp)} · ${item.ticket ? `Ticket ${item.ticket}` : "Jaringan lokal"}`;

    li.append(spanTingkat, judul, meta);
    li.addEventListener("click", () => saatPilih(item.id));
    ulEl.appendChild(li);
  });
}

export function renderPengunjung(daftar, tbody, jumlahEl, kueri = "") {
  if (!tbody) return;
  const semua = Array.isArray(daftar) ? daftar : [];
  const cari = kueri.trim().toLowerCase();
  const tersaring = semua.filter((s) =>
    `${s.ticket || ""} ${s.ip_address || ""} ${s.status || ""}`.toLowerCase().includes(cari)
  );
  if (jumlahEl) jumlahEl.textContent = `${formatAngka(semua.length)} / 5 sesi aktif`;
  if (!tersaring.length) {
    barisKosong(tbody, 6, semua.length ? "Tidak ada sesi yang cocok." : "Belum ada pengunjung aktif.");
    return;
  }
  tbody.replaceChildren();
  tersaring.forEach((sesi) => {
    const tr = document.createElement("tr");
    const kolom = [
      { teks: sesi.ticket || "—", mono: true },
      { teks: sesi.ip_address || "—", mono: true },
      { teks: formatWaktu(sesi.started_at), mono: true },
      { teks: formatWaktu(sesi.expires_at), mono: true },
      { teks: sisaWaktu(sesi.expires_at), mono: true },
      { teks: sesi.status === "active" ? "Aktif" : sesi.status || "—" }
    ];
    kolom.forEach((kol) => {
      const td = document.createElement("td");
      if (kol.mono) td.className = "mono";
      td.textContent = kol.teks;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

export function renderTabelDeteksi(daftar, tbody, jumlahEl, idDipilih, saatPilih) {
  if (!tbody) return;
  const baris = Array.isArray(daftar) ? daftar : [];
  if (jumlahEl) jumlahEl.textContent = `${formatAngka(baris.length)} event`;
  if (!baris.length) {
    barisKosong(tbody, 5, "Belum ada hasil deteksi.");
    return;
  }
  tbody.replaceChildren();
  baris.forEach((item) => {
    const tr = document.createElement("tr");
    tr.tabIndex = 0;
    tr.style.cursor = "pointer";
    if (item.id === idDipilih) tr.classList.add("dipilih");

    const tingkat = String(item.severity || "warning").toLowerCase();
    const tdWaktu = document.createElement("td");
    tdWaktu.className = "mono";
    tdWaktu.textContent = formatWaktu(item.timestamp);

    const tdKondisi = document.createElement("td");
    tdKondisi.className = "tingkat-teks";
    tdKondisi.dataset.tingkat = tingkat === "critical" ? "high" : tingkat;
    tdKondisi.textContent = LABEL_KONDISI_DETEKSI[tingkat] || "Kenaikan di atas batas wajar";

    const tdAturan = document.createElement("td");
    tdAturan.textContent = item.title || LABEL_ATURAN[item.category] || item.category || "—";

    const tdTicket = document.createElement("td");
    tdTicket.className = "mono";
    tdTicket.textContent = item.ticket || "—";

    const tdNilai = document.createElement("td");
    tdNilai.className = "kol-angka mono";
    tdNilai.textContent = item.score !== null && item.score !== undefined ? formatAngka(item.score, 2) : "—";

    tr.append(tdWaktu, tdKondisi, tdAturan, tdTicket, tdNilai);
    tr.addEventListener("click", () => saatPilih(item.id));
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        saatPilih(item.id);
      }
    });
    tbody.appendChild(tr);
  });
}

export async function muatBuktiDeteksi(detectionId, wadahEl) {
  if (!wadahEl) return;
  wadahEl.replaceChildren();
  const memuat = document.createElement("p");
  memuat.className = "kosong";
  memuat.textContent = "Memuat sumber data deteksi...";
  wadahEl.appendChild(memuat);
  try {
    const bukti = await request(`/detections/${encodeURIComponent(detectionId)}`);
    wadahEl.replaceChildren();
    const tingkat = String(bukti.severity || "warning").toLowerCase();
    const dl = document.createElement("dl");
    const info = [
      ["Kondisi", LABEL_KONDISI_DETEKSI[tingkat] || "Kenaikan di atas batas wajar"],
      ["Aturan", `${bukti.label} (${bukti.rule_id || "—"})`],
      ["Alasan", bukti.reason || "—"],
      ["Window analisis", `${formatWaktu(bukti.window_start)} – ${formatWaktu(bukti.window_end)}`],
      ["Ticket pengunjung", bukti.ticket || "Tidak terkait sesi pengunjung"],
      ["Alamat IP", bukti.client_ip || "—"],
      ["ID Aktivitas", bukti.activity_id || "—"]
    ];
    info.forEach(([k, v]) => {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      dl.append(dt, dd);
    });
    wadahEl.appendChild(dl);

    const daftarApp = Array.isArray(bukti.application_events) ? bukti.application_events : [];
    const subApp = document.createElement("h3");
    subApp.textContent = `Request pengunjung pada window (${daftarApp.length})`;
    wadahEl.appendChild(subApp);

    if (daftarApp.length) {
      const tabel = document.createElement("table");
      tabel.className = "tabel";
      tabel.innerHTML = "<thead><tr><th>Waktu</th><th>Method</th><th>Path</th><th>Status</th><th class=\"kol-angka\">Ukuran</th></tr></thead>";
      const tb = document.createElement("tbody");
      daftarApp.slice(0, 30).forEach((ev) => {
        const r = document.createElement("tr");
        [
          [formatWaktu(ev.observed_at, true), "mono"],
          [ev.method, "mono"],
          [ev.path, "mono"],
          [String(ev.status_code), "mono"],
          [`${formatAngka(ev.request_bytes)} B`, "kol-angka mono"]
        ].forEach(([teks, kls]) => {
          const td = document.createElement("td");
          td.className = kls;
          td.textContent = teks;
          r.appendChild(td);
        });
        tb.appendChild(r);
      });
      tabel.appendChild(tb);
      wadahEl.appendChild(tabel);
    } else {
      const p = document.createElement("p");
      p.className = "kosong";
      p.textContent = "Tidak ada application event pengunjung pada window ini.";
      wadahEl.appendChild(p);
    }

    const daftarPkt = Array.isArray(bukti.packet_events) ? bukti.packet_events : [];
    if (daftarPkt.length) {
      const subPkt = document.createElement("h3");
      subPkt.textContent = `Paket berkorelasi pada window (${daftarPkt.length})`;
      wadahEl.appendChild(subPkt);
    }
  } catch (galat) {
    wadahEl.replaceChildren();
    const p = document.createElement("p");
    p.className = "kosong";
    p.textContent = galat.message;
    wadahEl.appendChild(p);
  }
}

export function renderAlerts(daftar, wadahEl, jumlahEl, saatSegarkan) {
  if (!wadahEl) return;
  const baris = Array.isArray(daftar) ? daftar : [];
  if (jumlahEl) jumlahEl.textContent = `${formatAngka(baris.length)} alert`;
  wadahEl.replaceChildren();
  if (!baris.length) {
    const p = document.createElement("p");
    p.className = "hasil-teks";
    p.textContent = "Belum ada alert.";
    wadahEl.appendChild(p);
    return;
  }
  baris.forEach((item) => {
    const kartu = document.createElement("article");
    kartu.className = "kartu";
    const tingkat = String(item.severity || "warning").toLowerCase();
    kartu.dataset.tingkat = tingkat === "critical" ? "high" : tingkat;

    const judul = document.createElement("div");
    judul.className = "judul";
    judul.textContent = `${item.title} · ${item.status}`;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${formatWaktu(item.created_at)} · ${item.description}`;

    kartu.append(judul, meta);
    if (item.status === "open" || item.status === "acknowledged") {
      const aksi = document.createElement("div");
      aksi.className = "aksi";
      const tombol = document.createElement("button");
      tombol.type = "button";
      tombol.className = "tombol-sekunder";
      tombol.textContent = item.status === "open" ? "Tandai ditinjau" : "Selesaikan";
      tombol.addEventListener("click", async () => {
        tombol.disabled = true;
        try {
          const statusBerikut = item.status === "open" ? "acknowledged" : "resolved";
          await request(`/alerts/${encodeURIComponent(item.id)}`, {
            method: "PATCH",
            body: JSON.stringify({ status: statusBerikut })
          });
          await saatSegarkan();
        } catch (galat) {
          tombol.disabled = false;
          meta.textContent = galat.message;
        }
      });
      aksi.appendChild(tombol);
      kartu.appendChild(aksi);
    }
    wadahEl.appendChild(kartu);
  });
}

export function renderLogs(appEvents, sysLogs, tbodyApp, tbodySys) {
  if (tbodyApp) {
    const daftar = Array.isArray(appEvents) ? appEvents : [];
    if (!daftar.length) {
      barisKosong(tbodyApp, 8, "Belum ada application event.");
    } else {
      tbodyApp.replaceChildren();
      daftar.slice(0, 150).forEach((ev) => {
        const tr = document.createElement("tr");
        const internal = ev.origin === "internal_baseline";
        if (internal) tr.classList.add("internal");
        const sumber = internal ? "internal_baseline" : ev.ticket_code ? `Pengunjung (${ev.ticket_code})` : "Pengunjung";
        [
          [formatWaktu(ev.observed_at, true), "mono"],
          [sumber, ""],
          [ev.method || "—", "mono"],
          [ev.path || "—", "mono"],
          [String(ev.status_code ?? "—"), "mono"],
          [ev.client_ip || "—", "mono"],
          [`${formatAngka(ev.request_bytes || 0)} B`, "kol-angka mono"],
          [`${formatAngka(ev.response_bytes || 0)} B`, "kol-angka mono"]
        ].forEach(([teks, kls]) => {
          const td = document.createElement("td");
          if (kls) td.className = kls;
          td.textContent = teks;
          tr.appendChild(td);
        });
        tbodyApp.appendChild(tr);
      });
    }
  }
  if (tbodySys) {
    const daftar = Array.isArray(sysLogs) ? sysLogs : [];
    if (!daftar.length) {
      barisKosong(tbodySys, 5, "Belum ada system log.");
    } else {
      tbodySys.replaceChildren();
      daftar.slice(0, 150).forEach((log) => {
        const tr = document.createElement("tr");
        [
          [formatWaktu(log.created_at), "mono"],
          [log.level || "info", "mono"],
          [log.component || "—", "mono"],
          [log.event_type || "—", "mono"],
          [log.message || "—", ""]
        ].forEach(([teks, kls]) => {
          const td = document.createElement("td");
          if (kls) td.className = kls;
          td.textContent = teks;
          tr.appendChild(td);
        });
        tbodySys.appendChild(tr);
      });
    }
  }
}

export function renderInsiden(daftar, wadahEl, jumlahEl, saatSegarkan) {
  if (!wadahEl) return;
  const baris = Array.isArray(daftar) ? daftar : [];
  if (jumlahEl) jumlahEl.textContent = `${formatAngka(baris.length)} insiden`;
  wadahEl.replaceChildren();
  if (!baris.length) {
    const p = document.createElement("p");
    p.className = "hasil-teks";
    p.textContent = "Belum ada insiden yang memerlukan investigasi.";
    wadahEl.appendChild(p);
    return;
  }
  baris.forEach((item) => {
    const kartu = document.createElement("article");
    kartu.className = "kartu";
    kartu.dataset.tingkat = "high";

    const judul = document.createElement("div");
    judul.className = "judul";
    judul.textContent = `${item.label || "Insiden"} · ${item.status}`;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${formatWaktu(item.created_at)} · Ticket ${item.ticket_code || "—"} · ${item.reason || ""}`;

    kartu.append(judul, meta);
    if (item.status !== "resolved") {
      const aksi = document.createElement("div");
      aksi.className = "aksi";
      const tombol = document.createElement("button");
      tombol.type = "button";
      tombol.className = "tombol-sekunder";
      tombol.textContent = item.status === "open" ? "Mulai investigasi" : "Tandai selesai";
      tombol.addEventListener("click", async () => {
        tombol.disabled = true;
        try {
          const statusBerikut = item.status === "open" ? "investigating" : "resolved";
          await request(`/incidents/${encodeURIComponent(item.id)}`, {
            method: "PATCH",
            body: JSON.stringify({ status: statusBerikut })
          });
          await saatSegarkan();
        } catch (galat) {
          tombol.disabled = false;
          meta.textContent = galat.message;
        }
      });
      aksi.appendChild(tombol);
      kartu.appendChild(aksi);
    }
    wadahEl.appendChild(kartu);
  });
}

export function renderAnalisis(fitur, ringkasan, tbody, waktuEl) {
  if (!tbody) return;
  const f = fitur || {};
  if (waktuEl) {
    waktuEl.textContent = f.window_end
      ? `Window ${formatWaktu(f.window_start)} – ${formatWaktu(f.window_end)}`
      : "Belum ada window teranalisis";
  }
  const baris = [
    ["Request pengujian pengunjung", "Application event pengunjung", `${formatAngka(f.request_count || 0)} request (${formatAngka(f.request_rate || 0, 2)} req/d)`],
    ["Volume data pengunjung", "Application event pengunjung", `${formatByte(f.request_bytes || 0)} (${formatByte(f.bytes_per_second || 0)}/d)`],
    ["Rentang ukuran request pengunjung", "Application event pengunjung", f.request_count ? `${formatAngka(f.request_size_min || 0)} B – ${formatAngka(f.request_size_max || 0)} B (CV ${formatAngka(f.request_size_cv || 0, 2)})` : "—"],
    ["Heartbeat sesi pengunjung", "Dipisahkan dari perhitungan anomali", `${formatAngka(f.heartbeat_count || 0)} heartbeat`],
    ["Traffic normal internal", "internal_baseline (laptop)", `${formatAngka(f.internal_request_count || 0)} request (${formatAngka(f.internal_request_rate || 0, 2)} req/d)`],
    ["Volume data internal", "internal_baseline (laptop)", `${formatByte(f.internal_request_bytes || 0)} (${formatByte(f.internal_bytes_per_second || 0)}/d)`],
    ["Paket jaringan tertangkap", "Network sensor (Scapy)", `${formatAngka(f.packet_count || 0)} paket (${formatAngka(f.packet_rate || 0, 2)} pkt/d)`],
    ["Volume paket tertangkap", "Network sensor (Scapy)", `${formatByte(f.packet_bytes || 0)} (${formatByte(f.packet_bytes_per_second || 0)}/d)`],
    ["Total paket tersimpan", "Database SQLite", `${formatAngka(ringkasan?.total_packets || 0)} paket (${formatByte(ringkasan?.total_bytes || 0)})`]
  ];
  tbody.replaceChildren();
  baris.forEach(([nama, sumber, nilai]) => {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td");
    td1.textContent = nama;
    const td2 = document.createElement("td");
    td2.textContent = sumber;
    const td3 = document.createElement("td");
    td3.className = "kol-angka mono";
    td3.textContent = nilai;
    tr.append(td1, td2, td3);
    tbody.appendChild(tr);
  });
}

export function renderBaseline(baseline, fiturTerakhir, internalStatus, tbody, statusEl) {
  if (!tbody) return;
  const siap = baseline?.status === "ready";
  const sampel = Number(baseline?.sample_count || 0);
  if (statusEl) {
    statusEl.textContent = siap ? `Siap (${sampel} window)` : `Mengumpulkan (${sampel} window)`;
  }
  const dasar = baseline?.features || {};
  const kini = fiturTerakhir || {};
  const infoGen = internalStatus || {};
  const baris = [
    ["Target generator internal", `${formatAngka(infoGen.target_rate ?? 3, 1)} req/d`, `${formatAngka(infoGen.measured_rate ?? 0, 2)} req/d (10 detik terakhir)`],
    ["Laju request internal", `${formatAngka(dasar.internal_request_rate || 0, 2)} req/d`, `${formatAngka(kini.internal_request_rate || 0, 2)} req/d`],
    ["Volume byte internal", `${formatByte(dasar.internal_bytes_per_second || 0)}/d`, `${formatByte(kini.internal_bytes_per_second || 0)}/d`],
    ["Laju paket jaringan", `${formatAngka(dasar.packet_rate || 0, 2)} pkt/d`, `${formatAngka(kini.packet_rate || 0, 2)} pkt/d`],
    ["Variasi ukuran paket (CV)", formatAngka(dasar.packet_size_cv || 0, 2), formatAngka(kini.packet_size_cv || 0, 2)]
  ];
  tbody.replaceChildren();
  baris.forEach(([nama, nilaiDasar, nilaiKini]) => {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td");
    td1.textContent = nama;
    const td2 = document.createElement("td");
    td2.className = "kol-angka mono";
    td2.textContent = nilaiDasar;
    const td3 = document.createElement("td");
    td3.className = "kol-angka mono";
    td3.textContent = nilaiKini;
    tr.append(td1, td2, td3);
    tbody.appendChild(tr);
  });
}

export function renderKesehatan(health, ai, internalStatus, tbody, statusSensorEl) {
  if (!tbody) return;
  const komp = health?.components || {};
  const daftar = [
    ["Guest API (Port 8000)", health?.guest_api_status, komp.guest_api?.message || "Listener untuk perangkat pengunjung dan baseline internal."],
    ["Management API (Port 8001)", health?.management_api_status, komp.management_api?.message || "Listener lokal khusus dashboard."],
    ["Generator Baseline Internal", internalStatus?.status || komp.baseline_generator?.status, komp.baseline_generator?.message || `Mengirim sekitar ${internalStatus?.target_rate ?? 3} request/detik ke endpoint lokal.`],
    ["Network Sensor (Scapy/Npcap)", health?.sensor_status, komp.sensor?.message || "Pemeriksaan packet capture pada interface lokal."],
    ["Traffic Analyzer & Rule Engine", health?.analyzer_status, komp.analyzer?.message || "Menganalisis window traffic secara berkala."],
    ["Database SQLite", health?.database_status, "Penyimpanan lokal event, sesi, dan hasil deteksi."],
    ["WebSocket Dashboard", health?.websocket_status, komp.websocket?.message || "Aliran pembaruan langsung ke Web Utama."],
    ["Modul AI Pretrained (Opsional)", ai?.status || "disabled", ai?.message || "Rule Engine tetap berjalan tanpa ketergantungan pada modul AI."]
  ];
  tbody.replaceChildren();
  daftar.forEach(([nama, kode, pesan]) => {
    const [nada, label] = STATUS_LAYANAN[kode] || ["peringatan", kode || "Tidak diketahui"];
    const tr = document.createElement("tr");
    const tdNama = document.createElement("td");
    tdNama.textContent = nama;
    const tdStatus = document.createElement("td");
    tdStatus.className = "status-teks";
    tdStatus.dataset.tone = nada;
    tdStatus.textContent = label;
    const tdKet = document.createElement("td");
    tdKet.textContent = pesan;
    tr.append(tdNama, tdStatus, tdKet);
    tbody.appendChild(tr);
  });
  if (statusSensorEl) {
    const [, labelSensor] = STATUS_LAYANAN[health?.sensor_status] || ["peringatan", "Belum diketahui"];
    statusSensorEl.textContent = labelSensor;
  }
}
