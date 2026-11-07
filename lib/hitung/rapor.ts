import type { Lokasi, Mesin, PemakaianJam, Rapor, Tanggal, TotalJam } from "../tipe";
import { formatAngka, formatPersen } from "../format";
import { tentukanKategori } from "./kategori";
import type { Parameter } from "./parameter";
import { batasKWp, daftarSkenario, pilihRekomendasi } from "./plts";
import { deteksiPemborosan } from "./pemborosan";
import { jumlahKWh, kelengkapanData, kelompokkanPerHari } from "./ringkasan";

export type MasukanRapor = {
  lokasi: Lokasi;
  mesin: Mesin[];
  total: TotalJam[];
  pemakaian: PemakaianJam[];
  periode: { dari: Tanggal; sampai: Tanggal };
  tanggal: Tanggal;
  p: Parameter;
};

export function nomorRapor(lokasiId: string, tanggal: Tanggal): string {
  return `NL/RPR/${tanggal.slice(0, 7).replace("-", "")}/${lokasiId.toUpperCase()}`;
}

/** Susun rapor dari data mentah. Setiap angka berasal dari fungsi murni di lib/hitung. */
export function susunRapor(m: MasukanRapor): Rapor {
  const hari = kelompokkanPerHari(m.total, m.periode.dari, m.periode.sampai);
  const data = kelengkapanData(hari);
  if (data.hariLengkap === 0) throw new Error("Belum ada hari dengan data lengkap untuk menyusun rapor");

  const skenario = daftarSkenario(data.profilHarian, batasKWp(m.lokasi.dayaTersambungVA), m.p);
  const rekomendasi = pilihRekomendasi(skenario, m.p.ambangTerbuangRasio);
  const pemborosan = deteksiPemborosan(m.lokasi, m.mesin, m.pemakaian, m.p);

  const totalKWh = jumlahKWh(m.total);
  const hariTerukur = hari.length;
  const borosKWh = pemborosan.reduce((a, b) => a + b.kWhPerMinggu, 0) * (hariTerukur / 7);
  const { kategori, alasan } = tentukanKategori({
    totalKWh,
    borosKWh,
    balikModalTahun: rekomendasi?.balikModalTahun ?? null,
    adaRekomendasi: rekomendasi !== null,
    p: m.p,
  });

  const kWhMesin = m.pemakaian.filter((r) => r.mesinId !== "lainnya");
  const kenal = jumlahKWh(kWhMesin);
  const totalTerpisah = jumlahKWh(m.pemakaian);
  const rasioKenal = totalTerpisah > 0 ? kenal / totalTerpisah : 0;

  return {
    lokasiId: m.lokasi.id,
    nomor: nomorRapor(m.lokasi.id, m.tanggal),
    tanggal: m.tanggal,
    kategori,
    alasanKategori: alasan,
    skenario,
    rekomendasiKWp: rekomendasi?.kWp ?? null,
    pemborosan,
    catatanKeterbatasan: [
      `Diukur ${hariTerukur} hari (${data.hariLengkap} hari data lengkap, ${data.hariBolong} hari ada jam yang bolong). Hari bolong tidak dipakai untuk menghitung ukuran panel.`,
      `Pemisah beban mengenali ${formatPersen(rasioKenal)} pemakaian per mesin. Sisanya dicatat sebagai "lainnya".`,
      `Pemakaian setahun diperkirakan dari ${data.hariLengkap} hari terukur (dikali ${formatAngka(365 / data.hariLengkap, 1)}).`,
      "Belum memperhitungkan perubahan pesanan musiman, misalnya menjelang Lebaran atau tahun ajaran baru.",
      `Produksi panel memakai kurva sederhana ${formatAngka(m.p.yieldHarianPerKWp, 1)} kWh per kWp per hari, belum memakai data cuaca setempat.`,
    ],
  };
}
