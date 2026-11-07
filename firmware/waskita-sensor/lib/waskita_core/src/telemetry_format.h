// WASKITA - format waktu ISO 8601 dan JSON telemetri sesuai kontrak backend
// (backend/docs/CONTRACTS.md bagian 7, app/schemas/telemetry.py).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "power_calc.h"

namespace waskita {

// "YYYY-MM-DDTHH:MM:SS.mmm+07:00" dari epoch ms UTC dan offset zona waktu.
// Tidak memakai gmtime/strftime (portabel, tidak bergantung TZ sistem).
// Return panjang string, atau 0 bila buffer kurang.
size_t formatIso8601(int64_t epoch_ms, int32_t tz_offset_s, char* out, size_t cap);

// Satu objek sampel JSON. Bila device_id != nullptr, field device_id ikut
// ditulis (untuk POST /ingest); untuk elemen "samples" di /ingest-batch
// berikan nullptr. Return panjang, atau 0 bila buffer kurang.
size_t formatSampleJson(char* out, size_t cap, const char* device_id,
                        const char* iso_timestamp, const TelemetrySample& s);

// Normalisasi URL dasar API: hapus spasi, "/" di akhir, dan akhiran
// "/api/v1" (firmware menambahkan path sendiri). Wajib diawali http:// atau
// https://. Return false bila tidak valid.
bool normalizeApiBase(const char* in, char* out, size_t cap);

// ID perangkat: 1..64 karakter [A-Za-z0-9._-] (aman ditulis ke JSON tanpa escape).
bool isValidDeviceId(const char* id);

}  // namespace waskita
