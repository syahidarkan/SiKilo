import type { KategoriRapor } from "../tipe";
import { formatAngka, formatPersen } from "../format";
import type { Parameter } from "./parameter";

export type HasilKategori = { kategori: KategoriRapor; alasan: string };

/**
 * Aturan tertulis, diperiksa berurutan dan dicetak apa adanya di rapor:
 * 1. Pemborosan > ambang persen total pemakaian  -> efisiensi dulu
 * 2. Tarif/harga belum diisi (balik modal null)  -> belum bisa dihitung
 * 3. Balik modal skenario rekomendasi < ambang   -> layak
 * 4. Selain itu                                   -> belum layak
 */
export function tentukanKategori(m: {
  totalKWh: number;
  borosKWh: number;
  balikModalTahun: number | null;
  adaRekomendasi: boolean;
  p: Parameter;
}): HasilKategori {
  const rasioBoros = m.totalKWh > 0 ? m.borosKWh / m.totalKWh : 0;
  if (rasioBoros > m.p.ambangPemborosanRasio) {
    return {
      kategori: "efisiensi_dulu",
      alasan: `${formatPersen(rasioBoros)} listrik terbuang tanpa hasil, di atas batas ${formatPersen(m.p.ambangPemborosanRasio)}. Benahi dulu sebelum memasang panel.`,
    };
  }
  if (!m.adaRekomendasi) {
    return {
      kategori: "belum_layak",
      alasan: "Pemakaian siang hari terlalu kecil, sebagian besar listrik panel akan terbuang.",
    };
  }
  if (m.balikModalTahun === null) {
    return {
      kategori: "belum_bisa_dihitung",
      alasan: "Tarif PLN atau harga pasang panel belum diisi, jadi balik modal belum bisa dihitung.",
    };
  }
  if (m.balikModalTahun < m.p.ambangBalikModalTahun) {
    return {
      kategori: "layak",
      alasan: `Balik modal sekitar ${formatAngka(m.balikModalTahun, 1)} tahun, di bawah batas ${formatAngka(m.p.ambangBalikModalTahun, 0)} tahun.`,
    };
  }
  return {
    kategori: "belum_layak",
    alasan: `Balik modal sekitar ${formatAngka(m.balikModalTahun, 1)} tahun, melebihi batas ${formatAngka(m.p.ambangBalikModalTahun, 0)} tahun.`,
  };
}

export function teksAturanKategori(p: Parameter): string[] {
  return [
    `"Efisiensi dulu" bila listrik terbuang lebih dari ${formatPersen(p.ambangPemborosanRasio)} total pemakaian.`,
    `"Layak PLTS" bila balik modal ukuran yang disarankan kurang dari ${formatAngka(p.ambangBalikModalTahun, 0)} tahun.`,
    `Ukuran yang disarankan: panel terbesar yang listrik terbuangnya tidak lebih dari ${formatPersen(p.ambangTerbuangRasio)} produksinya.`,
    `Selain itu "belum layak". Bila tarif atau harga belum diisi: "belum bisa dihitung".`,
  ];
}

export const LABEL_STEMPEL: Record<KategoriRapor, string> = {
  layak: "LAYAK PLTS",
  efisiensi_dulu: "EFISIENSI DULU",
  belum_layak: "BELUM LAYAK",
  belum_bisa_dihitung: "BELUM BISA DIHITUNG",
};
