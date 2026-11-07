# Brief Claude Code: Prototype Desain NOTA LISTRIK

7 Nov 2026 · @al

## 1. Konteks dan tujuan

Bangun prototype desain yang bisa diklik untuk NOTA LISTRIK, ditambah model 3D parametrik casing sensor. Prototype ini dipakai untuk menguji alur dengan pemilik UMKM dan Disperinaker, dan untuk demo UNS Innovation Hackathon 2026 (Energy Track, Subtema C). Belum ada backend, sensor, atau AI sungguhan.

NOTA LISTRIK membantu UMKM di Sukoharjo dengan tiga hal:

1. Satu set sensor dijepit di kabel dekat meteran selama 2 sampai 4 minggu, lalu dipindah ke UMKM lain (alat bergilir).
2. AI pemisah beban (NILM) memecah pemakaian listrik per mesin per jam, lalu menandai listrik yang terbuang tanpa menghasilkan apa-apa, dalam rupiah.
3. Dari pola pemakaian siang hari, sistem menghitung ukuran PLTS atap yang pas dan lama balik modalnya. Hasilnya rapor energi untuk diajukan ke bank atau koperasi.

Alasan ukuran PLTS penting: sejak Permen ESDM Nomor 2 Tahun 2024, listrik PLTS atap yang diekspor ke jaringan PLN tidak mengurangi tagihan. Panel hanya bernilai sebesar listrik yang dipakai sendiri saat matahari bersinar, jadi panel kebesaran membuang uang.

Pengguna yang dilayani prototype ini:

| Pengguna | Kebutuhan utama | Perangkat |
|---|---|---|
| Pemilik UMKM | Tahu mesin mana yang membuang uang, dan apa yang harus dilakukan | HP, lewat WhatsApp dan web mobile |
| Teknisi pemasang | Memasang, mengaitkan, dan mencabut alat dengan cepat dan aman | HP |
| Petugas bank atau koperasi | Menilai kelayakan pinjaman PLTS dari satu dokumen | Rapor cetak atau PDF |
| Disperinaker Sukoharjo | Melihat sentra mana yang boros dan siapa yang layak dibantu PLTS | Laptop |

## 2. Ruang lingkup

Yang dibangun: lima layar web yang saling terhubung, berjalan dengan data simulasi, plus satu model 3D casing di OpenSCAD.

| Bagian | Isi | Prioritas |
|---|---|---|
| Nota WhatsApp | Pratinjau pesan di bingkai HP | Wajib |
| Rapor energi | Halaman A4 siap cetak | Wajib |
| Dashboard pemilik | Web mobile | Wajib |
| Aplikasi teknisi | Alur pasang, kalibrasi, cabut alat | Wajib |
| Dashboard dinas | Web desktop, ringkasan per sentra | Boleh sederhana |
| Casing 3D | Model parametrik OpenSCAD, STL, render PNG | Wajib |

Tidak dibangun di tahap ini:

- Firmware ESP32, MQTT, database, dan login sungguhan.
- Model NILM, LightGBM, pvlib, atau perhitungan PLTS yang presisi. Angka di prototype berasal dari generator data simulasi (bagian 6).
- Integrasi WhatsApp Business API. Pesan cukup ditampilkan sebagai pratinjau.
- Agen penjadwal mesin berbasis reinforcement learning.
- Halaman marketing atau landing page.

Struktur kode tetap harus memisahkan tampilan dari sumber data, supaya data simulasi nanti bisa diganti API FastAPI tanpa membongkar komponen.

## 3. Cara kerja yang diharapkan

Sebelum menulis kode, tanyakan ke tim hal-hal berikut dalam satu pesan. Kalau tidak dijawab, lanjut dengan default di kolom kanan dan catat sebagai asumsi.

| Pertanyaan | Default bila belum dijawab |
|---|---|
| Sektor UMKM uji coba dan daftar mesinnya | Skenario konveksi dari bagian 6, berlabel simulasi |
| Golongan dan tarif PLN per kWh yang dipakai | Variabel `TARIF_PER_KWH` kosong, layar menampilkan "[TARIF PLN]" |
| Harga PLTS per kWp dari penawaran installer | Variabel kosong, layar menampilkan "[HARGA INSTALLER]" |
| Ukuran komponen elektronik yang sudah dibeli | Nilai sementara di OpenSCAD dengan komentar UKUR ULANG |
| Nama produk, logo, dan font yang sudah dipilih | Teks "NOTA LISTRIK" polos, kotak "[LOGO]" |

Urutan kerja:

1. Tulis rencana singkat: struktur folder, daftar route, model data. Tunggu persetujuan.
2. Buat token desain (warna, tipografi, jarak) dan komponen dasar.
3. Buat generator data simulasi dan tipe datanya.
4. Bangun layar sesuai urutan prioritas di bagian 2.
5. Buat model OpenSCAD casing.
6. Jalankan pemeriksaan di bagian 13, lalu laporkan.

Aturan kerja:

- Bahasa antarmuka Bahasa Indonesia sehari-hari. Istilah teknis seperti kWh dan kWp boleh, tapi rupiah selalu ditampilkan lebih dulu.
- Format angka id-ID: Rp 125.000, 2,4 kWh, tanggal 14 Nov 2026.
- Jangan menulis "selesai" atau "berhasil" tanpa bukti dari output build, lint, atau tangkapan layar.
- Komentar kode hanya untuk menjelaskan alasan, bukan mengulang isi kode.
- Jangan menambah fitur atau abstraksi di luar brief ini. Kalau ada ide tambahan, tulis di laporan akhir.

## 4. Arah desain

Konsep visualnya nota belanja dan kuitansi warung: kertas, tinta, angka rupiah yang rapi berjajar. Nama produknya NOTA LISTRIK, dan pemilik UMKM sudah terbiasa membaca nota, jadi bentuk ini terasa akrab tanpa perlu diajari. Desain harus tetap punya karakter kalau nama dan logo dihapus.

Palet awal (boleh disesuaikan, tapi setiap perubahan harus lolos kontras WCAG AA):

| Peran | Nama | Hex | Pemakaian |
|---|---|---|---|
| Inti | Kertas | `#F6F3EC` | Latar halaman dan kartu |
| Inti | Tinta | `#1E1E1C` | Teks utama, garis tabel |
| Inti | Biru stempel | `#1F4E79` | Tautan, tombol utama, fokus |
| Aksen | Kuning surya | `#E8A317` | Hanya isian grafik produksi panel dan penanda jam matahari, tidak untuk teks di latar terang |
| Status | Merah stempel | `#A33A2A` | Hanya untuk pemborosan dan error |

Tipografi: IBM Plex Sans untuk teks dan IBM Plex Mono untuk angka (tabular, rata kanan), dimuat dari Google Fonts dengan fallback sistem. Angka rupiah adalah elemen terbesar di setiap layar pemilik.

Elemen khas yang boleh dipakai: garis putus-putus pemisah seperti struk, nomor nota di pojok, tabel rincian bergaya kuitansi, cap atau stempel berbentuk persegi panjang miring tipis. Stempel status harus jujur: data simulasi diberi stempel "DATA SIMULASI", bukan "TERVERIFIKASI".

Grafik: warna rata tanpa gradien, garis tipis, label langsung di grafik daripada legenda terpisah bila memungkinkan.

Dilarang:

- Gradien biru-ungu atau ungu-pink, glow, glassmorphism, latar grid.
- Semua elemen berbentuk pil, ikon sparkle, robot, atau petir sebagai hiasan.
- Badge "AI Powered" atau "New", tombol "Get Started" dan "Learn More".
- Pola template: hero dengan 3 kartu, "How It Works" 3 langkah, deretan logo "Trusted by", footer 4 kolom.
- Statistik, testimonial, atau nama UMKM yang terdengar asli tetapi karangan. Gunakan nama seperti "UMKM Contoh A".
- Meniru gaya Linear, Vercel, atau Stripe.

Wajib:

- Target sentuh minimal 44 x 44 px, tidak ada scroll menyamping di lebar 360 px.
- Kontras teks 4,5:1, teks besar 3:1.
- Semua bisa dipakai dengan keyboard, fokus terlihat jelas (cincin 2 px biru stempel).
- Setiap layar punya keadaan kosong, memuat, dan error yang didesain, bukan teks default.
- Setiap tombol dan tautan benar-benar melakukan sesuatu. Kalau fiturnya di luar cakupan, jangan tampilkan tombolnya.

## 5. Stack dan struktur proyek

Pakai Next.js (App Router) dengan TypeScript, karena dashboard produk nanti juga Next.js dan kodenya bisa dipakai ulang. Styling dengan Tailwind CSS yang membaca token dari CSS variables. Grafik batang dan garis dengan Recharts; heatmap 7 x 24 jam dibuat sendiri dengan SVG. Uji fungsi hitung dengan Vitest, tangkapan layar dengan Playwright. Pilih versi stabil yang sudah dirilis minimal dua minggu, dan kunci versinya di lockfile.

Struktur folder yang diharapkan:

```
nota-listrik-prototype/
  app/
    page.tsx                  # indeks prototype: daftar layar untuk presentasi
    wa/page.tsx               # pratinjau nota WhatsApp
    pemilik/page.tsx          # dashboard pemilik
    pemilik/mesin/[id]/page.tsx
    rapor/[lokasiId]/page.tsx # rapor energi A4
    teknisi/page.tsx          # daftar alat dan lokasi
    teknisi/pasang/page.tsx   # alur pemasangan
    teknisi/cabut/page.tsx    # alur pencabutan
    dinas/page.tsx            # dashboard dinas
  components/                 # komponen UI dan grafik
  lib/
    tipe.ts                   # tipe data (bagian 6)
    sumber-data.ts            # antarmuka SumberData
    simulasi/                 # generator data simulasi + skenario
    hitung/                   # fungsi murni: rupiah, skenario PLTS, skor
    format.ts                 # format id-ID
  styles/tokens.css
  cad/
    casing.scad
    README.md                 # daftar parameter yang harus diukur ulang
  tests/
```

Semua komponen mengambil data lewat `SumberData`, bukan mengimpor file simulasi langsung. Nanti implementasi simulasi diganti implementasi yang memanggil FastAPI.

Halaman indeks `/` bukan landing page. Isinya daftar layar dengan satu kalimat tujuan tiap layar dan tautan, untuk dipakai saat presentasi ke juri atau uji pengguna. Di setiap layar ada pita tipis "DATA SIMULASI" yang tidak bisa disembunyikan.

## 6. Model data dan data simulasi

Tipe data minimal. Nama boleh disesuaikan, tapi strukturnya dipertahankan karena akan dipakai backend nanti.

```ts
type Lokasi = {
  id: string; nama: string;            // "UMKM Contoh A"
  sektor: string; sentra: string;
  dayaTersambungVA: number;
  jamKerja: { mulai: string; selesai: string; hariLibur: number[] };
  status: "menunggu_pasang" | "kalibrasi" | "mengukur" | "rapor_siap" | "plts_terpasang" | "verifikasi";
  masaUkur: { mulai: string; selesaiRencana: string };
};

type Alat = { id: string; lokasiId: string | null; status: "online" | "offline" | "di_gudang"; terakhirTerlihat: string };

type Mesin = { id: string; lokasiId: string; nama: string; jenis: string; jumlah: number; dikelompokkan: boolean };

type PemakaianJam = { lokasiId: string; mesinId: string | "lainnya"; jam: string; kWh: number; keyakinan: number };

type Pemborosan = {
  id: string; lokasiId: string; mesinId: string;
  jenis: "nyala_luar_jam_kerja" | "panas_menganggur" | "beban_malam_tinggi";
  kWhPerMinggu: number; rupiahPerMinggu: number | null;  // null bila tarif belum diisi
  saran: string;
};

type SkenarioPLTS = {
  kWp: number; terpakaiSendiri_kWh_tahun: number; terbuang_kWh_tahun: number;
  hematRupiahTahun: number | null; biayaRupiah: number | null; balikModalTahun: number | null;
};

type Rapor = { lokasiId: string; nomor: string; tanggal: string; kategori: "layak" | "efisiensi_dulu" | "belum_layak"; skenario: SkenarioPLTS[]; rekomendasiKWp: number | null; pemborosan: Pemborosan[]; catatanKeterbatasan: string[] };
```

Generator data simulasi:

- Deterministik dengan seed, supaya tampilan sama setiap kali dibuka dan bisa ditangkap layar.
- Satu skenario sektor konveksi berisi 3 lokasi dengan status berbeda: sedang kalibrasi, sedang mengukur, dan rapor siap. Skenario kedua cukup kerangka kosong agar tim bisa mengisi sektor lain.
- Daya tiap mesin, jam kerja, dan pola pemakaian dipilih wajar oleh Claude Code, ditandai `// SIMULASI` di kode, dan didaftar di README beserta catatan bahwa angka ini harus diganti data lapangan.
- Masukkan pola pemborosan yang sengaja ditanam (misalnya setrika uap tetap panas saat istirahat siang) supaya layar pemborosan punya isi.
- Sisakan sebagian energi sebagai "lainnya" dan beri nilai keyakinan per mesin, karena NILM sungguhan tidak pernah mengenali 100 persen.

Perhitungan PLTS di prototype (fungsi murni di `lib/hitung/`, diuji Vitest):

```
E_terpakai = Σ_t min(B_t, P_t)        E_terbuang = Σ_t max(0, P_t − B_t)
```

B adalah beban per jam, P produksi panel per jam. Produksi per kWp memakai kurva sederhana jam 06.00 sampai 18.00 yang diskalakan oleh parameter `YIELD_HARIAN_PER_KWP`, diberi label "perkiraan kasar, akan diganti pvlib dan data NASA POWER". Hemat rupiah = energi terpakai sendiri x tarif. Balik modal = biaya pasang dibagi hemat per tahun. Bila tarif atau harga per kWp belum diisi, fungsi mengembalikan null dan layar menampilkan placeholder, bukan angka karangan.

Kategori rapor memakai aturan tertulis, bukan skor kotak hitam: "efisiensi dulu" bila pemborosan melebihi ambang persentase dari total pemakaian, "layak" bila skenario terbaik balik modal di bawah ambang tahun, selain itu "belum layak". Kedua ambang jadi parameter yang diputuskan tim, dan aturannya dicetak di rapor.

## 7. Layar: nota WhatsApp (`/wa`)

Layar ini menampilkan pesan dalam bingkai HP bergaya chat WhatsApp, tanpa meniru logo atau merek WhatsApp. Di atas bingkai ada pilihan lokasi, jenis pesan, dan minggu ke berapa. Pesan disusun dari template berisi angka hasil `lib/hitung/`, bukan teks bebas.

Empat jenis pesan:

1. Sambutan saat alat dipasang. Menjelaskan apa yang diukur, berapa lama alat terpasang, dan bahwa usaha tetap jalan seperti biasa.
2. Nota mingguan. Inti produk. Isinya total biaya listrik minggu ini, satu mesin dengan pemborosan terbesar beserta rupiahnya, dan satu saran yang bisa dikerjakan besok.
3. Alat terputus. Dikirim bila alat tidak mengirim data lebih dari beberapa jam, dengan langkah cek sederhana (stopkontak, WiFi) dan nomor teknisi.
4. Rapor akhir saat alat dicabut. Ringkasan masa ukur, kategori rapor, ukuran PLTS yang disarankan, dan tautan ke rapor.

Contoh struktur nota mingguan (isi `{}` dari data, bukan dari model bahasa):

```
NOTA LISTRIK · Minggu ke-{n}
{namaUsaha}

Biaya listrik minggu ini: {rupiahMinggu}

Terbuang: {rupiahTerbuang}
{namaMesin} tetap panas saat istirahat {jamMulai}-{jamSelesai}, {hariTerjadi} dari {hariKerja} hari kerja.

Saran besok: matikan {namaMesin} saat istirahat siang.
Perkiraan hemat: {rupiahHematPerBulan} per bulan.

Rincian per mesin: {tautanDashboard}
```

Aturan pesan:

- Satu pesan memuat satu saran saja. Pesan harus terbaca habis tanpa menggulir panjang di HP.
- Rupiah dulu, kWh hanya di dashboard.
- Bila keyakinan NILM untuk mesin tersebut rendah, kalimatnya memakai "kemungkinan" dan pesan tidak memberi angka hemat.
- Bila tarif belum diisi, tampilkan "[TARIF PLN]" di pratinjau, jangan menebak.
- Tombol "Salin teks" di bawah bingkai, berfungsi sungguhan, untuk dipakai saat uji ke pemilik UMKM.

## 8. Layar: dashboard pemilik (`/pemilik`)

Didesain untuk HP lebar 360 sampai 430 px. Pemilik harus bisa menjawab "uang listrik saya hilang ke mana dan apa yang harus saya lakukan" dalam 10 detik pertama. Urutan isi dari atas:

1. Kepala nota. Nama usaha, nomor nota, status masa ukur ("Hari ke-9 dari 21"), dan status alat (online, terakhir kirim data jam berapa).
2. Angka utama. Biaya listrik minggu ini dan rupiah yang terbuang, berdampingan. Yang terbuang memakai merah stempel.
3. Daftar pemborosan. Kartu per temuan: mesin, kapan terjadi, rupiah per minggu, satu saran. Diurutkan dari rupiah terbesar.
4. Rincian per mesin. Tabel bergaya kuitansi: nama mesin, porsi biaya (batang horizontal), rupiah, dan penanda keyakinan rendah bila di bawah ambang. Baris terakhir "lainnya". Ketuk baris membuka detail mesin.
5. Pola per jam. Heatmap 7 hari x 24 jam untuk total pemakaian. Jam kerja ditandai garis, jam matahari (sekitar 08.00 sampai 15.00) diberi latar kuning surya tipis, supaya terlihat berapa banyak pemakaian yang nanti bisa disuplai panel.

Detail mesin (`/pemilik/mesin/[id]`): grafik pemakaian per jam selama masa ukur, pemborosan khusus mesin itu, jumlah unit bila dikelompokkan (misalnya 12 mesin jahit dihitung satu kelompok), dan penjelasan keyakinan dalam satu kalimat biasa.

Keadaan yang wajib didesain:

| Keadaan | Yang tampil |
|---|---|
| Masa kalibrasi | Penjelasan bahwa minggu pertama alat sedang belajar mengenali mesin, angka per mesin belum tersedia, total pemakaian sudah tampil |
| Belum ada pemborosan | Pesan positif singkat, tanpa ilustrasi berlebihan |
| Alat offline | Peringatan di kepala nota dengan jam terakhir data masuk dan langkah cek |
| Memuat | Kerangka bentuk tabel dan angka, bukan pemutar |
| Error memuat | Penjelasan dan tombol "Coba lagi" yang benar-benar memuat ulang |
| Tarif belum diisi | Angka kWh tampil, kolom rupiah berisi "[TARIF PLN]" |

## 9. Layar: rapor energi (`/rapor/[lokasiId]`)

Dokumen paling penting di depan juri dan petugas koperasi. Maksimal 2 halaman A4, bisa dicetak langsung dari browser dengan CSS `@media print` (margin, pemutusan halaman, tanpa navigasi). Pembacanya bukan orang teknik listrik, jadi halaman pertama harus bisa dipahami tanpa membaca halaman kedua.

Halaman 1, ringkasan keputusan:

1. Kepala rapor: nomor rapor, tanggal, nama usaha, sektor, daya tersambung, periode ukur, kotak "[LOGO]".
2. Stempel kategori: "LAYAK PLTS", "EFISIENSI DULU", atau "BELUM LAYAK", dengan satu kalimat alasan.
3. Rekomendasi: ukuran panel dalam kWp, perkiraan hemat per bulan, biaya pasang, dan balik modal dalam tahun.
4. Grafik utama: rata-rata beban per jam hari kerja dibandingkan produksi panel ukuran yang disarankan. Bagian produksi yang melebihi beban diberi arsir sebagai "terbuang", supaya terlihat kenapa panel lebih besar tidak lebih baik.
5. Tiga pemborosan terbesar beserta rupiahnya, sebagai langkah sebelum memasang panel.

Halaman 2, dasar perhitungan:

| Isi | Keterangan |
|---|---|
| Tabel skenario | Beberapa ukuran kWp: terpakai sendiri, terbuang, hemat per tahun, biaya, balik modal. Baris rekomendasi ditandai |
| Rincian pemakaian per mesin | Porsi dan rupiah, dengan keyakinan |
| Asumsi | Tarif, harga per kWp, data matahari yang dipakai, aturan kategori dan ambangnya |
| Keterbatasan | Lama masa ukur, akurasi pengenalan mesin, profil setahun yang diperpanjang dari beberapa minggu, belum termasuk perubahan pesanan musiman |
| Status verifikasi | "Belum diverifikasi setelah pemasangan", dengan penjelasan bahwa sensor bisa dipasang ulang untuk membuktikan penghematan |

Ketentuan:

- Setiap angka di rapor berasal dari fungsi di `lib/hitung/`, dan bagian asumsi menyebut sumbernya.
- Bila tarif atau harga belum diisi, stempel kategori diganti "BELUM BISA DIHITUNG" dan kolom rupiah berisi placeholder.
- Pita "DATA SIMULASI" ikut tercetak.
- Uji tampilan cetak di Chrome: tidak ada tabel yang terpotong di tengah baris.

## 10. Layar: aplikasi teknisi (`/teknisi`)

Karena alat bergilir antar-UMKM, alur pasang dan cabut harus cepat, tidak bisa salah kaitkan alat ke lokasi, dan mengingatkan keselamatan. Didesain untuk HP, dipakai dengan satu tangan di dekat box meteran.

Halaman `/teknisi`: daftar alat (di gudang, terpasang, offline) dan daftar lokasi yang menunggu pemasangan atau pencabutan, masing-masing dengan tombol aksi.

Alur pasang (`/teknisi/pasang`), satu langkah per layar dengan indikator posisi:

1. Pilih alat. Masukkan ID alat dari label QR. Pemindaian kamera boleh ditiru dengan kolom ketik, tapi beri tahu di layar bahwa ini simulasi.
2. Pilih lokasi UMKM dari daftar "menunggu pasang".
3. Daftar periksa keselamatan. Wajib dicentang semua sebelum lanjut: sensor dijepit di kabel sisi pelanggan setelah meteran, tidak menyentuh kWh meter dan segel PLN, casing tertutup rapat, kabel tegangan terpasang di terminal.
4. Cek koneksi. Tampilkan keadaan "menunggu data", "data masuk" (dengan daya terbaca saat ini), atau "gagal" dengan saran (WiFi, catu daya). Simulasikan ketiganya, bisa dipilih dari kontrol khusus prototype.
5. Daftar mesin. Isi mesin utama di lokasi: nama, jenis, jumlah unit, centang "kelompokkan" untuk mesin sejenis yang banyak.
6. Kalibrasi smart plug. Kaitkan setiap smart plug ke satu mesin. Tampilkan pengingat bahwa smart plug dicabut setelah minggu pertama.
7. Selesai. Ringkasan, tanggal rencana cabut, dan pratinjau pesan sambutan WhatsApp yang akan diterima pemilik.

Alur cabut (`/teknisi/cabut`): pilih lokasi, konfirmasi masa ukur sudah cukup (tampilkan berapa hari data lengkap dan berapa hari bolong), konfirmasi smart plug dan sensor sudah dicabut, lalu ubah status alat menjadi "di gudang" dan lokasi menjadi "rapor siap".

Validasi: tombol "Lanjut" tidak aktif sampai langkah terisi benar, dan pesan error muncul di dekat kolom yang salah. Semua perubahan status tersimpan di state aplikasi selama sesi, dan terlihat di layar lain (misalnya lokasi yang baru dipasang muncul di dashboard pemilik dan dinas).

## 11. Layar: dashboard dinas (`/dinas`)

Untuk petugas Disperinaker di laptop (lebar 1280 px ke atas), tetap terbaca di tablet. Tujuannya memilih UMKM mana yang didampingi efisiensi dan mana yang diajukan untuk PLTS. Data per UMKM ditampilkan sebatas ringkasan; rincian per mesin hanya terbuka bila pemilik setuju (cukup ditandai kolom "izin rincian" di prototype).

Isi:

1. Ringkasan program. Jumlah alat, alat terpasang, UMKM yang sudah selesai diukur, rapor per kategori.
2. Per sentra atau sektor. Batang horizontal: total pemborosan rupiah per bulan dan jumlah UMKM "layak PLTS".
3. Tabel UMKM. Nama, sentra, status masa ukur, kategori rapor, rekomendasi kWp, pemborosan per bulan, tautan ke rapor. Bisa diurutkan dan difilter per status dan kategori.
4. Jadwal alat bergilir. Daftar alat dengan lokasi saat ini dan tanggal rencana cabut, agar dinas tahu kapan alat bebas untuk UMKM berikutnya.

Tidak perlu peta. Peta butuh layanan ubin dari luar dan menambah risiko, sementara tabel per sentra sudah menjawab pertanyaan dinas. Bila ingin, cukup tulis di laporan sebagai saran tahap berikutnya.

Keadaan kosong: program baru dimulai, belum ada rapor. Tampilkan jumlah alat dan jadwal pemasangan saja, tanpa grafik kosong.

## 12. Prototype 3D casing sensor (`cad/`)

Buat model parametrik di OpenSCAD (`cad/casing.scad`) dengan dua bagian: badan dan tutup. Semua ukuran berasal dari parameter di bagian atas file, supaya tim cukup mengganti angka setelah mengukur komponen asli dengan jangka sorong. Hasil: `casing_badan.stl`, `casing_tutup.stl`, dan render PNG tiga sudut pandang lewat OpenSCAD CLI.

Isi casing: papan ESP32, modul ZMPT101B, modul atau IC pengukur energi, catu daya AC-DC kecil, dan terminal blok untuk kabel 220 V.

Persyaratan desain:

1. Dua ruang terpisah. Ruang tegangan tinggi (terminal blok, catu daya, ZMPT101B) dan ruang tegangan rendah (ESP32, IC energi) dipisah dinding penuh, hanya ada celah kecil untuk kabel tegangan rendah.
2. Masuk kabel 220 V lewat lubang untuk cable gland, ukurannya parameter.
3. Lubang jack 3,5 mm untuk colokan SCT 013, di sisi ruang tegangan rendah, supaya sensor arus bisa dilepas saat alat pindah lokasi.
4. Tiga lubang LED (daya, WiFi, data) dengan label timbul di sebelahnya.
5. Akses USB ESP32 untuk flashing, dengan penutup kecil.
6. Ventilasi berupa celah di dinding samping, tidak di bagian atas, supaya debu dan tetesan air tidak langsung masuk.
7. Ceruk label QR di tutup untuk ID alat, ukuran parameter.
8. Pemasangan: dua tab sekrup dinding, dengan opsi parameter untuk klip rel DIN.
9. Tutup disekrup (dudukan untuk insert ulir M3 atau sekrup tapping), bukan klip, supaya tidak terbuka tanpa alat.
10. Tulisan timbul "220 V" di sisi ruang tegangan tinggi.

Parameter minimal:

| Parameter | Arti | Nilai awal |
|---|---|---|
| `tebal_dinding` | Tebal dinding | 2,4 mm |
| `celah` | Kelonggaran pas antar-bagian untuk cetak FDM | 0,3 mm |
| `esp32_p`, `esp32_l` | Ukuran papan ESP32 | UKUR ULANG |
| `zmpt_p`, `zmpt_l` | Ukuran modul tegangan | UKUR ULANG |
| `psu_p`, `psu_l`, `psu_t` | Ukuran catu daya AC-DC | UKUR ULANG |
| `energi_p`, `energi_l` | Ukuran modul IC energi | UKUR ULANG |
| `terminal_p`, `terminal_l` | Ukuran terminal blok | UKUR ULANG |
| `gland_d` | Diameter lubang cable gland | UKUR ULANG |
| `jack_d` | Diameter lubang jack 3,5 mm | UKUR ULANG |
| `led_d` | Diameter LED | UKUR ULANG |
| `qr_sisi` | Sisi ceruk label QR | UKUR ULANG |
| `pakai_din` | Klip rel DIN aktif atau tidak | false |

Nilai bertanda UKUR ULANG boleh diisi sementara agar model bisa dirender, tapi harus diberi komentar `// UKUR ULANG` di file dan didaftar di `cad/README.md`. Ukuran luar casing dihitung otomatis dari komponen, dinding, dan jarak bebas, bukan diketik manual.

Catatan keselamatan untuk README: casing cetak 3D hanya untuk prototype dan demo. Untuk dipasang di lokasi UMKM, pakai material tahan api (kelas UL94 V-0) atau box listrik pabrikan, dan rakitannya diperiksa orang yang kompeten di instalasi listrik. PETG atau ABS lebih cocok dari PLA untuk prototype karena lebih tahan panas.

## 13. Kriteria selesai dan cara melapor

Prototype dianggap selesai bila semua butir di bawah terbukti, bukan diklaim:

- [ ] `npm run build` dan `npm run lint` lulus tanpa error.
- [ ] Tes Vitest untuk `lib/hitung/` lulus, termasuk kasus tarif kosong, beban nol, dan produksi panel melebihi beban.
- [ ] Setiap route di bagian 5 terbuka tanpa error konsol.
- [ ] Tangkapan layar Playwright tiap route di lebar 360 px dan 1280 px, tersimpan di `screenshots/`.
- [ ] Tidak ada scroll menyamping di 360 px.
- [ ] Keadaan kosong, memuat, dan error tiap layar bisa dipicu dari kontrol prototype dan sudah ditangkap layar.
- [ ] Navigasi keyboard penuh di alur teknisi, fokus selalu terlihat.
- [ ] Pemeriksaan kontras otomatis (misalnya axe lewat Playwright) tanpa pelanggaran AA.
- [ ] Rapor tercetak 2 halaman A4 dari Chrome tanpa baris tabel terpotong, disimpan sebagai PDF contoh.
- [ ] Tidak ada tombol atau tautan mati. Pencarian `href="#"` dan handler kosong menghasilkan nol.
- [ ] Model OpenSCAD dirender tanpa error, STL dan PNG ada di `cad/`.
- [ ] Pita "DATA SIMULASI" muncul di semua layar dan di rapor cetak.

Laporan akhir untuk tim, singkat:

1. Apa yang dibangun, dengan tautan ke tangkapan layar.
2. Output asli dari build, lint, dan tes (tempel ringkasannya, bukan kata "lulus" saja).
3. Bagian yang belum bisa diuji dan alasannya.
4. Daftar semua nilai simulasi dan UKUR ULANG yang harus diganti data lapangan.
5. Asumsi yang diambil karena pertanyaan di bagian 3 belum dijawab.
6. Ide tambahan di luar brief, kalau ada, sebagai saran saja.

## 14. Pertanyaan terbuka untuk tim

Jawab sebelum brief diserahkan ke Claude Code bila memungkinkan. Yang belum terjawab akan diisi default dari bagian 3.

- [ ] Sektor dan sentra UMKM uji coba mana yang bisa diakses lewat Disperinaker Sukoharjo?
- [ ] Golongan tarif PLN UMKM uji coba, dan tarif per kWh yang berlaku?
- [ ] Harga PLTS per kWp dari minimal satu penawaran installer, termasuk tenant energi Inkubator UNS?
- [ ] Komponen elektronik apa yang sudah dibeli, terutama modul pengukur energi dan catu dayanya?
- [ ] Ambang kategori rapor: berapa persen pemborosan dianggap "efisiensi dulu", dan berapa tahun balik modal dianggap "layak"?
- [ ] Batas kapasitas PLTS atap per pelanggan menurut Permen ESDM Nomor 2 Tahun 2024, untuk membatasi skenario kWp di simulator?
- [ ] Logo dan identitas visual: dibuat tim sendiri, atau tetap placeholder sampai demo?
