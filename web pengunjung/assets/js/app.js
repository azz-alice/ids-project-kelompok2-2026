import { authHeaders, postJson, requestJson } from "./api.js";

const KUNCI_TOKEN = "ids-session-token";
const KUNCI_TIKET = "ids-session-ticket";
const KUNCI_TEMA = "ids-theme";
const INTERVAL_HEARTBEAT_MS = 8000;

const penyimpanan = {
  ambil(kunci) {
    try { return localStorage.getItem(kunci); } catch { return null; }
  },
  simpan(kunci, nilai) {
    try { localStorage.setItem(kunci, nilai); } catch { return; }
  },
  hapus(kunci) {
    try { localStorage.removeItem(kunci); } catch { return; }
  }
};

const elemen = {
  sesi: document.getElementById("sesi"),
  tiket: document.getElementById("tiket"),
  timer: document.getElementById("timer"),
  status: document.getElementById("status-sesi"),
  selesai: document.getElementById("sesi-selesai"),
  pesanSesi: document.getElementById("pesan-sesi"),
  sesiBaru: document.getElementById("sesi-baru"),
  pesan: document.getElementById("pesan-pengiriman"),
  jumlah: document.getElementById("hasil-jumlah"),
  byte: document.getElementById("hasil-byte"),
  jeda: document.getElementById("hasil-jeda"),
  hentikan: document.getElementById("hentikan"),
  tema: document.getElementById("theme-toggle"),
  pilihan: [...document.querySelectorAll("[data-scenario]")]
};

const keadaan = {
  sesi: null,
  token: null,
  offsetServerMs: 0,
  sibuk: false,
  pengendali: null,
  skenarioAktif: null,
  berakhir: true
};

function terapkanTema(tema) {
  document.documentElement.dataset.theme = tema;
  const label = tema === "dark" ? "Ganti ke tema terang" : "Ganti ke tema gelap";
  elemen.tema.setAttribute("aria-label", label);
  elemen.tema.title = label;
}
terapkanTema(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
elemen.tema.addEventListener("click", () => {
  const berikut = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  terapkanTema(berikut);
  penyimpanan.simpan(KUNCI_TEMA, berikut);
});
window.addEventListener("storage", (event) => {
  if (event.key === KUNCI_TEMA && (event.newValue === "light" || event.newValue === "dark")) terapkanTema(event.newValue);
});

const waktuServer = () => Date.now() + keadaan.offsetServerMs;

function sinkronWaktu(serverTime) {
  const nilai = new Date(serverTime || "").getTime();
  if (Number.isFinite(nilai)) keadaan.offsetServerMs = nilai - Date.now();
}

const sisaDetik = (iso) => (iso ? Math.max(0, Math.ceil((new Date(iso).getTime() - waktuServer()) / 1000)) : 0);

function formatWaktu(detik) {
  return `${String(Math.floor(detik / 60)).padStart(2, "0")}:${String(detik % 60).padStart(2, "0")}`;
}

function formatByte(nilai) {
  if (nilai < 1024) return `${nilai} B`;
  return `${(nilai / 1024).toFixed(1).replace(".", ",")} KB`;
}

function setPesan(teks, nada = "") {
  elemen.pesan.textContent = teks;
  if (nada) elemen.pesan.dataset.tone = nada;
  else delete elemen.pesan.dataset.tone;
}

function tampilkanSesi(status, label, pesan = "") {
  elemen.sesi.dataset.state = status;
  elemen.status.textContent = label;
  elemen.selesai.hidden = !pesan;
  elemen.pesanSesi.textContent = pesan;
}

function perbaruiTombol() {
  const jedaDetik = sisaDetik(keadaan.sesi?.cooldown_until);
  const siap = !keadaan.berakhir && !keadaan.sibuk && jedaDetik === 0;
  elemen.pilihan.forEach((tombol) => {
    tombol.disabled = !siap;
    tombol.setAttribute("aria-pressed", String(keadaan.sibuk && tombol.dataset.scenario === keadaan.skenarioAktif));
  });
  elemen.jeda.textContent = keadaan.berakhir ? "—" : jedaDetik > 0 ? `${jedaDetik} detik` : "Siap";
  elemen.hentikan.hidden = !keadaan.sibuk;
}

function perbaruiTimer() {
  if (!keadaan.sesi) return;
  const sisa = sisaDetik(keadaan.sesi.expires_at);
  elemen.timer.textContent = formatWaktu(sisa);
  if (sisa === 0 && !keadaan.berakhir) akhiriSesi();
  else perbaruiTombol();
}

function pakaiSesi(data) {
  keadaan.sesi = {
    ...keadaan.sesi,
    ticket_code: data.ticket_code ?? keadaan.sesi?.ticket_code,
    expires_at: data.expires_at,
    cooldown_until: data.cooldown_until ?? null
  };
  keadaan.berakhir = false;
  elemen.tiket.textContent = keadaan.sesi.ticket_code || "—";
  tampilkanSesi("aktif", "Sesi aktif");
  perbaruiTimer();
}

function akhiriSesi(pesan = "Sesi selesai. Mulai sesi baru untuk melanjutkan.") {
  keadaan.berakhir = true;
  if (keadaan.pengendali) keadaan.pengendali.abort();
  elemen.timer.textContent = "00:00";
  tampilkanSesi("selesai", "Sesi selesai", pesan);
  perbaruiTombol();
}

async function buatSesi() {
  const data = await postJson("/api/session/create", {});
  sinkronWaktu(data.server_time);
  keadaan.token = data.session_token;
  keadaan.sesi = { ticket_code: data.ticket_code };
  penyimpanan.simpan(KUNCI_TOKEN, data.session_token);
  penyimpanan.simpan(KUNCI_TIKET, data.ticket_code);
  pakaiSesi(data);
}

async function mulaiSesiBaru() {
  elemen.sesiBaru.disabled = true;
  tampilkanSesi("memuat", "Membuat sesi");
  penyimpanan.hapus(KUNCI_TOKEN);
  try {
    await buatSesi();
    setPesan("Belum ada aktivitas dikirim.");
    elemen.jumlah.textContent = "—";
    elemen.byte.textContent = "—";
  } catch (galat) {
    keadaan.berakhir = true;
    tampilkanSesi("gagal", "Sesi tidak dibuat", galat.status === 409 ? "Pengunjung aktif sudah penuh. Coba lagi sebentar." : galat.message);
    perbaruiTombol();
  } finally {
    elemen.sesiBaru.disabled = false;
  }
}

async function pulihkanSesi() {
  const token = penyimpanan.ambil(KUNCI_TOKEN);
  if (!token) {
    await mulaiSesiBaru();
    return;
  }
  keadaan.token = token;
  elemen.tiket.textContent = penyimpanan.ambil(KUNCI_TIKET) || "—";
  try {
    const data = await requestJson("/api/session/current", { headers: authHeaders(token) });
    sinkronWaktu(data.server_time);
    keadaan.sesi = { ticket_code: data.ticket_code };
    penyimpanan.simpan(KUNCI_TIKET, data.ticket_code);
    pakaiSesi(data);
  } catch (galat) {
    if (galat.status === 401) {
      keadaan.sesi = null;
      akhiriSesi();
    } else {
      keadaan.berakhir = true;
      tampilkanSesi("gagal", "Server tidak terjangkau", "Tidak dapat memeriksa sesi ke server.");
      elemen.sesiBaru.textContent = "Coba lagi";
      elemen.sesiBaru.dataset.mode = "ulang";
      perbaruiTombol();
    }
  }
}

function tidur(milidetik, sinyal) {
  return new Promise((selesai, tolak) => {
    if (sinyal.aborted) return tolak(new DOMException("Dihentikan", "AbortError"));
    const pewaktu = setTimeout(() => {
      sinyal.removeEventListener("abort", batal);
      selesai();
    }, milidetik);
    const batal = () => {
      clearTimeout(pewaktu);
      tolak(new DOMException("Dihentikan", "AbortError"));
    };
    sinyal.addEventListener("abort", batal, { once: true });
  });
}

async function jalankanSkenario(nama) {
  if (keadaan.berakhir || keadaan.sibuk) return;
  const token = keadaan.token;
  const pengendali = new AbortController();
  keadaan.pengendali = pengendali;
  keadaan.sibuk = true;
  keadaan.skenarioAktif = nama;
  perbaruiTombol();
  elemen.jumlah.textContent = "0";
  elemen.byte.textContent = "0 B";
  setPesan("Menyiapkan aktivitas.");
  let idAktivitas = null;
  let rencana = 0;
  let diterima = 0;
  let totalByte = 0;
  try {
    const paket = await postJson("/api/activity", { scenario: nama }, token);
    idAktivitas = paket.activity_id;
    rencana = paket.planned_request_count;
    keadaan.sesi.cooldown_until = paket.cooldown_until;
    perbaruiTombol();
    for (const [indeks, ukuran] of paket.payload_sizes.entries()) {
      if (indeks > 0) await tidur(paket.interval_seconds * 1000, pengendali.signal);
      const balasan = await postJson(
        "/api/activity/probe",
        { activity_id: idAktivitas, payload: "x".repeat(ukuran) },
        token,
        { "X-IDS-Activity-Id": idAktivitas },
        pengendali.signal
      );
      diterima = balasan.completed_request_count;
      totalByte += ukuran;
      elemen.jumlah.textContent = `${diterima} dari ${rencana}`;
      elemen.byte.textContent = formatByte(totalByte);
      setPesan(`Mengirim ${paket.scenario_label}: ${diterima} dari ${rencana} request.`);
    }
    setPesan(`${paket.scenario_label} selesai. ${diterima} request diterima server.`, "berhasil");
  } catch (galat) {
    if (galat.name === "AbortError") {
      setPesan(`Pengiriman dihentikan setelah ${diterima} request.`);
    } else if (galat.status === 401) {
      akhiriSesi();
      setPesan("Pengiriman berhenti karena sesi selesai.", "galat");
    } else {
      if (galat.status === 429 && galat.retryAfter > 0 && keadaan.sesi) {
        keadaan.sesi.cooldown_until = new Date(waktuServer() + galat.retryAfter * 1000).toISOString();
      }
      setPesan(galat.message, "galat");
    }
  } finally {
    keadaan.pengendali = null;
    keadaan.sibuk = false;
    keadaan.skenarioAktif = null;
    perbaruiTombol();
    if (idAktivitas && diterima < rencana && token) await batalkanAktivitas(idAktivitas, token);
  }
}

async function batalkanAktivitas(idAktivitas, token) {
  try {
    const status = await requestJson(`/api/activity/${idAktivitas}`, { headers: authHeaders(token) });
    elemen.jumlah.textContent = `${status.request_count} dari ${status.planned_count}`;
    elemen.byte.textContent = formatByte(status.actual_payload_bytes);
    if (status.status === "running") await postJson(`/api/activity/${idAktivitas}/cancel`, {}, token);
  } catch {
    return;
  }
}

async function kirimHeartbeat() {
  if (keadaan.berakhir || !keadaan.token) return;
  try {
    const data = await postJson("/api/session/heartbeat", {}, keadaan.token);
    sinkronWaktu(data.server_time);
    keadaan.sesi.expires_at = data.expires_at;
    keadaan.sesi.cooldown_until = data.cooldown_until ?? null;
    perbaruiTimer();
  } catch (galat) {
    if (galat.status === 401) akhiriSesi();
  }
}

elemen.pilihan.forEach((tombol) => tombol.addEventListener("click", () => jalankanSkenario(tombol.dataset.scenario)));
elemen.hentikan.addEventListener("click", () => keadaan.pengendali?.abort());
elemen.sesiBaru.addEventListener("click", () => {
  if (elemen.sesiBaru.dataset.mode === "ulang") {
    delete elemen.sesiBaru.dataset.mode;
    elemen.sesiBaru.textContent = "Mulai sesi baru";
    pulihkanSesi();
  } else {
    mulaiSesiBaru();
  }
});

setInterval(perbaruiTimer, 250);
setInterval(kirimHeartbeat, INTERVAL_HEARTBEAT_MS);
pulihkanSesi();
