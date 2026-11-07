import { describe, expect, it } from "vitest";
import { tentukanKategori, teksAturanKategori } from "@/lib/hitung/kategori";
import { buatParameter } from "@/lib/hitung/parameter";
import { balikModalTahun, biayaPasang, kWhKeRupiah } from "@/lib/hitung/rupiah";

describe("rupiah", () => {
  it("tarif kosong menghasilkan null, bukan nol", () => {
    expect(kWhKeRupiah(10, null)).toBeNull();
    expect(biayaPasang(2, null)).toBeNull();
  });
  it("menghitung bila terisi", () => {
    expect(kWhKeRupiah(10, 1500)).toBe(15000);
    expect(biayaPasang(2, 12_000_000)).toBe(24_000_000);
    expect(balikModalTahun(24_000_000, 6_000_000)).toBe(4);
  });
  it("balik modal null bila hemat nol atau negatif", () => {
    expect(balikModalTahun(1, 0)).toBeNull();
    expect(balikModalTahun(1, -5)).toBeNull();
    expect(balikModalTahun(null, 5)).toBeNull();
  });
});

describe("tentukanKategori", () => {
  const p = buatParameter({ ambangPemborosanRasio: 0.15, ambangBalikModalTahun: 6 });
  const dasar = { totalKWh: 1000, borosKWh: 50, balikModalTahun: 4, adaRekomendasi: true, p };

  it("efisiensi dulu bila pemborosan di atas ambang, meski balik modal belum bisa dihitung", () => {
    const h = tentukanKategori({ ...dasar, borosKWh: 200, balikModalTahun: null });
    expect(h.kategori).toBe("efisiensi_dulu");
    expect(h.alasan).toContain("20%");
  });
  it("tepat di ambang pemborosan belum dianggap efisiensi dulu", () => {
    expect(tentukanKategori({ ...dasar, borosKWh: 150 }).kategori).toBe("layak");
  });
  it("belum bisa dihitung bila tarif/harga kosong", () => {
    expect(tentukanKategori({ ...dasar, balikModalTahun: null }).kategori).toBe("belum_bisa_dihitung");
  });
  it("layak bila balik modal di bawah ambang", () => {
    expect(tentukanKategori(dasar).kategori).toBe("layak");
  });
  it("belum layak bila balik modal sama atau di atas ambang", () => {
    expect(tentukanKategori({ ...dasar, balikModalTahun: 6 }).kategori).toBe("belum_layak");
  });
  it("belum layak bila tidak ada ukuran panel yang pas", () => {
    expect(tentukanKategori({ ...dasar, adaRekomendasi: false, balikModalTahun: null }).kategori).toBe("belum_layak");
  });
  it("total nol tidak membagi dengan nol", () => {
    expect(tentukanKategori({ ...dasar, totalKWh: 0, borosKWh: 0 }).kategori).toBe("layak");
  });
  it("aturan tertulis memuat ambang yang dipakai", () => {
    const teks = teksAturanKategori(p).join(" ");
    expect(teks).toContain("15%");
    expect(teks).toContain("6 tahun");
  });
});
