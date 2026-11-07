# WASKITA — Agen AI Pengatur Energi untuk UMKM

WASKITA membantu UMKM melihat mesin paling boros listrik dari **satu titik ukur**, menyusun jadwal mesin harian yang lebih hemat, lalu menghitung **ukuran PLTS atap yang tepat setelah jadwal dioptimalkan** (ekspor ke PLN tidak dikreditkan, Permen ESDM No. 2/2024).
UNS Innovation Hackathon 2026 · Energy Track · Subtema C.

| Tahap | Isi | Lokasi |
|---|---|---|
| **Tahu** | Kotak sensor ESP32 + SCT-013 + ZMPT101B, NILM (pemisah beban) → kWh & Rp per mesin per jam | `firmware/`, `backend/app/nilm/` |
| **Atur** | Tiruan digital (cuaca NASA POWER, baterai, pola pesanan) + agen penjadwal (OR-Tools, behavior cloning + MaskablePPO, action masking) | `backend/app/digital_twin/`, `backend/app/agent/` |
| **Hemat** | Saran jadwal sore & nota mingguan via WhatsApp | `backend/app/services/` |
| **Punya PLTS** | Sizing PLTS setelah jadwal agen, rapor energi (PDF) | `backend/app/sizing/` |

## Struktur repo

```
app/, components/, styles/   Landing page (Next.js) + simulator yang memanggil backend
lib/waskita.ts               Jembatan landing page ↔ backend
backend/                     API FastAPI, dasbor web (backend/static), tes, dokumentasi (backend/docs)
firmware/waskita-sensor/     Firmware kotak sensor ESP32 (PlatformIO)
```

## Menjalankan secara lokal

**Backend + dasbor** (Python 3.12):

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
cp .env.example .env                              # isi SECRET_KEY & BOOTSTRAP_ADMIN_*
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

- Dasbor: http://localhost:8000 · API docs: http://localhost:8000/docs
- Opsional melatih agen RL: `pip install -r requirements-rl.txt` lalu `python scripts/train_agent.py`
- Tes: `.venv/Scripts/python -m pytest -q`

**Landing page** (Node 20):

```bash
npm ci
cp .env.example .env.local    # NEXT_PUBLIC_WASKITA_API_URL=http://localhost:8000
npm run dev                   # http://localhost:3000
```

**Firmware:** lihat `firmware/README.md` (kalibrasi, pengkabelan, catatan keselamatan PUIL).

## Status validasi (jujur)

Semua angka akurasi saat ini berasal dari **data sintetis/contoh** dan ditandai *belum divalidasi*:
metrik NILM (`backend/models/nilm_metrics.json`), selisih tagihan tiruan digital (`backend/models/twin_validation.json`), dan estimasi simulator.
Validasi lapangan (smart plug sebagai pembanding, tagihan PLN nyata UMKM uji) adalah langkah berikutnya menuju TKT 5.
Firmware belum dikompilasi/diuji pada perangkat ESP32 nyata.

Dokumentasi teknis: `backend/docs/` (CONTRACTS, NILM, DIGITAL_TWIN, AGENT, SIZING, WHATSAPP, API_DASHBOARD).
