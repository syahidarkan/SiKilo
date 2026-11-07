// Satu-satunya pintu data untuk layar. Implementasi simulasi ada di lib/simulasi;
// nanti diganti implementasi yang memanggil FastAPI dengan bentuk yang sama.
import type { Parameter } from "./hitung/parameter";
import type { MasukanMesin, Galat, IdChecklist, StatusKoneksi } from "./teknisi/validasi";
import type { Alat, Lokasi, Mesin, PemakaianJam, Pemborosan, Rapor, TotalJam, WaktuISO } from "./tipe";

export type HasilAksi = { ok: true } | { ok: false; galat: Galat[] };

export type MasukanPasang = {
  alatId: string;
  lokasiId: string;
  checklist: Partial<Record<IdChecklist, boolean>>;
  koneksi: StatusKoneksi;
  mesin: MasukanMesin[];
  plug: { plugId: string; mesinIndeks: number | null }[];
};

export type MasukanCabut = {
  lokasiId: string;
  masaCukup: boolean;
  plugDicabut: boolean;
  sensorDicabut: boolean;
};

export interface SumberData {
  /** "Sekarang" menurut sumber data. Simulasi memakai waktu tetap agar tampilan stabil. */
  waktuSekarang(): Promise<WaktuISO>;
  ambilParameter(): Promise<Parameter>;

  daftarLokasi(): Promise<Lokasi[]>;
  ambilLokasi(lokasiId: string): Promise<Lokasi | null>;
  daftarAlat(): Promise<Alat[]>;
  daftarMesin(lokasiId: string): Promise<Mesin[]>;
  ambilMesin(mesinId: string): Promise<Mesin | null>;

  /** Total dari meteran per jam. Tersedia sejak hari pertama, termasuk masa kalibrasi. */
  ambilTotalPerJam(lokasiId: string): Promise<TotalJam[]>;
  /** Hasil pemisah beban per mesin. Kosong selama masa kalibrasi. */
  ambilPemakaianPerMesin(lokasiId: string): Promise<PemakaianJam[]>;
  /** Kosong selama masa kalibrasi. */
  ambilPemborosan(lokasiId: string): Promise<Pemborosan[]>;
  /** null bila lokasi belum selesai diukur. */
  ambilRapor(lokasiId: string): Promise<Rapor | null>;
  daftarRapor(): Promise<Rapor[]>;

  pasangAlat(m: MasukanPasang): Promise<HasilAksi>;
  cabutAlat(m: MasukanCabut): Promise<HasilAksi>;
}
