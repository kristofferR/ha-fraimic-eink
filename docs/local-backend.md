# Local backend on stock firmware

Implementation for [phase 0 and phase 1](https://github.com/kristofferR/ha-fraimic-eink/issues/99).
The companion in `companion/` owns the stock HTTPS protocol and private transport
journal. The integration owns rendering, originals, creation history, providers
and playback. No firmware patch, update offer or enrollment replacement is included.

## Current evidence

The implementation has been exercised with local HTTP fixtures, synthetic silence,
fake inference providers and real HA/library code. It has **not been deployed to
HA or connected to a physical frame**. The older research experiments are useful
protocol evidence, not acceptance tests for this implementation.

The first hardware target is the **Large, native 1440 × 2560**, already paired.
Read-only HA inspection on **25 October 2026, 01:18 UTC** found:

- HA 2026.10.2; reported frame firmware 0.2.29. The saved firmware research
  identifies build f1555ee5; a fresh device build read is still required.
- Delivery: Hybrid; power: Minimum; polling option: 3,600 seconds; mount: 90°;
  playback enabled with Auto at queue end. Minimum disables periodic LAN polls.
- Last confirmed contact: 23 October, 20:09:50 UTC. Battery: cached 99%;
  charging/cable state: unknown. This is not a live charge measurement.
- Existing network controls reported connectivity-probe and time-sync allowances
  enabled and the vendor/WAN blocking rule disabled. No rule was changed.

Seven days of recorder history contain recharge jumps to 100%, unknown charging
intervals and a long 95–100% plateau. They cannot establish comparable per-mode
battery consumption. There is no measured battery improvement to report.

**Vendor-free** means the frame's API, audio and panel traffic stays on the local
backend. Public NTP and the stock TCP probe may remain reachable. **WAN-free** is
a separate test that also supplies local time, answers the connectivity probe,
and uses local artwork/STT/Assist/generation sources. Online artwork or inference
providers remain online even when the frame transport is local.

## Configuration and packaging

Start with one enrolled device and fixed-image voice. Obtain its existing full
device key and paired user ID privately; the truncated key in `/api/info` is
insufficient. Copy `companion/config.example.json` to a private directory outside
the checkout. Replace all placeholders. Generate a separate random bridge token
(at least 32 characters), and give each frame its own token. Do not use an HA
owner token, Supervisor token, vendor password or device key as the bridge token.

Run on the server or HA host that can receive frame traffic:

```sh
cd "/path/to/ha-fraimic-eink/companion"
uv sync --frozen --no-dev
uv run fraimic-backend --config "/private/fraimic/config.json"
```

Alternatively build the supplied rootless container:

```sh
docker build -t fraimic-backend:local "/path/to/ha-fraimic-eink/companion"
docker run --name fraimic-backend --restart unless-stopped \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  -p 8443:8443 -p 127.0.0.1:8080:8080 \
  -v "/private/fraimic:/data" fraimic-backend:local
```

For the container, set `bridge_bind` to `0.0.0.0` inside its network namespace;
keep the host publication restricted as above. For direct execution, keep the
example's loopback bind unless a private interface is explicitly required.

The mounted directory must be writable by UID 10001. Use a dedicated directory,
mode 0700, with configuration/key files mode 0600. The process needs no host
network, Docker socket, broad host mounts or Supervisor/Core API token. It calls
only the configured HA voice bridge. A future Supervisor app can package this
same service; this change does not install one.

`public_url` is the frame-facing HTTPS origin for upload and panel tickets. On
unchanged firmware the API origin is still `origin.fraimic.com`; DNS/routing and
an accepted certificate for that hostname must be prepared separately. A normal
owner-domain certificate or a DNS override alone is insufficient. The device TLS
listener has no management routes. A separate HTTP bridge on port 8080 shares its
state and exposes only the four authenticated bridge routes. Its default bind is
loopback; the container example binds inside the container and publishes loopback.
For HA on another host, publish it on a private interface reachable only by HA,
or put ordinary trusted TLS in front of it. Set HA's backend URL to that bridge
origin, for example `http://127.0.0.1:8080` for HA on the same host. HA does not
disable certificate verification or use the frame-specific trust chain. HTTP is
supported for a trusted private bridge network, not public exposure.

In the integration's options select **Backend**, enter the companion URL and the
same private bridge token, then choose:

- **Fixed library image:** an existing library image ID; no STT, AI or intent call.
- **Create artwork:** a configured STT entity, its supported language, and an
  `ai_task` entity supporting image generation. Selecting this opts into calls to
  those providers. Configure provider/account cost limits before enabling it.
- **Assist with a result card:** a compatible STT entity/language and an explicit
  conversation agent (default `homeassistant`). Commands follow that agent's HA
  exposure settings. The spoken answer becomes a library image and panel card.

The adapters follow the installed HA 2026.10 APIs, checked against
[STT entity documentation](https://contributors.home-assistant.io/core/entities/stt/)
and [AI Task](https://www.home-assistant.io/actions/ai_task.generate_image/).
The WAV container is validated, then raw mono 16-bit 16 kHz PCM is streamed to
the configured STT entity after checking its metadata support. AI Task's local
media result is copied into the Fraimic library immediately; expiring result URLs
are not the original's storage. Provider/model, transcript, effective prompt,
orientation, job ID and frame provenance remain attached to that original.

Switching from Hybrid/Cloud first retires the integration's vendor album/awake
state using the existing cleanup path. Do that while the vendor is reachable.
Do not block vendor traffic until the options reload has completed. Valid queued
LAN buffers migrate to the companion before their local pending state is cleared;
failed migration retains them for setup retry. The normal playback queue is
preserved. Backend mode blocks LAN upload, refresh, sleep and restart commands at
the client boundary so another HA path cannot interrupt a pull operation.

## Wire and ownership contract

The device listener allows only:

- `GET /api/v1/upload/check/{device_key}`
- `GET /api/v1/albums/{device_key}`
- `POST /api/v1/upload/audio/presign`
- `POST /audio/{upload_ticket}`
- `POST /api/v1/upload/audio/finalize`
- `GET /panel/{asset_ticket}`

Settings are omitted by default, preserving stock preferences. If configured,
all four boolean switches are required. Optional email-verification state is
explicitly configured, never inferred from a client-supplied account ID. Poll
telemetry persists the last contact, firmware version, orientation, periodic-poll
field and battery percentage. SSID/IP queries are accepted but not retained.
Every poll with a valid future HA deadline includes numeric `next_image_utc`.
Settings and deadlines are preserved across listener restarts. Firmware is always
null, including when the saved auto-update preference is true.

The album route is a per-frame, read-only projection of HA's current art transport
record and wake deadline. Its stable ID is `ha-{configured device id}`. The HA
library/playlists/queue remain the editing interface. Stock album CRUD, enrollment,
system images, arbitrary HTTP forwarding and vendor fallback are unsupported and
fail closed. This intentionally does not implement the broader catalog-mutation
proposal in `docs/firmware/album-playlist-mapping.md`.

The companion's `/bridge/state`, `/bridge/delivery`, `/bridge/schedule` and
`/bridge/cancel` require the per-frame bridge token. The integration exposes one
fixed-path `/api/fraimic/backend/voice` view with the same narrow credential. It
does not weaken gallery/admin authentication or expose generic service execution.
Never log Authorization headers, device paths, request bodies or signed URLs.
The companion disables access logging; reverse proxies must do the same for
these paths. They must not cache, compress, redirect or chunk the stock responses.

JSON is compact, at most 4,095 bytes, with an explicit positive Content-Length.
Multipart upload acknowledges only after complete WAV validation and durable
storage, with an exactly empty HTTP 200 body and Content-Length zero. Finalize
waits synchronously for a frozen panel buffer; it never returns 202 or heartbeat
chunks. Panel data is immutable, exact-length octet-stream: 960,000 bytes for
Standard and 2,304,000 for Large, with only valid panel nibbles.

There is one known voice/delivery window per frame. Presign holds routine content
offers; offered/transferring art blocks a new voice job. HA's routine attempts
receive a busy result and retry after the window. A scheduled image cannot replace
an active known voice job. **Stock firmware does not report recording start**, so
a recording that begins before presign can still race an already-issued poll
offer. Software locks cannot close that firmware gap.

An offered asset reserves 180 seconds. A completed/failed transfer keeps a 60/90
second Standard/Large render guard. Tickets permit at most four transfer attempts.
An unfetched ready voice result releases its exclusive window after 180 seconds;
its ticket can remain valid, but a late fetch must wait for any newer delivery.
Concurrent reads of one panel are refused. Interrupted transfers remain retryable;
they do not acknowledge display. Successful server writes become **served** with
`served_at`; neither this nor a finalize response proves client download completion
or a physical redraw. `confirmed_on_panel` stays false. Correlate firmware logs and
owner observation separately during hardware validation.

Queue acceptance advances delivery order and reserves the next HA-selected wake,
without changing the confirmed artwork or power-accounting state. Queue interval
changes update the deadline; an integration reload preserves a future deadline.
A three-minute margin after that wake lets the frame poll and settle before
automatic playback can replace unoffered art.
A sleeping frame learns changes only at its next poll. A minute-resolution HA
scheduler and stock wake timing still need physical validation. Once a deadline
is past, the backend stops advertising it; stock maintenance/fallback behavior
remains in effect during a prolonged HA outage.

## Durability, failures and retention

SQLite records the ticket, complete audio, immutable panel, state and wake
timestamp. Keep the database and private configuration in backups. One process
must own each database; do not run two replicas against it. Rotation/restarts
must preserve this directory.

- Up to eight live jobs globally, one active voice window per frame. Audio is
  bounded to 2,128,192 bytes/66 seconds; panel size and palette are checked.
- Audio expires ten minutes after presign (cleanup runs every 30 seconds) and is erased sooner on success,
  failure or cancellation. The journal uses SQLite secure deletion. Filesystem
  snapshots/backups may still retain historical blocks; exclude recordings from
  backup retention if that is required.
- Voice processing has a 480-second listener budget and 450-second HA budget,
  below the stock ten-minute wait. A disconnected finalize waiter does not cancel
  its provider task. HA unload cancels owned work; its journal prevents replay.
- An uncertain provider or command outcome is never invoked again for the same
  job ID. A later reconciliation can reuse a saved creation or return an uncertainty
  card. A failed initial request gets a short final error with no image URL, which
  stock firmware presents as failure and leaves the previous picture in place.
- Frozen voice assets expire after one hour without a download; scheduled art
  expires after seven days or its earlier composition deadline. Served assets
  remain available for up to three minutes for bounded retries.
- HA frozen voice results retain for 24 hours, with replay tombstones for eight
  days (maximum 512 records per frame). Cleanup runs on setup and new requests.
  Library originals/provenance are permanent until deleted through normal library
  actions. Transcripts are private library metadata, never application log text.

The **Local backend status** sensor exposes generation/transport state, job IDs,
deadlines and server-transfer evidence. It never marks a frame physically updated.
HA uses authenticated companion poll timestamps for last-contact and battery
evidence without pretending that the LAN API is awake.

## TLS lifecycle and rollback

The [saved-build TLS analysis](firmware/tls-durability.md) supersedes the older
expiry assumptions in the epic: Large 0.2.29 and Standard 0.2.28 omit date checks,
use the same embedded roots and supply no CRL. CA revocation predates the successful
research device tests. Fresh-key replacement passes host verification; physical
fresh-key rotation, future firmware/trust changes and unattended lifecycle behavior
remain unverified. Never infer support for an unseen firmware image.

Provision certificates privately; this repository contains no chain-signing keys,
device credentials or certificate-issuance automation. To replace the leaf, put
the reviewed full chain and matching private key in their configured paths, then
send SIGHUP to the listener. Existing connections continue on their old TLS
session; new handshakes use the replacement. Compare public fingerprints and
frame logs, never key contents. Do not offer firmware while this trust route is
being used. Back up the known working private leaf/chain/key for rollback.

The concrete activation sequence for a separately approved live test is:

1. Recheck the Large's current firmware/build, displayed art, pairing and settings.
   Retain the current HA integration and companion config/database backups.
2. Install the reviewed integration and start the companion in fixed-image mode.
   Verify the private bridge, fixture round trip and TLS from the LAN. Keep
   existing network behavior until both services are healthy.
3. Retire vendor art/wake albums while the account is reachable. Stage one library
   image. Prepare an expiring, frame-only DNS/routing change for the API hostname,
   with exact rollback commands and both DNS replicas identified. Do not redirect
   other clients or open the listener to the internet.
4. After approval, activate that bounded route. Confirm idle polls preserve settings
   and show no firmware. Then test the fixed image and one owner-spoken non-private
   recording. Confirm the displayed card visually, in addition to transfer logs.
5. Roll back by restoring that frame's original DNS/routing, checking both replicas
   and DNS cache expiry, and verifying a successful vendor poll. Restore the former
   integration options after the route is back. Keep already-created originals.
   Stop the companion only after its active request has ended or been recorded as
   uncertain. No flashing or factory reset belongs in this procedure.

## Hardware acceptance still required

Record timestamps, firmware/build, server state, frame log evidence and visual
observations for each case. Do not check these off on the basis of fixture tests.

- Vendor blocked: cold boot and normal poll; fixed-image voice round trip; backend
  restart before/after WAV acceptance, during finalize and during transfer; HA
  restart during a possibly billed call; interruption and ticket expiry.
- Rotate to a fresh-key leaf without changing the trusted chain. Test a deliberately
  rejected chain/hostname only in a bounded window with the working leaf ready.
  Reconcile the saved static expiry/revocation evidence with the exact live build.
- Sleep/wake: at least three scheduled wakes; earlier/later schedule changes while
  awake and asleep; missed deadlines; art and voice attempted together; confirm
  no second LAN redraw. Keep served/download/driver/visual evidence separate.
- Full WAN isolation, separately: local DNS, accurate local NTP and a local answer
  for the stock `8.8.8.8:53` TCP probe. Include cold boot, cached DNS expiration,
  backend/time/DNS outages and recovery. Verify traffic capture, not just the
  absence of vendor responses. Use local providers for a WAN-free voice claim.

Battery comparison requires elapsed time: run **at least 72 hours per useful mode**
(stock scheduled sleep, current Hybrid/Minimum, then local backend at the same
cadence). Keep brightness irrelevant (e-ink), artwork, wake interval, temperature,
Wi-Fi conditions and interaction count comparable. Record fresh contact timestamps,
battery percentage/voltage, charging/cable state, redraws, voice jobs and restarts.
Exclude recharge periods, unknown charging state, stale readings and the ≥95%
gauge plateau. Report percentage points/day only for comparable discharge windows,
with redraws/day and missing observations. These measurements have not begun under
controlled conditions and no multi-day completion is claimed.

## Validation commands

```sh
cd "/path/to/ha-fraimic-eink/companion"
uv sync --frozen
uv run pytest -q
uv run mypy
cd "/path/to/ha-fraimic-eink"
uv run --with pillow --with numpy --with pytest --with voluptuous --with resvg_py pytest
bun test tests/*.test.js
uv run --python 3.14 --with-requirements requirements_test.txt \
  pytest tests_ha --cov=custom_components.fraimic --cov-fail-under=29
uv run --python 3.14 --with-requirements requirements_test.txt mypy
```

Keep the HA-free suite, companion suite and real-HA suite in separate processes.
Fixtures use no private recordings, vendor connection, live HA writes, paid calls
or real frame. Host tests establish implementation behavior; the acceptance cases
above establish hardware behavior.

## Alignment with the related issues

[Protocol service](https://github.com/kristofferR/ha-fraimic-eink/issues/84) and
[recorded voice](https://github.com/kristofferR/ha-fraimic-eink/issues/86) remain
active phase-1 work. Their earlier HA-hosted-device-endpoint and URL-patch wording
is superseded by the companion/unchanged-firmware direction in the epic and later
research. The narrow HA bridge and library/provider work are reusable with a
future firmware transport. Firmware patch tooling/recovery are not prerequisites
for this stock route and belong to a separately justified later phase. Neither
issue should be closed until its physical acceptance criteria are met.
