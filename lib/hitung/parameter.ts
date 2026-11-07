// Parameter keputusan tim. Nilai null berarti belum ada data asli:
// fungsi hitung mengembalikan null dan layar menampilkan placeholder.

export type Parameter = {
  /** Rupiah per kWh sesuai golongan tarif PLN UMKM uji coba. */
  tarifPerKWh: number | null;
  /** Rupiah per kWp terpasang, dari penawaran installer. */
  hargaPerKWp: number | null;
  /** kWh per kWp per hari. Perkiraan kasar, akan diganti pvlib dan data NASA POWER. */
  yieldHarianPerKWp: number;
  /** "Efisiensi dulu" bila energi terbuang > ambang ini dari total pemakaian. */
  ambangPemborosanRasio: number;
  /** "Layak" bila balik modal skenario rekomendasi < ambang ini. */
  ambangBalikModalTahun: number;
  /** Rekomendasi = kWp terbesar yang produksi terbuangnya tidak melebihi rasio ini. */
  ambangTerbuangRasio: number;
  /** Di bawah ambang ini, pemborosan disebut "kemungkinan" dan tanpa angka hemat. */
  ambangKeyakinan: number;
  /** Langkah ukuran panel yang dicoba di tabel skenario. */
  langkahKWp: number;
};

export const PARAMETER_BAWAAN: Parameter = {
  tarifPerKWh: null, // TODO tim: isi dari golongan tarif PLN UMKM uji coba
  hargaPerKWp: null, // TODO tim: isi dari penawaran installer
  yieldHarianPerKWp: 4.0, // SIMULASI: kisaran umum Jawa Tengah, ganti pvlib + NASA POWER
  ambangPemborosanRasio: 0.15, // KEPUTUSAN TIM: nilai sementara
  ambangBalikModalTahun: 6, // KEPUTUSAN TIM: nilai sementara
  // KEPUTUSAN TIM: nilai sementara. Hari libur mingguan membuat produksi hari itu
  // hampir seluruhnya terbuang; di skenario konveksi ambang 10% hanya merekomendasikan 1 kWp.
  ambangTerbuangRasio: 0.2,
  ambangKeyakinan: 0.6, // KEPUTUSAN TIM: nilai sementara
  langkahKWp: 1,
};

export function buatParameter(ubah: Partial<Parameter> = {}): Parameter {
  return { ...PARAMETER_BAWAAN, ...ubah };
}
