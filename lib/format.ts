import type { JamMenit, Tanggal } from "./tipe";
import { pecahWaktu } from "./waktu";

export const PLACEHOLDER_TARIF = "[TARIF PLN]";
export const PLACEHOLDER_HARGA = "[HARGA INSTALLER]";

const angkaBulat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

/** "Rp 125.000". Nilai null menghasilkan placeholder, bukan angka tebakan. */
export function formatRupiah(nilai: number | null, placeholder = PLACEHOLDER_TARIF): string {
  if (nilai === null || !Number.isFinite(nilai)) return placeholder;
  const bulat = Math.round(nilai);
  const tanda = bulat < 0 ? "-" : "";
  return `${tanda}Rp ${angkaBulat.format(Math.abs(bulat))}`;
}

export function formatAngka(nilai: number, desimal = 1): string {
  return new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: desimal,
    maximumFractionDigits: desimal,
  }).format(nilai);
}

/** "2,4 kWh" */
export function formatKWh(nilai: number, desimal = 1): string {
  return `${formatAngka(nilai, desimal)} kWh`;
}

/** "2 kWp", "1,5 kWp" */
export function formatKWp(nilai: number | null): string {
  if (nilai === null) return "-";
  return `${formatAngka(nilai, Number.isInteger(nilai) ? 0 : 1)} kWp`;
}

export function formatPersen(rasio: number): string {
  return `${formatAngka(rasio * 100, 0)}%`;
}

/** "14 Nov 2026". Ditulis manual agar tidak bergantung data locale ICU di runtime. */
export function formatTanggal(tanggal: Tanggal): string {
  const [t, b, h] = tanggal.split("-").map(Number);
  return `${h} ${BULAN[b - 1]} ${t}`;
}

/** "08.00" sesuai kebiasaan penulisan jam di Indonesia. */
export function formatJam(jm: JamMenit | number): string {
  if (typeof jm === "number") return `${String(jm).padStart(2, "0")}.00`;
  return jm.replace(":", ".");
}

/** "14 Nov 2026, 15.20" */
export function formatWaktu(waktu: string): string {
  const { tanggal, jam, menit } = pecahWaktu(waktu);
  return `${formatTanggal(tanggal)}, ${String(jam).padStart(2, "0")}.${String(menit).padStart(2, "0")}`;
}

export function formatTahun(nilai: number | null): string {
  if (nilai === null || !Number.isFinite(nilai)) return "-";
  return `${formatAngka(nilai, 1)} tahun`;
}
