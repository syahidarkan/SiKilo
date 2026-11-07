# Casing sensor NOTA LISTRIK

Model parametrik OpenSCAD: badan dan tutup. Ukuran luar dihitung otomatis dari komponen, tebal dinding, dan jarak bebas. Dengan nilai sementara sekarang, ukuran luar badan **119,7 x 88,3 x 29,4 mm** (dicetak `ECHO` saat render).

## Catatan keselamatan

Casing cetak 3D ini hanya untuk prototype dan demo. Untuk dipasang di lokasi UMKM, pakai material tahan api (kelas UL94 V-0) atau box listrik pabrikan, dan rakitannya diperiksa orang yang kompeten di instalasi listrik. Untuk prototype, PETG atau ABS lebih cocok daripada PLA karena lebih tahan panas.

## Berkas

| Berkas | Isi |
|---|---|
| `casing.scad` | Model parametrik. Semua angka ada di bagian PARAMETER di atas file |
| `casing_badan.stl` | Badan: dua ruang, lubang gland, jack, USB, ventilasi, boss sekrup, tab dinding |
| `casing_tutup.stl` | Tutup, ditambah sumbat kecil penutup celah USB di sebelahnya |
| `render_depan.png`, `render_belakang.png` | Rakitan (tutup diangkat 25 mm) dari depan-kanan dan belakang-kiri |
| `render_atas_badan.png` | Badan dari atas: sekat, celah kabel, rel ESP32, boss |

## Cara render ulang

Butuh OpenSCAD 2021.01 atau lebih baru. `xvfb-run` hanya diperlukan di server tanpa layar.

```bash
cd cad
openscad -D 'bagian="badan"' -o casing_badan.stl casing.scad
openscad -D 'bagian="tutup"' -o casing_tutup.stl casing.scad
xvfb-run -a openscad --imgsize=1600,1200 --viewall --autocenter --colorscheme=Tomorrow \
  --camera=0,0,0,62,0,25,0 -o render_depan.png casing.scad
xvfb-run -a openscad --imgsize=1600,1200 --viewall --autocenter --colorscheme=Tomorrow \
  --camera=0,0,0,62,0,205,0 -o render_belakang.png casing.scad
xvfb-run -a openscad --render --imgsize=1600,1200 --viewall --autocenter --colorscheme=Tomorrow \
  -D 'bagian="badan"' --camera=0,0,0,30,0,0,0 -o render_atas_badan.png casing.scad
```

Opsi: `-D 'pakai_din=true'` mengganti tab dinding dengan klip rel DIN TS35, dan `-D 'pakai_insert=false'` mengganti lubang insert M3 dengan lubang pilot sekrup tapping. Kedua opsi sudah dicoba render dan menghasilkan mesh manifold.

## Susunan

- Ruang tegangan tinggi (kiri): terminal blok, catu daya AC-DC, ZMPT101B. Masuk kabel 220 V lewat gland di dinding kiri. Tulisan timbul "220 V" ada di dinding yang sama.
- Ruang tegangan rendah (kanan): ESP32 di atas dua rel dudukan, lalu modul IC energi. Jack 3,5 mm untuk SCT-013 dan celah USB ada di dinding kanan.
- Sekat penuh setinggi badan. Satu-satunya jalur antar-ruang adalah celah kabel tegangan rendah 6 x 4 mm di puncak sekat. Tutup punya rusuk yang menyambung sekat sampai ke pelat tutup.
- Ventilasi berupa celah 1,6 mm di dinding depan dan belakang, tidak ada lubang di atas.
- Tutup disekrup M3 di empat boss sudut. LED daya, WiFi, dan data ada di atas ruang tegangan rendah, dengan label timbul. Ceruk stiker QR ada di atas ruang tegangan tinggi.

## Parameter yang harus diukur ulang

Semua bertanda `// UKUR ULANG` di `casing.scad`. Nilai sekarang adalah perkiraan dari ukuran umum di pasaran, bukan hasil ukur komponen tim.

| Parameter | Arti | Nilai sementara (mm) |
|---|---|---|
| `esp32_p`, `esp32_l`, `esp32_t` | Papan ESP32 DevKit: panjang, lebar, tinggi | 51,5 / 28,5 / 13 |
| `esp32_pcb` | Tebal PCB ESP32 | 1,6 |
| `energi_p`, `energi_l`, `energi_t` | Modul IC pengukur energi | 40 / 30 / 10 |
| `zmpt_p`, `zmpt_l`, `zmpt_t` | Modul ZMPT101B | 49 / 19,5 / 22 |
| `psu_p`, `psu_l`, `psu_t` | Catu daya AC-DC | 34 / 20 / 15 |
| `terminal_p`, `terminal_l`, `terminal_t` | Terminal blok | 15,5 / 10 / 16 |
| `gland_d` | Lubang cable gland (PG7) | 12,5 |
| `jack_d` | Lubang jack 3,5 mm panel mount | 6,2 |
| `led_d` | Lubang LED 5 mm | 5,2 |
| `usb_l`, `usb_t`, `usb_pusat` | Celah USB dan tinggi pusat soket dari bawah PCB | 12 / 7,5 / 3,5 |
| `qr_sisi` | Sisi stiker QR ID alat | 25 |
| `insert_d`, `insert_dalam` | Lubang insert ulir M3 (sesuai merek insert) | 4,0 / 5,7 |
| `tapping_d` | Lubang pilot sekrup tapping | 2,5 |
| `kepala_d` | Diameter kepala sekrup M3 | 6,2 |
| `sekrup_dinding_d` | Lubang sekrup dinding pada tab | 4,5 |

Parameter yang tidak perlu diukur, tapi boleh diubah: `tebal_dinding` (2,4), `celah` (0,3), `jarak` (3), `jarak_atas` (5), `pakai_din` (false).

## Yang belum dibuat

- Lubang baut atau dudukan khusus untuk setiap modul. Posisi lubang modul belum diketahui, jadi sementara modul ditempel dengan double tape busa atau lem panas, dan ESP32 duduk di rel.
- Klip DIN baru berupa geometri dasar dan belum dicoba di rel sungguhan. Kekakuan lidah pegasnya bergantung pada material dan arah cetak.
- Belum ada model komponen di dalam rakitan, jadi bentrok antar-komponen hanya dicegah lewat perhitungan ukuran, bukan pemeriksaan visual.
