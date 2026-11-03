# Firmware node Kampung Adem

Heltec WiFi LoRa 32 V3 + SHT31, LoRaWAN Class A, OTAA, **AS923-2** (920-923 MHz).

## Siklus kerja

1. Bangun dari deep sleep tiap 5 menit, nyalakan Vext, baca SHT31 3 kali (median).
2. Simpan bacaan di ring buffer RTC (48 bacaan).
3. Tiap 2 bacaan (10 menit) kirim uplink tanpa konfirmasi, payload v1 12 byte (`include/payload.h`).
4. LinkCheck tiap 36 uplink (6 jam). Setelah 4 kali gagal (sekitar 24 jam), join OTAA ulang.
5. Watchdog 60 detik me-reset MCU jika siklus macet.

Offset kalibrasi **tidak** diterapkan di firmware; backend yang menerapkannya.

## Baterai di payload

Byte 11: `V = 2,00 + raw x 0,01` (resolusi 10 mV, rentang 2,01-4,55 V). `raw = 0` berarti tidak terukur.

## Build dan flash

```
cp include/secrets.example.h include/secrets.h   # isi DevEUI, JoinEUI, AppKey unik per node
pio run
pio run -t upload
pio device monitor
```

## Belum dikerjakan / perlu dicek

- Mode backlog (ringkasan per jam setelah jaringan pulih, dokumen 5.3) belum ada karena butuh format payload baru (versi 2). Perlu disepakati dulu.
- Pin I2C (GPIO41/42) dan level `VBAT_CTRL_ACTIVE` harus dicek terhadap revisi papan Heltec yang dibeli.
- Firmware belum dikompilasi di mesin pengembang (PlatformIO belum terpasang). Jalankan `pio run` sebelum uji bench.
