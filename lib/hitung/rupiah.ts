/** Energi x tarif. null bila tarif belum diisi. */
export function kWhKeRupiah(kWh: number, tarifPerKWh: number | null): number | null {
  if (tarifPerKWh === null) return null;
  return kWh * tarifPerKWh;
}

export function biayaPasang(kWp: number, hargaPerKWp: number | null): number | null {
  if (hargaPerKWp === null) return null;
  return kWp * hargaPerKWp;
}

/** null bila salah satu masukan kosong atau tidak ada penghematan (tidak akan pernah balik modal). */
export function balikModalTahun(biaya: number | null, hematPerTahun: number | null): number | null {
  if (biaya === null || hematPerTahun === null || hematPerTahun <= 0) return null;
  return biaya / hematPerTahun;
}
