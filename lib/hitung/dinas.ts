import type { Alat, KategoriRapor, Lokasi, Rapor, StatusLokasi } from "../tipe";

export type BarisUMKM = {
  lokasiId: string;
  nama: string;
  sentra: string;
  sektor: string;
  status: StatusLokasi;
  kategori: KategoriRapor | null;
  rekomendasiKWp: number | null;
  pemborosanKWhBulan: number | null;
  pemborosanRupiahBulan: number | null;
  izinRincian: boolean;
  adaRapor: boolean;
};

const MINGGU_PER_BULAN = 30 / 7;

export function barisUMKM(lokasi: Lokasi[], rapor: Map<string, Rapor>): BarisUMKM[] {
  return lokasi.map((l) => {
    const r = rapor.get(l.id) ?? null;
    const kWh = r ? r.pemborosan.reduce((a, b) => a + b.kWhPerMinggu, 0) * MINGGU_PER_BULAN : null;
    let rupiah: number | null = null;
    if (r && r.pemborosan.every((b) => b.rupiahPerMinggu !== null)) {
      rupiah = r.pemborosan.reduce((a, b) => a + (b.rupiahPerMinggu ?? 0), 0) * MINGGU_PER_BULAN;
    }
    return {
      lokasiId: l.id,
      nama: l.nama,
      sentra: l.sentra,
      sektor: l.sektor,
      status: l.status,
      kategori: r?.kategori ?? null,
      rekomendasiKWp: r?.rekomendasiKWp ?? null,
      pemborosanKWhBulan: kWh,
      pemborosanRupiahBulan: rupiah,
      izinRincian: l.izinRincian,
      adaRapor: r !== null,
    };
  });
}

export function ringkasanProgram(lokasi: Lokasi[], alat: Alat[], rapor: Map<string, Rapor>) {
  const perKategori: Record<KategoriRapor, number> = {
    layak: 0,
    efisiensi_dulu: 0,
    belum_layak: 0,
    belum_bisa_dihitung: 0,
  };
  for (const r of rapor.values()) perKategori[r.kategori]++;
  return {
    jumlahAlat: alat.length,
    alatTerpasang: alat.filter((a) => a.lokasiId !== null).length,
    alatOffline: alat.filter((a) => a.status === "offline").length,
    jumlahUMKM: lokasi.length,
    selesaiDiukur: lokasi.filter((l) => ["rapor_siap", "plts_terpasang", "verifikasi"].includes(l.status)).length,
    jumlahRapor: rapor.size,
    perKategori,
  };
}

export type BarisSentra = {
  sentra: string;
  jumlahUMKM: number;
  layakPLTS: number;
  pemborosanKWhBulan: number;
  /** null bila ada UMKM di sentra ini yang rupiahnya belum bisa dihitung */
  pemborosanRupiahBulan: number | null;
};

export function perSentra(baris: BarisUMKM[]): BarisSentra[] {
  const peta = new Map<string, BarisSentra>();
  for (const b of baris) {
    const s = peta.get(b.sentra) ?? {
      sentra: b.sentra,
      jumlahUMKM: 0,
      layakPLTS: 0,
      pemborosanKWhBulan: 0,
      pemborosanRupiahBulan: 0,
    };
    s.jumlahUMKM++;
    if (b.kategori === "layak") s.layakPLTS++;
    if (b.adaRapor) {
      s.pemborosanKWhBulan += b.pemborosanKWhBulan ?? 0;
      s.pemborosanRupiahBulan =
        s.pemborosanRupiahBulan === null || b.pemborosanRupiahBulan === null
          ? null
          : s.pemborosanRupiahBulan + b.pemborosanRupiahBulan;
    }
    peta.set(b.sentra, s);
  }
  return [...peta.values()].sort((a, b) => b.pemborosanKWhBulan - a.pemborosanKWhBulan);
}

export type KolomUrut = "nama" | "sentra" | "status" | "kategori" | "rekomendasiKWp" | "pemborosanKWhBulan";
export type FilterUMKM = { status?: StatusLokasi | null; kategori?: KategoriRapor | null };

/** Filter lalu urutkan. Nilai kosong selalu di bawah, apa pun arah urutannya. */
export function saringDanUrutkan(
  baris: BarisUMKM[],
  filter: FilterUMKM,
  urut: { kolom: KolomUrut; arah: "naik" | "turun" },
): BarisUMKM[] {
  const tersaring = baris.filter(
    (b) => (!filter.status || b.status === filter.status) && (!filter.kategori || b.kategori === filter.kategori),
  );
  const tanda = urut.arah === "naik" ? 1 : -1;
  return [...tersaring].sort((a, b) => {
    const x = a[urut.kolom];
    const y = b[urut.kolom];
    if (x === null && y === null) return 0;
    if (x === null) return 1;
    if (y === null) return -1;
    if (typeof x === "number" && typeof y === "number") return (x - y) * tanda;
    return String(x).localeCompare(String(y), "id") * tanda;
  });
}

export type JadwalAlat = {
  alatId: string;
  status: Alat["status"];
  lokasiId: string | null;
  namaLokasi: string | null;
  rencanaCabut: string | null;
};

/** Urut dari yang paling cepat bebas; alat di gudang (sudah bebas) di atas. */
export function jadwalAlat(alat: Alat[], lokasi: Lokasi[]): JadwalAlat[] {
  const petaLokasi = new Map(lokasi.map((l) => [l.id, l]));
  return alat
    .map((a) => {
      const l = a.lokasiId ? petaLokasi.get(a.lokasiId) : undefined;
      return {
        alatId: a.id,
        status: a.status,
        lokasiId: a.lokasiId,
        namaLokasi: l?.nama ?? null,
        rencanaCabut: l?.masaUkur?.selesaiRencana ?? null,
      };
    })
    .sort((a, b) => {
      if (a.rencanaCabut === b.rencanaCabut) return a.alatId.localeCompare(b.alatId);
      if (a.rencanaCabut === null) return -1;
      if (b.rencanaCabut === null) return 1;
      return a.rencanaCabut.localeCompare(b.rencanaCabut);
    });
}
