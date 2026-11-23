import { formatAngka, formatByte, formatWaktu } from "./format.js";

function hitungTangenMonotone(koordinat) {
  const n = koordinat.length;
  const dxs = new Array(n - 1);
  const ms = new Array(n - 1);
  for (let i = 0; i < n - 1; i += 1) {
    const dx = koordinat[i + 1].x - koordinat[i].x;
    const dy = koordinat[i + 1].y - koordinat[i].y;
    dxs[i] = dx;
    ms[i] = dx === 0 ? 0 : dy / dx;
  }

  const tangen = new Array(n);
  tangen[0] = ms[0] || 0;
  for (let i = 1; i < n - 1; i += 1) {
    const m0 = ms[i - 1];
    const m1 = ms[i];
    if (m0 * m1 <= 0) {
      tangen[i] = 0;
    } else {
      tangen[i] = (m0 + m1) / 2;
    }
  }
  tangen[n - 1] = ms[n - 2] || 0;

  for (let i = 0; i < n - 1; i += 1) {
    const m = ms[i];
    if (m === 0) {
      tangen[i] = 0;
      tangen[i + 1] = 0;
    } else {
      const a = tangen[i] / m;
      const b = tangen[i + 1] / m;
      const s = a * a + b * b;
      if (s > 9) {
        const tau = 3 / Math.sqrt(s);
        tangen[i] = tau * a * m;
        tangen[i + 1] = tau * b * m;
      }
    }
  }
  return { dxs, tangen };
}

function gambarKurvaFleksibel(ctx, koordinat) {
  const n = koordinat.length;
  if (!n) return;
  if (n === 1) {
    ctx.beginPath();
    ctx.arc(koordinat[0].x, koordinat[0].y, 1.5, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  if (n === 2) {
    ctx.beginPath();
    ctx.moveTo(koordinat[0].x, koordinat[0].y);
    ctx.lineTo(koordinat[1].x, koordinat[1].y);
    ctx.stroke();
    return;
  }

  const { dxs, tangen } = hitungTangenMonotone(koordinat);
  ctx.beginPath();
  ctx.moveTo(koordinat[0].x, koordinat[0].y);
  for (let i = 0; i < n - 1; i += 1) {
    const p1 = koordinat[i];
    const p2 = koordinat[i + 1];
    const dx = dxs[i];
    const cp1x = p1.x + dx / 3;
    const cp1y = p1.y + (tangen[i] * dx) / 3;
    const cp2x = p2.x - dx / 3;
    const cp2y = p2.y - (tangen[i + 1] * dx) / 3;
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
  }
  ctx.stroke();
}

function gambarAreaFleksibel(ctx, koordinat, yNol, warnaHex, opasitasPuncak = 0.12) {
  const n = koordinat.length;
  if (n < 2) return;
  const minY = Math.min(...koordinat.map((k) => k.y));
  const grad = ctx.createLinearGradient(0, minY, 0, yNol);
  grad.addColorStop(0, hexKeRgba(warnaHex, opasitasPuncak));
  grad.addColorStop(1, hexKeRgba(warnaHex, 0.0));

  const { dxs, tangen } = hitungTangenMonotone(koordinat);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(koordinat[0].x, yNol);
  ctx.lineTo(koordinat[0].x, koordinat[0].y);
  for (let i = 0; i < n - 1; i += 1) {
    const p1 = koordinat[i];
    const p2 = koordinat[i + 1];
    const dx = dxs[i];
    const cp1x = p1.x + dx / 3;
    const cp1y = p1.y + (tangen[i] * dx) / 3;
    const cp2x = p2.x - dx / 3;
    const cp2y = p2.y - (tangen[i + 1] * dx) / 3;
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
  }
  ctx.lineTo(koordinat[n - 1].x, yNol);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.restore();
}

function hexKeRgba(hex, alpha) {
  let c = hex.replace("#", "");
  if (c.length === 3) c = c.split("").map((ch) => ch + ch).join("");
  const num = parseInt(c, 16);
  const r = (num >> 16) & 255;
  const g = (num >> 8) & 255;
  const b = num & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export class GrafikTraffic {
  constructor({ canvas, kosongEl, tooltipEl, legendaEl }) {
    this.canvas = canvas;
    this.kosongEl = kosongEl;
    this.tooltipEl = tooltipEl;
    this.legendaEl = legendaEl;
    this.titik = [];
    this.sorotAktif = null;
    this.maxBPS = 2048;
    this.maxRPS = 5;
    this.targetBPS = 2048;
    this.targetRPS = 5;
    this.animasiId = null;

    this._ikatPeristiwa();
    this._renderLegenda();
  }

  _ikatPeristiwa() {
    this.canvas.addEventListener("mousemove", (event) => this._saatKursor(event));
    this.canvas.addEventListener("mouseleave", () => {
      this.sorotAktif = null;
      this._sembunyikanTooltip();
      this.gambar();
    });
    window.addEventListener("resize", () => this.gambar());

    this._observerTema = new MutationObserver(() => {
      this._renderLegenda();
      this.gambar();
    });
    this._observerTema.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"]
    });
  }

  _ambilWarna(varNama, fallback = "#2D3136") {
    return getComputedStyle(document.documentElement).getPropertyValue(varNama).trim() || fallback;
  }

  _ambilWarnaGaris() {
    const isDark = document.documentElement.dataset.theme === "dark";
    return {
      biru: isDark ? "#3b82f6" : "#2563eb",
      merah: isDark ? "#ef4444" : "#dc2626",
      kontras: isDark ? "#ffffff" : "#0f172a"
    };
  }

  _renderLegenda() {
    if (!this.legendaEl) return;
    this.legendaEl.replaceChildren();
    const w = this._ambilWarnaGaris();
    const itemLegenda = [
      { label: "Throughput (BPS)", warna: w.biru },
      { label: "Request Pengunjung (RPS)", warna: w.merah },
      { label: "Request Baseline (RPS)", warna: w.kontras }
    ];
    itemLegenda.forEach((item) => {
      const span = document.createElement("span");
      const ikon = document.createElement("i");
      ikon.style.backgroundColor = item.warna;
      span.append(ikon, document.createTextNode(item.label));
      this.legendaEl.appendChild(span);
    });
  }

  _hitungDomainTarget() {
    let mBps = 2048;
    let mRps = 5;
    this.titik.forEach((item) => {
      const bps = Number(item.bps || (item.packet_bytes || 0) + (item.app_bytes || 0));
      const rps = Number(item.rps || (item.internal || 0) + (item.visitor || 0));
      if (bps > mBps) mBps = bps;
      if (rps > mRps) mRps = rps;
    });
    this.targetBPS = Math.ceil(mBps * 1.15);
    this.targetRPS = Math.ceil(mRps * 1.15);
    if (!Number.isFinite(this.maxBPS) || this.maxBPS <= 0) this.maxBPS = this.targetBPS;
    if (!Number.isFinite(this.maxRPS) || this.maxRPS <= 0) this.maxRPS = this.targetRPS;
  }

  perbaruiData(respon) {
    const daftar = Array.isArray(respon?.points) ? respon.points : [];
    this.titik = daftar.slice(-60);
    this._renderLegenda();
    this._hitungDomainTarget();
    this._jalankanTransisi();
  }

  _jalankanTransisi() {
    if (this.animasiId) cancelAnimationFrame(this.animasiId);
    const langkah = () => {
      const dBps = this.targetBPS - this.maxBPS;
      const dRps = this.targetRPS - this.maxRPS;
      if (Math.abs(dBps) > 5 || Math.abs(dRps) > 0.1) {
        this.maxBPS += dBps * 0.12;
        this.maxRPS += dRps * 0.12;
        this.gambar();
        this.animasiId = requestAnimationFrame(langkah);
      } else {
        this.maxBPS = this.targetBPS;
        this.maxRPS = this.targetRPS;
        this.animasiId = null;
        this.gambar();
      }
    };
    langkah();
  }

  _dimensiLanes(lebar, tinggi) {
    const kiri = 64;
    const kanan = Math.max(kiri + 40, lebar - 16);
    const bawahX = tinggi - 22;
    const tinggiTersedia = bawahX - 14;
    const tinggiLane = Math.floor(tinggiTersedia / 2);
    const warna = this._ambilWarnaGaris();

    const laneBPS = {
      atas: 10,
      bawah: 10 + tinggiLane - 10,
      kiri,
      kanan,
      label: "BPS (Throughput)",
      warna: warna.biru,
      maksY: this.maxBPS
    };
    const laneRPS = {
      atas: 10 + tinggiLane + 8,
      bawah: bawahX - 6,
      kiri,
      kanan,
      label: "RPS (Requests/s)",
      warna: warna.merah,
      maksY: this.maxRPS
    };
    return { kiri, kanan, bawahX, laneBPS, laneRPS, warna };
  }

  _posisiX(indeks, kiri, kanan) {
    const jumlah = this.titik.length;
    if (jumlah <= 1) return kiri;
    return kiri + ((kanan - kiri) * indeks) / (jumlah - 1);
  }

  _posisiY(nilai, lane) {
    const rasio = Math.max(0, Math.min(1, Number(nilai || 0) / Math.max(1, lane.maksY)));
    return lane.bawah - rasio * (lane.bawah - lane.atas);
  }

  _saatKursor(event) {
    if (!this.titik.length) return;
    const rect = this.canvas.getBoundingClientRect();
    const dims = this._dimensiLanes(rect.width, rect.height);
    const xRel = event.clientX - rect.left;
    const yRel = event.clientY - rect.top;

    if (xRel < dims.kiri - 10 || xRel > dims.kanan + 10) {
      this.sorotAktif = null;
      this._sembunyikanTooltip();
      this.gambar();
      return;
    }

    const rasioX = (xRel - dims.kiri) / Math.max(1, dims.kanan - dims.kiri);
    const indeks = Math.max(0, Math.min(this.titik.length - 1, Math.round(rasioX * (this.titik.length - 1))));
    const item = this.titik[indeks];
    if (!item) {
      this.sorotAktif = null;
      this._sembunyikanTooltip();
      this.gambar();
      return;
    }

    const posX = this._posisiX(indeks, dims.kiri, dims.kanan);
    const yBps = this._posisiY(item.bps || (item.packet_bytes || 0) + (item.app_bytes || 0), dims.laneBPS);
    const yVisitor = this._posisiY(item.visitor || 0, dims.laneRPS);
    const yInternal = this._posisiY(item.internal || 0, dims.laneRPS);
    const warna = dims.warna;

    const kandidat = [
      {
        jenis: "bps",
        label: "Throughput (BPS)",
        nilai: `${formatByte(Number(item.bps || (item.packet_bytes || 0) + (item.app_bytes || 0)))}/d`,
        warna: warna.biru,
        x: posX,
        y: yBps,
        jarak: Math.abs(yRel - yBps),
        lane: dims.laneBPS
      },
      {
        jenis: "visitor",
        label: "Request Pengunjung (RPS)",
        nilai: `${formatAngka(Number(item.visitor || 0), 0)} req/d`,
        warna: warna.merah,
        x: posX,
        y: yVisitor,
        jarak: Math.abs(yRel - yVisitor),
        lane: dims.laneRPS
      },
      {
        jenis: "internal",
        label: "Request Baseline (RPS)",
        nilai: `${formatAngka(Number(item.internal || 0), 0)} req/d`,
        warna: warna.kontras,
        x: posX,
        y: yInternal,
        jarak: Math.abs(yRel - yInternal),
        lane: dims.laneRPS
      }
    ];

    kandidat.sort((a, b) => a.jarak - b.jarak);
    const terdekat = kandidat[0];
    const AMBANG_JARAK_PX = 24;

    if (terdekat && terdekat.jarak <= AMBANG_JARAK_PX) {
      this.sorotAktif = {
        indeks,
        jenis: terdekat.jenis,
        label: terdekat.label,
        nilai: terdekat.nilai,
        warna: terdekat.warna,
        x: terdekat.x,
        y: terdekat.y,
        t: item.t,
        lane: terdekat.lane
      };
      this._tampilkanTooltip(this.sorotAktif, rect, dims);
    } else {
      this.sorotAktif = null;
      this._sembunyikanTooltip();
    }
    this.gambar();
  }

  _sembunyikanTooltip() {
    if (this.tooltipEl) this.tooltipEl.hidden = true;
  }

  _tampilkanTooltip(sorot, rect, dims) {
    if (!this.tooltipEl) return;
    this.tooltipEl.replaceChildren();
    this.tooltipEl.style.borderColor = sorot.warna;
    this.tooltipEl.style.boxShadow = `0 4px 14px ${hexKeRgba(sorot.warna, 0.25)}`;

    const waktu = document.createElement("div");
    waktu.className = "waktu";
    waktu.textContent = formatWaktu(sorot.t);
    this.tooltipEl.appendChild(waktu);

    const baris = document.createElement("div");
    baris.className = "nilai-item";

    const dot = document.createElement("span");
    dot.className = "titik-warna";
    dot.style.backgroundColor = sorot.warna;

    const teks = document.createElement("span");
    teks.style.color = sorot.warna;
    teks.textContent = `${sorot.label}: `;

    const val = document.createElement("b");
    val.textContent = sorot.nilai;

    baris.append(dot, teks, val);
    this.tooltipEl.appendChild(baris);

    this.tooltipEl.hidden = false;
    const lebarTip = this.tooltipEl.offsetWidth || 180;
    const kiri = Math.min(Math.max(dims.kiri, sorot.x - lebarTip / 2), rect.width - lebarTip - 8);
    const atas = Math.max(6, sorot.y - 48);
    this.tooltipEl.style.left = `${Math.round(kiri)}px`;
    this.tooltipEl.style.top = `${Math.round(atas)}px`;
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

    const dims = this._dimensiLanes(rect.width, rect.height);
    const warnaGaris = this._ambilWarna("--line-soft", "#2D3136");
    const warnaBatas = this._ambilWarna("--line", "#373B41");
    const warnaTeks = this._ambilWarna("--text-muted", "#888888");

    const gambarLane = (lane, formatFn) => {
      ctx.strokeStyle = warnaGaris;
      ctx.lineWidth = 1;

      const yNol = Math.round(lane.bawah) + 0.5;
      const yTengah = Math.round(lane.bawah - (lane.bawah - lane.atas) * 0.5) + 0.5;
      const yAtas = Math.round(lane.atas) + 0.5;

      [yNol, yTengah, yAtas].forEach((y) => {
        ctx.beginPath();
        ctx.moveTo(dims.kiri, y);
        ctx.lineTo(dims.kanan, y);
        ctx.stroke();
      });

      ctx.font = '11px "Cascadia Mono", Consolas, monospace';
      ctx.fillStyle = warnaTeks;
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText("0", dims.kiri - 8, yNol);
      ctx.fillText(formatFn(Math.round(lane.maksY * 0.5)), dims.kiri - 8, yTengah);
      ctx.fillText(formatFn(Math.round(lane.maksY)), dims.kiri - 8, yAtas);

      ctx.fillStyle = lane.warna;
      ctx.textAlign = "left";
      ctx.font = "bold 11.5px var(--font-ui)";
      ctx.fillText(lane.label, 8, lane.atas + 10);
    };

    gambarLane(dims.laneBPS, (v) => (v >= 1024 ? `${(v / 1024).toFixed(0)}K` : `${v}`));
    gambarLane(dims.laneRPS, (v) => `${v}`);

    ctx.strokeStyle = warnaBatas;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(dims.kiri, dims.bawahX + 0.5);
    ctx.lineTo(dims.kanan, dims.bawahX + 0.5);
    ctx.stroke();

    if (!this.titik.length) return;

    ctx.fillStyle = warnaTeks;
    ctx.font = '11px "Cascadia Mono", Consolas, monospace';
    ctx.textBaseline = "top";
    const indeksWaktu = [0, Math.floor((this.titik.length - 1) / 2), this.titik.length - 1];
    indeksWaktu.forEach((idx, urutan) => {
      const item = this.titik[idx];
      if (!item) return;
      const posX = this._posisiX(idx, dims.kiri, dims.kanan);
      ctx.textAlign = urutan === 0 ? "left" : urutan === 2 ? "right" : "center";
      ctx.fillText(formatWaktu(item.t), posX, dims.bawahX + 6);
    });

    const koordinatBPS = this.titik.map((item, idx) => ({
      x: this._posisiX(idx, dims.kiri, dims.kanan),
      y: this._posisiY(item.bps || (item.packet_bytes || 0) + (item.app_bytes || 0), dims.laneBPS)
    }));
    gambarAreaFleksibel(ctx, koordinatBPS, dims.laneBPS.bawah, dims.laneBPS.warna, 0.12);

    ctx.save();
    ctx.strokeStyle = dims.laneBPS.warna;
    ctx.lineWidth = this.sorotAktif?.jenis === "bps" ? 2.5 : 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    gambarKurvaFleksibel(ctx, koordinatBPS);
    ctx.restore();

    const koordinatRpsInternal = this.titik.map((item, idx) => ({
      x: this._posisiX(idx, dims.kiri, dims.kanan),
      y: this._posisiY(item.internal || 0, dims.laneRPS)
    }));
    ctx.save();
    ctx.strokeStyle = dims.warna.kontras;
    ctx.lineWidth = this.sorotAktif?.jenis === "internal" ? 2 : 1.5;
    ctx.setLineDash([4, 4]);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    gambarKurvaFleksibel(ctx, koordinatRpsInternal);
    ctx.restore();

    const koordinatRpsVisitor = this.titik.map((item, idx) => ({
      x: this._posisiX(idx, dims.kiri, dims.kanan),
      y: this._posisiY(item.visitor || 0, dims.laneRPS)
    }));
    gambarAreaFleksibel(ctx, koordinatRpsVisitor, dims.laneRPS.bawah, dims.laneRPS.warna, 0.12);

    ctx.save();
    ctx.strokeStyle = dims.laneRPS.warna;
    ctx.lineWidth = this.sorotAktif?.jenis === "visitor" ? 2.5 : 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    gambarKurvaFleksibel(ctx, koordinatRpsVisitor);
    ctx.restore();

    if (this.sorotAktif) {
      const s = this.sorotAktif;
      ctx.save();
      ctx.strokeStyle = hexKeRgba(s.warna, 0.45);
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.moveTo(s.x + 0.5, s.lane.atas);
      ctx.lineTo(s.x + 0.5, s.lane.bawah);
      ctx.stroke();
      ctx.restore();

      ctx.save();
      ctx.beginPath();
      ctx.arc(s.x, s.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = hexKeRgba(s.warna, 0.25);
      ctx.fill();

      ctx.beginPath();
      ctx.arc(s.x, s.y, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = s.warna;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(s.x, s.y, 1.5, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
      ctx.restore();
    }
  }
}
