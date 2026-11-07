# Agen penjadwal WASKITA (tahap "Atur")

Agen menyusun jadwal mesin UMKM untuk satu hari (96 slot × 15 menit) agar
tagihan PLN serendah mungkin **tanpa** melanggar jam kerja dan tenggat
pesanan, lalu membandingkannya secara jujur dengan **kebiasaan lama pemilik**.

> **Status jujur:** semua angka di bawah berasal dari **simulasi tiruan digital
> pada skenario sintetis** (mesin, pesanan, kWp, baterai acak berdasarkan
> asumsi). Belum ada validasi dengan tagihan/meteran UMKM nyata.

| File | Isi |
| --- | --- |
| `app/digital_twin/factory_model.py` | `FlexibleMachine` (jendela kerja, mask, forced-ON), `DispatchProblem`, `simulate_schedule`, `validate_schedule` |
| `app/agent/baseline.py` | `habit_schedule` (kebiasaan lama), beban idle, `greedy_schedule` |
| `app/agent/ortools_baseline.py` | MILP CP-SAT (OR-Tools) |
| `app/agent/umkm_env.py` | Env Gymnasium + `action_masks()` untuk MaskablePPO |
| `app/agent/behavior_cloning.py` | Demonstrasi + pretraining kebijakan |
| `app/agent/scenarios.py` | Generator skenario latih/uji (tanggal acak sepanjang tahun, OrderBook) |
| `app/agent/ppo_scheduler.py` | Pemuat model PPO (impor sb3 opsional), fallback greedy |
| `app/agent/planner.py` | `plan_day` (kontrak CONTRACTS.md §4) |
| `app/api/v1/endpoints_dispatch.py` | `POST /api/v1/dispatch/optimize`, `GET /api/v1/dispatch/default-jobs` |
| `scripts/train_agent.py` | Pelatihan BC → MaskablePPO + evaluasi → `models/agent_eval.json` |

## 1. Baseline = kebiasaan lama (bukan "semua mesin nyala 24 jam")

Tiap mesin mulai di `habit_start_hour` (default
`settings.default_habit_start_hour`) dan jalan terus sampai runtime terpenuhi.
Bila blok itu melewati jam kerja mesin (`earliest_hour`–`deadline_hour`), blok
**digeser masuk** ke jam kerja — runtime tetap utuh, sehingga baseline dan
agen mengerjakan pekerjaan yang sama persis.

`MachineJob.idle_minutes_habit` (opsional) = menit mesin dibiarkan menyala
tanpa beban dalam kebiasaan lama (mis. boiler tetap panas saat istirahat). Daya
idle = `idle_power_w` atau `settings.default_idle_power_frac × power_w`
(**asumsi 40 %, belum diukur**). Idle hanya ditambahkan ke baseline; agen tidak
menjadwalkan idle.

**Penghematan = biaya baseline − biaya agen**, keduanya disimulasikan dengan
PV, baterai (SoC awal sama), beban dasar, dan tarif yang SAMA
(`simulate_schedule`). Nilainya **boleh negatif** dan tidak dipotong ke nol.
Respons API memecahnya menjadi `savings_breakdown.idle_idr` (hemat karena idle
hilang) dan `savings_breakdown.shifting_idr` (hemat/rugi karena geser jadwal).

## 2. Tarif & dari mana penghematan berasal

Semua biaya memakai `app/core/tariff.py`. UMKM golongan B-1/B-2 bertarif
**flat** (Rp 1.444,70/kWh untuk B-2), jadi:

- **Tanpa PLTS/baterai**, menggeser jam mesin **tidak** mengubah biaya sama
  sekali. Satu-satunya penghematan adalah mengurangi mesin yang menyala tanpa
  beban (idle). Planner menulis catatan ini di `notes`.
- **Dengan PLTS**, nilai penjadwalan muncul dari memindahkan beban ke jam
  surplus PV (ekspor tidak dikreditkan — Permen ESDM 2/2024 — sehingga PV yang
  tidak terpakai hilang).
- **Dengan baterai**, surplus PV disimpan lalu dipakai saat defisit.
- Skema `tou` (WBP 17:00–22:00, hanya B-3/I-3 > 200 kVA) membuat pergeseran
  keluar jam puncak bernilai walau tanpa PV (diuji di `tests/test_planner.py`).

Catatan: bila PV kecil (tak pernah melebihi beban dasar), seluruh produksi PV
sudah terserap beban dasar dan menggeser mesin juga tidak menghemat apa pun.
Ini sering terjadi pada skenario uji (lihat §6).

## 3. Aturan jadwal (sama di env, OR-Tools, greedy, dan validasi)

Per mesin: jendela `[earliest_slot, deadline_slot)`, runtime `R` slot, blok
minimum `L = min(min_continuous, R)`, cooldown `C` slot setelah dimatikan.

- Boleh ON hanya di jendela, bila sisa runtime > 0 dan cooldown selesai.
- **Forced-ON** bila (a) mesin sedang ON dan blok belum mencapai `L`, atau
  sisa runtime < `L`; (b) mesin ON dan mematikannya sekarang membuat sisa
  runtime tidak muat lagi (`R > slot_tersisa − max(C,1)`); (c) mesin OFF dan
  `R ≥ slot_tersisa` sampai deadline.
- Mesin tidak fleksibel (`is_flexible=False`) dipaku ke blok kebiasaan lama.

Akibatnya **aksi apa pun** yang dijalankan lewat env (bahkan acak) pasti
menyelesaikan 100 % pesanan tepat waktu; ini diuji secara properti
(`test_random_machines_random_actions_are_always_valid`). Jadwal OR-Tools juga
terbukti lolos mask tanpa koreksi (`test_milp_schedule_replays_exactly_in_env`).

## 4. Solver

### OR-Tools (CP-SAT)
- Variabel biner `x[i,t]`, Σx = runtime, nol di luar jendela.
- Blok minimum & cooldown sebagai constraint nyata (indikator start/stop).
- Neraca daya integer W: `pv + grid + discharge = beban + charge + curtail`.
- Baterai linear: SoC integer mWh, efisiensi √η per arah (dibulatkan ±0,4 %),
  charge hanya dari PV. Simulasi pelaporan memakai `Battery` (aturan greedy:
  isi dari surplus, kosongkan saat defisit — optimal untuk tarif flat); objective
  MILP bisa sedikit berbeda dari biaya terlapor.
- Objective leksikografis: (1) biaya energi minimum, skala integer
  `round(Rp/Wh × 0,25 × 10⁴)` (aman di int64); (2) dengan biaya itu, minimum
  jumlah start (Rp 1/start) dan sedekat mungkin dengan kebiasaan lama
  (Rp 0,05/slot) — sehingga bila tidak ada manfaat, jadwal pemilik dipertahankan.
- Batas waktu `settings.ortools_time_limit_s` (70 % fase 1, sisa fase 2).
  kWp = 0 ditangani (tanpa variabel grid; biaya = beban × tarif).

### Greedy
Satu blok kontinu per mesin (daya terbesar dulu) yang menyerap surplus PV
terbanyak; tie → paling dekat jam kebiasaan. kWp = 0 → persis kebiasaan lama
(bukan lagi "40 slot PV tertinggi"). Selalu patuh deadline.

### PPO (sb3-contrib MaskablePPO)
- Aksi `MultiDiscrete([2] × n_max)` (`n_max = settings.rl_max_machines`, default
  6; mesin lebih sedikit di-padding & di-mask OFF). `action_masks()` konsisten
  dengan aturan §3.
- Observasi (versi 2): waktu, PV sekarang & rata-rata 1 j / 4 j ke depan,
  surplus, tarif, SoC & kapasitas baterai, sisa energi PV hari ini; per mesin:
  daya, sisa runtime, slack, status, boleh ON, wajib ON, di jendela, progres blok.
- Reward = −(biaya PLN slot + Rp 1 per start) × 10⁻⁴.
- Pelatihan: **behavior cloning** dari demonstrasi (jadwal OR-Tools bila lebih
  murah > Rp 1 dari kebiasaan lama, selain itu kebiasaan lama), lalu
  fine-tuning MaskablePPO pada tanggal acak sepanjang tahun latih (2025) dengan
  variasi mesin, `OrderBook`, kWp (0–6), dan baterai. Model (BC saja vs BC+PPO)
  dipilih di set validasi; diuji di tahun lain (2024).

### `plan_day(..., solver="auto")`
PPO bila model terlatih ada, jumlah mesin ≤ `n_max`, jadwalnya lolos
`validate_schedule`, **dan** tidak lebih mahal daripada kebiasaan lama tanpa
idle; selain itu OR-Tools; bila OR-Tools gagal → greedy. `deadlines_met` selalu
dihitung ulang dari jadwal final. Alasan fallback ditulis di `notes`.

## 5. API

`POST /api/v1/dispatch/optimize` (header `Authorization: Bearer …`):

```json
{
  "target_date": "2025-07-15",
  "kwp_capacity": 3.0,
  "battery_kwh": 5.0,
  "solver": "auto",
  "apply_order_book": false,
  "jobs": []
}
```

`jobs` kosong → contoh mesin default (`GET /api/v1/dispatch/default-jobs`).
Respons: `machines[]` (blok agen & blok kebiasaan lama per mesin,
`deadline_met`), `schedule[96]` (`machines_on`, beban, PV, grid, curtail, SoC,
tarif, biaya), `baseline_cost_idr`, `savings_idr` (boleh negatif),
`savings_breakdown`, `deadlines_met`, `pv_source`, `solver_used`, `notes`.
Field `SlotSchedule.machine_id` dipertahankan untuk kompatibilitas tetapi usang.

## 6. Melatih & mengevaluasi

```bash
cd backend
pip install -r requirements.txt -r requirements-rl.txt   # torch ~200 MB
python scripts/train_agent.py --timesteps 30000           # ±10 menit di CPU laptop
python scripts/train_agent.py --timesteps 0 --bc-episodes 300   # BC saja
```

Keluaran: `models/ppo_dispatcher.zip` (**jangan di-commit**, sudah di
`.gitignore`), `models/ppo_dispatcher.meta.json`, `models/agent_eval.json`.
Server memuat model saat start bila sb3-contrib terpasang; bila tidak, API
tetap jalan dengan OR-Tools.

### Hasil pelatihan singkat (7 Nov 2026)

Perintah: `python scripts/train_agent.py --timesteps 30000 --bc-episodes 150 --bc-epochs 30`
(total 402 s di CPU). Demonstrasi: 59 hari jadwal OR-Tools, 91 hari kebiasaan
lama (OR-Tools tidak lebih murah > Rp 1 — umumnya kWp kecil/0 atau hari libur).
Uji: 30 skenario sintetis bercuaca 2024 (NASA POWER), 29 di antaranya punya
PV/baterai. Biaya rata-rata per hari (simulasi, Rp):

| Penjadwal | Biaya/hari | Hemat vs kebiasaan lama |
| --- | ---: | ---: |
| Kebiasaan lama (dengan idle) | 41.493 | — |
| Kebiasaan lama tanpa idle | 40.186 | 3,1 % |
| Greedy | 39.870 | 3,9 % |
| OR-Tools | 39.830 | 4,0 % |
| PPO (BC + 30k langkah) | 40.604 | 2,1 % |
| Planner `auto` (PPO + pengaman → OR-Tools) | 39.850 | 4,0 % |

Temuan apa adanya:
- PPO memenuhi 100 % deadline (dijamin mask), tetapi **1,9 % lebih mahal
  daripada OR-Tools** secara total; lebih buruk daripada kebiasaan lama tanpa
  idle di 37 % skenario (di sana planner `auto` jatuh ke OR-Tools). Sebagian
  besar "penghematan" PPO berasal dari menghapus idle, bukan dari penjadwalan.
- Fine-tuning PPO 30k langkah (lr 1e-4) **tidak mengubah** biaya validasi
  dibanding BC saja (49.169 vs 49.169) — anggaran latih terlalu kecil untuk
  perbaikan berarti. Klaim "RL mengalahkan solver" TIDAK didukung data ini.
- Greedy satu-blok sudah hampir optimal pada skenario ini (selisih 0,1 % dari
  OR-Tools) karena dengan tarif flat masalahnya adalah memaksimalkan konsumsi PV.
- Waktu: PPO ±0,4 s/hari, OR-Tools ±1,2 s/hari (batas 10 s).

Rincian per skenario ada di `models/agent_eval.json`.

## 7. Keterbatasan

- Profil mesin default, menit idle, daya idle, dan distribusi skenario adalah
  asumsi. Isi dengan data NILM/wawancara pemilik sebelum mengklaim penghematan.
- Baterai: tanpa degradasi; perbandingan memakai SoC awal sama tetapi SoC akhir
  hari bisa berbeda antara baseline dan agen (tidak dinilai).
- PV dari model (NASA POWER atau clear-sky); ketidakpastian cuaca harian belum
  dimodelkan (jadwal disusun dengan asumsi kurva PV diketahui).
- PPO hanya meniru/menyetel di atas OR-Tools pada skenario sintetis; untuk
  produksi OR-Tools tetap menjadi acuan dan jaring pengaman.
