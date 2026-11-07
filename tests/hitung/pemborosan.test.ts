import { describe, expect, it } from "vitest";
import { buatParameter } from "@/lib/hitung/parameter";
import { deteksiPemborosan, jendelaDariJam } from "@/lib/hitung/pemborosan";
import type { Lokasi, Mesin, PemakaianJam } from "@/lib/tipe";
import { keWaktuISO, tambahHari } from "@/lib/waktu";

const lokasi: Lokasi = {
  id: "uji",
  nama: "UMKM Uji",
  sektor: "Konveksi",
  sentra: "Sentra Uji",
  dayaTersambungVA: 3500,
  jamKerja: { mulai: "08:00", selesai: "16:00", hariLibur: [0], istirahat: { mulai: "12:00", selesai: "13:00" } },
  status: "mengukur",
  masaUkur: { mulai: "2026-11-02", selesaiRencana: "2026-11-22" },
  izinRincian: true,
};
const setrika: Mesin = { id: "setrika", lokasiId: "uji", nama: "Setrika uap", jenis: "pemanas", jumlah: 1, dikelompokkan: false };
const kulkas: Mesin = { id: "kulkas", lokasiId: "uji", nama: "Kulkas", jenis: "pendingin", jumlah: 1, dikelompokkan: false };
const potong: Mesin = { id: "potong", lokasiId: "uji", nama: "Mesin potong", jenis: "motor", jumlah: 1, dikelompokkan: false };

/** 2026-11-02 Senin s/d 2026-11-08 Minggu */
function bangun(fn: (mesinId: string, hari: number, jam: number) => number, mesin: Mesin[], keyakinan = 0.9) {
  const r: PemakaianJam[] = [];
  for (let h = 0; h < 7; h++) {
    const tgl = tambahHari("2026-11-02", h);
    for (let j = 0; j < 24; j++) {
      for (const m of mesin) r.push({ lokasiId: "uji", mesinId: m.id, jam: keWaktuISO(tgl, j), kWh: fn(m.id, h, j), keyakinan });
      r.push({ lokasiId: "uji", mesinId: "lainnya", jam: keWaktuISO(tgl, j), kWh: 0.1, keyakinan: 0 });
    }
  }
  return r;
}
const kerja = (h: number, j: number) => h < 6 && j >= 8 && j < 16 && j !== 12;

describe("deteksiPemborosan", () => {
  it("setrika panas saat istirahat 3 dari 6 hari kerja", () => {
    const data = bangun((_, h, j) => (kerja(h, j) ? 1 : h < 3 && j === 12 ? 0.8 : 0), [setrika]);
    const [b, ...lain] = deteksiPemborosan(lokasi, [setrika], data, buatParameter());
    expect(lain).toHaveLength(0);
    expect(b.jenis).toBe("panas_menganggur");
    expect(b.hariTerjadi).toBe(3);
    expect(b.hariDiamati).toBe(6);
    expect(b.jendela).toEqual({ mulai: "12:00", selesai: "13:00" });
    expect(b.kWhPerMinggu).toBeCloseTo(2.4, 6);
    expect(b.rupiahPerMinggu).toBeNull();
    expect(b.saran).toContain("istirahat 12.00-13.00");
  });

  it("rupiah terisi bila tarif ada", () => {
    const data = bangun((_, h, j) => (kerja(h, j) ? 1 : h < 3 && j === 12 ? 0.8 : 0), [setrika]);
    const [b] = deteksiPemborosan(lokasi, [setrika], data, buatParameter({ tarifPerKWh: 1000 }));
    expect(b.rupiahPerMinggu).toBeCloseTo(2400, 6);
  });

  it("mesin yang tertib tidak menghasilkan temuan", () => {
    const data = bangun((_, h, j) => (kerja(h, j) ? 1 : 0), [setrika, potong]);
    expect(deteksiPemborosan(lokasi, [setrika, potong], data, buatParameter())).toEqual([]);
  });

  it("pendingin yang menyala terus tidak dianggap boros", () => {
    const data = bangun(() => 0.15, [kulkas]);
    expect(deteksiPemborosan(lokasi, [kulkas], data, buatParameter())).toEqual([]);
  });

  it("malam hari dipisah dari luar jam kerja, dan jendela melewati tengah malam", () => {
    const data = bangun((_, h, j) => (kerja(h, j) ? 1 : j >= 22 || j < 2 ? 0.6 : j >= 16 && j < 18 ? 0.5 : 0), [potong]);
    const hasil = deteksiPemborosan(lokasi, [potong], data, buatParameter());
    const malam = hasil.find((b) => b.jenis === "beban_malam_tinggi")!;
    const luar = hasil.find((b) => b.jenis === "nyala_luar_jam_kerja")!;
    expect(malam.jendela).toEqual({ mulai: "22:00", selesai: "02:00" });
    expect(luar.jendela).toEqual({ mulai: "16:00", selesai: "18:00" });
    expect(hasil[0].kWhPerMinggu).toBeGreaterThanOrEqual(hasil[1].kWhPerMinggu);
  });

  it("membawa keyakinan rata-rata mesin", () => {
    const data = bangun((_, h, j) => (kerja(h, j) ? 1 : h < 3 && j === 12 ? 0.8 : 0), [setrika], 0.4);
    expect(deteksiPemborosan(lokasi, [setrika], data, buatParameter())[0].keyakinan).toBeCloseTo(0.4, 6);
  });

  it("data kosong", () => {
    expect(deteksiPemborosan(lokasi, [setrika], [], buatParameter())).toEqual([]);
  });
});

describe("jendelaDariJam", () => {
  it("rentang biasa dan melingkar", () => {
    expect(jendelaDariJam([16, 17, 18])).toEqual({ mulai: "16:00", selesai: "19:00" });
    expect(jendelaDariJam([23, 0, 1, 22])).toEqual({ mulai: "22:00", selesai: "02:00" });
    expect(jendelaDariJam([12])).toEqual({ mulai: "12:00", selesai: "13:00" });
  });
});
