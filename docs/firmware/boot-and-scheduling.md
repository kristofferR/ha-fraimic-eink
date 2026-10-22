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

### Pre-sleep ordering and outstanding work

The ordinary pre-sleep routine first checks for a pending OTA and its safety
predicate. An accepted update is attempted **before** service shutdown. A local
backend should continue withholding firmware offers unless an update is intended;
starting sleep does not guarantee that no further download/update work will run.

After an LED delay, the recovered order is:

1. Request connectivity-monitor stop; disable battery monitoring, power down the
   accelerometer and request fuel-gauge sleep.
2. Check the saved-image file and attempt to persist the `deep_sleep` marker.
3. Deinitialize portal/network services, including stopping the local HTTP server,
   then disconnect/stop/deinitialize Wi-Fi.
4. Call display shutdown with no white clear, log its result and continue.
5. Wait 200 ms, clear previous wake sources, request button EXT1 wake, then call
   the unified maintenance/album scheduler to add the next timer.
6. Flush logs, attempt to store the sleep timestamp and enter deep sleep.

This is an ordering trace, not a bounded shutdown transaction. Monitor stop does
not join its current probe/failover, as described below. Battery-monitor stop
`0x42029ccc` only clears its enable flag under a ten-tick mutex attempt; it does
not wait for an in-progress iteration. Sensor/marker failures do not gate the
remaining pre-sleep work. Local HTTP-server stop can itself wait without an
overall deadline; see [server lifecycle](local-api.md#server-capacity-and-lifecycle).
Consequently a shutdown log is not proof that deep sleep has already begun.

There is no explicit upload-worker abort/join, instruction-worker join or common
render-completion wait in this routine. Ordinary synchronous callers normally
finish before reaching it, but a worker surviving its caller's timeout needs
separate accounting. This trace does not establish that an overlapping worker
occurred on the device. A firmware extension needs to stop new producers, join
or cancel existing jobs, release their resources and shut down the panel before
sleep; changing only a visible busy flag is insufficient.

### Display shutdown suppresses its own failure evidence

Shutdown helper `0x42027c10` returns immediately when manager state already says
off. Otherwise, when initialized, it attempts to set busy state without checking
that setter's result. Its optional white clear is disabled by the ordinary
pre-sleep caller. If the controller-initialized flag is set, it selects all
controllers, sends command `0x02`, calls BUSY waiter `0x42027ad4`, then deselects
them. **The waiter's result is discarded.** This is not a wait for the renderer's
completion semaphore or its separate render-busy flag.

The BUSY waiter checks GPIO 6 for high, with one-tick delays and a default
30,000 ms budget from the manager configuration. That deadline belongs only to
this polling loop, not to the whole shutdown sequence. The following power-off
wrapper `0x42027a64(0)` runs the existing 5 + 5 + 3 second discharge sequence,
drives GPIO 40 low, clears its software power flag and returns zero. It does not
propagate expander/GPIO results. The manager's subsequent off-state update can
also fail without replacing the successful return. An uninitialized manager
takes a fallback that likewise returns zero after its shutdown attempt.

Thus an ordinary return from these recovered branches reports success even when
the BUSY waiter timed out. The pre-sleep caller contains a separate timeout log
claiming to force power off, but the checked helper does not propagate that BUSY
timeout into it, and the caller's log branch performs no additional force-off
operation. No hardware fault was induced. A future result/event must distinguish
attempted power-down from a verified safe state and retain full driver failures.
The [SPI ownership trace](rendering-and-concurrency.md#descriptors-and-manual-controller-selection-also-need-ownership)
also applies to the command/select operations in this helper.

### Final wake-source configuration is explicit

The normal path clears all previously enabled wake sources and calls the EXT1
setter with a 64-bit mask of `4` and mode `0`: GPIO 2, any-low on ESP32-S3.
The numeric meanings match the
[SDK sleep definitions](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_hw_support/include/esp_sleep.h).
It then calls the unified scheduler. A timer configured earlier in the wake
session is therefore not enough; the final scheduling step must restore it.
The caller ignores the button-wake setter's result, so the log saying both wake
sources are armed is not an independent readback of actual hardware state.

The storage-sleep path performs the same clear-and-button setup but does not call
the unified scheduler. It also lacks the ordinary path's explicit log-flush call
at the end. Both attempt to store the shared sleep timestamp. These differences
are static; physical wake behavior, interrupted cleanup and actual sleep duration
still need controlled checks under S06/D06.

## Album deadline persistence

`0x4202475c` accepts a numeric future `next_image_utc`, with
`next_scheduled_image_time` as a compatibility fallback. It passes the resulting
64-bit value to `0x42015d30`, which stores `app_data/sched_img_time` in NVS.
`0x42015d60` reloads it when the RAM cache is zero.

The HTTP 200 JSON parser writes zero when neither selected field provides a
future deadline. It selects the legacy field only when the primary is nonnumeric,
not when a numeric primary is past. Therefore an idle JSON response must still
carry the intended future deadline while an album schedule is active.
Some connection/HTTP errors return internal success but skip this setter; they
are not equivalent to a parsed empty object. See the
[error and field-selection contract](cloud-protocol.md#http-errors-are-not-equivalent-to-an-idle-json-response).

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

### Timezone format and default rules

The Large binary's parser at `0x420d0f54`, reached through `tzset` at
`0x420d0f3c`, consumes POSIX timezone syntax. Its recovered branches parse an
abbreviation and numeric offset, then optional daylight-saving rules. It does
not look up an IANA name in a timezone database. For `Europe/Oslo`, abbreviation
parsing stops at `/`, the required numeric offset fails, and the already-reset
state remains unnamed UTC. A leading `:` does not enable an IANA lookup.

If a DST abbreviation is supplied without transition dates, the actual binary
defaults to `M3.2.0` and `M11.1.0`, both at 02:00 local time: second Sunday in
March and first Sunday in November. The default DST offset is the standard
offset minus 3,600 seconds. These constants were checked in GNU disassembly at
`0x420d11d8` and `0x420d12ab`–`0x420d12de`, not inferred from the name alone.

The application configuration has 32 bytes including the terminator. An
enrollment UI or future firmware setting must translate an owner's timezone into
a supported rule that fits and validate it before saving. This does not add a
timezone setter to the stock poll-response contract. Preserve UTC epochs for
album delivery. Examples
below are parser checks, not settings applied to a frame:

| Input | Recovered/host-checked interpretation |
| --- | --- |
| `EST5EDT` | UTC−05 standard / UTC−04 daylight, with the default US transitions |
| `CET-1CEST` | UTC+01 / UTC+02, **still with US transitions** |
| `CET-1CEST,M3.5.0,M10.5.0/3` | Explicit last-Sunday March/October rules; 26 bytes plus terminator |
| `Europe/Oslo` or `:Europe/Oslo` | Parse error leaves unnamed UTC |
| `UTC0` | Fixed UTC |
| `UTC` | Missing numeric offset; parse error leaves unnamed UTC |

This affects stock onboarding choices too. The create-account page handler
`0x42019224` sends an embedded select list at `0x3c106f1c`. Its London/Dublin,
Paris/Berlin, Cairo/Helsinki, Sydney/Brisbane and Auckland/Fiji choices contain
DST abbreviations without explicit transition dates. The parser therefore uses
the same US default dates for all of them. The UI labels do not supply a regional
timezone database or repair the rule. This is static evidence from the actual
page bytes; no account was recreated to test it. The create-account POST stores
the submitted string, while sign-in separately clears it as described in
[identity persistence](storage-and-configuration.md#identity-layout-and-migration).

Nine host cases passed using the upstream parser with small environment,
allocation and scan wrappers. The wrappers stub transition-epoch calculation;
these tests check parsed rules/offsets, not actual clocks. Empty and unset `TZ`
were included as library controls. The application substitutes `EST5EDT` before
calling this parser when its configuration is empty, so those controls do not
describe the normal application's empty-setting behavior.
The [upstream parser source](https://raw.githubusercontent.com/espressif/newlib-esp32/esp-4.3.0/newlib/libc/time/tzset_r.c)
corroborates the recovered branches; the exact toolchain source revision remains
unproven. No timezone was written to either frame.

### DST flag survives the calendar calculation

`0x42014dcc` copies all 36 bytes of the current `struct tm`, then replaces only
seconds, minutes and hours before calling `mktime` at `0x420cfe14`. Consequently
`tm_isdst` still describes **now**, rather than asking the library to determine
the target date's DST state. When the initial target is less than 900 seconds
ahead, the routine adds the configured days to that already-normalized structure
and calls `mktime` again without resetting `tm_isdst`.

The instructions at `0x42014e42`–`0x42014e59` and `0x42014e7a`–`0x42014e85`
confirm both calls. The library's adjustment for a supplied, incorrect DST flag
was cross-checked past Ghidra's truncated `SALTU` flow in GNU disassembly.

Eight controlled host cases reproduced the caller using the upstream
[`mktime` implementation](https://raw.githubusercontent.com/espressif/newlib-esp32/esp-4.3.0/newlib/libc/time/mktime.c)
and explicit 2026 US/EU transition epochs:

| Case, requested maintenance time 03:00 | Recovered-call result | With DST redetermined before each conversion |
| --- | --- | --- |
| Ordinary date | 03:00 | 03:00 |
| Exactly 15 minutes before today's target | Today at 03:00 | Today at 03:00 |
| 14 minutes 59 seconds before today's target, interval four days | Four days later at 03:00 | Four days later at 03:00 |
| US/EU spring transition crossed by four-day interval | 04:00 | 03:00 |
| US/EU autumn transition crossed by four-day interval | 02:00 | 03:00 |
| US spring-transition day, calculated before the transition | 04:00 | 03:00 |

All eight expected outcomes passed. This is a **host reproduction supported by
binary inspection**, not execution of the firmware or a physical DST experiment.
It does not establish actual wake timing, persisted-schedule behavior after a
timezone change, or every ambiguous/nonexistent local-time case.

A firmware correction should set `tm_isdst = -1` before **each** `mktime` call,
check conversion failure, and define the policy for ambiguous/nonexistent local
times. Resetting it only before the first call is insufficient because that call
normalizes and writes the flag again. The current local API has no identified
dedicated maintenance-schedule setter; the remaining indirect-reference audit
and device checks keep S05 open.

The subsequent [Standard comparison](standard-model-comparison.md#calendar-and-led-follow-up)
confirmed matching relevant calendar, DST-correction and POSIX-parser branches,
plus byte-identical onboarding timezone options. Physical timing remains untested
on both frames.

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

### Reachability cache and monitor lifecycle

The cached result at `0x3fcaca8f` and station-event flag at `0x3fcaca8e` are
separate. Initialization clears both. Starting the monitor sets the station-event
flag, and the worker initially marks reachability healthy/true before probing.
The worker normally waits the healthy interval before its first probe, although
an IP-acquired event can release its wait semaphore early.

IP-acquired notification `0x4202f884` sets the station-event flag and signals the
monitor. Disconnect notification `0x4202f8ac` clears that flag **without clearing
cached reachability**. The loop also checks the portal's station-connected getter
`0x4201e050`; when either station check is false, it skips the TCP probe and leaves
the previous reachability value. Wait/passive states request reconnection, while
other states just continue waiting. The first-time-user flag returned by
`0x42015258` also skips probing; `0x42015264` derives that flag from saved Wi-Fi
credentials and setup completion. This is distinct from factory-test mode.
Consequently the cached getter alone is not a fresh test of Wi-Fi or backend
availability, even if its value is true. Callers that separately check station
state have an additional guard.

The monitor uses an 8,192-byte task stack, priority 2, with no fixed core.
Stop `0x4202f144` clears its run flag and releases the wait semaphore, then
returns; it does not join the task or interrupt an already-running probe/failover.
The worker clears its handle only when it reaches its exit. An immediate restart
while that handle remains nonzero returns `ESP_ERR_INVALID_STATE` (`0x103`).
These are static lifecycle findings, not a measured shutdown delay or an observed
restart failure.

### Fallback AP configuration and captive DNS

Fallback helper `0x4201d8f0` requests an AP+station configuration with an empty
password, open authentication, broadcast SSID, channel 1 and at most four
clients. The [SDK field layout](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_wifi/include/esp_wifi_types_generic.h)
identifies these fields. SSID helper `0x42019b24` caches `Fraimic_<number>`, using
the final two MAC bytes as a 16-bit decimal number; failure to read both Wi-Fi and
base MAC falls back to `fraimic_setup`. This is not a device-unique secret.

The helper returns immediately if Wi-Fi is already AP+station. Otherwise it calls
AP `set_config` **before** switching to AP+station, ignores both return values,
then logs that the AP is enabled. The SDK [configuration contract](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_wifi/include/esp_wifi.h)
requires the selected interface to be enabled. Thus the requested configuration
and success log alone do not establish which configuration actually became
active when entering from station-only mode. Normal setup `0x4201d528` uses the
opposite order and checks mode/configuration/start errors. No AP configuration
or transition was measured in this pass.

Both paths start DNS worker `0x420199b0`, with a 4,096-byte stack and priority 5.
It binds UDP **`0.0.0.0:53`**, without an AP-interface restriction. For ordinary
single-question DNS requests it appends an IPv4 answer for **`192.168.4.1`**, TTL
60 seconds. There is no hostname lookup, upstream forwarding, backend selection
or query-type dispatch. In particular, this is a captive-portal responder, not
a resolver that can provide the frame's custom cloud or time service.

The recovered packet loop accepts received lengths 13–496 bytes from its
512-byte receive buffer, copies the input, changes the response flags and low
answer-count byte, then appends 16 bytes. It does not validate the question name,
type/class or the other DNS counts before doing so. Non-A queries and unusual
packet structures therefore should not be treated as supported DNS behavior.
These bounds and transformations were inspected statically; no crafted DNS
traffic was sent to the device.

After binding, the DNS loop has no stop condition, Wi-Fi-mode check or successful
path that closes its socket. Recovery helper `0x4201d990` switches AP+station to
station-only when background Wi-Fi retry is inactive, but does not stop DNS.
The wildcard binding therefore permits a **possible remaining LAN listener**
after the AP disappears; actual reachability and lifetime across Wi-Fi teardown
are untested. Do not assume that the “AP disabled” log means DNS was stopped.

Initial setup discards the DNS task handle; fallback stores its own handle at
`0x3fca7448` and only creates a task when that slot is zero. The worker's
socket/bind-failure exits delete the task without clearing that slot. A competing
listener or failed bind can therefore leave fallback's creation guard latched.
Whether the existing setup worker already owns the socket is a separate question
from whether fallback successfully created another worker.

For a future local-backend firmware, give the portal/DNS service explicit start,
stop and error handling, bind it to the intended interface, and keep its lifetime
separate from backend health. Stock emulation still needs the API, asset, time
and public-probe dependencies described here; the captive DNS service does not
replace them.

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
