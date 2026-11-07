import type { SkenarioPLTS } from "../tipe";
import type { Parameter } from "./parameter";
import { balikModalTahun, biayaPasang, kWhKeRupiah } from "./rupiah";

export const LABEL_KURVA_SURYA = "perkiraan kasar, akan diganti pvlib dan data NASA POWER";
export const JAM_SURYA = { mulai: 6, selesai: 18 } as const;

/**
 * Produksi per jam untuk 1 kWp dalam sehari (24 nilai, kWh).
 * Bentuk setengah sinus 06.00-18.00, diskalakan agar totalnya = yieldHarian.
 */
export function kurvaProduksiPerKWp(yieldHarian: number): number[] {
  const bobot = Array.from({ length: 24 }, (_, jam) => {
    if (jam < JAM_SURYA.mulai || jam >= JAM_SURYA.selesai) return 0;
    const t = (jam + 0.5 - JAM_SURYA.mulai) / (JAM_SURYA.selesai - JAM_SURYA.mulai);
    return Math.sin(Math.PI * t);
  });
  const total = bobot.reduce((a, b) => a + b, 0);
  return bobot.map((b) => (b / total) * yieldHarian);
}

/**
 * E_terpakai = Σ min(B_t, P_t), E_terbuang = Σ max(0, P_t - B_t).
 * Ekspor ke PLN tidak mengurangi tagihan (Permen ESDM 2/2024), jadi kelebihan dihitung terbuang.
 */
export function hitungEnergi(beban: number[], produksi: number[]): { terpakai: number; terbuang: number } {
  if (beban.length !== produksi.length) {
    throw new Error(`Panjang beban (${beban.length}) dan produksi (${produksi.length}) berbeda`);
  }
  let terpakai = 0;
  let terbuang = 0;
  for (let t = 0; t < beban.length; t++) {
    const b = Math.max(0, beban[t]);
    const p = Math.max(0, produksi[t]);
    terpakai += Math.min(b, p);
    terbuang += Math.max(0, p - b);
  }
  return { terpakai, terbuang };
}

function cekProfil(profilHarian: number[][]) {
  if (profilHarian.length === 0) throw new Error("Profil harian kosong: belum ada hari dengan data lengkap");
  for (const hari of profilHarian) {
    if (hari.length !== 24) throw new Error("Setiap profil harian harus berisi 24 nilai per jam");
  }
}

/**
 * Satu skenario ukuran panel. Profil beberapa minggu diperpanjang ke setahun
 * dengan faktor 365 / jumlah hari terukur (keterbatasan ini dicetak di rapor).
 */
export function hitungSkenario(profilHarian: number[][], kWp: number, p: Parameter): SkenarioPLTS {
  cekProfil(profilHarian);
  const produksi = kurvaProduksiPerKWp(p.yieldHarianPerKWp).map((v) => v * kWp);
  let terpakai = 0;
  let terbuang = 0;
  for (const hari of profilHarian) {
    const e = hitungEnergi(hari, produksi);
    terpakai += e.terpakai;
    terbuang += e.terbuang;
  }
  const faktorTahun = 365 / profilHarian.length;
  const terpakaiTahun = terpakai * faktorTahun;
  const hemat = kWhKeRupiah(terpakaiTahun, p.tarifPerKWh);
  const biaya = biayaPasang(kWp, p.hargaPerKWp);
  return {
    kWp,
    terpakaiSendiri_kWh_tahun: terpakaiTahun,
    terbuang_kWh_tahun: terbuang * faktorTahun,
    hematRupiahTahun: hemat,
    biayaRupiah: biaya,
    balikModalTahun: balikModalTahun(biaya, hemat),
  };
}

/**
 * Batas atas skenario. Asumsi sementara: tidak melebihi daya tersambung (kVA),
 * menunggu jawaban tim soal batas kapasitas menurut Permen ESDM 2/2024.
 */
export function batasKWp(dayaTersambungVA: number): number {
  return dayaTersambungVA / 1000;
}

export function daftarSkenario(profilHarian: number[][], kWpMaks: number, p: Parameter): SkenarioPLTS[] {
  const hasil: SkenarioPLTS[] = [];
  for (let k = p.langkahKWp; k <= kWpMaks + 1e-9; k += p.langkahKWp) {
    hasil.push(hitungSkenario(profilHarian, Math.round(k * 100) / 100, p));
  }
  return hasil;
}

export function rasioTerbuang(s: SkenarioPLTS): number {
  const produksi = s.terpakaiSendiri_kWh_tahun + s.terbuang_kWh_tahun;
  return produksi === 0 ? 0 : s.terbuang_kWh_tahun / produksi;
}

/**
 * Aturan rekomendasi (dicetak di rapor): kWp terbesar yang produksi terbuangnya
 * tidak lebih dari ambangTerbuangRasio. Berbasis energi, jadi tetap bisa dihitung
 * walau tarif dan harga belum diisi.
 */
export function pilihRekomendasi(skenario: SkenarioPLTS[], ambangTerbuangRasio: number): SkenarioPLTS | null {
  let terpilih: SkenarioPLTS | null = null;
  for (const s of skenario) {
    if (s.terpakaiSendiri_kWh_tahun > 0 && rasioTerbuang(s) <= ambangTerbuangRasio) {
      if (!terpilih || s.kWp > terpilih.kWp) terpilih = s;
    }
  }
  return terpilih;
}

/** Rata-rata beban per jam (24 nilai) dari sekumpulan hari. */
export function rataPerJam(profilHarian: number[][]): number[] {
  const hasil = new Array(24).fill(0);
  if (profilHarian.length === 0) return hasil;
  for (const hari of profilHarian) for (let j = 0; j < 24; j++) hasil[j] += hari[j];
  return hasil.map((v) => v / profilHarian.length);
}
