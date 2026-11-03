# Format payload uplink v1

Payload yang dikirim node sensor lewat LoRaWAN (port aplikasi bebas, uplink tanpa konfirmasi). Panjang tetap **12 byte**, urutan byte **big-endian**.

Kode acuan:

- Firmware: `firmware/include/payload.h`
- Backend (decoder dan encoder acuan): `backend/app/core/payload.py`
- Uji: `backend/tests/test_core.py`

Kedua sisi harus selalu sama. Setiap perubahan format **wajib** menaikkan `version` dan disertai pembaruan decoder beserta ujinya.

## Tabel field

| Byte | Field | Tipe | Skala | Keterangan |
| --- | --- | --- | --- | --- |
| 0 | `version` | uint8 | | Selalu `1` untuk format ini |
| 1-2 | `seq` | uint16 | | Nomor urut uplink, berputar ke 0 setelah 65535. Celah nomor berarti paket hilang |
| 3-4 | `temp_now` | int16 | x0,01 °C | Suhu udara bacaan terbaru |
| 5-6 | `rh_now` | uint16 | x0,01 % | Kelembapan relatif bacaan terbaru |
| 7-8 | `temp_prev` | int16 | x0,01 °C | Suhu udara bacaan 5 menit sebelumnya |
| 9-10 | `rh_prev` | uint16 | x0,01 % | Kelembapan relatif bacaan 5 menit sebelumnya |
| 11 | `battery` | uint8 | lihat di bawah | Tegangan baterai |

Node membaca sensor tiap 5 menit dan mengirim tiap 10 menit, jadi satu paket membawa 2 bacaan. Backend memberi waktu `received_at` untuk bacaan `now` dan `received_at - 5 menit` untuk bacaan `prev`. Bacaan yang sudah tersimpan dari paket sebelumnya tidak disimpan ulang.

Offset kalibrasi (`offset_temp`, `offset_rh`) **tidak** diterapkan di firmware. Nilai dalam payload adalah nilai mentah sensor; backend yang menerapkan offset.

## Skala baterai

```
V = 2,00 + raw x 0,01
```

- Resolusi 10 mV, rentang `raw` 1 sampai 255, yaitu 2,01 V sampai 4,55 V.
- `raw = 0` berarti tegangan **tidak terukur** (disimpan sebagai kosong, bukan 2,00 V).
- Nilai di luar rentang dipotong ke 1 atau 255 saat encode.
- Di bawah 3,4 V (pengaturan `low_battery_ticket_v`) dibuat tiket baterai otomatis. Di bawah 3,3 V bacaan juga ditandai `suspect` dengan alasan QC `low_battery`.

## Nilai penanda bacaan hilang

Jika sensor gagal dibaca, atau belum ada bacaan sebelumnya (misalnya paket pertama setelah node menyala), firmware mengisi:

| Field | Nilai penanda |
| --- | --- |
| suhu (`temp_now`, `temp_prev`) | `0x7FFF` |
| kelembapan (`rh_now`, `rh_prev`) | `0xFFFF` |

Backend membaca penanda ini sebagai kosong (null). Bacaan kosong **tidak pernah** diganti dengan nilai buatan.

## Contoh

Bacaan normal: seq 42, suhu 33,57 °C dan 61,20 %, bacaan sebelumnya 33,41 °C dan 62,05 %, baterai 3,98 V.

```
01 00 2A 0D 1D 17 E8 0D 0D 18 3D C6
```

| Byte | Hex | Nilai |
| --- | --- | --- |
| 0 | `01` | version 1 |
| 1-2 | `00 2A` | seq 42 |
| 3-4 | `0D 1D` | 3357 -> 33,57 °C |
| 5-6 | `17 E8` | 6120 -> 61,20 % |
| 7-8 | `0D 0D` | 3341 -> 33,41 °C |
| 9-10 | `18 3D` | 6205 -> 62,05 % |
| 11 | `C6` | 198 -> 2,00 + 1,98 = 3,98 V |

Sensor gagal dibaca dan baterai tidak terukur: seq 43.

```
01 00 2B 7F FF FF FF 0D 0D 18 3D 00
```

## Penolakan payload

Decoder menolak payload (dicatat, tidak disimpan sebagai bacaan) jika kosong, `version` bukan 1, atau panjang bukan 12 byte. Uplink dari DevEUI yang tidak terdaftar atau nonaktif dicatat di tabel `unknown_devices`.

## Rencana versi 2 (belum dirancang)

Mode backlog (ringkasan per jam setelah jaringan pulih, dokumen perancangan bagian 5.3) membutuhkan format baru. Belum disepakati.
