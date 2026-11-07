/**
 * Jembatan landing page ↔ backend WASKITA (FastAPI).
 *
 * Alamat backend diatur lewat NEXT_PUBLIC_WASKITA_API_URL (lihat .env.example);
 * default http://localhost:8000 untuk pengembangan lokal.
 */
export const WASKITA_API_URL = (process.env.NEXT_PUBLIC_WASKITA_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

/** Dasbor web (SPA) yang disajikan backend. */
export const DASHBOARD_URL = `${WASKITA_API_URL}/`;
export const REGISTER_URL = `${WASKITA_API_URL}/#daftar`;

export type MachineKey = 'setrika_uap' | 'kompresor_angin' | 'oven_pemanas' | 'mesin_cuci_dryer';

export interface EstimatePoint {
  kwp: number;
  habit_savings_idr_per_month: number;
  agent_savings_idr_per_month: number;
}

export interface Estimate {
  connected_power_va: number;
  machines: MachineKey[];
  recommended_kwp: number | null;
  kwp_without_agent: number | null;
  kwp_reduction_pct: number | null;
  monthly_bill_now_idr: number;
  monthly_savings_idr: number;
  savings_pct: number;
  capex_idr: number;
  payback_years: number | null;
  target_savings_pct: number;
  target_reached: boolean;
  tariff_idr_per_kwh: number;
  tariff_group: string;
  pv_source: string;
  headline: string;
  curve: EstimatePoint[];
  assumptions: string[];
  compute_time_s: number;
}

/** Minta estimasi ukuran PLTS dari tiruan digital WASKITA (tanpa login). */
export async function fetchEstimate(
  connectedPowerVa: number,
  machines: MachineKey[],
  signal?: AbortSignal,
): Promise<Estimate> {
  const res = await fetch(`${WASKITA_API_URL}/api/v1/public/estimate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ connected_power_va: connectedPowerVa, machines }),
    signal,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (typeof j?.detail === 'string') detail = j.detail;
    } catch {
      /* abaikan */
    }
    throw new Error(detail);
  }
  return (await res.json()) as Estimate;
}
