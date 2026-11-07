import { describe, expect, it } from "vitest";
import { buatParameter } from "@/lib/hitung/parameter";
import {
  batasKWp,
  daftarSkenario,
  hitungEnergi,
  hitungSkenario,
  kurvaProduksiPerKWp,
  pilihRekomendasi,
  rasioTerbuang,
  rataPerJam,
} from "@/lib/hitung/plts";

const nol = () => new Array(24).fill(0);
const datar = (v: number) => new Array(24).fill(v);

describe("kurvaProduksiPerKWp", () => {
  it("jumlah harian sama dengan yield dan nol di luar 06.00-18.00", () => {
    const k = kurvaProduksiPerKWp(4);
    expect(k).toHaveLength(24);
    expect(k.reduce((a, b) => a + b, 0)).toBeCloseTo(4, 10);
    for (const j of [0, 5, 18, 23]) expect(k[j]).toBe(0);
    expect(Math.max(...k)).toBe(Math.max(k[11], k[12]));
  });
});

describe("hitungEnergi", () => {
  it("beban nol: semua produksi terbuang", () => {
    const p = kurvaProduksiPerKWp(4);
    expect(hitungEnergi(nol(), p)).toEqual({ terpakai: 0, terbuang: expect.closeTo(4, 10) });
  });

  it("produksi melebihi beban: kelebihan dihitung terbuang", () => {
    expect(hitungEnergi([1, 2, 0.5], [3, 1, 0.5])).toEqual({ terpakai: 2.5, terbuang: 2 });
  });

  it("beban selalu di atas produksi: tidak ada yang terbuang", () => {
    const p = kurvaProduksiPerKWp(4);
    const e = hitungEnergi(datar(10), p);
    expect(e.terbuang).toBe(0);
    expect(e.terpakai).toBeCloseTo(4, 10);
  });

  it("nilai negatif dari sensor diperlakukan nol", () => {
    expect(hitungEnergi([-1], [2])).toEqual({ terpakai: 0, terbuang: 2 });
  });

  it("menolak panjang deret yang berbeda", () => {
    expect(() => hitungEnergi([1, 2], [1])).toThrow(/berbeda/);
  });
});

describe("hitungSkenario", () => {
  it("tarif dan harga kosong: rupiah dan balik modal null, kWh tetap terhitung", () => {
    const s = hitungSkenario([datar(10)], 2, buatParameter());
    expect(s.hematRupiahTahun).toBeNull();
    expect(s.biayaRupiah).toBeNull();
    expect(s.balikModalTahun).toBeNull();
    expect(s.terpakaiSendiri_kWh_tahun).toBeCloseTo(2 * 4 * 365, 6);
  });

  it("tarif terisi tapi harga kosong: hemat ada, biaya dan balik modal null", () => {
    const s = hitungSkenario([datar(10)], 1, buatParameter({ tarifPerKWh: 1000 }));
    expect(s.hematRupiahTahun).toBeCloseTo(4 * 365 * 1000, 4);
    expect(s.biayaRupiah).toBeNull();
    expect(s.balikModalTahun).toBeNull();
  });

  it("menghitung hemat dan balik modal dari energi terpakai sendiri", () => {
    const p = buatParameter({ tarifPerKWh: 1000, hargaPerKWp: 10_000_000 });
    const s = hitungSkenario([datar(10), datar(10)], 2, p);
    const hemat = 2 * 4 * 365 * 1000;
    expect(s.hematRupiahTahun).toBeCloseTo(hemat, 4);
    expect(s.biayaRupiah).toBe(20_000_000);
    expect(s.balikModalTahun).toBeCloseTo(20_000_000 / hemat, 8);
  });

  it("beban nol: hemat nol sehingga balik modal null, bukan tak hingga", () => {
    const p = buatParameter({ tarifPerKWh: 1000, hargaPerKWp: 10_000_000 });
    const s = hitungSkenario([nol()], 1, p);
    expect(s.hematRupiahTahun).toBe(0);
    expect(s.balikModalTahun).toBeNull();
    expect(s.terbuang_kWh_tahun).toBeCloseTo(4 * 365, 6);
  });

  it("diperpanjang ke setahun dengan faktor 365 / jumlah hari", () => {
    const sehari = hitungSkenario([datar(10)], 1, buatParameter());
    const duaHariSatuLibur = hitungSkenario([datar(10), nol()], 1, buatParameter());
    expect(duaHariSatuLibur.terpakaiSendiri_kWh_tahun).toBeCloseTo(sehari.terpakaiSendiri_kWh_tahun / 2, 6);
    expect(duaHariSatuLibur.terbuang_kWh_tahun).toBeCloseTo((4 * 365) / 2, 6);
  });

  it("menolak profil kosong atau profil yang bukan 24 jam", () => {
    expect(() => hitungSkenario([], 1, buatParameter())).toThrow(/kosong/);
    expect(() => hitungSkenario([[1, 2]], 1, buatParameter())).toThrow(/24/);
  });
});

describe("daftarSkenario dan rekomendasi", () => {
  // Beban siang 1 kW: panel kecil terpakai habis, panel besar banyak terbuang
  const siang = Array.from({ length: 24 }, (_, j) => (j >= 8 && j < 16 ? 1 : 0.1));

  it("membuat skenario dari langkah sampai batas kWp", () => {
    const s = daftarSkenario([siang], 5.5, buatParameter());
    expect(s.map((x) => x.kWp)).toEqual([1, 2, 3, 4, 5]);
  });

  it("terbuang naik seiring ukuran panel", () => {
    const s = daftarSkenario([siang], 5, buatParameter());
    const rasio = s.map(rasioTerbuang);
    for (let i = 1; i < rasio.length; i++) expect(rasio[i]).toBeGreaterThan(rasio[i - 1]);
  });

  it("memilih kWp terbesar yang terbuangnya tidak melewati ambang", () => {
    const s = daftarSkenario([siang], 5, buatParameter());
    const r = pilihRekomendasi(s, 0.2);
    expect(r).not.toBeNull();
    expect(rasioTerbuang(r!)).toBeLessThanOrEqual(0.2);
    const lebihBesar = s.find((x) => x.kWp === r!.kWp + 1);
    if (lebihBesar) expect(rasioTerbuang(lebihBesar)).toBeGreaterThan(0.2);
  });

  it("beban nol: tidak ada rekomendasi", () => {
    expect(pilihRekomendasi(daftarSkenario([nol()], 3, buatParameter()), 0.2)).toBeNull();
  });

  it("batas kWp mengikuti daya tersambung", () => {
    expect(batasKWp(5500)).toBe(5.5);
  });

  it("rata-rata per jam", () => {
    expect(rataPerJam([datar(2), datar(4)])).toEqual(datar(3));
    expect(rataPerJam([])).toEqual(nol());
  });
});
