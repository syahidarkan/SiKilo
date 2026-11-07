# Lapisan data dan hitung NOTA LISTRIK

Folder ini berisi semua logika di belakang layar prototype: tipe data, sumber data simulasi, fungsi hitung PLTS dan pemborosan, template pesan WhatsApp, dan validasi alur teknisi. Tidak ada komponen React di sini, jadi layar bisa dibangun terpisah tanpa saling bentrok.

## Susunan

| Berkas | Isi |
|---|---|
| `tipe.ts` | Kontrak data (bagian 6 brief), dipakai juga oleh backend FastAPI nanti |
| `sumber-data.ts` | Antarmuka `SumberData`, satu-satunya pintu data untuk layar |
| `simulasi/` | Generator ber-seed, skenario konveksi, kerangka skenario kosong, `SumberSimulasi` |
| `hitung/` | Fungsi murni: rupiah, skenario PLTS, kategori rapor, deteksi pemborosan, ringkasan pemilik, ringkasan dinas, penyusun rapor |
| `pesan/nota-wa.ts` | Empat template pesan: sambutan, mingguan, alat terputus, rapor akhir |
| `teknisi/validasi.ts` | Validasi tiap langkah pasang dan cabut, dengan error per kolom |
| `format.ts` | Format id-ID: `Rp 125.000`, `2,4 kWh`, `14 Nov 2026`, `08.00` |
| `waktu.ts` | Aritmetika tanggal dalam WIB tetap, tidak bergantung zona waktu mesin |

## Cara pakai dari layar

```ts
import { buatSumberSimulasi } from "@/lib/simulasi";
import { rincianPerMesin, biayaPeriode, heatmapMingguan } from "@/lib/hitung/ringkasan";

const sumber = buatSumberSimulasi(); // simpan satu instans per sesi, mis. di React context

const [lokasi, total, perMesin, mesin, p] = await Promise.all([
  sumber.ambilLokasi("umkm-b"),
  sumber.ambilTotalPerJam("umkm-b"),
  sumber.ambilPemakaianPerMesin("umkm-b"), // kosong selama kalibrasi
  sumber.daftarMesin("umkm-b"),
  sumber.ambilParameter(),
]);
const rincian = rincianPerMesin(perMesin, mesin, p);
```

Layar hanya boleh memanggil method `SumberData` dan fungsi `lib/hitung`. Jangan mengimpor `simulasi/skenario-*.ts` langsung, karena nanti `SumberSimulasi` diganti implementasi yang memanggil FastAPI dengan method yang sama.

Kontrol khusus prototype (bukan bagian `SumberData`) ada di `SumberSimulasi`:

| Method | Untuk keadaan |
|---|---|
| `aturJeda(ms)` | Memuat (kerangka) |
| `aturGagal(true/false)` | Error memuat dan tombol "Coba lagi" |
| `aturStatusAlat(id, "offline", waktu)` | Alat offline; data berhenti di jam terakhir terlihat |
| `buatSumberSimulasi("kosong")` | Program baru dimulai, belum ada rapor |
| `snapshot()` / `pulihkan()` | Menyimpan perubahan dari alur teknisi ke `sessionStorage` agar bertahan saat halaman dimuat ulang |

Lokasi `umkm-a` sedang kalibrasi, `umkm-b` sedang mengukur (hari ke-9 dari 21), `umkm-c` rapor siap, dan `umkm-d` menunggu pasang. Waktu "sekarang" di simulasi tetap 14 Nov 2026 15.20 WIB.

## Aturan hitung

- Energi terpakai sendiri = Σ min(beban, produksi); terbuang = Σ max(0, produksi − beban), per jam. Ekspor ke PLN dianggap tidak bernilai (Permen ESDM 2/2024).
- Produksi per kWp: setengah sinus 06.00–18.00 yang totalnya `yieldHarianPerKWp`. Perkiraan kasar, akan diganti pvlib dan data NASA POWER.
- Profil setahun = jumlah hari dengan data lengkap × (365 / jumlah hari tersebut). Hari dengan jam bolong tidak dipakai.
- Rekomendasi kWp: ukuran terbesar yang produksi terbuangnya tidak lebih dari `ambangTerbuangRasio`. Aturan ini berbasis energi, jadi tetap jalan walau tarif dan harga kosong.
- Kategori rapor, diperiksa berurutan: efisiensi dulu (pemborosan > `ambangPemborosanRasio`), belum layak (tidak ada ukuran yang pas), belum bisa dihitung (tarif/harga kosong), layak (balik modal < `ambangBalikModalTahun`), selain itu belum layak.
- Tarif atau harga `null` menghasilkan rupiah `null`. Layar menampilkan `[TARIF PLN]` atau `[HARGA INSTALLER]` lewat `formatRupiah`, tidak pernah angka tebakan.

## Nilai yang harus diganti

### Keputusan tim (`hitung/parameter.ts`)

| Parameter | Sekarang | Catatan |
|---|---|---|
| `tarifPerKWh` | `null` | Golongan tarif PLN UMKM uji coba |
| `hargaPerKWp` | `null` | Dari penawaran installer |
| `yieldHarianPerKWp` | 4,0 | SIMULASI, ganti hasil pvlib |
| `ambangPemborosanRasio` | 15% | Batas "efisiensi dulu" |
| `ambangBalikModalTahun` | 6 tahun | Batas "layak" |
| `ambangTerbuangRasio` | 20% | Sangat menentukan rekomendasi: di UMKM Contoh C, 10% menghasilkan 1 kWp, 20% menghasilkan 5 kWp |
| `ambangKeyakinan` | 0,6 | Di bawah ini pesan memakai "kemungkinan" dan tanpa angka hemat |
| Batas kWp | = daya tersambung (kVA) | `batasKWp()` di `hitung/plts.ts`, menunggu jawaban soal batas kapasitas Permen ESDM 2/2024 |

### SIMULASI (`simulasi/skenario-konveksi.ts`, `simulasi/sumber-simulasi.ts`, `simulasi/generator.ts`)

Semua angka di bawah ini karangan yang dibuat wajar untuk konveksi kecil, bukan hasil ukur.

| Nilai | A (kalibrasi) | B (mengukur) | C (rapor siap) |
|---|---|---|---|
| Daya tersambung | 3.500 VA | 5.500 VA | 7.700 VA |
| Mesin jahit (kelompok) | 6 unit, 0,7 kW | 12 unit, 1,4 kW | 20 unit, 2,4 kW |
| Mesin obras (kelompok) | 2 unit, 0,25 kW | 4 unit, 0,5 kW | 6 unit, 0,8 kW |
| Setrika uap | 1 unit, 0,9 kW | 2 unit, 1,8 kW | 3 unit, 2,7 kW |
| Mesin potong kain | - | 0,35 kW | 0,5 kW |
| Lampu dan kipas | 0,4 kW | 0,6 kW | 1,0 kW |
| Kulkas | - | - | 0,12 kW terus-menerus |
| Beban "lainnya" | 0,12 kW + 8% beban mesin | 0,15 kW + 8% | 0,2 kW + 8% |

Daya di atas adalah rata-rata seluruh kelompok saat jam kerja, bukan daya papan nama.

- Jam kerja 08.00–16.00, istirahat 12.00–13.00, libur Minggu. Jam pertama kerja 70% beban. Saat istirahat 5% beban.
- Keyakinan pemisah beban: jahit 0,84–0,86, obras 0,50–0,55 (sengaja rendah), setrika 0,90–0,91, potong 0,70–0,72, lampu 0,78–0,80, kulkas 0,66; variasi ±0,05 per jam.
- Pemborosan yang ditanam: setrika B panas saat istirahat (peluang 70% per hari kerja, 1,5 kW), lampu B menyala 16.00–19.00 (45%, 0,5 kW), setrika C panas saat istirahat (80%, 2,3 kW), mesin potong C menyala 22.00–02.00 (30%, 0,3 kW).
- Jam bolong: B 10 Nov 2026 02.00–06.00, C 20 Okt 2026 10.00–15.00.
- Masa ukur standar 21 hari (`MASA_UKUR_HARI`). Seed skenario 20261107.
- Deteksi pemborosan: jam dianggap "menyala" bila di atas 25% rata-rata jam kerja mesin itu; temuan di bawah 0,5 kWh per minggu disembunyikan (`hitung/pemborosan.ts`).

## Uji

```bash
npm test          # Vitest, semua tes di tests/
npm run typecheck # tsc --noEmit untuk seluruh proyek
```
