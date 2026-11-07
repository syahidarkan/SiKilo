// Kerangka sektor kedua. Tim mengisi lokasi, mesin, dan profil mesin dari data lapangan
// mengikuti bentuk skenario-konveksi.ts. Juga dipakai untuk keadaan "program baru dimulai".
import type { Skenario } from "./skenario";

export const skenarioKosong: Skenario = {
  id: "kosong",
  sektor: "[SEKTOR KEDUA]",
  seed: 1,
  waktuAcuan: "2026-11-14T15:20:00+07:00",
  lokasi: [],
  alat: [
    { id: "NL-001", lokasiId: null, status: "di_gudang", terakhirTerlihat: "2026-11-14T09:00:00+07:00" },
    { id: "NL-002", lokasiId: null, status: "di_gudang", terakhirTerlihat: "2026-11-14T09:00:00+07:00" },
  ],
  mesin: [],
  profilMesin: {},
  bebanLainnya: {},
  bolong: [],
  tanggalRapor: {},
};
