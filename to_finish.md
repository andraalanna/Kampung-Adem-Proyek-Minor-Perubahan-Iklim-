# To finish (handoff, updated 3 Nov 2026)

Scope agreed with the user: **software only, fed by simulated sensor data**. Hardware (firmware, LoRaWAN gateway, ChirpStack/MQTT) is design-only; keep those files as design artifacts, no more work on them.

Nothing is committed yet.

## 1. Done on 3 Nov 2026

- [x] Clean-start verification of `infra/docker-compose.dev.yml`: no false `ticket_offline`. Open tickets after start: `KA-SBY-0004 ticket_battery`, `KA-SBY-0010 ticket_anomaly` only.
- [x] Fixed a false `ticket_anomaly` on healthy node `KA-SBY-0009`: the MAD check now requires |z| > 3.5 in every check over the last hour (design doc 10.2, "selama lebih dari 1 jam") and uses all non-invalid readings so a neighbor-flagged node does not shrink the reference group. Test added (32 tests).
- [x] Screenshots re-run, all pages render, no console errors besides the expected pre-login 401.
- [x] `.gitignore`, `CLAUDE.md` (in repo, updated), `README.md`, `docs/demo.md`, `docs/payload.md`, design doc copied to `docs/`.
- [ ] Ask the user whether to **commit** (and push to `origin` = github.com/andraalanna/Kampung-Adem-Proyek-Minor-Perubahan-Iklim-).

## 3. Nice to have (ask before doing)

- Simulator "skenario" for presentations: e.g. `python -m app.sim live --boost 3` already exists to force SIAGA/AWAS live. Maybe a dashboard-visible "Mode demo" toggle or a fast-forward speed option.
- Tier C estimation (regression on LST baseline + IDW residuals) is not implemented; falls back to tier B, as the design doc allows.
- Kelurahan staff "combined summary" WhatsApp (doc 11.6, 13.3 merging within 15 min) not implemented.
- Monthly report is CSV only; PDF not done.
- BMKG reference value on the dashboard shows "Belum terhubung" (no integration).
- Dark mode not done.
- Firmware never compiled: `pio run` failed downloading RadioLib due to a Windows long-path issue (not a code error). Only matters if hardware ever happens.

## 4. Decisions waiting for the user (affect alert behaviour, CLAUDE.md says ask)

1. **Escalated AWAS exit rule.** AWAS reached by "SIAGA lasting 3 h" now exits by SIAGA's exit rule (HI < 39 °C for 60 min), stored as `rw_status.escalated`. Before the fix it flapped AWAS -> SIAGA immediately and could resend AWAS every 3 h. Confirm this interpretation (ideally with Dinkes).
2. **Manual alerts do not send WhatsApp.** `POST /alerts` with `send_whatsapp: true` returns 422, because the approved template needs measured values and a separate manual-advisory template has not been worded/approved.
3. **Payload conventions** chosen within v1: battery byte `V = 2.00 + raw x 0.01` (raw 0 = not measured); missing reading sentinels temp `0x7FFF`, RH `0xFFFF`. Mirrored in `firmware/include/payload.h` and `backend/app/core/payload.py`.
4. **Daily cap counts both templates** (`peringatan_panas_rw` and `status_panas_turun`) toward the 3 messages per recipient per day. Held messages (quiet hours, cap, cooldown) are logged as `held` and never sent later.
5. Backlog mode (hourly summaries after the network recovers, doc 5.3) needs a payload v2; not designed.

Real commands are now in `CLAUDE.md` and `docs/demo.md`.
