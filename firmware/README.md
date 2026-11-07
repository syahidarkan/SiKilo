# WASKITA – Firmware Kotak Sensor (ESP32)

Kotak sensor ini adalah sisi hardware tahap **"Tahu"** WASKITA: mengukur listrik
satu fasa UMKM (setelah meteran PLN), lalu mengirim **1 sampel per detik** ke
backend WASKITA untuk NILM, tiruan digital, dan agen penjadwal.

```
firmware/
├── README.md                     ← dokumen ini
└── waskita-sensor/               ← proyek PlatformIO (Arduino, esp32dev)
    ├── platformio.ini
    ├── partitions_waskita.csv    ← 2 slot OTA 1,625 MB + LittleFS 640 KB
    ├── include/config.h          ← pin, tipe CT, kalibrasi awal, sampling, batas buffer
    ├── include/secrets.example.h ← salin ke include/secrets.h (diabaikan git)
    ├── src/main.cpp              ← WiFi, portal, NTP, kirim/buffer, LED, tombol, serial, OTA
    ├── lib/waskita_core/         ← perhitungan daya + ring buffer + format JSON (tanpa Arduino)
    └── test/test_core/           ← uji unit Unity (pio test -e native)
```

> **Status jujur (versi 0.1.0)**
> - Kode **belum dikompilasi dengan toolchain ESP32** (PlatformIO tidak tersedia di
>   mesin pengembang saat ditulis). Yang sudah dilakukan: cek sintaks/tipe dengan
>   `avr-g++ -fsyntax-only` + header tiruan API ESP32, dan simulasi numerik
>   algoritma (port Python float32) terhadap semua skenario di `test/test_core`.
>   Jalankan `pio run` dan `pio test -e native` sebelum dipakai.
> - **Belum diuji di perangkat keras** dan **akurasi belum divalidasi** terhadap
>   alat ukur referensi. Angka akurasi apa pun harus berasal dari prosedur
>   "Validasi" di bawah, bukan dari dokumen ini.

---

## 1. Cara kerja singkat

| Tahap | Detail |
|---|---|
| Sampling | ADC1 12 bit, **4 kHz** pasangan sampel (V lalu I segera sesudahnya), 12 siklus ditangkap tiap 500 ms |
| Jendela | **10 siklus penuh 50 Hz (~200 ms)**, dibatasi zero-crossing naik tegangan |
| Offset DC | Dihapus numerik (rata-rata pada siklus bulat) → bias 1,65 V tidak harus presisi |
| Koreksi fase | Gaya EmonLib: tegangan diinterpolasi di posisi `k − 1 + PHASE_CAL` |
| Besaran | `Vrms`, `Irms`, `P = mean(v·i)`, `S = Vrms·Irms`, `Q = tanda · √max(S²−P², 0)`, `PF = P/S`, frekuensi dari zero-crossing (interpolasi) |
| Tanda Q | Dari pergeseran fasa fundamental: korelasi arus dengan tegangan tertunda ¼ periode (`+` induktif/arus tertinggal, `−` kapasitif). Bila \|Q_fundamental\| < 2 % S, tanda dianggap `+` |
| Agregasi | 2 jendela → 1 sampel/detik (V, I secara RMS; P, Q dirata-rata; f rata-rata jendela valid) |
| Kirim | `POST /api/v1/telemetry/ingest` (1 sampel) atau `/ingest-batch` (backlog, ≤ 120/batch; kontrak maks. 500) |
| Offline | Ring buffer RAM ~30 menit → spool LittleFS ~4,5 jam (setelah jam NTP tersinkron) |

Catatan teknis:
- **Q memuat daya distorsi.** Dengan beban non-linear (adaptor, driver LED, inverter),
  `√(S²−P²)` lebih besar daripada Q fundamental. Ini sesuai spesifikasi tim, tetapi
  perlu diingat saat membaca fitur Q di NILM.
- **`p_active` dikirim ≥ 0.** Bila P negatif (CT terbalik atau ekspor PLTS), nilai
  dikirim 0 W dan arah dicatat lokal (serial `status` → `detik_P_negatif`, peringatan
  setelah 10 detik berturut-turut). Perbaiki dengan membalik klem CT atau
  `#define CT_INVERT 1`.
- Nilai di-clamp agar lolos skema backend (`app/schemas/telemetry.py`):
  V 0–300, I 0–200, f 48–52 Hz. Jika frekuensi tak terukur (tegangan hilang),
  dikirim 50,000 Hz (nominal).

## 2. Daftar komponen & perkiraan harga

Perkiraan harga eceran marketplace Indonesia (belum ongkir; bisa berbeda jauh
antar toko/waktu — **bukan kutipan resmi**).

| No | Komponen | Jml | Perkiraan (Rp) |
|---|---|---|---|
| 1 | ESP32 DevKit V1 (ESP32-WROOM-32, 4 MB flash) | 1 | 55.000 – 90.000 |
| 2 | CT split-core **SCT-013-000** 100 A : 50 mA (keluaran arus) — *atau* SCT-013-030 30 A/1 V | 1 | 60.000 – 100.000 |
| 3 | Modul sensor tegangan **ZMPT101B** (dengan op-amp & trimpot) | 1 | 20.000 – 40.000 |
| 4 | Resistor burden 33 Ω 1 % (hanya untuk SCT-013-000) | 1 | 500 – 1.000 |
| 5 | Resistor 10 kΩ 1 % (pembagi bias CT) | 2 | 1.000 |
| 6 | Resistor 10 kΩ + 20 kΩ 1 % (pembagi keluaran ZMPT) | 1+1 | 1.000 |
| 7 | Kapasitor elektrolit 10 µF/16 V (bias CT) + 100 nF | 1+1 | 1.000 |
| 8 | Jack audio 3,5 mm female (konektor CT) | 1 | 3.000 – 6.000 |
| 9 | Catu daya 5 V: adaptor USB ber-SNI **atau** modul HLK-PM01 | 1 | 25.000 – 50.000 |
| 10 | Sekring kaca 0,5 A + holder (jalur AC ke ZMPT/catu) | 1 | 8.000 – 15.000 |
| 11 | Enclosure plastik ABS/PC berinsulasi (mis. IP65 ±115×90×55 mm) | 1 | 25.000 – 60.000 |
| 12 | PCB lubang, terminal block AC, kabel NYAF 0,75–1,5 mm², cable gland | – | 20.000 – 40.000 |
| | **Total perkiraan** | | **± 220.000 – 400.000** |

Opsional: smart plug dengan pengukur energi (untuk validasi), tang ampere
(clamp meter) dan multimeter True-RMS (untuk kalibrasi).

## 3. Diagram pengkabelan

ESP32 hanya boleh menerima **0 – 3,3 V** di pin ADC. Pakai **ADC1** (GPIO32–39);
ADC2 tidak bisa dibaca saat WiFi aktif. Firmware memakai **GPIO34 (arus)** dan
**GPIO35 (tegangan)**.

### 3a. Sensor arus SCT-013-000 (100 A : 50 mA) + burden + bias 1,65 V

```
            3V3 (ESP32)
             │
            [10k]
             │
             ├──────────────┬──────────────────┐  titik bias ≈ 1,65 V
             │              │                  │
            [10k]        (+)│10µF              │
             │              │                  │  jack 3,5 mm (CT)
            GND            GND                 ├──── sleeve ──┐
                                               │              │  SCT-013-000
                                         [33 Ω burden]        │  (dijepit di
                                               │              │   kabel FASA)
   GPIO34 (ADC1_CH6) ◄─────────────────────────┴──── tip ─────┘
```

- Burden 33 Ω → 35 A RMS ≈ ±0,82 V puncak di sekitar 1,65 V (daerah linear ADC
  ESP32 pada atenuasi 11 dB kira-kira 0,15–2,45 V). Untuk sambungan > 7.700 VA,
  pakai 22 Ω dan ubah `CT_BURDEN_OHMS`.
- `I_CAL` awal = 2000 / 33 = 60,6 (diset otomatis dari `config.h`).

**Varian SCT-013-030 (30 A / 1 V):** burden sudah di dalam CT, **jangan pasang
33 Ω**. Rangkaian bias sama, tip langsung ke GPIO34. Di `config.h`:
`#define CT_TYPE CT_TYPE_VOLTAGE_OUTPUT` (I_CAL awal = 30). 1 V RMS = 1,41 V
puncak sehingga di atas ~17 A sinyal masuk daerah non-linear ADC.

### 3b. Sensor tegangan ZMPT101B

```
  Sisi AC (di dalam enclosure, terpisah dari sisi DC)
  L (keluaran MCB) ──[sekring 0,5 A]──► ZMPT101B "L"
  N ──────────────────────────────────► ZMPT101B "N"

  Sisi DC
  5V  (VIN ESP32) ──► ZMPT101B VCC
  GND             ──► ZMPT101B GND
  ZMPT101B OUT ──[10k]──┬──► GPIO35 (ADC1_CH7)
                        │
                      [20k]       (keluaran tengah 2,5 V × 2/3 ≈ 1,67 V;
                        │          ayunan maks. LM358 0..3,5 V → 0..2,33 V aman)
                       GND
```

- Modul ZMPT101B diberi **5 V** (op-amp LM358 di modul tidak bisa berayun penuh
  pada 3,3 V) lalu keluarannya **dibagi 2/3** agar tetap < 3,3 V dan berpusat
  ±1,65 V.
- Atur trimpot modul (sebelum kalibrasi) sampai gelombang di GPIO35 sekitar
  **1,0–1,2 Vpp** pada 220–230 V (cek dengan perintah `status`: V harus stabil;
  bila dekat 0 atau "terpotong", ubah trimpot).

### 3c. Lain-lain

```
  GPIO2  → LED biru onboard (status)
  GPIO0  → tombol BOOT onboard (tahan 5 detik = reset konfigurasi)
  5V/GND → adaptor USB 5 V ber-SNI (disarankan) atau HLK-PM01 di sisi AC bersekring
```

## 4. ⚠️ CATATAN KESELAMATAN (PUIL 2011 / SNI 0225:2011 beserta amandemennya)

Perangkat ini bersentuhan dengan **tegangan jaringan 220–230 V AC yang dapat
mematikan**. Dokumen ini bukan pengganti PUIL 2011; ikuti PUIL dan arahan
instalatir.

1. **Pemasangan hanya oleh teknisi/instalatir listrik bersertifikat**
   (bersertifikat kompetensi tenaga teknik ketenagalistrikan, dari badan usaha
   instalasi yang sah). Pemilik UMKM tidak memasang sendiri bagian yang
   bertegangan.
2. **Posisi setelah meteran PLN.** Semua sambungan berada di **sisi instalasi
   pelanggan** (di PHB/panel setelah APP & MCB utama). **Dilarang membuka,
   merusak, atau memindahkan segel APP / kWh meter PLN**, dan dilarang menyadap
   kabel sebelum meteran.
3. **CT jepit tanpa memotong kabel.** SCT-013 adalah CT *split-core*: dijepit
   mengelilingi **satu** konduktor (fasa L) tanpa mengupas/memotong isolasi.
   Jangan menjepit L dan N bersamaan (hasil ≈ 0). Untuk SCT-013-000, sambungkan
   dulu ke rangkaian burden sebelum menjepit kabel berbeban — sekunder CT
   tipe keluaran arus yang terbuka dapat menimbulkan tegangan berbahaya.
4. **ZMPT101B di sisi keluaran MCB, dengan proteksi.** Ambil tegangan dari sisi
   beban MCB (bukan sebelum MCB utama), lewat **sekring 0,5 A** (atau MCB kecil)
   tersendiri, kabel berpenampang sesuai, terminal tertutup tanpa tembaga
   terbuka.
5. **Enclosure berinsulasi.** Kotak plastik non-konduktif, tertutup rapat, tidak
   ada bagian bertegangan yang bisa tersentuh; pisahkan fisik sisi AC dan sisi
   DC/ESP32 (jarak rambat memadai), gunakan cable gland/strain relief, beri label
   "AWAS TEGANGAN 220 V".
6. **Kerja tanpa tegangan.** Matikan MCB sebelum membuka panel, pastikan dengan
   tespen/multimeter, pasang label "sedang dikerjakan". Kalibrasi dilakukan
   dengan enclosure tertutup; sambungan laptop hanya lewat USB ke ESP32 (sisi
   DC terisolasi oleh trafo ZMPT101B dan CT), jangan menyentuh sisi AC.
7. Gunakan catu 5 V bersertifikat (SNI). Jika memakai HLK-PM01, ia berada di sisi
   AC dan wajib bersekring serta berada di dalam enclosure.
8. Jangan dipasang di lokasi basah/panas tanpa enclosure dengan IP yang sesuai.

## 5. Build & flash

```bash
pip install platformio          # atau ekstensi PlatformIO di VS Code
cd firmware/waskita-sensor
cp include/secrets.example.h include/secrets.h   # lalu ganti password portal/OTA
pio run -e esp32dev                    # kompilasi
pio run -e esp32dev -t upload          # flash via USB
pio device monitor -e esp32dev         # serial 115200, ketik: help
pio test -e native                     # uji unit (butuh gcc/g++; Windows: MSYS2/MinGW-w64)
```

OTA (opsional, isi `OTA_PASSWORD` ≥ 8 karakter di `secrets.h`):

```bash
WASKITA_OTA_PASSWORD='password-ota' pio run -e esp32dev_ota -t upload --upload-port waskita-a1b2c3.local
```

Portal WiFiManager sengaja **tanpa menu "update"** (unggah firmware lewat portal
tidak berpassword).

## 6. Registrasi perangkat di backend

Device diregistrasi lewat `POST /api/v1/devices` (role **admin/installer**) yang
mengembalikan **API key sekali saja** (lihat `backend/docs/CONTRACTS.md` §7).
Field mengikuti model `Device(device_id, umkm_id, firmware_version?)`; cek skema
pasti di Swagger backend (`/docs`).

```bash
API=http://192.168.1.10:8000

# 1) Login sebagai admin/installer (form OAuth2)
TOKEN=$(curl -s -X POST "$API/api/v1/auth/login" \
  -d "username=installer1&password=..." | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2) Registrasi. device_id = yang tampil di serial saat boot (default WSK-<6 hex MAC>)
curl -s -X POST "$API/api/v1/devices" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"device_id":"WSK-A1B2C3","umkm_id":1,"firmware_version":"0.1.0"}'
# → simpan API key yang dikembalikan; tidak bisa dilihat lagi.

# 3) (Opsional) uji key sebelum ke lapangan
curl -s -X POST "$API/api/v1/telemetry/ingest" \
  -H "X-Device-Key: <API_KEY>" -H "Content-Type: application/json" \
  -d '{"device_id":"WSK-A1B2C3","timestamp":"2026-11-07T12:00:00+07:00","v_rms":228.1,"i_rms":1.2,"p_active":250.0,"q_reactive":30.0,"frequency":50.0}'
```

## 7. Provisioning WiFi (tanpa hard-code)

1. Nyalakan perangkat. Bila belum dikonfigurasi, LED **berkedip cepat** dan muncul
   Access Point **`WASKITA-XXXX`** (password = `PORTAL_AP_PASSWORD`).
2. Sambungkan HP → buka `http://192.168.4.1` → **Configure WiFi**.
3. Pilih SSID, isi password WiFi, lalu:
   - **URL server WASKITA** — contoh `http://192.168.1.10:8000` (akhiran `/api/v1` dan `/` dibuang otomatis),
   - **ID perangkat** — harus sama dengan `device_id` saat registrasi,
   - **Device key** — API key dari registrasi (kosongkan bila tidak ingin mengubah key lama).
4. Simpan. Semua disimpan di NVS (Preferences). Key tidak pernah ditampilkan
   kembali di portal maupun serial.

Portal ditutup otomatis setelah 5 menit (`PORTAL_TIMEOUT_S`) lalu perangkat terus
mencoba WiFi tersimpan tiap 30 detik; pengukuran **tetap berjalan** dan data
di-buffer. Perintah serial `portal` membuka portal kapan saja.

**Reset konfigurasi:** tahan tombol **BOOT (GPIO0) 5 detik** setelah perangkat
menyala (LED menyala terus setelah 1 detik). Menghapus WiFi, URL, ID, key, dan
spool; **kalibrasi dipertahankan** (`cal reset` untuk menghapus kalibrasi).

## 8. LED status (GPIO2)

| Pola | Arti |
|---|---|
| Menyala terus | Boot / tombol reset sedang ditahan |
| Kedip cepat (100 ms) | Portal konfigurasi aktif |
| Kedip lambat (0,5 s) | Menyambung WiFi / menunggu jam NTP |
| Kedip singkat tiap 2 s | Online, data terkirim |
| 2 kedip tiap 2 s | Ada antrean/buffer atau kiriman terakhir gagal |
| 3 kedip tiap 2 s | Konfigurasi belum lengkap atau server menolak key (401/403) |

## 9. Kalibrasi (WAJIB per unit)

Butuh: **multimeter True-RMS**, **tang ampere (clamp meter)**, dan **beban
resistif** yang diketahui (setrika, pemanas air/ketel listrik, lampu pijar;
1–2 kW ideal). Buka serial monitor 115200 baud.

1. **Cek bias (tanpa tegangan AC).** Ukur DC di GPIO34 dan GPIO35 ≈ 1,6–1,7 V.
2. **Tegangan.** Ukur V AC dengan multimeter di stopkontak/terminal yang sama →
   ketik `cal v 228.4` (angka multimeter). Firmware menskala `V_CAL` dan menyimpannya.
3. **Arah CT.** Nyalakan beban; `status` harus menunjukkan **P positif**. Bila
   negatif, balik klem CT (atau `CT_INVERT 1` lalu flash ulang).
4. **Arus.** Dengan beban resistif menyala (≥ 2 A), ukur arus kabel yang sama
   dengan tang ampere → `cal i 8.70`.
5. **Fase.** Beban resistif masih menyala → `cal phase`. Tunggu 5 detik → `status`:
   **PF ≈ 1,00** dan Q mendekati 0. (Atau set manual: `cal phase 1.12`.)
6. **Cek silang** dengan beban induktif (kipas, kulkas, pompa air): Q harus
   **positif**, PF < 1.
7. Catat `cal show` di lembar instalasi (V_CAL, I_CAL, PHASE_CAL, nomor unit).

Ulangi kalibrasi bila trimpot ZMPT diubah, CT/resistor burden diganti, atau
perangkat dipindah.

### Perintah serial

| Perintah | Fungsi |
|---|---|
| `status` | V, I, P, Q, PF, f, fasa, laju sampel, WiFi/NTP, antrean RAM/spool, statistik kirim |
| `cal show` / `cal reset` | Tampilkan / kembalikan kalibrasi default |
| `cal v <V>`, `cal i <A>` | Kalibrasi terhadap pembacaan alat ukur |
| `cal phase` / `cal phase <x>` | Kalibrasi fase otomatis (beban resistif) / manual |
| `config` | URL server, device_id, status key, nama AP & hostname |
| `portal` | Buka portal WiFi |
| `reboot` | Pindahkan buffer RAM ke flash lalu restart |

## 10. Validasi: membandingkan dengan smart plug & meteran PLN

Hasil validasi harus diukur — **sebelum itu tandai semua angka akurasi sebagai
"belum divalidasi"**.

**A. Per peralatan dengan smart plug pengukur energi**

1. Pasang smart plug ber-pengukur daya (mis. merek apa pun yang menampilkan W dan
   kWh) di antara stopkontak dan **satu** peralatan.
2. Matikan beban lain di jalur yang diukur CT, atau catat beban dasar dulu lalu
   hitung selisih saat peralatan dinyalakan.
3. Rekam ≥ 1 jam (lebih baik mencakup siklus ON/OFF peralatan). Catat kWh smart
   plug di awal/akhir; dari backend, jumlahkan `p_active × 1 s / 3.600.000` (kWh)
   pada rentang yang sama.
4. Hitung `galat % = (E_waskita − E_plug) / E_plug × 100` dan juga galat daya
   saat tunak (P rata-rata 1 menit).
5. Ingat: smart plug sendiri punya galat (spesifikasi pabrik umumnya beberapa
   persen dan jarang terverifikasi). Untuk klaim akurasi formal, gunakan meter
   referensi terkalibrasi (power analyzer / kWh meter kelas 1).

**B. Seluruh instalasi vs kWh meter PLN**

1. Catat angka kWh meter PLN (foto) pada jam X, lalu 24 jam kemudian.
2. Bandingkan dengan energi total telemetri pada rentang yang sama (data hilang
   >1 % dari rentang → ulangi).

Contoh lembar hasil:

| Tanggal | Beban | Referensi | E_ref (kWh) | E_WASKITA (kWh) | Galat (%) | Catatan |
|---|---|---|---|---|---|---|
| … | Setrika 1.000 W | smart plug | … | … | … | belum divalidasi |

## 11. Perilaku offline & pengiriman ulang

- Sampel masuk ke **ring buffer RAM** (default 1.800 sampel ≈ 30 menit, 32 byte/sampel).
- Bila RAM penuh **dan jam sudah tersinkron NTP**, 300 sampel tertua dipindah ke
  **spool LittleFS** (`/spool.bin`, maks. 512 KB ≈ 16 ribu sampel ≈ 4,5 jam,
  timestamp epoch → aman setelah reboot). Bila spool penuh atau jam belum
  sinkron, sampel tertua di RAM ditimpa (dihitung di `status`).
- Saat online: spool dikirim dulu (paling tua), lalu RAM, lewat
  `POST /api/v1/telemetry/ingest-batch` `{device_id, samples:[…]}` ≤ 120 sampel
  per batch (batas kontrak 500; HTTP 413 → ukuran batch dibagi dua). Bila hanya
  ada 1 sampel → `POST /ingest`.
- Gagal jaringan/5xx → coba lagi dengan backoff 2 s … 60 s. 400/422 → batch
  dibuang (dicatat) agar antrean tidak macet. 401/403 → data disimpan, LED 3 kedip.
- Sampel yang diambil sebelum NTP tersinkron tetap diberi timestamp benar setelah
  sinkron (disimpan sebagai uptime lalu dipetakan ke epoch) selama tidak reboot.
- **Catatan untuk backend:** jika respons hilang setelah server menyimpan data,
  firmware mengirim ulang → backend sebaiknya **deduplikasi pada (device_id, timestamp)**.
- Timestamp: ISO 8601 WIB, mis. `2026-11-07T12:34:56.789+07:00`.

## 12. Batasan yang diketahui

- Satu fasa, satu CT. Instalasi 3 fasa butuh 3 CT + 3 tegangan (belum didukung).
- ADC ESP32 tidak linear di dekat 0 V dan > ~2,45 V; akurasi arus kecil (< ~0,2 A)
  terbatas derau — di bawah `I_NOISE_FLOOR_A` (0,08 A) arus dianggap 0.
- Akurasi frekuensi bergantung pada kristal ESP32 (biasanya ±10–40 ppm);
  belum diverifikasi terhadap referensi.
- HTTPS tanpa `WASKITA_ROOT_CA` = tanpa verifikasi sertifikat (hanya untuk uji).
- Kalibrasi, akurasi, dan ketahanan jangka panjang **belum divalidasi di lapangan**.
