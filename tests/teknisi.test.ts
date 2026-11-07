import { describe, expect, it } from "vitest";
import { skenarioKonveksi } from "@/lib/simulasi/skenario-konveksi";
import {
  validasiAlat,
  validasiCabut,
  validasiChecklist,
  validasiKoneksi,
  validasiLokasiPasang,
  validasiMesin,
  validasiPlug,
  type HasilValidasi,
} from "@/lib/teknisi/validasi";

const { alat, lokasi } = skenarioKonveksi;
const pesan = (h: HasilValidasi) => (h.ok ? [] : h.galat.map((g) => `${g.kolom}: ${g.pesan}`));

describe("validasi pasang", () => {
  it("ID alat: format, terdaftar, dan harus di gudang", () => {
    expect(pesan(validasiAlat("", alat, lokasi))[0]).toMatch(/^alatId: Isi ID/);
    expect(pesan(validasiAlat("ABC", alat, lokasi))[0]).toMatch(/Format/);
    expect(pesan(validasiAlat("NL-999", alat, lokasi))[0]).toMatch(/tidak terdaftar/);
    expect(pesan(validasiAlat("NL-002", alat, lokasi))[0]).toMatch(/masih tercatat di UMKM Contoh B/);
    expect(validasiAlat(" nl-003 ", alat, lokasi).ok).toBe(true);
  });

  it("lokasi harus menunggu pasang", () => {
    expect(validasiLokasiPasang(null, lokasi).ok).toBe(false);
    expect(pesan(validasiLokasiPasang("umkm-b", lokasi))[0]).toMatch(/tidak sedang menunggu/);
    expect(validasiLokasiPasang("umkm-d", lokasi).ok).toBe(true);
  });

  it("semua butir keselamatan wajib dicentang", () => {
    expect(pesan(validasiChecklist({ sisi_pelanggan: true, segel_pln: true }))).toHaveLength(2);
    expect(
      validasiChecklist({ sisi_pelanggan: true, segel_pln: true, casing_tertutup: true, terminal: true }).ok,
    ).toBe(true);
  });

  it("koneksi hanya lolos bila data masuk", () => {
    expect(validasiKoneksi("menunggu").ok).toBe(false);
    expect(pesan(validasiKoneksi("gagal"))[0]).toMatch(/WiFi/);
    expect(validasiKoneksi("masuk").ok).toBe(true);
  });

  it("daftar mesin: error menempel ke kolom yang salah", () => {
    expect(pesan(validasiMesin([]))).toEqual(["mesin: Isi minimal satu mesin utama."]);
    const g = pesan(
      validasiMesin([
        { nama: "Mesin jahit", jenis: "motor", jumlah: 12, dikelompokkan: true },
        { nama: " mesin JAHIT ", jenis: "motor", jumlah: 1, dikelompokkan: false },
        { nama: "", jenis: "pemanas", jumlah: 0, dikelompokkan: false },
        { nama: "Obras", jenis: "motor", jumlah: 1, dikelompokkan: true },
        { nama: "Potong", jenis: "motor", jumlah: 1.5, dikelompokkan: false },
      ]),
    );
    expect(g).toEqual([
      expect.stringMatching(/^mesin\.1\.nama: Nama sama dengan baris 1/),
      expect.stringMatching(/^mesin\.2\.nama: /),
      expect.stringMatching(/^mesin\.2\.jumlah: /),
      expect.stringMatching(/^mesin\.3\.dikelompokkan: /),
      expect.stringMatching(/^mesin\.4\.jumlah: /),
    ]);
  });

  it("smart plug: satu plug satu mesin", () => {
    expect(validasiPlug([], 2).ok).toBe(false);
    expect(pesan(validasiPlug([{ plugId: "SP-1", mesinIndeks: null }], 2))[0]).toMatch(/Pilih mesin/);
    expect(pesan(validasiPlug([{ plugId: "SP-1", mesinIndeks: 5 }], 2))[0]).toMatch(/tidak ada/);
    expect(
      pesan(
        validasiPlug(
          [
            { plugId: "SP-1", mesinIndeks: 0 },
            { plugId: "SP-2", mesinIndeks: 0 },
          ],
          2,
        ),
      )[0],
    ).toMatch(/sudah dikaitkan ke SP-1/);
    expect(validasiPlug([{ plugId: "SP-1", mesinIndeks: 1 }], 2).ok).toBe(true);
  });

  it("cabut butuh tiga konfirmasi", () => {
    expect(pesan(validasiCabut({ masaCukup: true, plugDicabut: false, sensorDicabut: false }))).toHaveLength(2);
    expect(validasiCabut({ masaCukup: true, plugDicabut: true, sensorDicabut: true }).ok).toBe(true);
  });
});
