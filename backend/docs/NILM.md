# NILM WASKITA — tahap "Tahu"

NILM (*Non-Intrusive Load Monitoring*) memecah satu pembacaan panel (kotak
sensor di MCB utama) menjadi pemakaian per mesin, tanpa memasang sensor di
setiap mesin. Dokumen ini menjelaskan alur, format data, cara melatih dan
mengevaluasi, serta batasannya.

> **Status akurasi: belum divalidasi di lapangan.** Semua angka di bawah berasal
> dari data **sintetis**. Angka lapangan baru boleh diklaim setelah pipeline
> evaluasi dijalankan pada data smart plug nyata (`--data-source field`).

## 1. Alur

```
telemetri 1 Hz ──► EventDetector ──► TransientEvent ──► NILMClassifier ──► LoadDisaggregator ──► energi/jam per mesin
(panel)            (event_detector)   (ON/OFF, ΔP, ΔQ,   (LightGBM atau       (status ON/OFF,      (HourlyEnergy, residu =
                                       inrush)            heuristik)           daya per mesin)       "Baseload / Background")
```

| Modul | Isi |
|---|---|
| `app/nilm/event_detector.py` | Detektor dua status (STABIL/TRANSIEN). ΔP = median sesudah − baseline stabil sebelum. Inrush dan ramp 2–3 sampel menjadi **satu** event. Parameter dari `settings.nilm_event_threshold_w`, `nilm_event_window_s`, `nilm_event_max_transient_s`. |
| `app/nilm/feature_extractor.py` | Fitur: `abs_delta_p, abs_delta_q, ratio_q_p, inrush_peak_ratio, is_on, transient_duration_s`. Tanpa jam/hari agar model tidak menghafal jadwal. |
| `app/nilm/profiles.py` | Prototipe tanda tangan listrik per mesin (ΔP, Q/P, inrush). Nilai tipikal, bukan hasil ukur. |
| `app/nilm/classifier.py` | LightGBM bila bundle model valid; selain itu heuristik jarak-ke-prototipe dengan confidence dari jarak (bukan angka tetap). |
| `app/nilm/disaggregator.py` | Melacak instans mesin ON, mencocokkan OFF (ΔP **dan** ΔQ terdekat), menghitung energi per jam dengan konservasi energi. |
| `app/nilm/ground_truth.py` | Baca CSV, ekstrak transisi smart plug, cocokkan event ↔ transisi, energi per jam smart plug. |
| `scripts/generate_synthetic_data.py` | Data sintetis: panel + smart plug. |
| `scripts/train_nilm.py` | Latih LightGBM dari label smart plug. |
| `scripts/evaluate_nilm.py` | Ukur F1 per mesin dan akurasi energi, tulis JSON ke `settings.nilm_metrics_path`. |

### Konservasi energi (disaggregator)

Untuk tiap sampel: `E_total = P_terukur × Δt` (Δt dibatasi `max_gap_s`, default
10 s). Jika Σ estimasi mesin ≤ P_terukur, sisanya masuk `"Baseload / Background"`;
jika lebih besar, semua estimasi diskalakan proporsional dan residu = 0. Jadi
Σ energi semua label per jam = energi terukur (diuji di
`tests/test_disaggregator.py`).

Penjaga untuk OFF yang terlewat:
1. OFF yang diklasifikasi sebagai mesin X boleh mematikan instans X dengan
   toleransi daya longgar (ΔP saat ON bisa terdistorsi event lain).
2. Bila P atau Q terukur terus-menerus (≥ `stale_s`, default 60 s) jauh di bawah
   jumlah estimasi, instans yang paling mungkin basi dilepas. Catatan: bila
   panel punya bank kapasitor (Q terukur turun), atur `stale_q_margin_var` lebih
   besar.
3. Opsional `max_instances_per_label` (dari inventaris `MachineProfile`).
   Default tak dibatasi karena satu UMKM bisa punya beberapa mesin sejenis.

## 2. Format data

Waktu: ISO 8601. Tanpa zona waktu = waktu lokal (WIB). Bila ada zona waktu
(`Z` atau `+07:00`), nilai dikonversi ke `settings.site_timezone`.

### 2.1 Panel (kotak sensor) — `*_panel.csv`

```
timestamp,v_rms,i_rms,p_active,q_reactive,frequency
2026-10-14T08:00:00,219.41,2.415,512.33,174.02,50.012
```

1 baris per sampel, idealnya 1 Hz (detektor mengasumsikan `sample_rate_hz=1`).
Satuan: V, A, W, VAR, Hz. Ini sama dengan isi `TelemetryRecord`, jadi data dari
database bisa diekspor langsung ke format ini.

### 2.2 Smart plug (ground truth per mesin) — `*_plugs.csv`

Format panjang, satu baris per pembacaan per mesin:

```
timestamp,appliance_label,p_active,status
2026-10-14T08:00:00,Motor Jahit Induksi,0.0,OFF
2026-10-14T08:00:10,Motor Jahit Induksi,318.4,ON
```

| Kolom | Wajib | Keterangan |
|---|---|---|
| `timestamp` | ya | waktu pembacaan |
| `appliance_label` | ya | nama mesin; sama persis untuk satu mesin. Gunakan nama di `APPLIANCE_LABELS` bila cocok (id kelas tetap); nama lain otomatis mendapat id baru saat training. |
| `p_active` | ya | daya (W). Energi dihitung dengan *zero-order hold*: nilai dianggap berlaku sampai baris berikutnya dari mesin yang sama. Celah > 15 menit dianggap data hilang. |
| `status` | tidak | `ON/OFF`, `1/0`, atau `true/false`. Bila tidak ada: ON jika `p_active > 15 W`. |

Generator sintetis menulis baris tiap 10 s **dan** tepat saat status berubah,
dengan `p_active` = rata-rata daya sejak baris itu sampai baris berikutnya.

#### Memakai smart plug lapangan (Tuya / Sonoff)

1. Pasang satu smart plug ber-pengukur daya per mesin yang ingin dilabeli
   (kapasitas plug harus ≥ daya puncak mesin; kompresor/setrika > 1 kW perlu
   plug 16 A). Mesin di atas kapasitas plug bisa memakai CT clamp per cabang.
2. Sinkronkan jam: kotak sensor dan plug harus sama-sama memakai NTP. Selisih
   jam > `settings.nilm_label_tolerance_s` (default 5 s) membuat event tidak
   tercocokkan; naikkan toleransi bila plug hanya melapor tiap 10–30 s.
3. Ekspor riwayat daya:
   - **Tuya**: Tuya IoT Platform → Device → *Device Logs*/API
     `GET /v1.0/devices/{id}/logs` (DP `cur_power`, biasanya satuan 0,1 W —
     bagi 10), atau Home Assistant + integrasi Tuya lalu ekspor riwayat sensor.
   - **Sonoff (firmware Tasmota/ESPHome)**: kirim `ENERGY.Power` via MQTT ke
     Home Assistant / InfluxDB, lalu ekspor.
   - Home Assistant: *History* → unduh CSV (`entity_id,state,last_changed`)
     lalu ubah nama kolom menjadi `appliance_label,p_active,timestamp`.
4. Gabungkan semua plug ke satu CSV format panjang di atas, tulis panel ke
   `field_panel.csv`, lalu latih & evaluasi (bagian 3) dengan
   `--data-source field`. Pisahkan hari latih dan hari uji.

## 3. Menjalankan pipeline

Dari folder `backend`:

```bash
# 1) Data sintetis kecil (± 1 menit). site-seed sama → mesin sama; seed beda → hari beda.
python scripts/generate_synthetic_data.py --days 4 --seed 1 --prefix train --start 2026-10-05
python scripts/generate_synthetic_data.py --days 2 --seed 2 --prefix test  --start 2026-10-14

# 2) Latih (label dari smart plug, bukan aturan)
python scripts/train_nilm.py --panel data/synthetic/train_panel.csv \
    --plugs data/synthetic/train_plugs.csv --data-source synthetic

# 3) Evaluasi pada data uji terpisah → models/nilm_metrics.json
python scripts/evaluate_nilm.py --panel data/synthetic/test_panel.csv \
    --plugs data/synthetic/test_plugs.csv --data-source synthetic
```

Data lapangan: ganti path dan `--data-source field`.

Model (`models/nilm_lgbm.pkl`) disimpan sebagai bundle
`{format_version, model, feature_names, label_map, data_source, trained_at,
holdout, versions, ...}` dan **tidak di-commit**. Saat dimuat, bila
`format_version` atau `feature_names` tidak cocok, file rusak, atau berupa model
lama (bukan bundle), classifier otomatis memakai heuristik dan mencatat
alasannya di `NILMClassifier.fallback_reason`.

### Pelabelan dari smart plug

Untuk setiap event panel, dicari transisi smart plug dengan arah sama (ON/OFF),
`|Δt| ≤ nilm_label_tolerance_s`, dan |ΔP| tidak berbeda > 60% dari daya plug.
Pasangan dipilih greedy berdasarkan biaya `Δt/toleransi + selisih relatif
daya`; satu transisi hanya dipakai sekali. Event tanpa pasangan dilabeli
`"Baseload / Background"` (beban tanpa plug seperti lampu/kipas, atau noise).

## 4. Metrik

- **Klasifikasi event**: precision/recall/F1 per mesin terhadap label smart plug.
- **Recall deteksi**: porsi transisi smart plug yang memiliki event panel pasangan.
- **Akurasi energi** (Kolter & Johnson, 2011), per jam:
  `Acc = 1 − Σ_t |ê_t − e_t| / (2 Σ_t e_t)`; overall dijumlah atas semua mesin
  ber-smart-plug. Baseload juga dilaporkan, dengan ground truth turunan
  (total panel − Σ smart plug).
- Target proposal: ≥ 80% untuk mesin utama. JSON memuat
  `meets_80pct_f1` / `meets_80pct_energy` per mesin.

JSON (`settings.nilm_metrics_path`) berisi `data_source`, `validation_status`,
`inputs`, `classifier`, `per_appliance`, `overall`, dan `baselines.heuristic`.

### Hasil terakhir (data SINTETIS, belum divalidasi)

Latih 4 hari (1.305 event), uji 2 hari terpisah (172.800 sampel, 718 event,
676 transisi plug), `site-jitter` 0,2:

| Mesin | F1 event | Akurasi energi | Energi est. / plug (kWh) |
|---|---|---|---|
| Kompresor Pendingin Freezer | 1,000 | 0,970 | 3,66 / 3,61 |
| Kompresor Udara Sablon | 1,000 | 0,929 | 2,66 / 3,03 |
| Motor Drum Pengering Laundry | 1,000 | 0,984 | 4,80 / 4,85 |
| Motor Jahit Induksi | 0,985 | 0,967 | 4,21 / 4,32 |
| Setrika Pemanas Uap | 0,996 | 0,972 | 3,42 / 3,55 |
| **Overall** | akurasi event 0,994, macro-F1 0,996 | **0,967** | — |

Recall deteksi 0,975. Pembanding heuristik: akurasi event 0,999, akurasi energi
0,959.

**Cara membaca angka ini dengan jujur:**
- Data sintetis jauh lebih mudah daripada lapangan: tanda tangan mesin
  terpisah jelas, sampling 1 Hz sempurna, jam sinkron, tidak ada mesin sejenis
  ganda, harmonisa/VFD, PV, atau beban yang dayanya berubah terus (mis. mesin
  jahit servo, inverter AC).
- Heuristik setara dengan LightGBM di sini karena prototipe heuristik dan
  generator berbagi profil yang sama (meski digeser `site-jitter`). Ini **bukan**
  bukti heuristik cukup untuk lapangan.
- Angka ≥ 80% di atas tidak boleh dikutip sebagai akurasi produk sampai
  dievaluasi dengan `--data-source field` pada minimal beberapa hari kerja di
  UMKM nyata.

## 5. Batasan yang diketahui

- Dua mesin yang berubah status dalam detik yang sama tergabung menjadi satu
  event (ΔP gabungan) → biasanya terlabel salah/latar.
- Mesin dengan daya bervariasi kontinu (servo, VFD, inverter) tidak cocok
  dengan model event ON/OFF; energinya akan masuk residu atau salah atribusi.
- Energi selama ±W detik transien masuk baseload (latensi deteksi).
- Detektor mengasumsikan sampling seragam; bila firmware mengirim buffer
  offline, kirim berurutan per perangkat.
