# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

## Project

**Kampung Adem**: real-time, neighborhood-level (RW) heat map and early warning system for Surabaya, built for MK4056 Perubahan Iklim (ITB), Kelompok 6.

Low-cost temperature/humidity sensor nodes send data over LoRaWAN to a backend that computes heat index per RW, overlays Landsat land surface temperature (LST), shows a map dashboard, and sends official WhatsApp alerts to RT/RW and kader posyandu.

The full design document (architecture, BOM, ERD, API, thresholds, flowcharts) is `docs/Kampung Adem Dokumen Perancangan Sistem End-to-End.md` (exported from Claude Docs: "Kampung Adem: Dokumen Perancangan Sistem End-to-End"). **Treat it as the source of truth.** If code and the doc disagree, ask before changing either.

## Scope

**Software only, fed by simulated sensor data.** There is no hardware (no sensors, no gateway). The firmware, ChirpStack, MQTT and production compose files are **design artifacts**: keep them consistent with the payload contract, but do not invest more work in them unless hardware becomes real. Demos run on the simulator (`backend/app/sim`), which pushes uplinks through the real ingest code (payload v1 encode, decode, QC, DB), so the backend is exercised exactly as with hardware. The dashboard shows a "Mode demo" banner; never present simulated values as real measurements.

## Structure

```
backend/         Python FastAPI
  app/api/       REST routers under /api/v1
  app/core/      pure logic: payload codec, heat index, QC, status engine, crypto, time
  app/ingest/    ChirpStack MQTT consumer + HTTP ingest (design-only path for hardware)
  app/worker/    scheduler: health/QC, status + RW estimation, satellite, WhatsApp notifier
  app/sim/       simulator: demo dataset (seed), backfill, live uplinks
  app/models/    SQLAlchemy models
  app/cli.py     admin CLI (keys, admin user, RW GeoJSON import)
  migrations/    Alembic
  tests/         pytest
frontend/        React + Vite + TypeScript dashboard (react-leaflet, TanStack Query, Tailwind, Recharts)
firmware/        Heltec WiFi LoRa 32 V3 node firmware (PlatformIO). Design only, never compiled
satellite/       Earth Engine script for Landsat LST
infra/           docker-compose.dev.yml (demo), docker-compose.yml (production design), Caddy,
                 ChirpStack, Mosquitto, backup scripts
docs/            design doc, demo guide, payload spec
```

## Tech stack (decided, do not swap without discussion)

| Layer | Choice |
| --- | --- |
| Sensor | Sensirion SHT31 over I2C (addr 0x44) |
| Node | Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262) |
| Radio | LoRaWAN Class A, OTAA, **AS923-2** (Indonesia, 920-923 MHz). Never 433 MHz or US915 plans. |
| Network server | ChirpStack v4, self-hosted |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic, Alembic, APScheduler |
| Database | PostgreSQL + TimescaleDB + PostGIS (image `timescale/timescaledb-ha`), Redis |
| Frontend | React + Vite + TypeScript, react-leaflet, OSM tiles |
| Satellite | Google Earth Engine Python API, Landsat 8/9 C2 L2 ST, MODIS MOD11A1 v061 |
| WhatsApp | WhatsApp Cloud API (Meta) only, approved **utility** templates |
| Hosting | One Indonesian VPS, Docker Compose |

## Commands

Backend (from `backend/`, Windows paths shown; use `.venv/bin/` on Linux/macOS):

```
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest                                # tests
.venv/Scripts/python -m ruff check app tests migrations       # lint
alembic upgrade head                                          # needs DATABASE_URL
uvicorn app.main:app --reload                                 # API, docs at /api/docs
python -m app.worker.main                                     # scheduled jobs
python -m app.sim seed | backfill --hours 24 | live [--boost 2] | demo
python -m app.cli gen-key | create-admin EMAIL NAME | import-rw FILE.geojson
```

Frontend (from `frontend/`): `npm install`, `npm run dev` (proxies `/api` to :8000), `npm run build`, `npm run lint`, `npm test`.

Demo stack (database, API, worker, simulator; no hardware):

```
docker compose -f infra/docker-compose.dev.yml up --build -d
cd frontend && npm run dev          # http://localhost:5173
docker compose -f infra/docker-compose.dev.yml down -v   # reset everything
```

Startup order: `db` -> `api` (runs migrations) -> `simulator-backfill` (seed + 24 h backfill, one-shot) -> `worker` and `simulator` (live). The worker waits for the backfill so health checks never see half-filled history. Demo logins and scenario details: `docs/demo.md`.

Production stack (design, untested): `infra/docker-compose.yml` with `infra/.env` copied from `infra/.env.example`.

Firmware (design only): `pio run`, `pio run -t upload`. Last attempt failed on Windows while downloading RadioLib (long-path issue, not a code error).

## Domain rules (important, easy to get wrong)

1. **Air temperature is not LST.** Sensor = air temperature at about 2 m. Satellite = land surface temperature. Never label LST as "suhu udara", never trigger alerts from LST.
2. **Satellite data is not real-time.** Landsat revisit is 8 days combined and often cloudy. Always show `lst_scene_date`.
3. **Alerts are operational thresholds, not medical diagnosis.** Never write UI or message copy that says someone has heatstroke. Use "panas ekstrem tingkat lingkungan", not "gelombang panas/heatwave".
4. **Status levels** (heat index, °C, from `alert_thresholds`, never hardcoded):
   - NORMAL < 32, WASPADA 32 to < 41 (dashboard only), SIAGA >= 41 for 30 min (WhatsApp), AWAS >= 46 for 30 min or SIAGA for 3 h (WhatsApp)
   - Exit uses hysteresis (2 °C lower, 60 min). TIDAK ADA DATA when no valid reading for 30 min.
   - Only RW estimated from real sensors (tier A) go through the status engine and may send WhatsApp automatically. Tier B/C/D estimates are displayed but carry status TIDAK ADA DATA.
   - AWAS reached by escalation (SIAGA for 3 h) is stored as `rw_status.escalated` and exits by SIAGA's exit rule (pending confirmation with Dinkes, see "Open decisions").
5. **Heat index:** NWS Rothfusz regression (compute in °F, convert to °C); Steadman simple formula below 80 °F.
6. **Anti-spam:** cooldown 3 h per RW per level, max 3 alert messages per recipient per day (both templates count), quiet hours 21.00-05.00 WIB except AWAS. Held messages are logged as `held` and never sent later.
7. **Missing data is never filled with fake values.** Show gaps; hourly aggregates need >= 70% of readings.
8. **Calibration offsets** (`offset_temp`, `offset_rh`) are applied in the backend, not in firmware.
9. **Device QC** (worker, every 10 min): neighbor check (> 4 °C from kelurahan median, `ok` readings only, downgrades to `suspect`) and MAD anomaly (|robust z| > 3.5 in every check over the last hour, on all non-invalid readings) which opens a "cek perangkat" ticket.

## Data contracts

**Uplink payload v1 (12 bytes, big-endian):** full spec in `docs/payload.md`.

| Bytes | Field | Encoding |
| --- | --- | --- |
| 0 | version | uint8 (= 1) |
| 1-2 | seq | uint16 |
| 3-4 | temp_now | int16, x0.01 °C |
| 5-6 | rh_now | uint16, x0.01 % |
| 7-8 | temp_prev | int16, x0.01 °C |
| 9-10 | rh_prev | uint16, x0.01 % |
| 11 | battery | uint8, `V = 2.00 + raw x 0.01` (raw 0 = not measured) |

Missing-reading sentinels: temp `0x7FFF`, RH `0xFFFF` (decoded as null). Mirrored in `firmware/include/payload.h` and `backend/app/core/payload.py`; keep them in sync.

Node reads every 5 min, sends every 10 min (2 readings per packet), unconfirmed uplinks. Any payload change bumps `version` and needs a decoder update with tests.

**QC flags:** `ok`, `suspect`, `invalid`. Only `ok` feeds status.

**API:** all routes under `/api/v1`, JSON, timestamps ISO 8601 with `+07:00`, temperatures in °C. Map endpoints return GeoJSON (SRID 4326). OpenAPI docs at `/api/docs`.

**Database additions beyond the ERD (doc 9.2)** (see `backend/app/models/__init__.py`):

- `rw_status`: current status-engine state per RW (level, since, no-data since, escalated).
- `status_events`: log of every status/alert change.
- `unknown_devices`: uplinks from unregistered DevEUIs (doc 15.4).
- `alert_thresholds`: also holds exit value/duration, escalation, version, active flag, approval note, so hysteresis and escalation live in the table, not in code.
- `sensor_readings`: `seq`, `qc_reasons`, raw temp/RH; `notification_logs`: queue + webhook fields.
- `recipients`: `phone_hash`, `opt_out_at`.

## Not implemented yet (known gaps)

- Tier C estimation (regression on LST baseline + IDW residuals): falls back to tier B, as the doc allows.
- Kelurahan staff combined summary WhatsApp (doc 11.6, 13.3).
- Monthly report as PDF (CSV only).
- BMKG reference value (dashboard shows "Belum terhubung").
- Dark mode.
- Backlog mode (hourly summaries after network recovery, doc 5.3): needs payload v2, not designed.
- Manual alerts (`POST /alerts`) cannot send WhatsApp (`send_whatsapp: true` returns 422) until a manual-advisory template is worded and approved.

## Open decisions (ask the user / Dinkes before changing)

1. Escalated AWAS exit rule (see domain rule 4).
2. Manual-advisory WhatsApp template wording.
3. Payload conventions within v1 (battery scale, sentinels): chosen by us, not yet reviewed.
4. Daily cap counting both templates; held messages never sent later.

## Conventions

- Code, identifiers, commit messages: English. UI copy, WhatsApp templates, user docs: **Bahasa Indonesia**, plain and formal-friendly.
- Do not use em dashes in user-facing text or docs.
- Every status/alert change must be logged; every WhatsApp send gets a `notification_logs` row.
- Database changes only through Alembic migrations. Geometry columns get GiST indexes.
- Keep the system cheap and simple: no Kubernetes, no extra databases, no paid services without discussion.

## Security and privacy

- Never commit secrets. WhatsApp System User token, DB passwords, encryption keys, ChirpStack/AppKeys go in `infra/.env` (gitignored); see `infra/.env.example`. `infra/dev.env` is committed on purpose: dev-only values, clearly labelled, never for production.
- Phone numbers are encrypted at the application level (AES-GCM) plus a hash for lookup; show them masked in the UI.
- Store only **counts** of vulnerable residents per RW, never names or addresses.
- Each LoRaWAN node has a unique AppKey. Verify the `X-Hub-Signature-256` header on Meta webhooks.
- Recipients must have opt-in recorded (`opt_in_at`) before receiving WhatsApp messages. Handle "STOP".
- No unofficial WhatsApp Web automation libraries, ever.

## When unsure

Prefer asking over guessing for anything that changes thresholds, alert behavior, message wording, payload format, or hardware choices. These affect real residents and are reviewed with Dinkes/kelurahan.
