import { describe, expect, it } from "vitest";
import { barisUMKM, jadwalAlat, perSentra, ringkasanProgram, saringDanUrutkan } from "@/lib/hitung/dinas";
import { biayaPeriode, heatmapMingguan, kelengkapanData, kelompokkanPerHari, posisiMasaUkur, rincianPerMesin } from "@/lib/hitung/ringkasan";
import { buatSumberSimulasi } from "@/lib/simulasi";
import type { MasukanPasang } from "@/lib/sumber-data";

const pasangValid: MasukanPasang = {
  alatId: "nl-003",
  lokasiId: "umkm-d",
  checklist: { sisi_pelanggan: true, segel_pln: true, casing_tertutup: true, terminal: true },
  koneksi: "masuk",
  mesin: [
    { nama: "Mesin jahit", jenis: "motor", jumlah: 8, dikelompokkan: true },
    { nama: "Setrika uap", jenis: "pemanas", jumlah: 1, dikelompokkan: false },
  ],
  plug: [
    { plugId: "SP-1", mesinIndeks: 0 },
    { plugId: "SP-2", mesinIndeks: 1 },
  ],
};

describe("generator simulasi", () => {
  it("deterministik: dua instans menghasilkan data identik", async () => {
    const a = await buatSumberSimulasi().ambilPemakaianPerMesin("umkm-c");
    const b = await buatSumberSimulasi().ambilPemakaianPerMesin("umkm-c");
    expect(a.length).toBeGreaterThan(0);
    expect(a).toEqual(b);
  });

  it("total meteran sama dengan jumlah per mesin + lainnya", async () => {
    const s = buatSumberSimulasi();
    const total = await s.ambilTotalPerJam("umkm-b");
    const per = await s.ambilPemakaianPerMesin("umkm-b");
    const jumlah = (xs: { kWh: number }[]) => xs.reduce((a, r) => a + r.kWh, 0);
    expect(jumlah(total)).toBeCloseTo(jumlah(per), 6);
  });

  it("menyisakan energi 'lainnya' dan keyakinan per mesin di bawah 100%", async () => {
    const per = await buatSumberSimulasi().ambilPemakaianPerMesin("umkm-c");
    expect(per.some((r) => r.mesinId === "lainnya" && r.kWh > 0)).toBe(true);
    expect(Math.max(...per.filter((r) => r.mesinId !== "lainnya").map((r) => r.keyakinan))).toBeLessThan(1);
  });

  it("masa kalibrasi: total tersedia, per mesin dan pemborosan belum", async () => {
    const s = buatSumberSimulasi();
    expect((await s.ambilTotalPerJam("umkm-a")).length).toBeGreaterThan(0);
    expect(await s.ambilPemakaianPerMesin("umkm-a")).toEqual([]);
    expect(await s.ambilPemborosan("umkm-a")).toEqual([]);
  });

  it("pemborosan tertanam terdeteksi: setrika uap panas saat istirahat di UMKM Contoh B", async () => {
    const b = await buatSumberSimulasi().ambilPemborosan("umkm-b");
    expect(b[0]).toMatchObject({ mesinId: "umkm-b-setrika", jenis: "panas_menganggur" });
  });

  it("data berhenti di waktu acuan dan memuat jam bolong yang ditanam", async () => {
    const s = buatSumberSimulasi();
    const total = await s.ambilTotalPerJam("umkm-c");
    const k = kelengkapanData(kelompokkanPerHari(total, "2026-10-13", "2026-11-02"));
    expect(k).toMatchObject({ hariLengkap: 20, hariBolong: 1, tanggalBolong: ["2026-10-20"] });
    const totalB = await s.ambilTotalPerJam("umkm-b");
    expect(totalB.at(-1)!.jam).toBe("2026-11-14T14:00:00+07:00");
  });
});

describe("ringkasan pemilik", () => {
  it("rincian per mesin: porsi berjumlah 1 dan 'lainnya' di baris terakhir", async () => {
    const s = buatSumberSimulasi();
    const p = await s.ambilParameter();
    const r = rincianPerMesin(await s.ambilPemakaianPerMesin("umkm-b"), await s.daftarMesin("umkm-b"), p);
    expect(r.at(-1)!.mesinId).toBe("lainnya");
    expect(r.reduce((a, x) => a + x.porsi, 0)).toBeCloseTo(1, 9);
    expect(r.find((x) => x.mesinId === "umkm-b-obras")!.keyakinanRendah).toBe(true);
    expect(r.every((x) => x.rupiah === null)).toBe(true);
  });

  it("biaya periode tanpa tarif: kWh ada, rupiah null", async () => {
    const s = buatSumberSimulasi();
    const b = biayaPeriode(await s.ambilTotalPerJam("umkm-b"), "2026-11-08", "2026-11-14", await s.ambilParameter());
    expect(b.kWh).toBeGreaterThan(0);
    expect(b.rupiah).toBeNull();
  });

  it("heatmap 7 x 24 dan posisi masa ukur", async () => {
    const s = buatSumberSimulasi();
    const h = heatmapMingguan(await s.ambilTotalPerJam("umkm-b"));
    expect(h.baris).toHaveLength(7);
    expect(h.baris.every((r) => r.length === 24)).toBe(true);
    expect(h.maks).toBeGreaterThan(0);
    const l = (await s.ambilLokasi("umkm-b"))!;
    expect(posisiMasaUkur(l, "2026-11-14")).toEqual({ hariKe: 9, dari: 21 });
  });
});

describe("rapor", () => {
  it("UMKM Contoh C: tarif kosong sehingga belum bisa dihitung, rekomendasi kWp tetap ada", async () => {
    const r = (await buatSumberSimulasi().ambilRapor("umkm-c"))!;
    expect(r.kategori).toBe("belum_bisa_dihitung");
    expect(r.rekomendasiKWp).not.toBeNull();
    expect(r.skenario.every((x) => x.hematRupiahTahun === null && x.balikModalTahun === null)).toBe(true);
    expect(r.nomor).toBe("NL/RPR/202611/UMKM-C");
  });

  it("dengan tarif dan harga terisi kategori menjadi keputusan, bukan placeholder", async () => {
    const r = (await buatSumberSimulasi("konveksi", { parameter: { tarifPerKWh: 1, hargaPerKWp: 1 } }).ambilRapor("umkm-c"))!;
    expect(["layak", "belum_layak", "efisiensi_dulu"]).toContain(r.kategori);
    expect(r.skenario.every((x) => x.balikModalTahun !== null)).toBe(true);
  });

  it("rekomendasi kWp sensitif terhadap ambang terbuang (dicatat di lib/README.md)", async () => {
    expect((await buatSumberSimulasi().ambilRapor("umkm-c"))!.rekomendasiKWp).toBe(5);
    const ketat = buatSumberSimulasi("konveksi", { parameter: { ambangTerbuangRasio: 0.1 } });
    expect((await ketat.ambilRapor("umkm-c"))!.rekomendasiKWp).toBe(1);
  });

  it("lokasi yang belum selesai diukur tidak punya rapor", async () => {
    expect(await buatSumberSimulasi().ambilRapor("umkm-b")).toBeNull();
  });
});

describe("alur teknisi mengubah state sesi", () => {
  it("menolak pemasangan alat yang masih terpasang di lokasi lain", async () => {
    const h = await buatSumberSimulasi().pasangAlat({ ...pasangValid, alatId: "NL-001" });
    expect(h.ok).toBe(false);
  });

  it("pasang: alat online di lokasi baru, lokasi kalibrasi, belum ada data karangan", async () => {
    const s = buatSumberSimulasi();
    expect(await s.pasangAlat(pasangValid)).toEqual({ ok: true });
    const l = (await s.ambilLokasi("umkm-d"))!;
    expect(l.status).toBe("kalibrasi");
    expect(l.masaUkur).toEqual({ mulai: "2026-11-14", selesaiRencana: "2026-12-04" });
    expect((await s.daftarAlat()).find((a) => a.id === "NL-003")).toMatchObject({ lokasiId: "umkm-d", status: "online" });
    expect((await s.daftarMesin("umkm-d")).map((m) => m.nama)).toEqual(["Mesin jahit", "Setrika uap"]);
    expect(await s.ambilTotalPerJam("umkm-d")).toEqual([]);
    // alat yang sama tidak bisa dipasang dua kali
    expect((await s.pasangAlat({ ...pasangValid, lokasiId: "umkm-d" })).ok).toBe(false);
  });

  it("cabut: alat kembali ke gudang dan lokasi punya rapor", async () => {
    const s = buatSumberSimulasi();
    const konfirmasi = { masaCukup: true, plugDicabut: true, sensorDicabut: true };
    expect(await s.cabutAlat({ lokasiId: "umkm-b", ...konfirmasi })).toEqual({ ok: true });
    expect((await s.daftarAlat()).find((a) => a.id === "NL-002")).toMatchObject({ lokasiId: null, status: "di_gudang" });
    expect((await s.ambilLokasi("umkm-b"))!.status).toBe("rapor_siap");
    expect(await s.ambilRapor("umkm-b")).not.toBeNull();
    expect((await s.cabutAlat({ lokasiId: "umkm-b", ...konfirmasi })).ok).toBe(false);
  });

  it("cabut ditolak bila belum ada sehari pun data lengkap", async () => {
    const s = buatSumberSimulasi();
    await s.pasangAlat(pasangValid);
    const h = await s.cabutAlat({ lokasiId: "umkm-d", masaCukup: true, plugDicabut: true, sensorDicabut: true });
    expect(h.ok).toBe(false);
  });

  it("snapshot dan pulihkan mempertahankan perubahan antar-halaman", async () => {
    const s = buatSumberSimulasi();
    await s.pasangAlat(pasangValid);
    const s2 = buatSumberSimulasi();
    s2.pulihkan(JSON.parse(JSON.stringify(s.snapshot())));
    expect((await s2.ambilLokasi("umkm-d"))!.status).toBe("kalibrasi");
  });
});

describe("kontrol prototype", () => {
  it("mode gagal membuat panggilan ditolak, lalu pulih", async () => {
    const s = buatSumberSimulasi();
    s.aturGagal(true);
    await expect(s.daftarLokasi()).rejects.toThrow(/gagal dimuat/);
    s.aturGagal(false);
    await expect(s.daftarLokasi()).resolves.toHaveLength(4);
  });

  it("alat offline: data berhenti di jam terakhir terlihat", async () => {
    const s = buatSumberSimulasi();
    s.aturStatusAlat("NL-002", "offline", "2026-11-14T09:30:00+07:00");
    const t = await s.ambilTotalPerJam("umkm-b");
    expect(t.at(-1)!.jam).toBe("2026-11-14T08:00:00+07:00");
  });

  it("hasil tidak bisa mengubah state sumber", async () => {
    const s = buatSumberSimulasi();
    (await s.daftarLokasi())[0].nama = "diubah";
    expect((await s.daftarLokasi())[0].nama).toBe("UMKM Contoh A");
  });
});

describe("dashboard dinas", () => {
  it("ringkasan, per sentra, filter, urut, jadwal alat", async () => {
    const s = buatSumberSimulasi();
    const [lokasi, alat, rapor] = await Promise.all([s.daftarLokasi(), s.daftarAlat(), s.daftarRapor()]);
    const peta = new Map(rapor.map((r) => [r.lokasiId, r]));
    expect(ringkasanProgram(lokasi, alat, peta)).toMatchObject({
      jumlahAlat: 4,
      alatTerpasang: 2,
      selesaiDiukur: 1,
      jumlahRapor: 1,
      perKategori: { belum_bisa_dihitung: 1 },
    });
    const baris = barisUMKM(lokasi, peta);
    const c = baris.find((b) => b.lokasiId === "umkm-c")!;
    expect(c.pemborosanKWhBulan).toBeGreaterThan(0);
    expect(c.pemborosanRupiahBulan).toBeNull();
    const sentra = perSentra(baris);
    expect(sentra.map((x) => x.sentra)).toEqual(["Sentra Contoh 2", "Sentra Contoh 1"]);
    expect(saringDanUrutkan(baris, { status: "mengukur" }, { kolom: "nama", arah: "naik" }).map((b) => b.lokasiId)).toEqual(["umkm-b"]);
    const urutKWp = saringDanUrutkan(baris, {}, { kolom: "rekomendasiKWp", arah: "naik" });
    expect(urutKWp[0].lokasiId).toBe("umkm-c");
    expect(urutKWp.slice(1).every((b) => b.rekomendasiKWp === null)).toBe(true);
    expect(jadwalAlat(alat, lokasi).map((j) => j.alatId)).toEqual(["NL-003", "NL-004", "NL-002", "NL-001"]);
  });

  it("program baru: skenario kosong tanpa rapor", async () => {
    const s = buatSumberSimulasi("kosong");
    const [lokasi, alat, rapor] = await Promise.all([s.daftarLokasi(), s.daftarAlat(), s.daftarRapor()]);
    expect(ringkasanProgram(lokasi, alat, new Map(rapor.map((r) => [r.lokasiId, r])))).toMatchObject({
      jumlahAlat: 2,
      jumlahRapor: 0,
    });
  });
});
