# Kampung Adem

Peta panas dan sistem peringatan dini panas ekstrem tingkat lingkungan (per RW) untuk Kota Surabaya.

Proyek mata kuliah MK4056 Perubahan Iklim, Institut Teknologi Bandung, Kelompok 6.

## Apa itu Kampung Adem

Kampung Adem memantau suhu udara dan kelembapan di tingkat RW, menghitung indeks panas, lalu:

- menampilkan **peta panas per RW** di dashboard, dengan lapisan tambahan suhu permukaan tanah (LST) dari citra satelit Landsat;
- memberi **status** NORMAL, WASPADA, SIAGA, atau AWAS untuk tiap RW berdasarkan ambang operasional;
- mengirim **peringatan WhatsApp resmi** (WhatsApp Cloud API, template yang disetujui) kepada ketua RT/RW dan kader posyandu saat status mencapai SIAGA atau AWAS.

Status adalah ambang operasional tingkat lingkungan, bukan diagnosis medis. Suhu permukaan dari satelit tidak dipakai untuk peringatan.

Rancangan lengkap (arsitektur, perangkat keras, basis data, API, ambang, alur peringatan) ada di [docs/Kampung Adem Dokumen Perancangan Sistem End-to-End.md](<docs/Kampung Adem Dokumen Perancangan Sistem End-to-End.md>).

## Status proyek

Yang sudah berjalan adalah **perangkat lunak dengan data sensor simulasi**: backend, worker (QC, status, peringatan, satelit), dashboard, dan simulator. Perangkat keras (firmware node, gateway LoRaWAN, ChirpStack) baru sebatas **rancangan** dan belum diuji di lapangan.

## Mencoba demo

Butuh Docker Desktop dan Node.js 20 atau lebih baru.

```
docker compose -f infra/docker-compose.dev.yml up --build -d
cd frontend
npm install
npm run dev
```

Buka http://localhost:5173 dan masuk dengan `admin@demo.kampungadem.id`, kata sandi `adem-demo-2026`.

Panduan demo lengkap (akun lain, isi data per RW, alur presentasi, cara memicu SIAGA/AWAS): [docs/demo.md](docs/demo.md).

## Struktur folder

| Folder | Isi |
| --- | --- |
| `backend/` | API (FastAPI), ingest uplink, worker terjadwal, simulator, migrasi basis data |
| `frontend/` | Dashboard web (React, Vite, TypeScript, Leaflet) |
| `firmware/` | Firmware node Heltec WiFi LoRa 32 V3 + SHT31 (rancangan) |
| `satellite/` | Skrip Google Earth Engine untuk LST Landsat |
| `infra/` | Docker Compose (demo dan produksi), Caddy, ChirpStack, Mosquitto, skrip backup |
| `docs/` | Dokumen perancangan, panduan demo, spesifikasi payload |

## Dokumentasi

- [Dokumen perancangan sistem](<docs/Kampung Adem Dokumen Perancangan Sistem End-to-End.md>)
- [Panduan demo](docs/demo.md)
- [Format payload uplink v1](docs/payload.md)
- [Catatan firmware](firmware/README.md)
- [CLAUDE.md](CLAUDE.md): panduan teknis untuk pengembang (perintah, aturan domain, konvensi), dalam bahasa Inggris

## Pengembangan

Ringkasan perintah (detail di [CLAUDE.md](CLAUDE.md)):

```
# backend/
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check app tests migrations

# frontend/
npm run lint
npm test
npm run build
```

## Keamanan dan privasi

- Rahasia (token WhatsApp, kata sandi basis data, kunci enkripsi, AppKey LoRaWAN) disimpan di `infra/.env` yang tidak masuk git. Contohnya ada di `infra/.env.example`. Berkas `infra/dev.env` hanya berisi nilai untuk demo lokal.
- Nomor telepon penerima dienkripsi dan ditampilkan tersamar.
- Hanya **jumlah** warga rentan per RW yang disimpan, tanpa nama atau alamat.
- Penerima WhatsApp harus memberi persetujuan (opt-in) dan dapat berhenti dengan membalas "STOP".
