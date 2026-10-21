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

The [NVS follow-up](storage-and-configuration.md#a-failed-schedule-clear-can-reload-the-old-deadline)
found that zero is also the getter's cache-miss sentinel. If a clear fails to
persist, a subsequent getter can reload the old NVS deadline in the same wake
session. This is an untested storage-fault consequence, distinct from the
ordinary successful-save semantics above.

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

The awake USB-powered read on 21 October actually reported `EST5EDT` in `/info`;
the synchronized log time was UTC−04:00. This confirms that timezone on this
unit at the time of the read, not merely a static fallback. No timezone was
changed. Album UTC epochs and maintenance local-calendar times must stay distinct.

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

The saved previous-boot log explicitly recorded `FACTORY-TEST-TIMEOUT` after ten
minutes, with a configured user taking the sleep-only path. It confirmed a
2,304,000-byte saved image, gauge sleep, Wi-Fi shutdown and both button/timer wake
sources. The later USB-powered boot reported `DEEP_SLEEP` and the existing-user
button-wake path. Plug/tap ordering was not controlled; these observations do
not establish ordinary unplugged idle-sleep behavior or the battery bug's cause.

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

The recovered monitor entry is `0x4202f674`; its interval selector is
`0x4202eeb4`. Intervals below are waits between iterations, so probe execution
can add time:

| State | Wait |
| --- | --- |
| Healthy (1) | 60 seconds |
| Suspect (2) | 15 seconds |
| Verify replacement AP (3) | No interval wait before the probe |
| Wait/retry (4) | 30 seconds powered; 60 seconds on battery |
| Passive (5) | 60 seconds powered; 300 seconds on battery |

Here “powered” means charging detection **or keep-awake**, via `0x4202ee94`.
The passive-state log mentioning five minutes does not describe both branches.
The monitor initially sets cached reachability true; that is initialization,
not proof a probe has succeeded.

Failure handler `0x4202f2f0` moves healthy to suspect, marks connectivity false
and enables the fallback AP. Repeated failures lead to AP failover/verification,
retry cycles and eventually passive checks. It can clear the AP blacklist and
retry after exhaustion. Success handler `0x4202f294` clears failure counters,
marks healthy, disables fallback AP and records channel/BSSID information.
Disconnected wait/passive states also attempt Wi-Fi reconnection.

Consequently WAN loss can provoke AP recovery even while a local API is healthy.
Changing only the API hostname, or bypassing the voice getter, does not repair
that policy. These detailed Large transitions are static findings; Large-specific
backend-up/WAN-down and recovery timing still need a controlled device experiment.

**Observed on Standard 0.2.28:** its blocked TCP reachability probe triggered AP
failover and interrupted a working download at 556,592 of 960,000 bytes. An
owner-approved, source-specific exception restored internet-available state and
stability. That exception was removed after the capture; the original policy
again blocks the Standard probe. See the [live comparison](standard-model-comparison.md#public-reachability-caused-a-real-transfer-failure).
This confirms an operational consequence on Standard without establishing full
offline operation or every Large transition.

### Time service

`0x42014e90` rotates explicit SNTP servers from a table at `0x3c13bbc4`:

1. `time.google.com`
2. `pool.ntp.org`
3. `time.cloudflare.com`
4. `time.nist.gov`

The recovered background initializer `0x420167b4` calls this routine with five
attempts. It cycles Google, pool, Cloudflare, NIST, then Google again, stopping
and restarting the SNTP client between attempts. Semaphore wait budgets are
200, 400, 800, 1,000 and 1,000 ticks: **2, 4, 8, 10 and 10 seconds** with this
build's 10 ms tick. Their sum is 34 seconds before call overhead; this is not a
measured startup duration. A successful response can finish an attempt earlier.

The time state has separate meanings:

| Address | Meaning in recovered code |
| --- | --- |
| `0x3fca6b4c` | Application considers time synchronized; scheduler and OTA safety consume this flag |
| `0x3fca6b43` | Synchronization completed in this wake session; permits the routine's early return |
| `0x3fca6b44` | Synchronization is in progress |
| `0x3fca6b48` | Shared completion semaphore handle |

Callback `0x42014728` reads the clock and checks that the local-calendar year is
at least 2020 (`tm_year >= 120`). Only then does it set the synchronized flag and
signal the semaphore. An earlier year logs a warning without signaling. This is
a plausibility check, not a bound on drift or proof the time source is accurate.
On successful completion, the waiting routine applies the configured timezone,
or `EST5EDT` if empty, and sets the completed-this-wake flag.

The recovered fast and background initialization paths do not promote a plausible
RTC clock into that application flag. The callback is the only recovered writer
of `true`; the checked alternatives clear or read it. This is not a proof against
all indirect writes or a controlled cold-boot/deep-sleep experiment. RTC survival
alone therefore does not establish working offline scheduling. Without the flag,
the unified scheduler takes the 24-hour fallback described above.

### Time failure also triggers AP failover

Startup does not treat time-server failure as an isolated scheduling problem:

1. After Wi-Fi association, `0x420167b4` calls synchronization at `0x42016d84`.
2. A nonzero result records a Wi-Fi failure event and calls the no-internet AP
   failover routine `0x4201daa0` at `0x42016ef7`.
3. That routine can blacklist the current BSSID, disconnect Wi-Fi, remove fixed
   BSSID/channel selection and reconnect or scan the same SSID for another AP.
   Its exhaustion counter limits this path; a call need not find another AP.
4. After successful failover, startup clears the completed-this-wake flag and
   tries five SNTP attempts again. Failed recovery uses fallback scheduling.
5. Startup starts the separate public-connectivity monitor after this sequence.

Thus **a working API and successful public TCP probe are insufficient if time
synchronization fails**. The time-failure path can cause AP switching before the
monitor starts. These are Large 0.2.29 static findings, cross-checked with GNU
disassembly. They do not change the evidence that the blocked TCP probe caused
the observed Standard transfer failure; no NTP-outage test was performed.

There is also a separate fallback-AP trigger in the button-wait routine
`0x4201163c`: if station Wi-Fi is connected but the time-synchronized flag is
false, it calls `0x4201d8f0`. That helper switches to AP+station mode and starts
the no-internet DNS task if needed. Reaching this branch can therefore advertise
the fallback AP without first observing a failed public TCP probe. Its timing
relative to background initialization has not been validated on the frame.

For stock-firmware emulation, a candidate WAN-free setup would provide accurate
local NTP responses for the four names, satisfy the frame-scoped TCP reachability
test, and separately supply the accepted HTTPS API/assets. DNS redirection to a
local time server is an untested compatibility approach, not a discovered
firmware setting. The TCP probe only accepts refusal in its post-selection
`SO_ERROR` branch; do not assume any immediate firewall rejection works.
No DNS, routing or frame settings were changed during this static pass.

A later firmware change should configure time sources explicitly and distinguish
time-service failure from AP failure. Cold boots, retained RTC time, recovery,
clock corrections, TLS validation and scheduled wakes still require a controlled
offline test.

### Time synchronization error-path follow-up

`0x42014e90` sets the in-progress flag before creating its completion semaphore.
If allocation fails, the branch at `0x42014fc6` returns `0x101` without clearing
the flag. A later caller can consequently take the already-in-progress path,
which waits up to 3,000 ticks (30 seconds), although that failed attempt never
started SNTP. This is a static resource-failure candidate, not a reproduced
device failure or an explanation of the earlier TLS allocation errors.

The shared completion semaphore also needs a concurrency audit: an overlapping
caller waits 30 seconds, while the initiator's five wait budgets sum to 34 seconds.
Whether such calls actually overlap, consume each other's completion signal or
recover through a later callback remains untested. Do not infer a runtime race
from these timeout values alone.

### Setup and identity

The account/setup screens have server fetches even when local filesystem support
exists. Web/authentication selectors are separate from the central API selector.
For the first emulator, preserve the already-paired identity and supply required
system assets. A factory reset is not a harmless way to test local-cloud support.
