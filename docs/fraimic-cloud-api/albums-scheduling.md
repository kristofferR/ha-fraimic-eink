# Cloud albums as a battery-preserving delivery path

Verified 2026-09-07 against `origin.fraimic.com` and a 31.5" frame on firmware
0.2.29. The point: with `keep_awake` off the frame deep-sleeps and wakes itself
for the album schedule, so images can be delivered without HA ever talking to
the frame over the LAN.

## Frame behaviour

- Every ~30 s while awake the frame calls `GET /api/v1/upload/check/{device_key}`
  and logs `Poll OK: upload=Y|N, next_img=set|-, fw=…, settings=[…]`.
- `next_image_utc` from that poll is a deep-sleep wake candidate:
  `SYSTEM_MANAGER: WAKEUP: Timer set for album image (in 1038s)`. Without an
  album it falls back to the 4-day ghosting refresh
  (`WAKEUP: No valid wake candidates, using refresh schedule as-is`).
- Activating an album pushed its first image on the very next poll
  (`upload=Y`) and set the next image to `created_at + interval`.
- The cloud serves a fully processed panel binary (2,304,000 bytes for the
  31.5"). Download ran at ~27 KB/s (85 s), render ~40 s: poll to glass in about
  2 min 15 s.
- `keepAwakeEnabled` is applied on the next poll
  (`Device settings changed: … keep_awake=disabled`). The frame then sleeps
  after 120 s without activity (`[ACTIVITY] Idle for 120s, entering deep
  sleep`); local `/api/info` and `/logs` requests count as activity.
- Timer wake: `Reset reason: DEEP_SLEEP`, `Timer wake-up: ALBUM IMAGE —
  performing server check`, poll → `upload=Y` → download → render → idle →
  sleep. Whole wake ≈ 4.5 min including the 120 s idle.
- Slots are anchored to the album's `created_at` plus multiples of the
  interval (00:38:52 → 00:58:52 → 01:18:52), not to when the frame fetched.
- A sequential album with one image re-serves that image every slot: the frame
  downloads and renders it again. Keep the album's images fresh or lengthen the
  interval; there is no "nothing new" short-circuit.
- `PUT /api/v1/albums/{id}` re-anchors the slots to the album's new
  `updated_at` (PUT at 05:05:28 → slots at 05:25:28, 05:45:28, …). Replacing
  `upload_ids` while the frame slept was served at the following slot.
- An album-timer wake is short: poll → download (87 s) → render (63 s) →
  `[ALBUM] Album wake complete — entering deep sleep`, no 120 s idle wait.
  About 2 min 40 s awake per slot. Only wakes that are not album wakes (button,
  keep-awake) use the idle timer.
- The frame keeps only the current and one previous boot in its log ring
  buffer, so an unobserved wake is lost.
- Log timestamps on the frame are in the firmware's local zone (UTC-4 here),
  not the household's.

Cloud album acceptance is reported as `queued: true`, `cloud_queued: true`,
`uploaded: false`, and `displayed: false`. The account API does not confirm
which image reached the glass, so previews and now-playing metadata retain
the last confirmed local display. Playlist delivery order advances separately;
automatic uploads wait until after the cloud wake slot before replacing its image.

## Account auth

Supabase email/password. The anon key is public in the web bundle
(`app.fraimic.com/assets/index-*.js`, project `sclpedxwezoiwzesfdps`).

```
POST https://sclpedxwezoiwzesfdps.supabase.co/auth/v1/token?grant_type=password
apikey: <anon key>
{"email": "...", "password": "..."}
→ {access_token (1 h), refresh_token, expires_at, user}
POST …/token?grant_type=refresh_token  {"refresh_token": "..."}
```

Bad credentials: `{"code":400,"error_code":"invalid_credentials"}`. Quirk: the
web app first tries `URLSearchParams`-encoded password, then the raw one.
Account routes take `Authorization: Bearer <access_token>`.

## Upload an image

```
POST /api/v1/upload/image/presign?content_type=image/png&mark_for_check_for_upload=false
→ {url, fields{...}, key, upload_id}
POST {url}  multipart: every `fields` entry, then `file`   → 204
```

`mark_for_check_for_upload=false` keeps the upload out of the "new upload"
push so it only shows when an album serves it. The record is visible at
`GET /api/v1/gallery/{upload_id}` (orientation/crop_params null).

## Albums

```
POST /api/v1/albums
{
  "name": "…", "description": "…", "active": true,
  "device_assignments": [{"device_id": "<uuid from /api/v1/account/devices>"}],
  "schedule": {"type": "interval", "interval_value": 20, "interval_unit": "minutes"},
      or      {"type": "specific_days", "days": ["monday", …]},
  "playback_mode": "sequential" | "random",
  "upload_ids": ["…"]
}
PUT /api/v1/albums/{id}   same fields, partial (the web app sends {"upload_ids": [...]} alone)
DELETE /api/v1/albums/{id}
```

`device_assignments` uses the account `device_id` UUID, not the frame's
`device_key`. Response adds `images[{upload_id, url (presigned original), created_at}]`,
`image_count`, `created_at`, `updated_at`.

## Device settings

```
POST /api/v1/account/settings
{"device_id": "…", "settings": {"voiceRecordingEnabled": true, "keepAwakeEnabled": false,
                               "chargingLedEnabled": true, "style": "NONE"}}
```

Send all four keys (the web app does). They land in `pending_settings` and are
applied on the frame's next poll.
