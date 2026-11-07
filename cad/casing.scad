// Casing sensor NOTA LISTRIK: badan + tutup, parametrik.
// Semua ukuran luar dihitung dari komponen, dinding, dan jarak bebas.
// Nilai bertanda UKUR ULANG adalah perkiraan dari lembar data umum; ukur
// komponen asli dengan jangka sorong lalu ganti angkanya di bagian PARAMETER.
//
// Render satu bagian:  openscad -D 'bagian="badan"' -o casing_badan.stl casing.scad
// Pilihan bagian: "badan", "tutup", "rakitan" (pratinjau, tutup terangkat)

bagian = "rakitan";

// ===================== PARAMETER =====================

// --- Umum cetak FDM ---
tebal_dinding = 2.4;
tebal_lantai  = 2.4;
tebal_tutup   = 2.4;
celah         = 0.3;   // kelonggaran pas antar-bagian
jarak         = 3;     // jarak bebas komponen ke dinding dan antar-komponen
jarak_atas    = 5;     // ruang di atas komponen tertinggi untuk kabel

// --- Komponen ruang tegangan rendah ---
esp32_p   = 51.5;  // UKUR ULANG: panjang papan ESP32 DevKit
esp32_l   = 28.5;  // UKUR ULANG
esp32_t   = 13;    // UKUR ULANG: tinggi papan termasuk komponen atas
esp32_pcb = 1.6;   // UKUR ULANG: tebal PCB
energi_p  = 40;    // UKUR ULANG: modul IC pengukur energi
energi_l  = 30;    // UKUR ULANG
energi_t  = 10;    // UKUR ULANG

// --- Komponen ruang tegangan tinggi ---
zmpt_p     = 49;   // UKUR ULANG: modul ZMPT101B
zmpt_l     = 19.5; // UKUR ULANG
zmpt_t     = 22;   // UKUR ULANG
psu_p      = 34;   // UKUR ULANG: catu daya AC-DC (mis. modul 5 V 3 W)
psu_l      = 20;   // UKUR ULANG
psu_t      = 15;   // UKUR ULANG
terminal_p = 15.5; // UKUR ULANG: terminal blok 3 kutub pitch 5,08
terminal_l = 10;   // UKUR ULANG
terminal_t = 16;   // UKUR ULANG

// --- Lubang ---
gland_d   = 12.5;  // UKUR ULANG: lubang cable gland (PG7 = 12,5)
jack_d    = 6.2;   // UKUR ULANG: jack 3,5 mm panel mount
led_d     = 5.2;   // UKUR ULANG: LED 5 mm + kelonggaran
usb_l     = 12;    // UKUR ULANG: lebar celah colokan USB
usb_t     = 7.5;   // UKUR ULANG: tinggi celah colokan USB
usb_pusat = 3.5;   // UKUR ULANG: tinggi pusat soket USB dari bawah PCB
dudukan_t = 4;     // tinggi rel dudukan di bawah ESP32

// --- Sekat dan celah kabel tegangan rendah ---
celah_kabel_l = 6;
celah_kabel_t = 4;

// --- Ventilasi (dinding samping saja) ---
vent_lebar   = 1.6;  // sempit agar jari dan kawat besar tidak masuk
vent_tinggi  = 8;
vent_jarak   = 4;

// --- Label QR di tutup ---
qr_sisi   = 25;   // UKUR ULANG: sisi stiker QR
qr_dalam  = 0.6;

// --- Sekrup tutup ---
pakai_insert  = true;  // true: insert ulir M3, false: sekrup tapping
insert_d      = 4.0;   // UKUR ULANG: diameter lubang insert M3
insert_dalam  = 5.7;   // UKUR ULANG
tapping_d     = 2.5;   // UKUR ULANG: lubang pilot sekrup tapping M3
sekrup_d      = 3.4;   // lubang tembus di tutup
kepala_d      = 6.2;   // UKUR ULANG: kepala sekrup M3
kepala_dalam  = 1.2;
boss_d        = 8;
bibir_t       = 3;     // bibir tutup yang masuk ke badan

// --- Pemasangan ---
pakai_din        = false;
tab_p            = 12;
tab_l            = 16;
tab_t            = 3;
sekrup_dinding_d = 4.5;  // UKUR ULANG: sesuai fisher/sekrup dinding
din_lebar        = 35;   // rel DIN TS35

// --- Teks timbul ---
teks_font  = "DejaVu Sans:style=Bold";
teks_timbul = 0.6;

$fn = 48;

// ===================== TURUNAN (jangan diketik manual) =====================

// Komponen disusun dengan panjang searah X dan bertumpuk searah Y.
hv_x = max(terminal_p, psu_p, zmpt_p) + 2 * jarak;
hv_y = terminal_l + psu_l + zmpt_l + 4 * jarak;
lv_x = max(esp32_p, energi_p) + 2 * jarak;
lv_y = esp32_l + energi_l + 3 * jarak;

// Ujung Y diberi ruang boss sekrup agar komponen tidak bertabrakan dengan boss.
dalam_x = hv_x + tebal_dinding + lv_x;
dalam_y = max(hv_y, lv_y) + 2 * boss_d;
dalam_z = max(esp32_t + dudukan_t, energi_t, zmpt_t, psu_t, terminal_t) + jarak_atas;

luar_x = dalam_x + 2 * tebal_dinding;
luar_y = dalam_y + 2 * tebal_dinding;
luar_z = dalam_z + tebal_lantai;

sekat_x = tebal_dinding + hv_x;                 // sisi kiri sekat
lv_x0   = sekat_x + tebal_dinding;               // awal ruang tegangan rendah
y0      = tebal_dinding + boss_d;                // awal area komponen

esp32_y0 = y0 + jarak;
energi_y0 = esp32_y0 + esp32_l + jarak;

// Boss sedikit masuk ke dinding: silinder yang hanya menyinggung dinding menghasilkan mesh non-manifold
boss_tepi = tebal_dinding + boss_d / 2 - 0.6;
boss_pos = [
  [boss_tepi, boss_tepi],
  [luar_x - boss_tepi, boss_tepi],
  [boss_tepi, luar_y - boss_tepi],
  [luar_x - boss_tepi, luar_y - boss_tepi],
];

echo(str("Ukuran luar badan (mm): ", luar_x, " x ", luar_y, " x ", luar_z));
assert(gland_d < luar_z - tebal_lantai - 2, "gland_d terlalu besar untuk tinggi badan");
assert(celah_kabel_t < dalam_z - bibir_t, "celah kabel lebih tinggi dari sekat");

// ===================== BADAN =====================

// Diekstrusi mulai 0,3 mm di dalam permukaan agar menyatu dengan dinding (manifold)
module teks_timbul_di(t, ukuran) {
  translate([0, 0, -0.3]) linear_extrude(teks_timbul + 0.3) text(t, size = ukuran, font = teks_font, halign = "center", valign = "center");
}

module badan() {
  difference() {
    union() {
      difference() {
        cube([luar_x, luar_y, luar_z]);
        translate([tebal_dinding, tebal_dinding, tebal_lantai]) cube([dalam_x, dalam_y, dalam_z + 1]);
      }
      // Sekat penuh antara ruang tegangan tinggi dan rendah; berhenti di bawah bibir tutup
      translate([sekat_x, tebal_dinding, 0]) cube([tebal_dinding, dalam_y, luar_z - bibir_t]);
      // Boss sekrup tutup
      for (p = boss_pos) translate([p[0], p[1], 0]) cylinder(d = boss_d, h = luar_z - bibir_t);
      // Rel dudukan ESP32 agar tinggi soket USB tetap
      for (dy = [0, esp32_l - 3])
        translate([lv_x0 + jarak, esp32_y0 + dy, 0]) cube([esp32_p, 3, tebal_lantai + dudukan_t]);
      // Tulisan "220 V" timbul di dinding sisi tegangan tinggi
      translate([0, luar_y * 0.72, luar_z / 2]) rotate([90, 0, -90]) teks_timbul_di("220 V", 5);
      tab_pemasangan();
    }
    // Celah kabel tegangan rendah di puncak sekat
    translate([sekat_x - 1, luar_y / 2 - celah_kabel_l / 2, luar_z - bibir_t - celah_kabel_t])
      cube([tebal_dinding + 2, celah_kabel_l, celah_kabel_t + 1]);
    // Lubang insert / pilot di boss
    for (p = boss_pos)
      translate([p[0], p[1], luar_z - bibir_t - (pakai_insert ? insert_dalam : 10)])
        cylinder(d = pakai_insert ? insert_d : tapping_d, h = 20);
    // Cable gland 220 V di dinding kiri (ruang tegangan tinggi)
    translate([-1, luar_y * 0.35, tebal_lantai + dalam_z / 2]) rotate([0, 90, 0]) cylinder(d = gland_d, h = tebal_dinding + 2);
    // Jack 3,5 mm SCT-013 di dinding kanan, sejajar modul energi
    translate([luar_x - tebal_dinding - 1, energi_y0 + energi_l / 2, tebal_lantai + dalam_z / 2])
      rotate([0, 90, 0]) cylinder(d = jack_d, h = tebal_dinding + 2);
    // Akses USB ESP32 di dinding kanan
    translate([luar_x - tebal_dinding - 1, esp32_y0 + esp32_l / 2 - usb_l / 2,
               tebal_lantai + dudukan_t + usb_pusat - usb_t / 2])
      cube([tebal_dinding + 2, usb_l, usb_t]);
    ventilasi();
  }
  if (pakai_din) klip_din();
}

module ventilasi() {
  z0 = tebal_lantai + 3;
  for (ruang = [[tebal_dinding + boss_d, sekat_x - boss_d * 0.2], [lv_x0 + boss_d * 0.2, luar_x - tebal_dinding - boss_d]]) {
    n = floor((ruang[1] - ruang[0]) / (vent_lebar + vent_jarak));
    for (i = [0 : n - 1]) {
      x = ruang[0] + i * (vent_lebar + vent_jarak) + vent_jarak / 2;
      for (y = [-1, luar_y - tebal_dinding - 1]) translate([x, y, z0]) cube([vent_lebar, tebal_dinding + 2, vent_tinggi]);
    }
  }
}

module tab_pemasangan() {
  if (!pakai_din)
    for (sisi = [0, 1])
      // Tab dibuat 1 mm lebih panjang dan masuk ke dinding agar menyatu
      translate([sisi == 0 ? -tab_p : luar_x - 1, luar_y / 2 - tab_l / 2, 0])
        difference() {
          cube([tab_p + 1, tab_l, tab_t]);
          translate([sisi == 0 ? tab_p / 2 : tab_p / 2 + 1, tab_l / 2, -1]) cylinder(d = sekrup_dinding_d, h = tab_t + 2);
        }
}

// Klip rel DIN TS35 di bawah badan: kait tetap di atas, lidah pegas di bawah.
module klip_din() {
  lebar = min(30, luar_x - 10);
  x0 = luar_x / 2 - lebar / 2;
  yc = luar_y / 2;
  translate([x0, 0, 0]) mirror([0, 0, 1]) {
    // pelat dasar
    translate([0, yc - din_lebar / 2 - 6, 0]) cube([lebar, din_lebar + 12, 2]);
    // kait tetap
    translate([0, yc + din_lebar / 2 + celah, 0]) cube([lebar, 2, 3.5]);
    translate([0, yc + din_lebar / 2 - 2, 2.5]) cube([lebar, 4.3, 1.2]);
    // lidah pegas dengan tonjolan miring
    translate([lebar / 2 - 5, yc - din_lebar / 2 - 2 - celah, 0]) {
      cube([10, 2, 3.5]);
      translate([0, 2, 2.5]) rotate([0, 90, 0]) linear_extrude(10) polygon([[0, 0], [-1.2, 0], [0, 2.3]]);
    }
  }
}

// ===================== TUTUP =====================

module tutup() {
  dalam_bibir = [dalam_x - 2 * celah, dalam_y - 2 * celah];
  difference() {
    union() {
      cube([luar_x, luar_y, tebal_tutup]);
      // Bibir pengarah, dikosongkan di sekitar boss
      translate([0, 0, tebal_tutup]) difference() {
        translate([tebal_dinding + celah, tebal_dinding + celah, 0]) cube([dalam_bibir[0], dalam_bibir[1], bibir_t]);
        translate([tebal_dinding + celah + 1.6, tebal_dinding + celah + 1.6, -1])
          cube([dalam_bibir[0] - 3.2, dalam_bibir[1] - 3.2, bibir_t + 2]);
        for (p = boss_pos) translate([p[0], p[1], -1]) cylinder(d = boss_d + 2 * celah, h = bibir_t + 2);
      }
      // Rusuk penutup di atas sekat, menyambung pemisahan dua ruang sampai tutup
      translate([sekat_x, tebal_dinding + celah, tebal_tutup]) cube([tebal_dinding, dalam_y - 2 * celah, bibir_t - celah]);
      // Label timbul LED di sisi luar; dicerminkan Y agar tegak setelah tutup dibalik saat dipasang
      for (i = [0 : 2])
        translate([led_x(i), led_y() - led_d - 3, 0]) mirror([0, 1, 0]) mirror([0, 0, 1])
          teks_timbul_di(["DAYA", "WIFI", "DATA"][i], 2.8);
    }
    for (p = boss_pos) {
      translate([p[0], p[1], -1]) cylinder(d = sekrup_d, h = tebal_tutup + 2);
      translate([p[0], p[1], -1]) cylinder(d = kepala_d, h = kepala_dalam + 1);
    }
    for (i = [0 : 2]) translate([led_x(i), led_y(), -1]) cylinder(d = led_d, h = tebal_tutup + 2);
    // Ceruk QR di sisi luar, di atas ruang tegangan tinggi
    translate([tebal_dinding + hv_x / 2 - qr_sisi / 2, luar_y / 2 - qr_sisi / 2, -0.01]) cube([qr_sisi, qr_sisi, qr_dalam]);
  }
}

function led_x(i) = lv_x0 + lv_x / 2 + (i - 1) * 12;
function led_y() = luar_y / 2 + 6;

// Penutup kecil celah USB: sumbat tekan dengan pegangan, dicetak bersama tutup.
module penutup_usb() {
  cube([usb_l + 4, usb_t + 4, 1.6]);
  translate([2 + celah, 2 + celah, 1.6]) cube([usb_l - 2 * celah, usb_t - 2 * celah, tebal_dinding]);
}

assert(qr_sisi < hv_x && qr_sisi < luar_y - 2 * boss_d, "qr_sisi lebih besar dari area tutup");

// ===================== KELUARAN =====================

if (bagian == "badan") {
  badan();
} else if (bagian == "tutup") {
  tutup();
  translate([0, -usb_t - 10, 0]) penutup_usb();
} else {
  color("#d8d2c4") badan();
  // Tutup dibalik ke posisi terpasang lalu diangkat agar isi terlihat
  color("#1f4e79") translate([0, luar_y, luar_z + tebal_tutup + 25]) rotate([180, 0, 0]) tutup();
}
