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
  status: document.getElementById("status-sesi"),
  selesai: document.getElementById("sesi-selesai"),
  pesanSesi: document.getElementById("pesan-sesi"),
  sesiBaru: document.getElementById("sesi-baru"),
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

function tampilkanSesi(status, label, pesan = "") {
  elemen.sesi.dataset.state = status;
  elemen.status.textContent = label;
  elemen.selesai.hidden = !pesan;
  elemen.pesanSesi.textContent = pesan;
}

function perbaruiTombol() {
  if (keadaan.sesi && sisaDetik(keadaan.sesi.expires_at) === 0 && !keadaan.berakhir) {
    akhiriSesi();
    return;
  }
  const jedaDetik = sisaDetik(keadaan.sesi?.cooldown_until);
  const siap = !keadaan.berakhir && !keadaan.sibuk && jedaDetik === 0;
  elemen.pilihan.forEach((tombol) => {
    tombol.disabled = !siap;
    tombol.setAttribute("aria-pressed", String(keadaan.sibuk && tombol.dataset.scenario === keadaan.skenarioAktif));
  });
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
  perbaruiTombol();
}

function akhiriSesi(pesan = "Sesi selesai. Mulai sesi baru untuk melanjutkan.") {
  keadaan.berakhir = true;
  if (keadaan.pengendali) keadaan.pengendali.abort();
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
  let idAktivitas = null;
  let rencana = 0;
  let diterima = 0;

  const protokol = "RANDOM";
  const batchCount = 30;
  const mode = "burst";

  try {
    const payloadAktivitas = { scenario: nama, protocol: protokol, mode, batch_count: batchCount };
    const paket = await postJson("/api/activity", payloadAktivitas, token);
    idAktivitas = paket.activity_id;
    rencana = paket.planned_request_count;
    keadaan.sesi.cooldown_until = paket.cooldown_until;
    perbaruiTombol();

    for (const [indeks, ukuran] of paket.payload_sizes.entries()) {
      if (indeks > 0) await tidur(paket.interval_seconds * 1000, pengendali.signal);
      const balasan = await postJson(
        "/api/activity/probe-protocol",
        { activity_id: idAktivitas, protocol: protokol, payload: "x".repeat(ukuran) },
        token,
        { "X-IDS-Activity-Id": idAktivitas },
        pengendali.signal
      );
      diterima = balasan.completed_request_count;
    }
  } catch (galat) {
    if (galat.status === 401) {
      akhiriSesi();
    } else if (galat.status === 429 && galat.retryAfter > 0 && keadaan.sesi) {
      keadaan.sesi.cooldown_until = new Date(waktuServer() + galat.retryAfter * 1000).toISOString();
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
    perbaruiTombol();
  } catch (galat) {
    if (galat.status === 401) akhiriSesi();
  }
}

elemen.pilihan.forEach((tombol) => tombol.addEventListener("click", () => jalankanSkenario(tombol.dataset.scenario)));
elemen.sesiBaru.addEventListener("click", () => {
  if (elemen.sesiBaru.dataset.mode === "ulang") {
    delete elemen.sesiBaru.dataset.mode;
    elemen.sesiBaru.textContent = "Mulai sesi baru";
    pulihkanSesi();
  } else {
    mulaiSesiBaru();
  }
});

setInterval(perbaruiTombol, 1000);
setInterval(kirimHeartbeat, INTERVAL_HEARTBEAT_MS);
pulihkanSesi();
