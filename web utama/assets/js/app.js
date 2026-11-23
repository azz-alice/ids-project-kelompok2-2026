import { request } from "./api.js";
import { GrafikTraffic } from "./grafik.js";
import {
  muatBuktiDeteksi,
  renderAlerts,
  renderAnalisis,
  renderBaseline,
  renderInsiden,
  renderKesehatan,
  renderLogs,
  renderPengunjung,
  renderRingkasDeteksi,
  renderTabelDeteksi
} from "./halaman.js";
import { TabelTraffic } from "./tabel_traffic.js";

const KUNCI_TEMA = "ids-theme";
const root = document.documentElement;
const byId = (id) => document.getElementById(id);

const tombolTema = byId("theme-toggle");
const tombolMenu = byId("tombol-menu");
const menuSamping = byId("menu-samping");
const latarMenu = byId("latar-menu");
const statusKoneksi = byId("status-koneksi");
const kondisiTraffic = byId("kondisi-traffic");

const daftarMenu = [...document.querySelectorAll(".menu-item[data-halaman]")];
const daftarHalaman = [...document.querySelectorAll(".halaman[data-view]")];

const grafik = new GrafikTraffic({
  canvas: byId("grafik"),
  kosongEl: byId("grafik-kosong"),
  tooltipEl: byId("tooltip-grafik"),
  legendaEl: byId("legenda-grafik")
});

const tabelTraffic = new TabelTraffic({
  tbody: byId("isi-tabel-traffic"),
  kosongEl: byId("tabel-kosong"),
  jumlahEl: byId("jumlah-baris"),
  inputCari: byId("cari-ip"),
  selectProtocol: byId("filter-protocol"),
  selectSumber: byId("filter-sumber"),
  detailBox: byId("detail-baris"),
  detailIsi: byId("detail-isi"),
  tombolTutup: byId("tutup-detail")
});

const keadaan = {
  sesiAktif: [],
  deteksi: [],
  deteksiDipilih: null,
  timerSnapshot: null,
  timerSeri: null,
  kondisiTraffic: null
};

function formatDurasi(detik) {
  const d = Math.max(0, Math.floor(detik || 0));
  const m = Math.floor(d / 60);
  const s = d % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const LABEL_KONDISI_TEKNIS = {
  normal: "NORMAL",
  above_baseline: "DEVIASI BASELINE",
  anomalous: "ANOMALI TRAFFIC",
  recovering: "STABILISASI"
};

function perbaruiKondisiAi(tc) {
  if (!tc) return;
  keadaan.kondisiTraffic = { ...tc };
  const widget = byId("kondisi-widget");
  const teks = byId("kondisi-traffic");
  const waktu = byId("kondisi-waktu");
  if (!widget || !teks || !waktu) return;

  const kode = tc.code || "normal";
  const namaKondisi = LABEL_KONDISI_TEKNIS[kode] || tc.status || "NORMAL";
  widget.dataset.state = kode;
  teks.textContent = namaKondisi;

  let dur = 0;
  if (kode === "normal" || kode === "above_baseline") {
    dur = tc.normal_duration_seconds ?? 0;
  } else if (kode === "anomalous") {
    dur = tc.anomaly_duration_seconds ?? 0;
  } else if (kode === "recovering") {
    dur = tc.recovery_duration_seconds ?? 0;
  }
  waktu.textContent = formatDurasi(dur);
  widget.title = tc.message || namaKondisi;
}

function terapkanTema(tema) {
  root.dataset.theme = tema;
  if (tombolTema) {
    const label = tema === "dark" ? "Ganti ke tema terang" : "Ganti ke tema gelap";
    tombolTema.setAttribute("aria-label", label);
    tombolTema.title = label;
  }
  grafik.perbaruiData({ points: grafik.titik, has_events: grafik.adaEvent });
}

if (tombolTema) {
  terapkanTema(root.dataset.theme === "dark" ? "dark" : "light");
  tombolTema.addEventListener("click", () => {
    const berikut = root.dataset.theme === "dark" ? "light" : "dark";
    terapkanTema(berikut);
    try { localStorage.setItem(KUNCI_TEMA, berikut); } catch { return; }
  });
  window.addEventListener("storage", (event) => {
    if (event.key === KUNCI_TEMA && (event.newValue === "light" || event.newValue === "dark")) {
      terapkanTema(event.newValue);
    }
  });
}

function aturMenuTerbuka(terbuka, kembalikanFokus = false) {
  if (!menuSamping || !tombolMenu) return;
  document.body.classList.toggle("menu-terbuka", terbuka);
  tombolMenu.setAttribute("aria-expanded", String(terbuka));
  tombolMenu.setAttribute("aria-label", terbuka ? "Tutup menu" : "Buka menu");
  menuSamping.setAttribute("aria-hidden", String(!terbuka));
  menuSamping.inert = !terbuka;
  if (!terbuka && kembalikanFokus) tombolMenu.focus();
}

aturMenuTerbuka(false, false);

tombolMenu?.addEventListener("click", () => {
  const sedangTerbuka = document.body.classList.contains("menu-terbuka");
  aturMenuTerbuka(!sedangTerbuka, sedangTerbuka);
});
latarMenu?.addEventListener("click", () => aturMenuTerbuka(false, true));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.body.classList.contains("menu-terbuka")) {
    aturMenuTerbuka(false, true);
  }
});

function tampilkanHalaman(nama) {
  daftarHalaman.forEach((hal) => {
    const cocok = hal.dataset.view === nama;
    hal.hidden = !cocok;
    hal.classList.toggle("aktif", cocok);
  });
  daftarMenu.forEach((btn) => {
    const cocok = btn.dataset.halaman === nama;
    btn.classList.toggle("aktif", cocok);
    if (cocok) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  if (nama === "live") {
    tabelTraffic.render();
    requestAnimationFrame(() => grafik.gambar());
  }
}

daftarMenu.forEach((btn) => {
  btn.addEventListener("click", () => {
    tampilkanHalaman(btn.dataset.halaman);
    aturMenuTerbuka(false, false);
  });
});

tampilkanHalaman("live");

function setStatusKoneksi(kode, teks) {
  if (!statusKoneksi) return;
  statusKoneksi.dataset.state = kode;
  statusKoneksi.textContent = teks;
}

function pilihDeteksi(detectionId, bukaHalaman = false) {
  keadaan.deteksiDipilih = detectionId;
  if (bukaHalaman) tampilkanHalaman("deteksi");
  renderTabelDeteksi(
    keadaan.deteksi,
    byId("isi-deteksi"),
    byId("jumlah-deteksi"),
    keadaan.deteksiDipilih,
    (id) => pilihDeteksi(id, false)
  );
  muatBuktiDeteksi(detectionId, byId("bukti-deteksi"));
}

byId("lihat-deteksi")?.addEventListener("click", () => tampilkanHalaman("deteksi"));

function terapkanSnapshot(data) {
  if (!data) return;
  const tc = data.traffic_condition || {};
  perbaruiKondisiAi(tc);

  tabelTraffic.setSnapshot(data.traffic || [], data.application_events || []);

  keadaan.deteksi = Array.isArray(data.detections) ? data.detections : [];
  renderRingkasDeteksi(
    keadaan.deteksi,
    byId("panel-deteksi"),
    byId("deteksi-ringkas"),
    (id) => pilihDeteksi(id, true)
  );
  if (!keadaan.deteksiDipilih && keadaan.deteksi.length) {
    keadaan.deteksiDipilih = keadaan.deteksi[0].id;
    muatBuktiDeteksi(keadaan.deteksiDipilih, byId("bukti-deteksi"));
  }
  renderTabelDeteksi(
    keadaan.deteksi,
    byId("isi-deteksi"),
    byId("jumlah-deteksi"),
    keadaan.deteksiDipilih,
    (id) => pilihDeteksi(id, false)
  );

  keadaan.sesiAktif = Array.isArray(data.sessions) ? data.sessions : [];
  renderPengunjung(
    keadaan.sesiAktif,
    byId("isi-pengunjung"),
    byId("jumlah-pengunjung"),
    byId("cari-pengunjung")?.value || ""
  );

  renderAlerts(data.alerts || [], byId("daftar-alert"), byId("jumlah-alert"), muatSnapshot);
  renderLogs(data.application_events || [], data.system_logs || [], byId("isi-log-aplikasi"), byId("isi-log-sistem"));
  renderInsiden(data.incidents || [], byId("daftar-insiden"), byId("jumlah-insiden"), muatSnapshot);
  renderAnalisis(data.latest_features, data.overview, byId("isi-analisis"), byId("waktu-window"));
  renderBaseline(data.baseline, data.latest_features, data.internal_baseline, byId("isi-baseline"), byId("status-baseline"));
  renderKesehatan(data.health, data.ai, data.internal_baseline, byId("isi-kesehatan"), byId("status-sensor"));
}

async function muatSnapshot() {
  try {
    const data = await request("/dashboard/snapshot");
    terapkanSnapshot(data);
  } catch (galat) {
    setStatusKoneksi("disconnected", galat.message || "API tidak terjangkau");
  }
}

async function muatSeri() {
  if (document.hidden || byId("grafik-kotak")?.offsetParent === null) return;
  try {
    const data = await request("/dashboard/series?seconds=90");
    grafik.perbaruiData(data);
  } catch {
    return;
  }
}

function jadwalkanSnapshot(jeda = 220) {
  if (keadaan.timerSnapshot) return;
  keadaan.timerSnapshot = setTimeout(() => {
    keadaan.timerSnapshot = null;
    muatSnapshot();
  }, jeda);
}

function jadwalkanSeri(jeda = 260) {
  if (keadaan.timerSeri) return;
  keadaan.timerSeri = setTimeout(() => {
    keadaan.timerSeri = null;
    muatSeri();
  }, jeda);
}

async function muatInterfaceSensor() {
  const select = byId("pilih-interface");
  const pesan = byId("pesan-sensor");
  if (!select) return;
  try {
    const data = await request("/sensor/interfaces");
    select.replaceChildren();
    const awal = document.createElement("option");
    awal.value = "";
    awal.textContent = data.items?.length ? "Pilih interface lokal" : "Interface tidak ditemukan";
    select.appendChild(awal);
    (data.items || []).forEach((nama) => {
      const opt = document.createElement("option");
      opt.value = nama;
      opt.textContent = nama;
      select.appendChild(opt);
    });
  } catch (galat) {
    if (pesan) pesan.textContent = galat.message;
  }
}

async function ubahSensor(mulai) {
  const select = byId("pilih-interface");
  const pesan = byId("pesan-sensor");
  const tombol = byId(mulai ? "mulai-sensor" : "hentikan-sensor");
  const iface = select?.value || "";
  if (mulai && !iface) {
    if (pesan) pesan.textContent = "Pilih interface terlebih dahulu.";
    return;
  }
  if (tombol) tombol.disabled = true;
  try {
    const respon = await request(mulai ? "/sensor/start" : "/sensor/stop", {
      method: "POST",
      body: JSON.stringify(mulai ? { interface_name: iface } : {})
    });
    if (pesan) pesan.textContent = respon.message || "Status sensor diperbarui.";
    await muatSnapshot();
  } catch (galat) {
    if (pesan) pesan.textContent = galat.message;
    await muatSnapshot();
  } finally {
    if (tombol) tombol.disabled = false;
  }
}

async function muatStatusIntel() {
  const teks = byId("hasil-intel");
  if (!teks) return;
  try {
    const data = await request("/threat-intelligence/status");
    teks.textContent = `${data.status}: ${data.message}`;
  } catch (galat) {
    teks.textContent = galat.message;
  }
}

byId("form-intel")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = byId("input-intel");
  const tombol = byId("periksa-intel");
  const teks = byId("hasil-intel");
  const ip = (input?.value || "").trim();
  if (!ip) {
    if (teks) teks.textContent = "Masukkan alamat IP yang ingin diperiksa.";
    return;
  }
  if (tombol) tombol.disabled = true;
  if (teks) teks.textContent = "Memeriksa reputasi alamat IP...";
  try {
    const hasil = await request("/threat-intelligence/check", {
      method: "POST",
      body: JSON.stringify({ ip_address: ip })
    });
    const skor = hasil.score === null || hasil.score === undefined ? "" : ` (skor ${hasil.score}/100)`;
    if (teks) teks.textContent = `${hasil.status}: ${hasil.message}${skor}`;
  } catch (galat) {
    if (teks) teks.textContent = galat.message;
  } finally {
    if (tombol) tombol.disabled = false;
  }
});

byId("cari-pengunjung")?.addEventListener("input", (event) => {
  renderPengunjung(keadaan.sesiAktif, byId("isi-pengunjung"), byId("jumlah-pengunjung"), event.target.value);
});
byId("mulai-sensor")?.addEventListener("click", () => ubahSensor(true));
byId("hentikan-sensor")?.addEventListener("click", () => ubahSensor(false));

setInterval(() => {
  if (keadaan.kondisiTraffic) {
    const tc = keadaan.kondisiTraffic;
    const kode = tc.code || "normal";
    const waktu = byId("kondisi-waktu");
    if (waktu) {
      if (kode === "normal" || kode === "above_baseline") {
        if (typeof tc.normal_duration_seconds === "number") {
          tc.normal_duration_seconds += 1;
          waktu.textContent = formatDurasi(tc.normal_duration_seconds);
        }
      } else if (kode === "anomalous") {
        if (typeof tc.anomaly_duration_seconds === "number") {
          tc.anomaly_duration_seconds += 1;
          waktu.textContent = formatDurasi(tc.anomaly_duration_seconds);
        }
      } else if (kode === "recovering") {
        if (typeof tc.recovery_duration_seconds === "number") {
          tc.recovery_duration_seconds += 1;
          waktu.textContent = formatDurasi(tc.recovery_duration_seconds);
        }
      }
    }
  }

  muatSeri();

  if (!byId("isi-pengunjung")?.closest(".halaman")?.hidden) {
    renderPengunjung(
      keadaan.sesiAktif,
      byId("isi-pengunjung"),
      byId("jumlah-pengunjung"),
      byId("cari-pengunjung")?.value || ""
    );
  }
}, 1000);

function hubungkanWebSocket() {
  const skema = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${skema}//${window.location.host}/ws/dashboard`);
  setStatusKoneksi("waiting", "Menghubungkan");

  ws.addEventListener("open", () => {
    setStatusKoneksi("connected", "Terhubung");
  });

  ws.addEventListener("message", (event) => {
    let pesan;
    try {
      pesan = JSON.parse(event.data);
    } catch {
      return;
    }
    if (pesan.type === "snapshot") {
      terapkanSnapshot(pesan.data);
      return;
    }
    if (pesan.type === "packet") {
      tabelTraffic.tambahPacket(pesan.data);
      return;
    }
    if (pesan.type === "application_event") {
      tabelTraffic.tambahAplikasi(pesan.data);
      if (pesan.data && pesan.data.origin !== "internal") {
        jadwalkanSnapshot(150);
      }
      return;
    }
    if (pesan.type === "traffic_condition") {
      perbaruiKondisiAi(pesan.data);
      jadwalkanSnapshot();
      return;
    }
    if (["detection", "alert", "incident", "session", "activity", "health"].includes(pesan.type)) {
      jadwalkanSnapshot();
    }
    if (pesan.type === "traffic_window") {
      jadwalkanSeri(200);
    }
  });

  ws.addEventListener("close", () => {
    setStatusKoneksi("disconnected", "Terputus");
    setTimeout(muatSnapshot, 400);
    setTimeout(hubungkanWebSocket, 2500);
  });

  ws.addEventListener("error", () => ws.close());
}

muatSnapshot();
muatSeri();
muatInterfaceSensor();
muatStatusIntel();
hubungkanWebSocket();
