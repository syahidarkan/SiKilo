import type { Alat, JenisMesin, Lokasi } from "../tipe";

export type Galat = { kolom: string; pesan: string };
export type HasilValidasi = { ok: true } | { ok: false; galat: Galat[] };

const hasil = (galat: Galat[]): HasilValidasi => (galat.length ? { ok: false, galat } : { ok: true });

/** Label QR alat: "NL-" + tiga angka. Huruf kecil dan spasi dari ketikan teknisi dirapikan. */
export function rapikanIdAlat(masukan: string): string {
  return masukan.trim().toUpperCase().replace(/\s+/g, "");
}

export function validasiAlat(masukan: string, alat: Alat[], lokasi: Lokasi[]): HasilValidasi {
  const id = rapikanIdAlat(masukan);
  if (!id) return hasil([{ kolom: "alatId", pesan: "Isi ID alat dari label QR di tutup casing." }]);
  if (!/^NL-\d{3}$/.test(id)) {
    return hasil([{ kolom: "alatId", pesan: "Format ID alat: NL- diikuti tiga angka, misalnya NL-003." }]);
  }
  const a = alat.find((x) => x.id === id);
  if (!a) return hasil([{ kolom: "alatId", pesan: `Alat ${id} tidak terdaftar. Periksa lagi label QR.` }]);
  if (a.status !== "di_gudang" || a.lokasiId !== null) {
    const nama = lokasi.find((l) => l.id === a.lokasiId)?.nama ?? "lokasi lain";
    return hasil([{ kolom: "alatId", pesan: `Alat ${id} masih tercatat di ${nama}. Cabut dulu sebelum dipasang di tempat lain.` }]);
  }
  return { ok: true };
}

export function validasiLokasiPasang(lokasiId: string | null, lokasi: Lokasi[]): HasilValidasi {
  if (!lokasiId) return hasil([{ kolom: "lokasiId", pesan: "Pilih UMKM yang akan dipasangi alat." }]);
  const l = lokasi.find((x) => x.id === lokasiId);
  if (!l) return hasil([{ kolom: "lokasiId", pesan: "UMKM tidak ditemukan." }]);
  if (l.status !== "menunggu_pasang") {
    return hasil([{ kolom: "lokasiId", pesan: `${l.nama} tidak sedang menunggu pemasangan.` }]);
  }
  return { ok: true };
}

export const CHECKLIST_KESELAMATAN = [
  { id: "sisi_pelanggan", teks: "Sensor arus dijepit di kabel sisi pelanggan, setelah meteran." },
  { id: "segel_pln", teks: "Tidak menyentuh kWh meter dan segel PLN." },
  { id: "casing_tertutup", teks: "Casing tertutup rapat dan sekrup terpasang." },
  { id: "terminal", teks: "Kabel tegangan terpasang kencang di terminal." },
] as const;

export type IdChecklist = (typeof CHECKLIST_KESELAMATAN)[number]["id"];

export function validasiChecklist(centang: Partial<Record<IdChecklist, boolean>>): HasilValidasi {
  return hasil(
    CHECKLIST_KESELAMATAN.filter((c) => !centang[c.id]).map((c) => ({
      kolom: `checklist.${c.id}`,
      pesan: "Wajib dicentang sebelum lanjut.",
    })),
  );
}

export type StatusKoneksi = "menunggu" | "masuk" | "gagal";

export function validasiKoneksi(status: StatusKoneksi): HasilValidasi {
  if (status === "masuk") return { ok: true };
  return hasil([
    {
      kolom: "koneksi",
      pesan:
        status === "gagal"
          ? "Data belum masuk. Cek WiFi usaha dan pastikan catu daya alat menyala."
          : "Tunggu sampai data pertama masuk.",
    },
  ]);
}

export type MasukanMesin = { nama: string; jenis: JenisMesin; jumlah: number; dikelompokkan: boolean };
export const BATAS_UNIT = 200;

export function validasiMesin(daftar: MasukanMesin[]): HasilValidasi {
  const galat: Galat[] = [];
  if (daftar.length === 0) galat.push({ kolom: "mesin", pesan: "Isi minimal satu mesin utama." });
  const namaTerpakai = new Map<string, number>();
  daftar.forEach((m, i) => {
    const nama = m.nama.trim();
    if (!nama) galat.push({ kolom: `mesin.${i}.nama`, pesan: "Nama mesin wajib diisi." });
    const kunci = nama.toLowerCase();
    if (nama && namaTerpakai.has(kunci)) {
      galat.push({ kolom: `mesin.${i}.nama`, pesan: `Nama sama dengan baris ${namaTerpakai.get(kunci)! + 1}. Gabungkan jadi satu baris.` });
    } else if (nama) namaTerpakai.set(kunci, i);
    if (!Number.isInteger(m.jumlah) || m.jumlah < 1 || m.jumlah > BATAS_UNIT) {
      galat.push({ kolom: `mesin.${i}.jumlah`, pesan: `Jumlah unit harus bilangan bulat 1 sampai ${BATAS_UNIT}.` });
    } else if (m.dikelompokkan && m.jumlah < 2) {
      galat.push({ kolom: `mesin.${i}.dikelompokkan`, pesan: "Kelompokkan hanya untuk 2 unit atau lebih." });
    }
  });
  return hasil(galat);
}

/** Setiap smart plug terkait ke tepat satu mesin, dan satu mesin tidak dipakai dua plug. */
export function validasiPlug(kaitan: { plugId: string; mesinIndeks: number | null }[], jumlahMesin: number): HasilValidasi {
  const galat: Galat[] = [];
  if (kaitan.length === 0) galat.push({ kolom: "plug", pesan: "Kaitkan minimal satu smart plug." });
  const dipakai = new Map<number, string>();
  for (const k of kaitan) {
    if (k.mesinIndeks === null) {
      galat.push({ kolom: `plug.${k.plugId}`, pesan: `Pilih mesin untuk ${k.plugId}.` });
    } else if (k.mesinIndeks < 0 || k.mesinIndeks >= jumlahMesin) {
      galat.push({ kolom: `plug.${k.plugId}`, pesan: "Mesin tidak ada di daftar." });
    } else if (dipakai.has(k.mesinIndeks)) {
      galat.push({ kolom: `plug.${k.plugId}`, pesan: `Mesin ini sudah dikaitkan ke ${dipakai.get(k.mesinIndeks)}.` });
    } else dipakai.set(k.mesinIndeks, k.plugId);
  }
  return hasil(galat);
}

export function validasiCabut(k: { masaCukup: boolean; plugDicabut: boolean; sensorDicabut: boolean }): HasilValidasi {
  const galat: Galat[] = [];
  if (!k.masaCukup) galat.push({ kolom: "masaCukup", pesan: "Konfirmasi masa ukur sudah cukup." });
  if (!k.plugDicabut) galat.push({ kolom: "plugDicabut", pesan: "Konfirmasi semua smart plug sudah dicabut." });
  if (!k.sensorDicabut) galat.push({ kolom: "sensorDicabut", pesan: "Konfirmasi sensor sudah dilepas dari kabel." });
  return hasil(galat);
}

export function gabung(...h: HasilValidasi[]): HasilValidasi {
  return hasil(h.flatMap((x) => (x.ok ? [] : x.galat)));
}
