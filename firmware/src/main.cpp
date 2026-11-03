// Kampung Adem sensor node firmware (design doc 5.3, 15.2, 15.3).
// Wake every 5 min -> read SHT31 (median of 3) -> ring buffer in RTC memory ->
// every 2nd reading send an unconfirmed LoRaWAN Class A uplink (AS923-2) -> deep sleep.
// Calibration offsets are NOT applied here; the backend applies them.

#include <Adafruit_SHT31.h>
#include <Arduino.h>
#include <Preferences.h>
#include <RadioLib.h>
#include <Wire.h>
#include <esp_sleep.h>
#include <esp_task_wdt.h>

#include "config.h"
#include "payload.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Copy include/secrets.example.h to include/secrets.h and fill in this node's keys"
#endif

// ---------------------------------------------------------------- state kept across deep sleep
RTC_DATA_ATTR uint8_t rtcSession[RADIOLIB_LORAWAN_SESSION_BUF_SIZE];
RTC_DATA_ATTR bool rtcHasSession = false;
RTC_DATA_ATTR uint16_t rtcSeq = 0;
RTC_DATA_ATTR uint32_t rtcReadCount = 0;
RTC_DATA_ATTR uint32_t rtcUplinkCount = 0;
RTC_DATA_ATTR uint8_t rtcLinkFails = 0;
RTC_DATA_ATTR Reading rtcRing[RING_SIZE];
RTC_DATA_ATTR uint8_t rtcRingHead = 0;  // index of the next write

SPIClass loraSpi(HSPI);
SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY, loraSpi);
LoRaWANNode node(&radio, &AS923_2);
Adafruit_SHT31 sht(&Wire1);
Preferences prefs;

static const uint64_t joinEUI = NODE_JOIN_EUI;
static const uint64_t devEUI = NODE_DEV_EUI;
static uint8_t appKey[] = NODE_APP_KEY;

// ---------------------------------------------------------------- sensor
static float median3(float a, float b, float c) {
  if (a > b) std::swap(a, b);
  if (b > c) std::swap(b, c);
  if (a > b) std::swap(a, b);
  return b;
}

static bool sampleOnce(float& t, float& h) {
  if (!sht.readBoth(&t, &h)) return false;  // includes CRC check
  return !isnan(t) && !isnan(h);
}

static Reading readSensor() {
  pinMode(VEXT_PIN, OUTPUT);
  digitalWrite(VEXT_PIN, LOW);  // sensor power on
  delay(SENSOR_WARMUP_MS);
  Wire1.begin(SHT_SDA, SHT_SCL);
  Reading r{NAN, NAN};

  if (sht.begin(SHT_ADDR)) {
    float ts[SENSOR_SAMPLES], hs[SENSOR_SAMPLES];
    int n = 0;
    for (int i = 0; i < SENSOR_SAMPLES; i++) {
      float t, h;
      if (sampleOnce(t, h) || sampleOnce(t, h)) {  // retry once on failure
        ts[n] = t;
        hs[n] = h;
        n++;
      }
    }
    if (n == 3) {
      r.temp_c = median3(ts[0], ts[1], ts[2]);
      r.rh_pct = median3(hs[0], hs[1], hs[2]);
    } else if (n > 0) {
      r.temp_c = ts[0];
      r.rh_pct = hs[0];
    }
  }
  Wire1.end();
  digitalWrite(VEXT_PIN, HIGH);  // sensor power off
  return r;
}

static float readBattery() {
  pinMode(VBAT_CTRL_PIN, OUTPUT);
  digitalWrite(VBAT_CTRL_PIN, VBAT_CTRL_ACTIVE);
  delay(5);
  uint32_t mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(VBAT_ADC_PIN);
  digitalWrite(VBAT_CTRL_PIN, !VBAT_CTRL_ACTIVE);
  return (mv / 8.0f) / 1000.0f * VBAT_DIVIDER;
}

// ---------------------------------------------------------------- LoRaWAN
static bool restoreOrJoin() {
  node.beginOTAA(joinEUI, devEUI, appKey, appKey);

  // DevNonces must survive power loss, so they live in flash (NVS), not RTC memory.
  prefs.begin("lorawan", false);
  uint8_t nonces[RADIOLIB_LORAWAN_NONCES_BUF_SIZE];
  if (prefs.getBytes("nonces", nonces, sizeof(nonces)) == sizeof(nonces)) {
    node.setBufferNonces(nonces);
  }
  if (rtcHasSession) {
    node.setBufferSession(rtcSession);
  }

  int16_t state = node.activateOTAA();
  if (state == RADIOLIB_LORAWAN_SESSION_RESTORED) {
    prefs.end();
    return true;
  }
  if (state == RADIOLIB_LORAWAN_NEW_SESSION) {
    memcpy(nonces, node.getBufferNonces(), sizeof(nonces));
    prefs.putBytes("nonces", nonces, sizeof(nonces));
    prefs.end();
    rtcLinkFails = 0;
    return true;
  }
  // Join failed: store nonces anyway (DevNonce was used) and back off until next cycle.
  memcpy(nonces, node.getBufferNonces(), sizeof(nonces));
  prefs.putBytes("nonces", nonces, sizeof(nonces));
  prefs.end();
  rtcHasSession = false;
  Serial.printf("join failed: %d\n", state);
  return false;
}

static void sendUplink(const Reading& now, const Reading& prev, float battery) {
  uint8_t payload[PAYLOAD_LEN];
  encodePayload(payload, rtcSeq, now, prev, battery);

  bool doLinkCheck = (rtcUplinkCount % LINKCHECK_EVERY_N_UPLINKS) == 0;
  if (doLinkCheck) node.sendMacCommandReq(RADIOLIB_LORAWAN_MAC_LINK_CHECK);

  int16_t state = node.sendReceive(payload, sizeof(payload), LORAWAN_FPORT);
  rtcSeq++;  // seq advances even on failure so the backend can count lost packets
  rtcUplinkCount++;
  if (state < RADIOLIB_ERR_NONE) {
    Serial.printf("uplink error: %d\n", state);
  }

  if (doLinkCheck) {
    uint8_t margin = 0, gwCnt = 0;
    if (node.getMacLinkCheckAns(&margin, &gwCnt) == RADIOLIB_ERR_NONE && gwCnt > 0) {
      rtcLinkFails = 0;
    } else if (++rtcLinkFails >= LINKCHECK_FAILS_BEFORE_REJOIN) {
      rtcHasSession = false;  // force a fresh OTAA join next cycle
      rtcLinkFails = 0;
      return;
    }
  }
  memcpy(rtcSession, node.getBufferSession(), RADIOLIB_LORAWAN_SESSION_BUF_SIZE);
  rtcHasSession = true;
}

// ---------------------------------------------------------------- main cycle
static void goToSleep() {
  radio.sleep();
  digitalWrite(VEXT_PIN, HIGH);
  esp_sleep_enable_timer_wakeup((uint64_t)READ_INTERVAL_S * 1000000ULL);
  esp_deep_sleep_start();
}

void setup() {
  Serial.begin(115200);
  esp_task_wdt_init(WDT_TIMEOUT_S, true);  // reset the MCU if the cycle hangs
  esp_task_wdt_add(NULL);

  if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TIMER) {
    // Cold boot: RTC memory is not trustworthy.
    rtcHasSession = false;
    rtcReadCount = 0;
    rtcRingHead = 0;
    for (auto& r : rtcRing) r = Reading{NAN, NAN};
  }

  Reading now = readSensor();
  rtcRing[rtcRingHead] = now;
  uint8_t prevIdx = (rtcRingHead + RING_SIZE - 1) % RING_SIZE;
  Reading prev = rtcReadCount > 0 ? rtcRing[prevIdx] : Reading{NAN, NAN};
  rtcRingHead = (rtcRingHead + 1) % RING_SIZE;
  rtcReadCount++;
  Serial.printf("read #%lu T=%.2f RH=%.2f\n", (unsigned long)rtcReadCount, now.temp_c, now.rh_pct);

  if (rtcReadCount % READINGS_PER_UPLINK == 0) {
    float battery = readBattery();
    loraSpi.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_NSS);
    if (radio.begin() == RADIOLIB_ERR_NONE && restoreOrJoin()) {
      sendUplink(now, prev, battery);
    }
  }
  esp_task_wdt_reset();
  goToSleep();
}

void loop() {}
