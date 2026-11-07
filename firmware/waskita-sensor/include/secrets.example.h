// WASKITA - contoh rahasia build.
//
// Salin file ini menjadi include/secrets.h lalu ganti nilainya.
// include/secrets.h diabaikan git (lihat .gitignore) - JANGAN di-commit.
//
// SSID/password WiFi, URL server, dan device key TIDAK ditaruh di sini:
// semuanya diisi lewat portal WiFiManager "WASKITA-xxxx" dan disimpan di
// NVS (Preferences) perangkat.
#pragma once

// Password Access Point portal konfigurasi (minimal 8 karakter).
// String kosong = AP terbuka (TIDAK disarankan: device key dikirim lewat
// form portal, siapa pun di dekat perangkat bisa ikut tersambung).
#define PORTAL_AP_PASSWORD "ganti-password-portal"

// Password OTA (ArduinoOTA). Minimal 8 karakter. String kosong = OTA mati.
#define OTA_PASSWORD ""

// Sertifikat root CA (PEM) server bila API memakai https://.
// String kosong = koneksi TLS TANPA verifikasi sertifikat (hanya untuk uji
// coba; rentan penyadapan/man-in-the-middle). Isi dengan literal string
// berurutan (tiap baris PEM diakhiri \n), misalnya:
//   "-----BEGIN CERTIFICATE-----\n"  "MIIF...\n"  "-----END CERTIFICATE-----\n"
#define WASKITA_ROOT_CA ""
