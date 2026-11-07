import { describe, expect, it } from "vitest";
import { formatJam, formatKWh, formatKWp, formatRupiah, formatTanggal, formatWaktu, PLACEHOLDER_HARGA } from "@/lib/format";
import { pesanMingguan, pesanRaporAkhir, pesanSambutan, pesanTerputus } from "@/lib/pesan/nota-wa";
import type { Pemborosan } from "@/lib/tipe";

describe("format id-ID", () => {
  it("rupiah", () => {
    expect(formatRupiah(125000)).toBe("Rp 125.000");
    expect(formatRupiah(1234567.6)).toBe("Rp 1.234.568");
    expect(formatRupiah(-5000)).toBe("-Rp 5.000");
    expect(formatRupiah(null)).toBe("[TARIF PLN]");
    expect(formatRupiah(null, PLACEHOLDER_HARGA)).toBe("[HARGA INSTALLER]");
  });
  it("energi, tanggal, jam", () => {
    expect(formatKWh(2.44)).toBe("2,4 kWh");
    expect(formatKWp(2)).toBe("2 kWp");
    expect(formatKWp(1.5)).toBe("1,5 kWp");
    expect(formatTanggal("2026-11-14")).toBe("14 Nov 2026");
    expect(formatTanggal("2026-08-03")).toBe("3 Agu 2026");
    expect(formatJam("12:00")).toBe("12.00");
    expect(formatJam(6)).toBe("06.00");
    expect(formatWaktu("2026-11-14T08:20:00Z")).toBe("14 Nov 2026, 15.20");
  });
});

const boros: Pemborosan = {
  id: "x",
  lokasiId: "b",
  mesinId: "setrika",
  jenis: "panas_menganggur",
  kWhPerMinggu: 7,
  rupiahPerMinggu: 7000,
  saran: "Matikan setrika uap saat istirahat 12.00-13.00, nyalakan lagi 10 menit sebelum kerja.",
  jendela: { mulai: "12:00", selesai: "13:00" },
  hariTerjadi: 4,
  hariDiamati: 6,
  keyakinan: 0.9,
};
const dasar = {
  mingguKe: 2,
  namaUsaha: "UMKM Contoh B",
  rupiahMinggu: 250000,
  pemborosanTeratas: boros,
  namaMesin: "Setrika uap",
  ambangKeyakinan: 0.6,
  tautanDashboard: "/pemilik",
};

describe("pesan WhatsApp", () => {
  it("nota mingguan berisi rupiah, kejadian, satu saran, dan perkiraan hemat per bulan", () => {
    const t = pesanMingguan(dasar);
    expect(t).toContain("NOTA LISTRIK · Minggu ke-2");
    expect(t).toContain("Biaya listrik minggu ini: Rp 250.000");
    expect(t).toContain("Terbuang: Rp 7.000");
    expect(t).toContain("Setrika uap tetap panas saat istirahat 12.00-13.00, 4 dari 6 hari kerja.");
    expect(t.match(/Saran besok/g)).toHaveLength(1);
    expect(t).toContain("Perkiraan hemat: Rp 30.000 per bulan.");
    expect(t).not.toMatch(/kWh/);
  });

  it("tarif kosong: placeholder, bukan tebakan", () => {
    const t = pesanMingguan({ ...dasar, rupiahMinggu: null, pemborosanTeratas: { ...boros, rupiahPerMinggu: null } });
    expect(t).toContain("Biaya listrik minggu ini: [TARIF PLN]");
    expect(t).toContain("Terbuang: [TARIF PLN]");
    expect(t).toContain("Perkiraan hemat: [TARIF PLN] per bulan.");
  });

  it("keyakinan rendah: memakai 'kemungkinan' dan tanpa angka hemat", () => {
    const t = pesanMingguan({ ...dasar, pemborosanTeratas: { ...boros, keyakinan: 0.5 } });
    expect(t).toContain("Kemungkinan setrika uap tetap panas");
    expect(t).not.toContain("Perkiraan hemat");
  });

  it("tanpa pemborosan: pesan positif tanpa saran hemat", () => {
    const t = pesanMingguan({ ...dasar, pemborosanTeratas: null, namaMesin: null });
    expect(t).toContain("tidak ada listrik terbuang yang menonjol");
    expect(t).not.toContain("Terbuang:");
  });

  it("sambutan, terputus, dan rapor akhir", () => {
    const s = pesanSambutan({ namaUsaha: "UMKM Contoh D", masaUkur: { mulai: "2026-11-14", selesaiRencana: "2026-12-04" } });
    expect(s).toContain("14 Nov 2026 sampai 4 Des 2026");
    expect(s).toContain("[NOMOR TEKNISI]");
    const t = pesanTerputus({ namaUsaha: "UMKM Contoh B", terakhirData: "2026-11-14T10:00:00+07:00", nomorTeknisi: "0812-0000-0000" });
    expect(t).toContain("14 Nov 2026, 10.00");
    expect(t).toContain("0812-0000-0000");
    const r = pesanRaporAkhir({
      namaUsaha: "UMKM Contoh C",
      periode: { dari: "2026-10-13", sampai: "2026-11-02" },
      hariLengkap: 20,
      kategori: "belum_bisa_dihitung",
      rekomendasiKWp: 5,
      tautanRapor: "/rapor/umkm-c",
    });
    expect(r).toContain("BELUM BISA DIHITUNG");
    expect(r).toContain("5 kWp");
  });
});
