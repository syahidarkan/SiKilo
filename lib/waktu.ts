import type { JamMenit, Tanggal, WaktuISO } from "./tipe";

// Semua waktu diproses sebagai WIB tetap (+07:00) lewat aritmetika UTC,
// supaya hasil tidak bergantung zona waktu mesin build, server, atau browser.
const OFFSET_WIB_MS = 7 * 3600_000;

export function keWaktuISO(tanggal: Tanggal, jam: number): WaktuISO {
  return `${tanggal}T${String(jam).padStart(2, "0")}:00:00+07:00`;
}

/** Pecah waktu ISO ber-offset apa pun menjadi tanggal dan jam WIB. */
export function pecahWaktu(waktu: WaktuISO): { tanggal: Tanggal; jam: number; menit: number } {
  const ms = Date.parse(waktu);
  if (Number.isNaN(ms)) throw new Error(`Waktu tidak valid: ${waktu}`);
  const wib = new Date(ms + OFFSET_WIB_MS);
  return {
    tanggal: wib.toISOString().slice(0, 10),
    jam: wib.getUTCHours(),
    menit: wib.getUTCMinutes(),
  };
}

/** 0 = Minggu ... 6 = Sabtu */
export function hariDalamMinggu(tanggal: Tanggal): number {
  return new Date(`${tanggal}T00:00:00Z`).getUTCDay();
}

export function tambahHari(tanggal: Tanggal, n: number): Tanggal {
  const d = new Date(`${tanggal}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Jumlah hari dari a ke b (b - a). */
export function selisihHari(a: Tanggal, b: Tanggal): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

export function rentangTanggal(mulai: Tanggal, sampaiInklusif: Tanggal): Tanggal[] {
  const n = selisihHari(mulai, sampaiInklusif);
  return Array.from({ length: Math.max(0, n + 1) }, (_, i) => tambahHari(mulai, i));
}

export function jamMenitKeJam(jm: JamMenit): number {
  const [j, m] = jm.split(":").map(Number);
  return j + m / 60;
}

/** Apakah jam (awal slot satu jam) berada di [mulai, selesai). */
export function dalamJendela(jam: number, mulai: JamMenit, selesai: JamMenit): boolean {
  const a = jamMenitKeJam(mulai);
  const b = jamMenitKeJam(selesai);
  return a <= b ? jam >= a && jam < b : jam >= a || jam < b;
}
