import { dariAplikasi, dariPacket, formatAngka, formatByte, formatWaktu } from "./format.js";

const BATAS_BARIS = 500;
const PROTOKOL_KENAL = new Set(["TCP", "UDP", "ICMP", "ARP", "HTTP"]);

export class TabelTraffic {
  constructor({
    tbody,
    kosongEl,
    jumlahEl,
    inputCari,
    selectProtocol,
    selectSumber,
    detailBox,
    detailIsi,
    tombolTutup
  }) {
    this.tbody = tbody;
    this.kosongEl = kosongEl;
    this.jumlahEl = jumlahEl;
    this.inputCari = inputCari;
    this.selectProtocol = selectProtocol;
    this.selectSumber = selectSumber;
    this.detailBox = detailBox;
    this.detailIsi = detailIsi;
    this.tombolTutup = tombolTutup;
    this.baris = [];
    this.kunciSet = new Set();
    this.kunciDipilih = null;
    this._renderPending = false;

    this._ikatPeristiwa();
  }

  _ikatPeristiwa() {
    this.inputCari?.addEventListener("input", () => this.render());
    this.selectProtocol?.addEventListener("change", () => this.render());
    this.selectSumber?.addEventListener("change", () => this.render());
    this.tombolTutup?.addEventListener("click", () => {
      this.kunciDipilih = null;
      if (this.detailBox) this.detailBox.hidden = true;
      this.render();
    });
  }

  setSnapshot(packets = [], appEvents = []) {
    const gabungan = [
      ...packets.map(dariPacket),
      ...appEvents.map(dariAplikasi)
    ];
    gabungan.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
    const unik = [];
    const dilihat = new Set();
    for (const item of gabungan) {
      if (dilihat.has(item.kunci)) continue;
      dilihat.add(item.kunci);
      unik.push(item);
      if (unik.length >= BATAS_BARIS) break;
    }
    this.baris = unik;
    this.kunciSet = dilihat;
    this._jadwalkanRender();
  }

  tambahPacket(data) {
    if (!data) return;
    this._sisipkanDepan(dariPacket(data));
  }

  tambahAplikasi(data) {
    if (!data) return;
    this._sisipkanDepan(dariAplikasi(data));
  }

  _jadwalkanRender() {
    if (this._renderPending) return;
    this._renderPending = true;
    requestAnimationFrame(() => {
      this._renderPending = false;
      this.render();
    });
  }

  _sisipkanDepan(item) {
    if (this.kunciSet.has(item.kunci)) return;
    this.kunciSet.add(item.kunci);
    this.baris.unshift(item);
    if (this.baris.length > BATAS_BARIS) {
      const dihapus = this.baris.pop();
      if (dihapus) this.kunciSet.delete(dihapus.kunci);
    }
    this._jadwalkanRender();
  }

  _saring() {
    const cari = (this.inputCari?.value || "").trim().toLowerCase();
    const protokol = this.selectProtocol?.value || "all";
    const sumber = this.selectSumber?.value || "all";

    return this.baris.filter((item) => {
      if (sumber === "packet" && item.jenis !== "packet") return false;
      if (sumber === "aplikasi" && item.jenis !== "aplikasi") return false;
      if (sumber === "pengunjung" && item.asal !== "pengunjung") return false;
      if (sumber === "internal" && item.asal !== "internal") return false;

      if (protokol !== "all") {
        if (protokol === "OTHER") {
          if (PROTOKOL_KENAL.has(item.protocol)) return false;
        } else if (item.protocol !== protokol) {
          return false;
        }
      }

      if (cari) {
        const gabungan = `${item.sourceIp} ${item.destinationIp} ${item.sourcePort} ${item.destinationPort} ${item.path} ${item.ticket || ""}`.toLowerCase();
        if (!gabungan.includes(cari)) return false;
      }
      return true;
    });
  }

  render() {
    if (!this.tbody || this.tbody.offsetParent === null) return;
    const hasil = this._saring();
    if (this.jumlahEl) {
      this.jumlahEl.textContent = hasil.length === this.baris.length
        ? `${formatAngka(hasil.length)} baris`
        : `${formatAngka(hasil.length)} / ${formatAngka(this.baris.length)} baris`;
    }

    this.tbody.replaceChildren();
    if (!hasil.length) {
      if (this.kosongEl) {
        this.kosongEl.textContent = this.baris.length
          ? "Tidak ada baris traffic yang sesuai dengan filter."
          : "Menunggu packet capture dan application event.";
        this.kosongEl.hidden = false;
      }
      return;
    }
    if (this.kosongEl) this.kosongEl.hidden = true;

    const frag = document.createDocumentFragment();
    hasil.slice(0, 250).forEach((item) => {
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      if (item.asal === "internal") tr.classList.add("internal");
      if (item.kunci === this.kunciDipilih) tr.classList.add("dipilih");

      const kolom = [
        { teks: formatWaktu(item.timestamp, true), kelas: "kol-waktu" },
        { teks: item.sourceIp, kelas: "kol-ip" },
        { teks: item.destinationIp, kelas: "kol-ip" },
        { teks: String(item.sourcePort), kelas: "kol-port" },
        { teks: String(item.destinationPort), kelas: "kol-port" },
        { teks: item.protocol, kelas: "kol-protocol" },
        { teks: `${formatAngka(item.length)} B`, kelas: "kol-angka" },
        { teks: item.method, kelas: "kol-method" },
        { teks: item.path, kelas: "kol-path", title: item.path },
        { teks: String(item.statusCode), kelas: "kol-status", status: item.statusCode },
        { teks: item.sourceType, kelas: "kol-sumber" }
      ];

      kolom.forEach((kol) => {
        const td = document.createElement("td");
        td.className = kol.kelas;
        td.textContent = kol.teks;
        if (kol.title && kol.title !== "—") td.title = kol.title;
        if (kol.kelas === "kol-status" && typeof kol.status === "number") {
          if (kol.status >= 500) td.dataset.tingkat = "galat";
          else if (kol.status >= 400) td.dataset.tingkat = "peringatan";
        }
        tr.appendChild(td);
      });

      const pilih = () => {
        this.kunciDipilih = item.kunci;
        this._tampilkanDetail(item);
        this.tbody.querySelectorAll("tr.dipilih").forEach((el) => el.classList.remove("dipilih"));
        tr.classList.add("dipilih");
      };
      tr.addEventListener("click", pilih);
      tr.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          pilih();
        }
      });
      frag.appendChild(tr);
    });
    this.tbody.appendChild(frag);
  }

  _tampilkanDetail(item) {
    if (!this.detailBox || !this.detailIsi) return;
    this.detailIsi.replaceChildren();
    const entri = [
      ["Timestamp", formatWaktu(item.timestamp, true)],
      ["Source Type", item.sourceType],
      ["Source", `${item.sourceIp}:${item.sourcePort}`],
      ["Destination", `${item.destinationIp}:${item.destinationPort}`],
      ["Protocol", item.protocol],
      ["Length", `${formatAngka(item.length)} B (${formatByte(item.length)})`]
    ];
    if (item.jenis === "aplikasi") {
      entri.push(
        ["HTTP Method", item.method],
        ["HTTP Path", item.path],
        ["Status Code", String(item.statusCode)],
        ["Response Size", item.responseBytes !== null ? `${formatAngka(item.responseBytes)} B` : "—"],
        ["Durasi", item.durationMs !== null ? `${formatAngka(item.durationMs, 2)} ms` : "—"],
        ["Ticket Pengunjung", item.ticket || "Tidak terkait sesi pengunjung"]
      );
    } else {
      entri.push(
        ["TCP Flags", item.tcpFlags || "—"],
        ["Korelasi Sesi", item.correlationMethod || "Tidak berkorelasi"],
        ["Ticket Pengunjung", item.ticket || "—"]
      );
    }

    entri.forEach(([label, nilai]) => {
      const div = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = nilai;
      div.append(dt, dd);
      this.detailIsi.appendChild(div);
    });
    this.detailBox.hidden = false;
  }
}
