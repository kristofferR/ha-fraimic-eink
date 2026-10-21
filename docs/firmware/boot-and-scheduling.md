# Boot, sleep and scheduling

[Research index](README.md)

## Main lifecycle

`0x42012810` is the main loop; `0x42012338` contains pre-sleep work. The recovered
branches distinguish normal boot, physical-button wake, charging-cable wake,
display-maintenance timer wake and album-image timer wake. First-time setup has
its own instruction screens/AP mode and timeout behavior.

The loop coordinates background Wi-Fi initialization, a cloud poll, recording,
upload/download/render, pending OTA, requested sleep and idle sleep. Display work
and recording are not independent tasks with independent image/audio memory.

| Situation | Relevant behavior |
| --- | --- |
| Already-paired physical wake | Start background services; accept recording/button workflow |
| Album timer wake | Initialize storage/network, check cloud work, calculate next wake |
| Maintenance timer wake | Restore/refresh saved display content through a separate branch |
| Charging wake | Battery monitoring and idle/LED behavior depend on setup and switches |
| First-time setup timeout | Enter storage sleep |
| Pending OTA before idle/sleep | May install first if safety conditions pass |
| Deep sleep | Wi-Fi/local HTTP unavailable until a supported wake source fires |

A plain LAN packet cannot wake a frame already in deep sleep. More frequent
scheduled wakeups trade battery life for responsiveness. HA's existing push queue
and a proposed frame-driven pull scheduler solve different parts of that problem.

## Album deadline persistence

`0x4202475c` accepts a numeric future `next_image_utc`, with
`next_scheduled_image_time` as a compatibility fallback. It passes the resulting
64-bit value to `0x42015d30`, which stores `app_data/sched_img_time` in NVS.
`0x42015d60` reloads it when the RAM cache is zero.

The successful-response parser writes zero for a missing, null, invalid or past
deadline. Therefore an idle success response must still carry the intended future
deadline while an album schedule is active. A failed network transaction exits
before this parsing path and is not equivalent to a successful empty response.

## Two deadlines compete

`0x42015de8` selects between maintenance refresh and album content:

```text
threshold = now + 30 seconds
candidate = none
if maintenance_time > threshold:
    candidate = maintenance_time, reason 0
if album_time > threshold and (no candidate or album_time < candidate.time):
    candidate = album_time, reason 1
```

The comparison is strict. Equal deadlines retain maintenance reason 0. This
routine returns a structure across multiple registers; Ghidra's inferred return
type can omit part of the logic. The comparisons were checked in GNU disassembly.

Choose deadlines that remain more than 30 seconds away **after** downloads and
panel work finish. `now + 31` at response construction is not sufficient margin
for a long transfer/redraw.

### Maintenance timing

`0x42016274` creates a schedule with `(interval_days=4, hour=3, minute=0)` when
none is stored. `0x42015f2c` accepts intervals 1–30 days, hours 0–23 and minutes
0–59. These are internal function parameters, not proof of a public setter API.

`0x42014dcc` calculates in local calendar time. The initial target can be today's
03:00 if at least 15 minutes away; otherwise it adds the configured day interval.
It uses the stored POSIX timezone, with `EST5EDT` fallback. This is not always a
96-hour interval, and the fallback may not match the owner's location.

### Missing/missed schedule behavior

- After an album wake, a positive saved album timestamp that is no longer more
  than 30 seconds ahead triggers a five-minute retry, retaining album wake reason.
- If no album timestamp remains, the branch falls back to maintenance scheduling.
- Consequently a successful poll that clears the timestamp can also remove the
  five-minute retry path.
- Without valid synchronized time, unified scheduling uses a 24-hour fallback
  when Wi-Fi credentials are available.
- The lower-level timer setter has an elapsed-target safety fallback of roughly
  60 seconds. This is separate from the album retry and not a promise of one-minute
  cloud polling.

A device timing test is still needed for outages, drift, overdue events,
maintenance collisions, long rendering, timezone changes and cold boots.

## Storage sleep and factory-test mode

`0x42010674` marks `deep_sleep` and `storage_mode`, shuts down Wi-Fi/display,
clears wake sources and arms a physical-button EXT1 wake. Logs explicitly describe
this as storage mode with no scheduled wakeups. Do not treat this as ordinary
album sleep or assume a remote wake remains possible.

Opening the `/test` landing page enters a roughly ten-minute factory-test mode
that suppresses background behavior. Its eventual timeout sleep is not evidence
that ordinary idle sleep works. `/test?action=battery` is a separate read branch.
See [local API side effects](local-api.md).

## Offline dependencies

### Public reachability gate

`0x4202ed80` opens a nonblocking TCP connection to `8.8.8.8:53` and waits up to
three seconds. A successful connection or `ECONNREFUSED` (111) after selection
counts as reachable. This is neither a DNS lookup nor ICMP ping.

`0x4202f18c` returns the cached connectivity result. Voice processing at
`0x42011adc` waits about five seconds, then aborts before upload if it stays false.
The connectivity manager also influences recovery/failover. Patching only one
getter to always return true would not repair the manager's other decisions.

**Proposed:** distinguish Wi-Fi association, local backend availability and WAN
availability. Probe the configured backend instead of requiring a public target.

### Time service

`0x42014e90` rotates explicit SNTP servers from a table at `0x3c13bbc4`:

1. `time.google.com`
2. `pool.ntp.org`
3. `time.cloudflare.com`
4. `time.nist.gov`

The routine manages a synchronized-time flag used by scheduling and OTA safety.
RTC time surviving deep sleep does not establish successful offline cold boot.
Local NTP configuration, cold-boot behavior and failure recovery need explicit
support/testing in a custom firmware.

### Setup and identity

The account/setup screens have server fetches even when local filesystem support
exists. Web/authentication selectors are separate from the central API selector.
For the first emulator, preserve the already-paired identity and supply required
system assets. A factory reset is not a harmless way to test local-cloud support.
