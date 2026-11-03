#pragma once
// Pin map and timing for Heltec WiFi LoRa 32 V3. Check against the official Heltec pinout
// for your board revision before field deployment (design doc 5.3 marks I2C pins as [Usulan]).

// SX1262 (fixed on the board)
#define LORA_NSS 8
#define LORA_DIO1 14
#define LORA_RST 12
#define LORA_BUSY 13
#define LORA_SCK 9
#define LORA_MISO 11
#define LORA_MOSI 10

// SHT31 on the second I2C bus (first bus GPIO17/18 is the OLED)
#define SHT_SDA 41
#define SHT_SCL 42
#define SHT_ADDR 0x44

// Vext powers the sensor; LOW = on
#define VEXT_PIN 36

// Battery: ADC on GPIO1 through the onboard divider (390k/100k), enabled by GPIO37.
// Board V3.1 enables the divider with HIGH, V3.0 with LOW. Set for your boards.
#define VBAT_ADC_PIN 1
#define VBAT_CTRL_PIN 37
#define VBAT_CTRL_ACTIVE HIGH
#define VBAT_DIVIDER 4.9f

// Timing (design doc 5.3): read every 5 min, send every 2nd reading (10 min)
#define READ_INTERVAL_S 300
#define READINGS_PER_UPLINK 2
#define SENSOR_WARMUP_MS 20
#define SENSOR_SAMPLES 3

// LinkCheck once per 6 h (36 uplinks); rejoin after 4 failed checks (~24 h without answer)
#define LINKCHECK_EVERY_N_UPLINKS 36
#define LINKCHECK_FAILS_BEFORE_REJOIN 4

#define LORAWAN_FPORT 1
#define WDT_TIMEOUT_S 60

// RTC ring buffer: 48 readings (~4 h)
#define RING_SIZE 48
