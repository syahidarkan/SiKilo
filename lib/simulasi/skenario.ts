import type { Alat, JamMenit, Lokasi, Mesin, Tanggal, WaktuISO } from "../tipe";

/** Pola pemborosan yang sengaja ditanam supaya layar pemborosan punya isi. */
export type TanamPemborosan = {
  saat: "istirahat" | "luar_jam_kerja" | "malam";
  mulai: JamMenit;
  selesai: JamMenit;
  /** Daya rata-rata kelompok mesin saat terjadi, kW. */
  kW: number;
  /** Peluang terjadi di satu hari (kerja untuk "istirahat"). */
  peluangHari: number;
};

export type ProfilMesin = {
  /** Daya rata-rata seluruh unit dalam kelompok saat jam kerja, kW. */
  kWKerja: number;
  /** Variasi acak relatif per jam (0..1). */
  variasi: number;
  /** Keyakinan rata-rata pemisah beban untuk mesin ini. */
  keyakinan: number;
  /** Daya saat tidak dipakai, kW. Untuk pendingin yang menyala terus. */
  kWSiaga?: number;
  tanam?: TanamPemborosan[];
};

export type Skenario = {
  id: string;
  sektor: string;
  seed: number;
  /** "Sekarang" di dunia simulasi; data dibangkitkan sampai jam ini. */
  waktuAcuan: WaktuISO;
  lokasi: Lokasi[];
  alat: Alat[];
  mesin: Mesin[];
  profilMesin: Record<string, ProfilMesin>;
  /** Beban yang tidak dikenali (kulkas kecil, router, charger), kW, per lokasi. */
  bebanLainnya: Record<string, { dasarKW: number; rasioSaatKerja: number }>;
  /** Jam tanpa data karena alat terputus. */
  bolong: { lokasiId: string; tanggal: Tanggal; jamMulai: number; jumlahJam: number }[];
  /** Tanggal rapor dibuat untuk lokasi yang statusnya rapor_siap. */
  tanggalRapor: Record<string, Tanggal>;
};
