// SIMULASI: seluruh angka di file ini karangan yang dibuat wajar untuk usaha
// konveksi skala kecil. Wajib diganti data lapangan setelah pengukuran pertama.
// Nama usaha dan sentra sengaja generik agar tidak dikira UMKM asli.
import type { Lokasi, Mesin } from "../tipe";
import type { Skenario } from "./skenario";

const jamKerjaKonveksi: Lokasi["jamKerja"] = {
  mulai: "08:00", // SIMULASI
  selesai: "16:00", // SIMULASI
  hariLibur: [0], // SIMULASI: libur Minggu
  istirahat: { mulai: "12:00", selesai: "13:00" }, // SIMULASI
};

const lokasi: Lokasi[] = [
  {
    id: "umkm-a",
    nama: "UMKM Contoh A",
    sektor: "Konveksi",
    sentra: "Sentra Contoh 1",
    dayaTersambungVA: 3500, // SIMULASI
    jamKerja: jamKerjaKonveksi,
    status: "kalibrasi",
    masaUkur: { mulai: "2026-11-11", selesaiRencana: "2026-12-01" },
    izinRincian: true,
  },
  {
    id: "umkm-b",
    nama: "UMKM Contoh B",
    sektor: "Konveksi",
    sentra: "Sentra Contoh 1",
    dayaTersambungVA: 5500, // SIMULASI
    jamKerja: jamKerjaKonveksi,
    status: "mengukur",
    masaUkur: { mulai: "2026-11-06", selesaiRencana: "2026-11-26" },
    izinRincian: false,
  },
  {
    id: "umkm-c",
    nama: "UMKM Contoh C",
    sektor: "Konveksi",
    sentra: "Sentra Contoh 2",
    dayaTersambungVA: 7700, // SIMULASI
    jamKerja: jamKerjaKonveksi,
    status: "rapor_siap",
    masaUkur: { mulai: "2026-10-13", selesaiRencana: "2026-11-02" },
    izinRincian: true,
  },
  {
    id: "umkm-d",
    nama: "UMKM Contoh D",
    sektor: "Konveksi",
    sentra: "Sentra Contoh 2",
    dayaTersambungVA: 4400, // SIMULASI
    jamKerja: jamKerjaKonveksi,
    status: "menunggu_pasang",
    masaUkur: null,
    izinRincian: false,
  },
];

function m(lokasiId: string, kode: string, nama: string, jenis: Mesin["jenis"], jumlah: number): Mesin {
  return { id: `${lokasiId}-${kode}`, lokasiId, nama, jenis, jumlah, dikelompokkan: jumlah > 1 };
}

const mesin: Mesin[] = [
  m("umkm-a", "jahit", "Mesin jahit", "motor", 6),
  m("umkm-a", "obras", "Mesin obras", "motor", 2),
  m("umkm-a", "setrika", "Setrika uap", "pemanas", 1),
  m("umkm-a", "lampu", "Lampu dan kipas", "penerangan", 1),

  m("umkm-b", "jahit", "Mesin jahit", "motor", 12),
  m("umkm-b", "obras", "Mesin obras", "motor", 4),
  m("umkm-b", "setrika", "Setrika uap", "pemanas", 2),
  m("umkm-b", "potong", "Mesin potong kain", "motor", 1),
  m("umkm-b", "lampu", "Lampu dan kipas", "penerangan", 1),

  m("umkm-c", "jahit", "Mesin jahit", "motor", 20),
  m("umkm-c", "obras", "Mesin obras", "motor", 6),
  m("umkm-c", "setrika", "Setrika uap", "pemanas", 3),
  m("umkm-c", "potong", "Mesin potong kain", "motor", 1),
  m("umkm-c", "lampu", "Lampu dan kipas", "penerangan", 1),
  m("umkm-c", "kulkas", "Kulkas", "pendingin", 1),
];

export const skenarioKonveksi: Skenario = {
  id: "konveksi",
  sektor: "Konveksi",
  seed: 20261107,
  waktuAcuan: "2026-11-14T15:20:00+07:00",
  lokasi,
  alat: [
    { id: "NL-001", lokasiId: "umkm-a", status: "online", terakhirTerlihat: "2026-11-14T15:15:00+07:00" },
    { id: "NL-002", lokasiId: "umkm-b", status: "online", terakhirTerlihat: "2026-11-14T15:18:00+07:00" },
    { id: "NL-003", lokasiId: null, status: "di_gudang", terakhirTerlihat: "2026-11-02T16:40:00+07:00" },
    { id: "NL-004", lokasiId: null, status: "di_gudang", terakhirTerlihat: "2026-10-09T11:05:00+07:00" },
  ],
  mesin,
  // SIMULASI: daya rata-rata kelompok saat jam kerja (bukan daya papan nama),
  // keyakinan sengaja rendah untuk obras karena bentuk bebannya mirip mesin jahit.
  profilMesin: {
    "umkm-a-jahit": { kWKerja: 0.7, variasi: 0.25, keyakinan: 0.84 },
    "umkm-a-obras": { kWKerja: 0.25, variasi: 0.3, keyakinan: 0.5 },
    "umkm-a-setrika": { kWKerja: 0.9, variasi: 0.2, keyakinan: 0.9 },
    "umkm-a-lampu": { kWKerja: 0.4, variasi: 0.05, keyakinan: 0.78 },

    "umkm-b-jahit": { kWKerja: 1.4, variasi: 0.25, keyakinan: 0.86 },
    "umkm-b-obras": { kWKerja: 0.5, variasi: 0.3, keyakinan: 0.52 },
    "umkm-b-setrika": {
      kWKerja: 1.8,
      variasi: 0.2,
      keyakinan: 0.91,
      tanam: [{ saat: "istirahat", mulai: "12:00", selesai: "13:00", kW: 1.5, peluangHari: 0.7 }],
    },
    "umkm-b-potong": { kWKerja: 0.35, variasi: 0.4, keyakinan: 0.72 },
    "umkm-b-lampu": {
      kWKerja: 0.6,
      variasi: 0.05,
      keyakinan: 0.78,
      tanam: [{ saat: "luar_jam_kerja", mulai: "16:00", selesai: "19:00", kW: 0.5, peluangHari: 0.45 }],
    },

    "umkm-c-jahit": { kWKerja: 2.4, variasi: 0.25, keyakinan: 0.85 },
    "umkm-c-obras": { kWKerja: 0.8, variasi: 0.3, keyakinan: 0.55 },
    "umkm-c-setrika": {
      kWKerja: 2.7,
      variasi: 0.2,
      keyakinan: 0.9,
      tanam: [{ saat: "istirahat", mulai: "12:00", selesai: "13:00", kW: 2.3, peluangHari: 0.8 }],
    },
    "umkm-c-potong": {
      kWKerja: 0.5,
      variasi: 0.4,
      keyakinan: 0.7,
      tanam: [{ saat: "malam", mulai: "22:00", selesai: "02:00", kW: 0.3, peluangHari: 0.3 }],
    },
    "umkm-c-lampu": { kWKerja: 1.0, variasi: 0.05, keyakinan: 0.8 },
    "umkm-c-kulkas": { kWKerja: 0.12, variasi: 0.3, keyakinan: 0.66, kWSiaga: 0.12 },
  },
  bebanLainnya: {
    "umkm-a": { dasarKW: 0.12, rasioSaatKerja: 0.08 }, // SIMULASI
    "umkm-b": { dasarKW: 0.15, rasioSaatKerja: 0.08 }, // SIMULASI
    "umkm-c": { dasarKW: 0.2, rasioSaatKerja: 0.08 }, // SIMULASI
  },
  bolong: [
    { lokasiId: "umkm-b", tanggal: "2026-11-10", jamMulai: 2, jumlahJam: 4 },
    { lokasiId: "umkm-c", tanggal: "2026-10-20", jamMulai: 10, jumlahJam: 5 },
  ],
  tanggalRapor: { "umkm-c": "2026-11-03" },
};
