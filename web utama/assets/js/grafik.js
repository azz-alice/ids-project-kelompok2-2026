import { formatAngka, formatByte, formatWaktu } from "./format.js";

const KONFIG_METRIK = {
  request: {
    satuan: "req/d",
    batasMinimum: 5,
    formatNilai: (nilai) => `${formatAngka(nilai, 0)} req/d`,
    seri: [
      { kunci: "visitor", label: "Request pengunjung", varWarna: "--accent" },
      { kunci: "internal", label: "Request internal (baseline)", varWarna: "--series-internal" }
    ]
  },
  paket: {
    satuan: "pkt/d",
    batasMinimum: 10,
    formatNilai: (nilai) => `${formatAngka(nilai, 0)} pkt/d`,
    seri: [
      { kunci: "packets", label: "Paket tertangkap", varWarna: "--accent" }
    ]
  },
  byte: {
    satuan: "B/d",
    batasMinimum: 2048,
    formatNilai: (nilai) => `${formatByte(nilai)}/d`,
    seri: [
      { kunci: "app_bytes", label: "Byte HTTP", varWarna: "--accent" },
      { kunci: "packet_bytes", label: "Byte paket", varWarna: "--series-internal" }
    ]
  }
};

function gambarKurvaHalus(ctx, koordinat) {
  if (!koordinat.length) return;
  ctx.beginPath();
  ctx.moveTo(koordinat[0].x, koordinat[0].y);
  if (koordinat.length === 1) {
    ctx.lineTo(koordinat[0].x + 0.5, koordinat[0].y);
    ctx.stroke();
    return;
  }
  if (koordinat.length === 2) {
    ctx.lineTo(koordinat[1].x, koordinat[1].y);
    ctx.stroke();
    return;
  }
  const batasAtasY = Math.min(...koordinat.map((t) => t.y));
  const batasBawahY = Math.max(...koordinat.map((t) => t.y));
  for (let i = 0; i < koordinat.length - 1; i += 1) {
    const p0 = koordinat[i - 1] || koordinat[i];
    const p1 = koordinat[i];
    const p2 = koordinat[i + 1];
    const p3 = koordinat[i + 2] || p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp1y = Math.max(batasAtasY, Math.min(batasBawahY, p1.y + (p2.y - p0.y) / 6));
    const cp2y = Math.max(batasAtasY, Math.min(batasBawahY, p2.y - (p3.y - p1.y) / 6));
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
  }
  ctx.stroke();
}

export class GrafikTraffic {
  constructor({ canvas, kosongEl, tooltipEl, legendaEl, selectMetrik }) {
    this.canvas = canvas;
    this.kosongEl = kosongEl;
    this.tooltipEl = tooltipEl;
    this.legendaEl = legendaEl;
    this.selectMetrik = selectMetrik;
    this.metrik = selectMetrik?.value || "request";
    this.titik = [];
    this.adaEvent = false;
    this.indeksSorot = null;
    this.domainY = 5;
    this.targetDomainY = 5;
    this.animasiId = null;

    this._ikatPeristiwa();
    this._renderLegenda();
  }

  _ikatPeristiwa() {
    if (this.selectMetrik) {
      this.selectMetrik.addEventListener("change", () => {
        this.metrik = this.selectMetrik.value;
        this.indeksSorot = null;
        this._sembunyikanTooltip();
        this._renderLegenda();
        this._hitungDomainTarget(true);
        this.gambar();
      });
    }
    this.canvas.addEventListener("mousemove", (event) => this._saatKursor(event));
    this.canvas.addEventListener("mouseleave", () => {
      this.indeksSorot = null;
      this._sembunyikanTooltip();
      this.gambar();
    });
    window.addEventListener("resize", () => this.gambar());
  }

  _ambilWarna(varNama) {
    return getComputedStyle(document.documentElement).getPropertyValue(varNama).trim() || "#2F5D8A";
  }

  _renderLegenda() {
    if (!this.legendaEl) return;
    const konfig = KONFIG_METRIK[this.metrik] || KONFIG_METRIK.request;
    this.legendaEl.replaceChildren();
    konfig.seri.forEach((seri) => {
      const span = document.createElement("span");
      const ikon = document.createElement("i");
      ikon.style.backgroundColor = this._ambilWarna(seri.varWarna);
      span.append(ikon, document.createTextNode(`${seri.label} (${konfig.satuan})`));
      this.legendaEl.appendChild(span);
    });
  }

  _hitungDomainTarget(langsung = false) {
    const konfig = KONFIG_METRIK[this.metrik] || KONFIG_METRIK.request;
    let maks = konfig.batasMinimum;
    this.titik.forEach((item) => {
      konfig.seri.forEach((seri) => {
        const nilai = Number(item[seri.kunci] || 0);
        if (nilai > maks) maks = nilai;
      });
    });
    this.targetDomainY = Math.ceil(maks * 1.18);
    if (langsung || !Number.isFinite(this.domainY) || this.domainY <= 0) {
      this.domainY = this.targetDomainY;
    }
  }

  perbaruiData(respon) {
    const daftar = Array.isArray(respon?.points) ? respon.points : [];
    this.titik = daftar.slice(-90);
    this.adaEvent = Boolean(respon?.has_events);
    this._renderLegenda();
    this._hitungDomainTarget(false);
    this._jalankanTransisi();
  }

  _jalankanTransisi() {
    if (this.animasiId) cancelAnimationFrame(this.animasiId);
    const langkah = () => {
      const selisih = this.targetDomainY - this.domainY;
      if (Math.abs(selisih) > 0.08) {
        this.domainY += selisih * 0.28;
        this.gambar();
        this.animasiId = requestAnimationFrame(langkah);
      } else {
        this.domainY = this.targetDomainY;
        this.animasiId = null;
        this.gambar();
      }
    };
    langkah();
  }

  _areaGambar(lebar, tinggi) {
    const kiri = 58;
    const kanan = Math.max(kiri + 40, lebar - 16);
    const atas = 14;
    const bawah = Math.max(atas + 40, tinggi - 26);
    const tinggiPlot = bawah - atas;
    const yNol = bawah - Math.max(10, Math.round(tinggiPlot * 0.1));
    const yPuncak = atas + 6;
    return { kiri, kanan, atas, bawah, yNol, yPuncak };
  }

  _posisiTitik(indeks, nilai, area, maksY) {
    const jumlah = this.titik.length;
    const x = jumlah <= 1
      ? area.kiri
      : area.kiri + ((area.kanan - area.kiri) * indeks) / (jumlah - 1);
    const rasio = Math.max(0, Math.min(1, Number(nilai || 0) / Math.max(1, maksY)));
    const y = area.yNol - rasio * (area.yNol - area.yPuncak);
    return { x, y };
  }

  _saatKursor(event) {
    if (!this.titik.length) return;
    const rect = this.canvas.getBoundingClientRect();
    const area = this._areaGambar(rect.width, rect.height);
    const xRel = event.clientX - rect.left;
    if (xRel < area.kiri - 8 || xRel > area.kanan + 8) {
      this.indeksSorot = null;
      this._sembunyikanTooltip();
      this.gambar();
      return;
    }
    const rasio = (xRel - area.kiri) / Math.max(1, area.kanan - area.kiri);
    const indeks = Math.max(0, Math.min(this.titik.length - 1, Math.round(rasio * (this.titik.length - 1))));
    this.indeksSorot = indeks;
    this._tampilkanTooltip(indeks, rect, area);
    this.gambar();
  }

  _sembunyikanTooltip() {
    if (this.tooltipEl) this.tooltipEl.hidden = true;
  }

  _tampilkanTooltip(indeks, rect, area) {
    const data = this.titik[indeks];
    if (!data || !this.tooltipEl) return;
    const konfig = KONFIG_METRIK[this.metrik] || KONFIG_METRIK.request;
    this.tooltipEl.replaceChildren();

    const waktu = document.createElement("div");
    waktu.className = "waktu";
    waktu.textContent = formatWaktu(data.t);
    this.tooltipEl.appendChild(waktu);

    konfig.seri.forEach((seri) => {
      const baris = document.createElement("div");
      baris.className = "nilai";
      const label = document.createElement("span");
      label.textContent = seri.label;
      const nilai = document.createElement("b");
      nilai.textContent = konfig.formatNilai(data[seri.kunci] || 0);
      baris.append(label, nilai);
      this.tooltipEl.appendChild(baris);
    });

    this.tooltipEl.hidden = false;
    const pos = this._posisiTitik(indeks, 0, area, this.domainY);
    const lebarTip = this.tooltipEl.offsetWidth || 170;
    const kiri = Math.min(Math.max(area.kiri, pos.x - lebarTip / 2), rect.width - lebarTip - 8);
    this.tooltipEl.style.left = `${Math.round(kiri)}px`;
    this.tooltipEl.style.top = "10px";
  }

  gambar() {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const lebarPiksel = Math.round(rect.width * dpr);
    const tinggiPiksel = Math.round(rect.height * dpr);
    if (this.canvas.width !== lebarPiksel || this.canvas.height !== tinggiPiksel) {
      this.canvas.width = lebarPiksel;
      this.canvas.height = tinggiPiksel;
    }
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);

    const area = this._areaGambar(rect.width, rect.height);
    const konfig = KONFIG_METRIK[this.metrik] || KONFIG_METRIK.request;
    const maksY = Math.max(konfig.batasMinimum, this.domainY || konfig.batasMinimum);
    const warnaGaris = this._ambilWarna("--line-soft");
    const warnaBatas = this._ambilWarna("--line");
    const warnaTeks = this._ambilWarna("--text-muted");

    ctx.font = '12px "Cascadia Mono", Consolas, monospace';
    ctx.fillStyle = warnaTeks;
    ctx.textBaseline = "middle";

    const langkahGrid = [0, 0.5, 1];
    langkahGrid.forEach((fraksi) => {
      const y = Math.round(area.yNol - fraksi * (area.yNol - area.yPuncak)) + 0.5;
      ctx.strokeStyle = warnaGaris;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(area.kiri, y);
      ctx.lineTo(area.kanan, y);
      ctx.stroke();

      const nilaiLabel = Math.round(maksY * fraksi);
      const teks = this.metrik === "byte" && nilaiLabel >= 1024
        ? `${(nilaiLabel / 1024).toFixed(1)}K`
        : `${nilaiLabel}`;
      ctx.textAlign = "right";
      ctx.fillText(teks, area.kiri - 8, y);
    });

    ctx.textAlign = "left";
    ctx.fillText(konfig.satuan, 8, area.atas + 2);

    ctx.strokeStyle = warnaBatas;
    ctx.beginPath();
    ctx.moveTo(area.kiri, area.bawah + 0.5);
    ctx.lineTo(area.kanan, area.bawah + 0.5);
    ctx.stroke();

    if (!this.titik.length) {
      if (this.kosongEl) {
        this.kosongEl.textContent = "Menunggu data traffic aktual dari backend.";
        this.kosongEl.hidden = false;
      }
      return;
    }

    const totalNilai = this.titik.reduce(
      (akum, item) => akum + konfig.seri.reduce((sub, s) => sub + Number(item[s.kunci] || 0), 0),
      0
    );
    if (this.kosongEl) {
      if (!this.adaEvent || totalNilai === 0) {
        this.kosongEl.textContent = this.metrik === "paket"
          ? "Belum ada paket tertangkap pada rentang waktu ini."
          : "Belum ada traffic pada rentang waktu ini.";
        this.kosongEl.hidden = false;
      } else {
        this.kosongEl.hidden = true;
      }
    }

    const indeksLabelWaktu = [0, Math.floor((this.titik.length - 1) / 2), this.titik.length - 1];
    ctx.textBaseline = "top";
    indeksLabelWaktu.forEach((idx, urutan) => {
      const item = this.titik[idx];
      if (!item) return;
      const pos = this._posisiTitik(idx, 0, area, maksY);
      ctx.textAlign = urutan === 0 ? "left" : urutan === 2 ? "right" : "center";
      ctx.fillText(formatWaktu(item.t), pos.x, area.bawah + 6);
    });

    [...konfig.seri].reverse().forEach((seri) => {
      const warna = this._ambilWarna(seri.varWarna);
      const koordinat = this.titik.map((item, idx) =>
        this._posisiTitik(idx, item[seri.kunci] || 0, area, maksY)
      );
      ctx.strokeStyle = warna;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      gambarKurvaHalus(ctx, koordinat);
    });

    if (this.indeksSorot !== null && this.titik[this.indeksSorot]) {
      const idx = this.indeksSorot;
      const posX = this._posisiTitik(idx, 0, area, maksY).x;
      ctx.strokeStyle = warnaBatas;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(posX + 0.5, area.atas);
      ctx.lineTo(posX + 0.5, area.bawah);
      ctx.stroke();

      konfig.seri.forEach((seri) => {
        const titik = this._posisiTitik(idx, this.titik[idx][seri.kunci] || 0, area, maksY);
        ctx.fillStyle = this._ambilWarna(seri.varWarna);
        ctx.beginPath();
        ctx.arc(titik.x, titik.y, 3.5, 0, Math.PI * 2);
        ctx.fill();
      });
    }
  }
}
