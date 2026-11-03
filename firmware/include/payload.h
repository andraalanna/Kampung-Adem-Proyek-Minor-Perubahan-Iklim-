#pragma once
// Uplink payload v1, 12 bytes, big-endian. Must match backend/app/core/payload.py.
//   0     version   uint8 (= 1)
//   1-2   seq       uint16
//   3-4   temp_now  int16  x0.01 C   (0x7FFF = missing)
//   5-6   rh_now    uint16 x0.01 %   (0xFFFF = missing)
//   7-8   temp_prev int16  x0.01 C
//   9-10  rh_prev   uint16 x0.01 %
//   11    battery   uint8  V = 2.00 + raw * 0.01 (0 = not measured)
// Any layout change bumps the version and needs a backend decoder update with tests.

#include <math.h>
#include <stdint.h>

#define PAYLOAD_VERSION 1
#define PAYLOAD_LEN 12
#define TEMP_MISSING 0x7FFF
#define RH_MISSING 0xFFFF

struct Reading {
  float temp_c;  // NAN when missing
  float rh_pct;  // NAN when missing
};

static inline int16_t encodeTemp(float t) {
  if (isnan(t)) return (int16_t)TEMP_MISSING;
  return (int16_t)lroundf(t * 100.0f);
}

static inline uint16_t encodeRh(float h) {
  if (isnan(h)) return RH_MISSING;
  if (h < 0) h = 0;
  if (h > 100) h = 100;
  return (uint16_t)lroundf(h * 100.0f);
}

static inline uint8_t encodeBattery(float v) {
  if (isnan(v) || v <= 0) return 0;
  long raw = lroundf((v - 2.0f) / 0.01f);
  if (raw < 1) raw = 1;
  if (raw > 255) raw = 255;
  return (uint8_t)raw;
}

static inline void putU16(uint8_t* b, uint16_t v) {
  b[0] = v >> 8;
  b[1] = v & 0xFF;
}

static inline void encodePayload(uint8_t out[PAYLOAD_LEN], uint16_t seq, const Reading& now,
                                 const Reading& prev, float battery_v) {
  out[0] = PAYLOAD_VERSION;
  putU16(out + 1, seq);
  putU16(out + 3, (uint16_t)encodeTemp(now.temp_c));
  putU16(out + 5, encodeRh(now.rh_pct));
  putU16(out + 7, (uint16_t)encodeTemp(prev.temp_c));
  putU16(out + 9, encodeRh(prev.rh_pct));
  out[11] = encodeBattery(battery_v);
}
