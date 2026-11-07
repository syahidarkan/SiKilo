#include "telemetry_format.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

namespace waskita {

namespace {

int64_t floorDiv(int64_t a, int64_t b) {
  int64_t q = a / b;
  if ((a % b != 0) && ((a < 0) != (b < 0))) --q;
  return q;
}

// Algoritma days_from_civil terbalik (Howard Hinnant), berlaku untuk semua
// tanggal Gregorian proleptik.
void civilFromDays(int64_t z, int* y, int* m, int* d) {
  z += 719468;
  const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
  const int64_t doe = z - era * 146097;
  const int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  int64_t yy = yoe + era * 400;
  const int64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const int64_t mp = (5 * doy + 2) / 153;
  const int64_t dd = doy - (153 * mp + 2) / 5 + 1;
  const int64_t mm = mp < 10 ? mp + 3 : mp - 9;
  if (mm <= 2) ++yy;
  *y = (int)yy;
  *m = (int)mm;
  *d = (int)dd;
}

inline float finite0(float x) { return isfinite(x) ? x : 0.0f; }

size_t checkedLen(int n, size_t cap) {
  if (n < 0 || (size_t)n >= cap) return 0;
  return (size_t)n;
}

}  // namespace

size_t formatIso8601(int64_t epoch_ms, int32_t tz_offset_s, char* out, size_t cap) {
  if (!out || cap == 0) return 0;
  const int64_t local_ms = epoch_ms + (int64_t)tz_offset_s * 1000;
  const int64_t secs = floorDiv(local_ms, 1000);
  const int ms = (int)(local_ms - secs * 1000);
  const int64_t days = floorDiv(secs, 86400);
  const int64_t sod = secs - days * 86400;
  int y, mo, d;
  civilFromDays(days, &y, &mo, &d);
  const int hh = (int)(sod / 3600);
  const int mi = (int)((sod % 3600) / 60);
  const int ss = (int)(sod % 60);
  const char sign = tz_offset_s < 0 ? '-' : '+';
  const int32_t aoff = tz_offset_s < 0 ? -tz_offset_s : tz_offset_s;
  const int tzh = (int)(aoff / 3600);
  const int tzm = (int)((aoff % 3600) / 60);
  const int n = snprintf(out, cap, "%04d-%02d-%02dT%02d:%02d:%02d.%03d%c%02d:%02d",
                         y, mo, d, hh, mi, ss, ms, sign, tzh, tzm);
  return checkedLen(n, cap);
}

size_t formatSampleJson(char* out, size_t cap, const char* device_id,
                        const char* iso_timestamp, const TelemetrySample& s) {
  if (!out || cap == 0 || !iso_timestamp) return 0;
  int n;
  if (device_id) {
    n = snprintf(out, cap,
                 "{\"device_id\":\"%s\",\"timestamp\":\"%s\",\"v_rms\":%.2f,"
                 "\"i_rms\":%.3f,\"p_active\":%.1f,\"q_reactive\":%.1f,"
                 "\"frequency\":%.3f}",
                 device_id, iso_timestamp, (double)finite0(s.v_rms),
                 (double)finite0(s.i_rms), (double)finite0(s.p_active),
                 (double)finite0(s.q_reactive), (double)finite0(s.frequency));
  } else {
    n = snprintf(out, cap,
                 "{\"timestamp\":\"%s\",\"v_rms\":%.2f,\"i_rms\":%.3f,"
                 "\"p_active\":%.1f,\"q_reactive\":%.1f,\"frequency\":%.3f}",
                 iso_timestamp, (double)finite0(s.v_rms), (double)finite0(s.i_rms),
                 (double)finite0(s.p_active), (double)finite0(s.q_reactive),
                 (double)finite0(s.frequency));
  }
  return checkedLen(n, cap);
}

bool normalizeApiBase(const char* in, char* out, size_t cap) {
  if (!in || !out || cap < 2) return false;
  while (*in && isspace((unsigned char)*in)) ++in;
  size_t len = strlen(in);
  while (len > 0 && isspace((unsigned char)in[len - 1])) --len;
  if (len + 1 > cap) return false;
  memcpy(out, in, len);
  out[len] = '\0';

  bool changed = true;
  while (changed) {
    changed = false;
    while (len > 0 && out[len - 1] == '/') {
      out[--len] = '\0';
      changed = true;
    }
    const char* suffix = "/api/v1";
    const size_t sl = strlen(suffix);
    if (len >= sl && strcmp(out + len - sl, suffix) == 0) {
      len -= sl;
      out[len] = '\0';
      changed = true;
    }
  }

  const bool http = strncmp(out, "http://", 7) == 0 && len > 7;
  const bool https = strncmp(out, "https://", 8) == 0 && len > 8;
  if (!http && !https) return false;
  for (size_t k = 0; k < len; ++k) {
    const unsigned char c = (unsigned char)out[k];
    if (c <= 0x20 || c == '"' || c == '\\' || c >= 0x7f) return false;
  }
  return true;
}

bool isValidDeviceId(const char* id) {
  if (!id) return false;
  const size_t len = strlen(id);
  if (len == 0 || len > 64) return false;
  for (size_t k = 0; k < len; ++k) {
    const char c = id[k];
    const bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                    (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
    if (!ok) return false;
  }
  return true;
}

}  // namespace waskita
