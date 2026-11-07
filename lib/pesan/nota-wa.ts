// Template pesan WhatsApp. Semua isi berasal dari data dan lib/hitung,
// tidak ada teks bebas dari model bahasa. Satu pesan memuat satu saran.
import type { KategoriRapor, Pemborosan, Tanggal } from "../tipe";
import { formatJam, formatKWp, formatRupiah, formatTanggal, formatWaktu } from "../format";
import { LABEL_STEMPEL } from "../hitung/kategori";

export const PLACEHOLDER_NOMOR_TEKNISI = "[NOMOR TEKNISI]";
const MINGGU_PER_BULAN = 30 / 7;

export type JenisPesan = "sambutan" | "mingguan" | "terputus" | "rapor_akhir";

export function pesanSambutan(m: {
  namaUsaha: string;
  masaUkur: { mulai: Tanggal; selesaiRencana: Tanggal };
  nomorTeknisi?: string | null;
}): string {
  return [
    "NOTA LISTRIK · Alat terpasang",
    m.namaUsaha,
    "",
    "Mulai hari ini alat kecil di dekat meteran mencatat pemakaian listrik usaha Anda setiap jam.",
    `Alat terpasang ${formatTanggal(m.masaUkur.mulai)} sampai ${formatTanggal(m.masaUkur.selesaiRencana)}.`,
    "",
    "Usaha tetap jalan seperti biasa. Tidak perlu mengubah apa pun.",
    "Setiap minggu Anda akan menerima nota: berapa biaya listrik dan mesin mana yang membuang uang.",
    "",
    `Pertanyaan atau alat bermasalah: ${m.nomorTeknisi || PLACEHOLDER_NOMOR_TEKNISI}`,
  ].join("\n");
}

function kalimatKejadian(b: Pemborosan, nama: string, mungkin: boolean): string {
  const pembuka = mungkin ? `Kemungkinan ${nama.toLowerCase()}` : nama;
  const rentang = `${formatJam(b.jendela.mulai)}-${formatJam(b.jendela.selesai)}`;
  const frekuensi =
    b.jenis === "panas_menganggur"
      ? `${b.hariTerjadi} dari ${b.hariDiamati} hari kerja`
      : `${b.hariTerjadi} dari ${b.hariDiamati} hari`;
  switch (b.jenis) {
    case "panas_menganggur":
      return `${pembuka} tetap panas saat istirahat ${rentang}, ${frekuensi}.`;
    case "nyala_luar_jam_kerja":
      return `${pembuka} masih menyala di luar jam kerja (${rentang}), ${frekuensi}.`;
    case "beban_malam_tinggi":
      return `${pembuka} menyala malam hari (${rentang}), ${frekuensi}.`;
  }
}

export function pesanMingguan(m: {
  mingguKe: number;
  namaUsaha: string;
  rupiahMinggu: number | null;
  pemborosanTeratas: Pemborosan | null;
  namaMesin: string | null;
  ambangKeyakinan: number;
  tautanDashboard: string;
}): string {
  const baris = [
    `NOTA LISTRIK · Minggu ke-${m.mingguKe}`,
    m.namaUsaha,
    "",
    `Biaya listrik minggu ini: ${formatRupiah(m.rupiahMinggu)}`,
    "",
  ];
  const b = m.pemborosanTeratas;
  if (!b || !m.namaMesin) {
    baris.push("Minggu ini tidak ada listrik terbuang yang menonjol. Pertahankan kebiasaan mematikan mesin saat tidak dipakai.");
  } else {
    const mungkin = b.keyakinan < m.ambangKeyakinan;
    baris.push(`Terbuang: ${formatRupiah(b.rupiahPerMinggu)}`);
    baris.push(kalimatKejadian(b, m.namaMesin, mungkin));
    baris.push("");
    baris.push(`Saran besok: ${b.saran}`);
    // Keyakinan rendah: jangan menjanjikan angka hemat yang belum pasti
    if (!mungkin) {
      const hematBulan = b.rupiahPerMinggu === null ? null : b.rupiahPerMinggu * MINGGU_PER_BULAN;
      baris.push(`Perkiraan hemat: ${formatRupiah(hematBulan)} per bulan.`);
    }
  }
  baris.push("", `Rincian per mesin: ${m.tautanDashboard}`);
  return baris.join("\n");
}

export function pesanTerputus(m: { namaUsaha: string; terakhirData: string; nomorTeknisi?: string | null }): string {
  return [
    "NOTA LISTRIK · Alat tidak mengirim data",
    m.namaUsaha,
    "",
    `Data terakhir masuk ${formatWaktu(m.terakhirData)}.`,
    "",
    "Mohon dicek:",
    "1. Colokan alat di stopkontak tidak lepas.",
    "2. WiFi usaha menyala.",
    "Jangan membuka casing alat.",
    "",
    `Kalau masih belum kembali, hubungi teknisi: ${m.nomorTeknisi || PLACEHOLDER_NOMOR_TEKNISI}`,
  ].join("\n");
}

export function pesanRaporAkhir(m: {
  namaUsaha: string;
  periode: { dari: Tanggal; sampai: Tanggal };
  hariLengkap: number;
  kategori: KategoriRapor;
  rekomendasiKWp: number | null;
  tautanRapor: string;
}): string {
  const saranPanel =
    m.rekomendasiKWp === null
      ? "Ukuran panel: belum disarankan."
      : `Ukuran panel yang pas: ${formatKWp(m.rekomendasiKWp)}.`;
  return [
    "NOTA LISTRIK · Rapor energi siap",
    m.namaUsaha,
    "",
    `Masa ukur ${formatTanggal(m.periode.dari)} - ${formatTanggal(m.periode.sampai)} (${m.hariLengkap} hari data lengkap). Alat sudah dicabut.`,
    "",
    `Hasil: ${LABEL_STEMPEL[m.kategori]}`,
    saranPanel,
    "",
    `Rapor lengkap untuk bank atau koperasi: ${m.tautanRapor}`,
  ].join("\n");
}
