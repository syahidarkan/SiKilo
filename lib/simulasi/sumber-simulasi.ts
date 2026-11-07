import { buatParameter, type Parameter } from "../hitung/parameter";
import { susunRapor } from "../hitung/rapor";
import { deteksiPemborosan } from "../hitung/pemborosan";
import { kelengkapanData, kelompokkanPerHari } from "../hitung/ringkasan";
import type { HasilAksi, MasukanCabut, MasukanPasang, SumberData } from "../sumber-data";
import {
  gabung,
  rapikanIdAlat,
  validasiAlat,
  validasiCabut,
  validasiChecklist,
  validasiKoneksi,
  validasiLokasiPasang,
  validasiMesin,
  validasiPlug,
} from "../teknisi/validasi";
import type { Alat, Lokasi, Mesin, PemakaianJam, Pemborosan, Rapor, StatusAlat, TotalJam } from "../tipe";
import { pecahWaktu, tambahHari } from "../waktu";
import { bangkitkanDataLokasi, batasData, type DataLokasi } from "./generator";
import type { Skenario } from "./skenario";

/** SIMULASI: lama masa ukur standar, di tengah rentang 2-4 minggu pada brief. */
export const MASA_UKUR_HARI = 21;

export type OpsiSimulasi = {
  parameter?: Partial<Parameter>;
  /** Jeda buatan agar keadaan "memuat" bisa dilihat dan ditangkap layar. */
  jedaMs?: number;
};

/** Bagian state yang berubah selama sesi, bisa disimpan ke sessionStorage oleh layar. */
export type SnapshotSesi = {
  lokasi: Lokasi[];
  alat: Alat[];
  mesin: Mesin[];
  dipasangSesiIni: string[];
};

export class SumberSimulasi implements SumberData {
  private lokasi: Lokasi[];
  private alat: Alat[];
  private mesin: Mesin[];
  private dipasangSesiIni = new Set<string>();
  private cache = new Map<string, DataLokasi>();
  private parameter: Parameter;
  private jedaMs: number;
  private gagal = false;

  constructor(
    private readonly skenario: Skenario,
    opsi: OpsiSimulasi = {},
  ) {
    this.lokasi = structuredClone(skenario.lokasi);
    this.alat = structuredClone(skenario.alat);
    this.mesin = structuredClone(skenario.mesin);
    this.parameter = buatParameter(opsi.parameter);
    this.jedaMs = opsi.jedaMs ?? 0;
  }

  // ---- Kontrol khusus prototype (tidak ada di SumberData) ----

  /** Semua panggilan berikutnya gagal sampai dimatikan lagi, untuk keadaan error. */
  aturGagal(gagal: boolean) {
    this.gagal = gagal;
  }

  aturJeda(ms: number) {
    this.jedaMs = ms;
  }

  aturStatusAlat(alatId: string, status: Exclude<StatusAlat, "di_gudang">, terakhirTerlihat?: string) {
    const a = this.alat.find((x) => x.id === alatId);
    if (!a || a.lokasiId === null) throw new Error(`Alat ${alatId} tidak sedang terpasang`);
    a.status = status;
    if (terakhirTerlihat) a.terakhirTerlihat = terakhirTerlihat;
  }

  snapshot(): SnapshotSesi {
    return structuredClone({
      lokasi: this.lokasi,
      alat: this.alat,
      mesin: this.mesin,
      dipasangSesiIni: [...this.dipasangSesiIni],
    });
  }

  pulihkan(s: SnapshotSesi) {
    this.lokasi = structuredClone(s.lokasi);
    this.alat = structuredClone(s.alat);
    this.mesin = structuredClone(s.mesin);
    this.dipasangSesiIni = new Set(s.dipasangSesiIni);
    this.cache.clear();
  }

  // ---- SumberData ----

  private async jalankan<T>(fn: () => T): Promise<T> {
    if (this.jedaMs > 0) await new Promise((r) => setTimeout(r, this.jedaMs));
    if (this.gagal) throw new Error("Data gagal dimuat (simulasi gangguan jaringan).");
    // Salinan agar layar tidak bisa mengubah state sumber secara tidak sengaja
    return structuredClone(fn());
  }

  private tanggalHariIni() {
    return pecahWaktu(this.skenario.waktuAcuan).tanggal;
  }

  private dataLokasi(lokasiId: string): DataLokasi {
    const l = this.lokasi.find((x) => x.id === lokasiId);
    // Lokasi yang dipasang lewat prototype belum punya riwayat; jangan mengarang data sebelum alat terpasang
    if (!l || this.dipasangSesiIni.has(lokasiId)) return { total: [], pemakaian: [] };
    const kunci = `${l.id}|${l.status}|${l.masaUkur?.mulai}|${l.masaUkur?.selesaiRencana}`;
    let data = this.cache.get(kunci);
    if (!data) {
      data = bangkitkanDataLokasi(this.skenario, l);
      this.cache.set(kunci, data);
    }
    // Alat offline: data berhenti di jam terakhir alat terlihat
    const alat = this.alat.find((a) => a.lokasiId === lokasiId);
    if (alat?.status === "offline") {
      const batas = Date.parse(alat.terakhirTerlihat);
      return {
        total: data.total.filter((r) => Date.parse(r.jam) + 3600_000 <= batas),
        pemakaian: data.pemakaian.filter((r) => Date.parse(r.jam) + 3600_000 <= batas),
      };
    }
    return data;
  }

  private periode(l: Lokasi) {
    const batas = batasData(l, this.skenario.waktuAcuan);
    if (!l.masaUkur || !batas) return null;
    return { dari: l.masaUkur.mulai, sampai: batas.sampai };
  }

  private hitungPemborosan(l: Lokasi): Pemborosan[] {
    if (l.status === "kalibrasi" || l.status === "menunggu_pasang") return [];
    const mesin = this.mesin.filter((m) => m.lokasiId === l.id);
    return deteksiPemborosan(l, mesin, this.dataLokasi(l.id).pemakaian, this.parameter);
  }

  private hitungRapor(l: Lokasi): Rapor | null {
    if (!["rapor_siap", "plts_terpasang", "verifikasi"].includes(l.status)) return null;
    const periode = this.periode(l);
    if (!periode) return null;
    const data = this.dataLokasi(l.id);
    if (data.total.length === 0) return null;
    return susunRapor({
      lokasi: l,
      mesin: this.mesin.filter((m) => m.lokasiId === l.id),
      total: data.total,
      pemakaian: data.pemakaian,
      periode,
      tanggal: this.skenario.tanggalRapor[l.id] ?? this.tanggalHariIni(),
      p: this.parameter,
    });
  }

  waktuSekarang() {
    return this.jalankan(() => this.skenario.waktuAcuan);
  }

  ambilParameter() {
    return this.jalankan(() => this.parameter);
  }

  daftarLokasi() {
    return this.jalankan(() => this.lokasi);
  }

  ambilLokasi(lokasiId: string) {
    return this.jalankan(() => this.lokasi.find((l) => l.id === lokasiId) ?? null);
  }

  daftarAlat() {
    return this.jalankan(() => this.alat);
  }

  daftarMesin(lokasiId: string) {
    return this.jalankan(() => this.mesin.filter((m) => m.lokasiId === lokasiId));
  }

  ambilMesin(mesinId: string) {
    return this.jalankan(() => this.mesin.find((m) => m.id === mesinId) ?? null);
  }

  ambilTotalPerJam(lokasiId: string): Promise<TotalJam[]> {
    return this.jalankan(() => this.dataLokasi(lokasiId).total);
  }

  ambilPemakaianPerMesin(lokasiId: string): Promise<PemakaianJam[]> {
    return this.jalankan(() => {
      const l = this.lokasi.find((x) => x.id === lokasiId);
      if (!l || l.status === "kalibrasi") return [];
      return this.dataLokasi(lokasiId).pemakaian;
    });
  }

  ambilPemborosan(lokasiId: string) {
    return this.jalankan(() => {
      const l = this.lokasi.find((x) => x.id === lokasiId);
      return l ? this.hitungPemborosan(l) : [];
    });
  }

  ambilRapor(lokasiId: string) {
    return this.jalankan(() => {
      const l = this.lokasi.find((x) => x.id === lokasiId);
      return l ? this.hitungRapor(l) : null;
    });
  }

  daftarRapor() {
    return this.jalankan(() => this.lokasi.map((l) => this.hitungRapor(l)).filter((r): r is Rapor => r !== null));
  }

  pasangAlat(m: MasukanPasang): Promise<HasilAksi> {
    return this.jalankan(() => {
      const alatId = rapikanIdAlat(m.alatId);
      const cek = gabung(
        validasiAlat(alatId, this.alat, this.lokasi),
        validasiLokasiPasang(m.lokasiId, this.lokasi),
        validasiChecklist(m.checklist),
        validasiKoneksi(m.koneksi),
        validasiMesin(m.mesin),
        validasiPlug(m.plug, m.mesin.length),
      );
      if (!cek.ok) return cek;

      const hariIni = this.tanggalHariIni();
      const alat = this.alat.find((a) => a.id === alatId)!;
      const lokasi = this.lokasi.find((l) => l.id === m.lokasiId)!;
      alat.lokasiId = lokasi.id;
      alat.status = "online";
      alat.terakhirTerlihat = this.skenario.waktuAcuan;
      lokasi.status = "kalibrasi";
      lokasi.masaUkur = { mulai: hariIni, selesaiRencana: tambahHari(hariIni, MASA_UKUR_HARI - 1) };
      this.mesin = this.mesin.filter((x) => x.lokasiId !== lokasi.id);
      m.mesin.forEach((x, i) =>
        this.mesin.push({
          id: `${lokasi.id}-m${i + 1}`,
          lokasiId: lokasi.id,
          nama: x.nama.trim(),
          jenis: x.jenis,
          jumlah: x.jumlah,
          dikelompokkan: x.dikelompokkan,
        }),
      );
      this.dipasangSesiIni.add(lokasi.id);
      return { ok: true } as const;
    });
  }

  cabutAlat(m: MasukanCabut): Promise<HasilAksi> {
    return this.jalankan((): HasilAksi => {
      const cek = validasiCabut(m);
      if (!cek.ok) return cek;
      const lokasi = this.lokasi.find((l) => l.id === m.lokasiId);
      if (!lokasi || !["kalibrasi", "mengukur"].includes(lokasi.status) || !lokasi.masaUkur) {
        return { ok: false, galat: [{ kolom: "lokasiId", pesan: "Lokasi ini tidak sedang diukur." }] };
      }
      const alat = this.alat.find((a) => a.lokasiId === lokasi.id);
      if (!alat) return { ok: false, galat: [{ kolom: "lokasiId", pesan: "Tidak ada alat tercatat di lokasi ini." }] };

      const periode = this.periode(lokasi)!;
      const { hariLengkap } = kelengkapanData(
        kelompokkanPerHari(this.dataLokasi(lokasi.id).total, periode.dari, periode.sampai),
      );
      if (hariLengkap === 0) {
        return {
          ok: false,
          galat: [{ kolom: "masaCukup", pesan: "Belum ada satu hari pun data lengkap, rapor tidak bisa dibuat." }],
        };
      }

      alat.status = "di_gudang";
      alat.lokasiId = null;
      alat.terakhirTerlihat = this.skenario.waktuAcuan;
      lokasi.status = "rapor_siap";
      lokasi.masaUkur = { mulai: lokasi.masaUkur.mulai, selesaiRencana: this.tanggalHariIni() };
      return { ok: true };
    });
  }
}
