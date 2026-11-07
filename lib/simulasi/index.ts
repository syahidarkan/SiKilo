import { skenarioKonveksi } from "./skenario-konveksi";
import { skenarioKosong } from "./skenario-kosong";
import { SumberSimulasi, type OpsiSimulasi } from "./sumber-simulasi";

export const SKENARIO = { konveksi: skenarioKonveksi, kosong: skenarioKosong } as const;
export type IdSkenario = keyof typeof SKENARIO;

export function buatSumberSimulasi(skenario: IdSkenario = "konveksi", opsi?: OpsiSimulasi): SumberSimulasi {
  return new SumberSimulasi(SKENARIO[skenario], opsi);
}

export { SumberSimulasi, MASA_UKUR_HARI } from "./sumber-simulasi";
export type { OpsiSimulasi, SnapshotSesi } from "./sumber-simulasi";
