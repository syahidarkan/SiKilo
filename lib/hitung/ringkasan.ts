import type { Lokasi, Mesin, PemakaianJam, Tanggal, TotalJam } from "../tipe";
import { hariDalamMinggu, pecahWaktu, rentangTanggal, selisihHari, tambahHari } from "../waktu";
import type { Parameter } from "./parameter";
import { kWhKeRupiah } from "./rupiah";

export type HariTerukur = { tanggal: Tanggal; perJam: (number | null)[]; jamTerisi: number };

/** Kelompokkan total per jam menjadi hari; jam tanpa data bernilai null. */
export function kelompokkanPerHari(total: TotalJam[], dari: Tanggal, sampai: Tanggal): HariTerukur[] {
  const peta = new Map<Tanggal, (number | null)[]>();
  for (const t of rentangTanggal(dari, sampai)) peta.set(t, new Array(24).fill(null));
  for (const r of total) {
    const { tanggal, jam } = pecahWaktu(r.jam);
    const hari = peta.get(tanggal);
    if (hari) hari[jam] = (hari[jam] ?? 0) + r.kWh;
  }
  return [...peta.entries()].map(([tanggal, perJam]) => ({
    tanggal,
    perJam,
    jamTerisi: perJam.filter((v) => v !== null).length,
  }));
}

/** Hari dengan 24 jam data dipakai untuk profil PLTS; sisanya dihitung "bolong". */
export function kelengkapanData(hari: HariTerukur[]) {
  const lengkap = hari.filter((h) => h.jamTerisi === 24);
  const bolong = hari.filter((h) => h.jamTerisi < 24);
  return {
    hariLengkap: lengkap.length,
    hariBolong: bolong.length,
    tanggalBolong: bolong.map((h) => h.tanggal),
    profilHarian: lengkap.map((h) => h.perJam as number[]),
  };
}

export function jumlahKWh(total: { kWh: number }[]): number {
  return total.reduce((a, r) => a + r.kWh, 0);
}

/** Total energi dan biaya di rentang [dari, sampai] inklusif. */
export function biayaPeriode(total: TotalJam[], dari: Tanggal, sampai: Tanggal, p: Parameter) {
  const kWh = jumlahKWh(
    total.filter((r) => {
      const t = pecahWaktu(r.jam).tanggal;
      return t >= dari && t <= sampai;
    }),
  );
  return { kWh, rupiah: kWhKeRupiah(kWh, p.tarifPerKWh) };
}

export type BarisMesin = {
  mesinId: string | "lainnya";
  nama: string;
  jumlah: number;
  dikelompokkan: boolean;
  kWh: number;
  porsi: number;
  rupiah: number | null;
  keyakinan: number;
  keyakinanRendah: boolean;
};

/** Rincian per mesin, urut dari terbesar, dengan "lainnya" selalu di baris terakhir. */
export function rincianPerMesin(pemakaian: PemakaianJam[], mesin: Mesin[], p: Parameter): BarisMesin[] {
  const akum = new Map<string, { kWh: number; bobotKeyakinan: number }>();
  for (const r of pemakaian) {
    const a = akum.get(r.mesinId) ?? { kWh: 0, bobotKeyakinan: 0 };
    a.kWh += r.kWh;
    a.bobotKeyakinan += r.kWh * r.keyakinan;
    akum.set(r.mesinId, a);
  }
  const total = [...akum.values()].reduce((s, a) => s + a.kWh, 0);
  const baris = (id: string, nama: string, jumlah: number, kelompok: boolean): BarisMesin => {
    const a = akum.get(id) ?? { kWh: 0, bobotKeyakinan: 0 };
    const keyakinan = a.kWh > 0 ? a.bobotKeyakinan / a.kWh : 0;
    return {
      mesinId: id,
      nama,
      jumlah,
      dikelompokkan: kelompok,
      kWh: a.kWh,
      porsi: total > 0 ? a.kWh / total : 0,
      rupiah: kWhKeRupiah(a.kWh, p.tarifPerKWh),
      keyakinan,
      keyakinanRendah: id !== "lainnya" && keyakinan < p.ambangKeyakinan,
    };
  };
  const daftar = mesin.map((m) => baris(m.id, m.nama, m.jumlah, m.dikelompokkan)).sort((a, b) => b.kWh - a.kWh);
  return [...daftar, baris("lainnya", "Lainnya (belum dikenali)", 1, false)];
}

export type SelHeatmap = { kWh: number | null };

/**
 * Heatmap 7 x 24: baris Senin..Minggu, kolom jam 0..23, nilai rata-rata kWh
 * dari semua tanggal dengan hari yang sama. null bila tidak ada data.
 */
export function heatmapMingguan(total: TotalJam[]): { baris: SelHeatmap[][]; maks: number } {
  const jumlah = Array.from({ length: 7 }, () => new Array(24).fill(0));
  const tanggalPerSel = Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => new Set<string>()));
  for (const r of total) {
    const { tanggal, jam } = pecahWaktu(r.jam);
    const idx = (hariDalamMinggu(tanggal) + 6) % 7; // Senin = 0
    jumlah[idx][jam] += r.kWh;
    tanggalPerSel[idx][jam].add(tanggal);
  }
  let maks = 0;
  const baris = jumlah.map((row, i) =>
    row.map((v, j) => {
      const n = tanggalPerSel[i][j].size;
      if (n === 0) return { kWh: null };
      const rata = v / n;
      maks = Math.max(maks, rata);
      return { kWh: rata };
    }),
  );
  return { baris, maks };
}

/** "Hari ke-9 dari 21". Nilai dibatasi agar tidak melewati rentang masa ukur. */
export function posisiMasaUkur(lokasi: Lokasi, hariIni: Tanggal): { hariKe: number; dari: number } | null {
  if (!lokasi.masaUkur) return null;
  const dari = selisihHari(lokasi.masaUkur.mulai, lokasi.masaUkur.selesaiRencana) + 1;
  const hariKe = Math.min(dari, Math.max(0, selisihHari(lokasi.masaUkur.mulai, hariIni) + 1));
  return { hariKe, dari };
}

/** Minggu ke-n masa ukur (1-based) beserta rentang tanggalnya. */
export function rentangMinggu(mulaiMasaUkur: Tanggal, mingguKe: number): { dari: Tanggal; sampai: Tanggal } {
  const dari = tambahHari(mulaiMasaUkur, (mingguKe - 1) * 7);
  return { dari, sampai: tambahHari(dari, 6) };
}
