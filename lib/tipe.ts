// Kontrak data bersama antara prototype dan backend FastAPI nanti.
// Struktur mengikuti bagian 6 brief; tambahan ditandai komentar "tambahan".

/** Tanggal "YYYY-MM-DD" (WIB). */
export type Tanggal = string;
/** Jam "HH:MM" (WIB). */
export type JamMenit = string;
/** Waktu ISO 8601 dengan offset WIB, misalnya "2026-11-14T08:00:00+07:00". */
export type WaktuISO = string;

export type StatusLokasi =
  | "menunggu_pasang"
  | "kalibrasi"
  | "mengukur"
  | "rapor_siap"
  | "plts_terpasang"
  | "verifikasi";

export type Lokasi = {
  id: string;
  nama: string;
  sektor: string;
  sentra: string;
  dayaTersambungVA: number;
  jamKerja: {
    mulai: JamMenit;
    selesai: JamMenit;
    /** 0 = Minggu ... 6 = Sabtu */
    hariLibur: number[];
    // tambahan: dibutuhkan untuk mendeteksi mesin panas saat istirahat
    istirahat: { mulai: JamMenit; selesai: JamMenit } | null;
  };
  status: StatusLokasi;
  masaUkur: { mulai: Tanggal; selesaiRencana: Tanggal } | null;
  // tambahan: dinas hanya boleh membuka rincian per mesin bila pemilik setuju
  izinRincian: boolean;
};

export type StatusAlat = "online" | "offline" | "di_gudang";

export type Alat = {
  id: string;
  lokasiId: string | null;
  status: StatusAlat;
  terakhirTerlihat: WaktuISO;
};

export type Mesin = {
  id: string;
  lokasiId: string;
  nama: string;
  jenis: JenisMesin;
  jumlah: number;
  dikelompokkan: boolean;
};

// tambahan: jenis dipakai detektor pemborosan (mis. hanya pemanas yang bisa "panas menganggur")
export type JenisMesin = "motor" | "pemanas" | "penerangan" | "pendingin" | "lain";

export type PemakaianJam = {
  lokasiId: string;
  mesinId: string | "lainnya";
  /** Awal jam pengukuran. */
  jam: WaktuISO;
  kWh: number;
  /** 0..1, keyakinan pemisah beban bahwa energi ini milik mesin tersebut. */
  keyakinan: number;
};

// tambahan: yang dilihat meteran (total), tersedia sejak hari pertama termasuk masa kalibrasi
export type TotalJam = { lokasiId: string; jam: WaktuISO; kWh: number };

export type JenisPemborosan = "nyala_luar_jam_kerja" | "panas_menganggur" | "beban_malam_tinggi";

export type Pemborosan = {
  id: string;
  lokasiId: string;
  mesinId: string;
  jenis: JenisPemborosan;
  kWhPerMinggu: number;
  /** null bila tarif belum diisi */
  rupiahPerMinggu: number | null;
  saran: string;
  // tambahan: dipakai kalimat nota ("12.00-13.00, 4 dari 6 hari kerja")
  jendela: { mulai: JamMenit; selesai: JamMenit };
  hariTerjadi: number;
  hariDiamati: number;
  keyakinan: number;
};

export type SkenarioPLTS = {
  kWp: number;
  terpakaiSendiri_kWh_tahun: number;
  terbuang_kWh_tahun: number;
  hematRupiahTahun: number | null;
  biayaRupiah: number | null;
  balikModalTahun: number | null;
};

// tambahan "belum_bisa_dihitung": brief bagian 9 meminta stempel ini bila tarif/harga kosong
export type KategoriRapor = "layak" | "efisiensi_dulu" | "belum_layak" | "belum_bisa_dihitung";

export type Rapor = {
  lokasiId: string;
  nomor: string;
  tanggal: Tanggal;
  kategori: KategoriRapor;
  // tambahan: satu kalimat alasan di samping stempel
  alasanKategori: string;
  skenario: SkenarioPLTS[];
  rekomendasiKWp: number | null;
  pemborosan: Pemborosan[];
  catatanKeterbatasan: string[];
};
