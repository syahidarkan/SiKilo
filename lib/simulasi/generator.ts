import type { Lokasi, PemakaianJam, Tanggal, TotalJam } from "../tipe";
import { dalamJendela, hariDalamMinggu, jamMenitKeJam, keWaktuISO, pecahWaktu, rentangTanggal } from "../waktu";
import { hashTeks, mulberry32 } from "./prng";
import type { Skenario } from "./skenario";

export type DataLokasi = { total: TotalJam[]; pemakaian: PemakaianJam[] };

const bulat3 = (v: number) => Math.round(v * 1000) / 1000;

/** Akhir data: akhir masa ukur, atau jam acuan simulasi bila masa ukur masih berjalan. */
export function batasData(lokasi: Lokasi, waktuAcuan: string): { sampai: Tanggal; jamTerakhirEksklusif: number } | null {
  if (!lokasi.masaUkur || lokasi.status === "menunggu_pasang") return null;
  const acuan = pecahWaktu(waktuAcuan);
  if (lokasi.masaUkur.selesaiRencana < acuan.tanggal) return { sampai: lokasi.masaUkur.selesaiRencana, jamTerakhirEksklusif: 24 };
  return { sampai: acuan.tanggal, jamTerakhirEksklusif: acuan.jam };
}

/**
 * Bangkitkan pemakaian per jam per mesin plus total meteran untuk satu lokasi.
 * Deterministik: seed diturunkan dari seed skenario dan id lokasi.
 */
export function bangkitkanDataLokasi(sk: Skenario, lokasi: Lokasi): DataLokasi {
  const batas = batasData(lokasi, sk.waktuAcuan);
  if (!batas || !lokasi.masaUkur) return { total: [], pemakaian: [] };

  const rng = mulberry32(sk.seed ^ hashTeks(lokasi.id));
  const acak = (variasi: number) => 1 + (rng() * 2 - 1) * variasi;
  const mesin = sk.mesin.filter((m) => m.lokasiId === lokasi.id && sk.profilMesin[m.id]);
  const lain = sk.bebanLainnya[lokasi.id] ?? { dasarKW: 0, rasioSaatKerja: 0 };
  const { jamKerja } = lokasi;
  const jamMulaiKerja = Math.floor(jamMenitKeJam(jamKerja.mulai));

  const total: TotalJam[] = [];
  const pemakaian: PemakaianJam[] = [];

  for (const tanggal of rentangTanggal(lokasi.masaUkur.mulai, batas.sampai)) {
    const hariKerja = !jamKerja.hariLibur.includes(hariDalamMinggu(tanggal));
    const terjadi = new Map<string, boolean>();
    for (const m of mesin) {
      (sk.profilMesin[m.id].tanam ?? []).forEach((t, i) => {
        const bisa = t.saat === "malam" || hariKerja;
        terjadi.set(`${m.id}#${i}`, bisa && rng() < t.peluangHari);
      });
    }
    const jamAkhir = tanggal === batas.sampai ? batas.jamTerakhirEksklusif : 24;

    for (let jam = 0; jam < jamAkhir; jam++) {
      const bolong = sk.bolong.some(
        (b) => b.lokasiId === lokasi.id && b.tanggal === tanggal && jam >= b.jamMulai && jam < b.jamMulai + b.jumlahJam,
      );
      const istirahat = jamKerja.istirahat !== null && dalamJendela(jam, jamKerja.istirahat.mulai, jamKerja.istirahat.selesai);
      const kerja = hariKerja && dalamJendela(jam, jamKerja.mulai, jamKerja.selesai) && !istirahat;
      const waktu = keWaktuISO(tanggal, jam);

      let jumlahMesin = 0;
      const barisJam: PemakaianJam[] = [];
      for (const m of mesin) {
        const pr = sk.profilMesin[m.id];
        let kW = 0;
        if (kerja) kW = pr.kWKerja * (jam === jamMulaiKerja ? 0.7 : 1) * acak(pr.variasi);
        // SIMULASI: sebagian kecil pekerja tetap bekerja saat istirahat
        else if (hariKerja && istirahat) kW = pr.kWKerja * 0.05 * acak(0.5);
        if (pr.kWSiaga) kW = Math.max(kW, pr.kWSiaga * acak(pr.variasi));
        (pr.tanam ?? []).forEach((t, i) => {
          if (terjadi.get(`${m.id}#${i}`) && dalamJendela(jam, t.mulai, t.selesai)) kW += t.kW * acak(0.1);
        });
        const keyakinan = Math.min(1, Math.max(0, pr.keyakinan + (rng() * 2 - 1) * 0.05));
        jumlahMesin += kW;
        barisJam.push({ lokasiId: lokasi.id, mesinId: m.id, jam: waktu, kWh: bulat3(kW), keyakinan: bulat3(keyakinan) });
      }
      const kWLainnya = lain.dasarKW * acak(0.2) + lain.rasioSaatKerja * jumlahMesin;
      // rng tetap dipanggil walau jam bolong, supaya pola hari lain tidak bergeser
      if (bolong) continue;
      pemakaian.push(...barisJam, { lokasiId: lokasi.id, mesinId: "lainnya", jam: waktu, kWh: bulat3(kWLainnya), keyakinan: 0 });
      total.push({
        lokasiId: lokasi.id,
        jam: waktu,
        kWh: bulat3(barisJam.reduce((a, r) => a + r.kWh, 0) + bulat3(kWLainnya)),
      });
    }
  }
  return { total, pemakaian };
}
