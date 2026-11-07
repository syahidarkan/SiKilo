import type { JamMenit, JenisPemborosan, Lokasi, Mesin, PemakaianJam, Pemborosan } from "../tipe";
import { formatJam } from "../format";
import { dalamJendela, hariDalamMinggu, pecahWaktu } from "../waktu";
import type { Parameter } from "./parameter";
import { kWhKeRupiah } from "./rupiah";

const JAM_MALAM = { mulai: "22:00", selesai: "05:00" } as const;
/** Satu jam dianggap "menyala" bila energinya di atas porsi ini dari rata-rata jam kerjanya. */
const RASIO_NYALA = 0.25;
/** Temuan di bawah ini tidak ditampilkan karena tidak sebanding dengan perhatian pemilik. */
const MIN_KWH_PER_MINGGU = 0.5;

type Jendela = { mulai: JamMenit; selesai: JamMenit };
type Slot = { tanggal: string; jam: number; kWh: number; keyakinan: number };

function adalahHariKerja(lokasi: Lokasi, tanggal: string) {
  return !lokasi.jamKerja.hariLibur.includes(hariDalamMinggu(tanggal));
}

function dalamJamKerja(lokasi: Lokasi, tanggal: string, jam: number) {
  return adalahHariKerja(lokasi, tanggal) && dalamJendela(jam, lokasi.jamKerja.mulai, lokasi.jamKerja.selesai);
}

function dalamIstirahat(lokasi: Lokasi, jam: number) {
  const ist = lokasi.jamKerja.istirahat;
  return ist !== null && dalamJendela(jam, ist.mulai, ist.selesai);
}

/** Rentang terpendek di jam melingkar yang mencakup semua jam, agar 22.00-02.00 tidak terbaca 00.00-24.00. */
export function jendelaDariJam(jam: number[]): Jendela {
  const urut = [...new Set(jam)].sort((a, b) => a - b);
  let celahTerbesar = -1;
  let idxMulai = 0;
  for (let i = 0; i < urut.length; i++) {
    const berikut = i + 1 < urut.length ? urut[i + 1] : urut[0] + 24;
    const celah = berikut - urut[i];
    if (celah > celahTerbesar) {
      celahTerbesar = celah;
      idxMulai = (i + 1) % urut.length;
    }
  }
  const mulai = urut[idxMulai];
  const akhir = urut[(idxMulai - 1 + urut.length) % urut.length];
  const jj = (j: number) => `${String(j % 24).padStart(2, "0")}:00`;
  return { mulai: jj(mulai), selesai: jj(akhir + 1) };
}

function saranUntuk(jenis: JenisPemborosan, nama: string, j: Jendela): string {
  const rentang = `${formatJam(j.mulai)}-${formatJam(j.selesai)}`;
  switch (jenis) {
    case "panas_menganggur":
      return `Matikan ${nama} saat istirahat ${rentang}, nyalakan lagi 10 menit sebelum kerja.`;
    case "nyala_luar_jam_kerja":
      return `Pastikan ${nama} dimatikan saat tutup. Tercatat masih menyala ${rentang}.`;
    case "beban_malam_tinggi":
      return `Cek ${nama} sebelum pulang. Tercatat menyala malam hari ${rentang}.`;
  }
}

/**
 * Deteksi berbasis aturan atas hasil pemisahan beban per mesin.
 * Hanya pemanas yang bisa "panas menganggur", dan pendingin dikecualikan dari
 * deteksi luar jam kerja karena memang harus menyala terus.
 */
export function deteksiPemborosan(
  lokasi: Lokasi,
  mesin: Mesin[],
  pemakaian: PemakaianJam[],
  p: Parameter,
): Pemborosan[] {
  const semuaTanggal = new Set<string>();
  const perMesin = new Map<string, Slot[]>();
  for (const r of pemakaian) {
    const { tanggal, jam } = pecahWaktu(r.jam);
    semuaTanggal.add(tanggal);
    if (r.mesinId === "lainnya") continue;
    const daftar = perMesin.get(r.mesinId) ?? [];
    daftar.push({ tanggal, jam, kWh: r.kWh, keyakinan: r.keyakinan });
    perMesin.set(r.mesinId, daftar);
  }
  const hariDiamati = semuaTanggal.size;
  const hariKerjaDiamati = [...semuaTanggal].filter((t) => adalahHariKerja(lokasi, t)).length;
  if (hariDiamati === 0) return [];

  const hasil: Pemborosan[] = [];
  for (const m of mesin) {
    const slot = perMesin.get(m.id);
    if (!slot || slot.length === 0 || m.jenis === "pendingin") continue;

    const kerja = slot.filter((s) => dalamJamKerja(lokasi, s.tanggal, s.jam) && !dalamIstirahat(lokasi, s.jam));
    const rataKerja = kerja.length ? kerja.reduce((a, s) => a + s.kWh, 0) / kerja.length : 0;
    if (rataKerja <= 0) continue;
    const ambangNyala = rataKerja * RASIO_NYALA;
    const keyakinan = slot.reduce((a, s) => a + s.keyakinan, 0) / slot.length;

    const kandidat: Record<JenisPemborosan, Slot[]> = {
      panas_menganggur: [],
      nyala_luar_jam_kerja: [],
      beban_malam_tinggi: [],
    };
    for (const s of slot) {
      if (s.kWh <= ambangNyala) continue;
      if (dalamJendela(s.jam, JAM_MALAM.mulai, JAM_MALAM.selesai)) {
        kandidat.beban_malam_tinggi.push(s);
      } else if (!dalamJamKerja(lokasi, s.tanggal, s.jam)) {
        kandidat.nyala_luar_jam_kerja.push(s);
      } else if (m.jenis === "pemanas" && dalamIstirahat(lokasi, s.jam)) {
        kandidat.panas_menganggur.push(s);
      }
    }

    for (const jenis of Object.keys(kandidat) as JenisPemborosan[]) {
      const daftar = kandidat[jenis];
      if (daftar.length === 0) continue;
      const kWhTotal = daftar.reduce((a, s) => a + s.kWh, 0);
      const kWhPerMinggu = (kWhTotal / hariDiamati) * 7;
      if (kWhPerMinggu < MIN_KWH_PER_MINGGU) continue;
      const jendela = jendelaDariJam(daftar.map((s) => s.jam));
      hasil.push({
        id: `${m.id}-${jenis}`,
        lokasiId: lokasi.id,
        mesinId: m.id,
        jenis,
        kWhPerMinggu,
        rupiahPerMinggu: kWhKeRupiah(kWhPerMinggu, p.tarifPerKWh),
        saran: saranUntuk(jenis, m.nama.toLowerCase(), jendela),
        jendela,
        hariTerjadi: new Set(daftar.map((s) => s.tanggal)).size,
        hariDiamati: jenis === "panas_menganggur" ? hariKerjaDiamati : hariDiamati,
        keyakinan,
      });
    }
  }
  // Urutkan dari kWh (setara rupiah, karena tarif sama) terbesar
  return hasil.sort((a, b) => b.kWhPerMinggu - a.kWhPerMinggu);
}
