# Boot, sleep and scheduling

[Research index](README.md)

## Main lifecycle

On Large, `0x42012810` is the main loop; `0x42012338` contains pre-sleep work. The recovered
branches distinguish normal boot, physical-button wake, charging-cable wake,
display-maintenance timer wake and album-image timer wake. First-time setup has
its own instruction screens/AP mode and timeout behavior.

The loop coordinates background Wi-Fi initialization, a cloud poll, recording,
upload/download/render, pending OTA, requested sleep and idle sleep. Display work
and recording are not independent tasks with independent image/audio memory.

| Situation | Relevant behavior |
| --- | --- |
| Already-paired physical wake | Start background services, then enter idle input waiting before recording admission |
| Album timer wake | Initialize storage/network, check cloud work, calculate next wake |
| Maintenance timer wake | Restore/refresh saved display content through a separate branch |
| Charging wake | Battery monitoring and idle/LED behavior depend on setup and switches |
| First-time setup timeout | Enter storage sleep |
| Pending OTA before idle/sleep | May install first if safety conditions pass |
| Deep sleep | Wi-Fi/local HTTP unavailable until a supported wake source fires |

A plain LAN packet cannot wake a frame already in deep sleep. More frequent
scheduled wakeups trade battery life for responsiveness. HA's existing push queue
and a proposed frame-driven pull scheduler solve different parts of that problem.

Physical wake and new recording admission use different boundaries. The
[input audit](input-and-gestures.md#held-input-in-the-idle-handler) traces the
idle handler's held-button timeouts and the inner release wait that does not
recheck pending sleep. Its virtual timing results are not measured wake latency.

### Boot classification and first recording admission

The two pinned builds differ before the shared wake classifier runs:

| Path or state | Large 0.2.29 | Standard 0.2.28 |
| --- | --- | --- |
| Application entry | `0x420142ec` | `0x420142a8` |
| Boot cable flag | `0x3fca6b12` | `0x3fca6b82` |
| Entry handling | Clear the flag; no GPIO 1 sample in this path | Clear the flag, then sample GPIO 1 on EXT1 wake; low sets it to one |
| Wake classifier | `0x4201088c` | `0x420105c8` |
| Main loop | `0x42012810` | `0x42012770` |
| Outer recording wrapper | `0x42010994` | `0x420106d0` |

Standard configures GPIO 1 as input with pull-up enabled, pull-down disabled and
interrupts disabled before sampling. Its six 32-bit configuration words are
`[2, 0, 1, 1, 0, 0]`, using the
[SDK GPIO structure](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_driver_gpio/include/driver/gpio.h)
and [numeric definitions](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/hal/include/hal/gpio_types.h).
This is a current GPIO-level test after wake, not a captured pin-source bitmap.
It does not establish which physical edge woke the frame or that the level
remained unchanged since sleep ended.

The direct-reference audit finds three Large flag references, with only a zero
write at entry, and six Standard references including its GPIO-derived write.
Each app contains one exact initialized pointer to its flag. Thus the recovered
normal Large path leaves its cable-specific boot branch inactive. The census
does not exclude arbitrary computed aliases. This boot flag is distinct from
the battery monitor's current-based cable detection; it is not a diagnosis of
the deferred battery-drain issue.

The classifier's 82-instruction body matches across models after relocation:

1. Only wake cause 3, EXT1, opens `app_data/deep_sleep` and requests a one-byte
   blob into a destination initialized to zero. Other wake causes return false
   without touching that marker.
2. Only a resulting byte of exactly one continues. The getter's return value is
   ignored; the host read-failure case leaves the initialized byte unchanged.
3. Attempt a read/write open, erase and commit before testing the boot cable
   flag. Erase/commit results do not change classification. Failure to open for
   writing also falls through to the flag test.
4. Return true only when the boot cable flag is zero. A cable-classified wake
   can therefore consume the marker even though this classifier returns false.

In controlled existing-user, ready-service main-loop cases, cold boot and EXT1
without a marker select `bg_init`; EXT1 with marker one and no cable flag selects
`bg_init_wake`. Standard's low GPIO 1 selects `bg_init_charging`. **All these cases
reach the idle input wait before the recording wrapper.** Waking and recording
are separate admission steps, including when the initial wake was a button.

The caller follow-up also resolves the pending-sleep question from the input
audit. When the modeled idle handler returns recording admission with a sleep
request still pending, both main loops reach the outer recording wrapper with
that flag still set. A first-time-state check occurs on this selected path, but
there is no intervening pending-sleep rejection. The wrapper still checks voice
enablement and microphone setup can fail; this is not proof of captured audio
or a physical sleep/recording race.

The [bounded cases and references](wake-admission-cases.json) contain 26 cases
per model, with synthetic NVS/GPIO/task results and no device operation. Entry
cases stop before system initialization; main cases do not establish setup,
timer, OTA, renderer or complete lifecycle equivalence. See the
[validation record](validation-2026-10-22.md#boot-wake-classification-and-admission-s06e01e02).

The subsequent [startup-readiness audit](startup-and-readiness.md) separates
early errors that exit application entry from tolerated cache/instruction
failures. It also follows failed background-task creation and shows that an
idle-entry checkpoint is not a service-readiness acknowledgment.

### Keep-awake changes ordinary idle admission, not the album wake path

The four-switch application function updates the RAM keep-awake byte before
calling its saver. Getter Large `0x420158a8` / Standard `0x420158c8` reads that
byte directly. Ordinary idle predicate `0x42010f4c` / `0x42010c90` returns false
when keep-awake is enabled, before checking charging, elapsed activity or
scheduled work. Thus a new snapshot can affect the **next ordinary idle check**
without reboot; it does not necessarily wait for the next wake to take effect.

The scope matters. The predicate checks factory-test mode first, so an expired
factory test can return true before the keep-awake gate. Explicit sleep and
other lifecycle branches also have their own admission. This switch is not a
universal prohibition on sleep.

Twenty instruction cases per build establish these selected outcomes:

| State or transition | Bounded result |
| --- | --- |
| Paired/verified ordinary operation, ten minutes idle, keep-awake off | Idle predicate requests sleep |
| Enable keep-awake, including when the settings saver returns an error | Next idle check declines sleep; RAM already contains the enabled value |
| Disable it again with the old activity timestamp | Next check requests sleep; applying the switch does not refresh that timestamp in the tested path |
| Charging or a poll task still running, keep-awake off | Idle check declines sleep in the selected state |
| Expired factory-test state, keep-awake on | Factory branch returns true before consulting keep-awake |
| Album phase with absent, overdue or future deadline, either switch value | Same ordinary pre-sleep or five-minute timer call; no keep-awake getter call |

The album cases begin after result processing. For no deadline or a deadline
31 seconds ahead, they reach the ordinary pre-sleep call. A positive deadline
15 seconds ahead takes the separate five-minute retry timer path. None first
calls the ordinary idle predicate. Consequently setting keep-awake in an album
poll is not a reliable command to convert that wake into normal interactive
operation. HA's existing restart-based awake-window approach addresses this
wake-context distinction; merely sending the setting is not equivalent.

With synchronized time and keep-awake off, the ordinary predicate has additional
holds. It declines sleep during the fifteen minutes leading up to 03:00 local
time, including 02:45 and 03:00, using its own hardcoded calendar calculation.
Outside that window, a positive album timestamp from **29 seconds overdue
through 120 seconds ahead** also holds it awake. The adjacent -30/+121-second
cases allow the normal expired-idle decision. This is separate from the
greater-than-30-second timer-selection rule. The cases supply calendar/epoch
values directly; they do not measure wall-clock timing or exercise timezone
conversion. Do not interpret these holds as a battery baseline or a guarantee
that all other sleep paths are blocked.

[Cases](keepawake-cases.json) and
[validation](validation-2026-10-22.md#keep-awake-setting-and-wake-context-s06c02e01e02)
record the real instruction boundaries and stubbed state/time inputs. The album
checks stop at the first pre-sleep/timer call, without executing shutdown. No
device setting, restart or sleep experiment occurred.

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

Both normal and storage-sleep paths clear previously enabled wake sources before
the final EXT1 setter. The requested masks differ:

| Model | Mask and pins | Ordinary-sleep call | Storage-sleep call |
| --- | --- | --- | --- |
| Large | `4`: GPIO 2 | `0x4201267e` | `0x4201081f` |
| Standard | `6`: GPIOs 1 and 2 | `0x420125de` | `0x42010f63` |

Both pass zero as the high 32 bits and mode `0`, any-low on ESP32-S3. Entry-time
calls at Large `0x420145ca` and Standard `0x420145ea` use the same respective
masks. Six bounded instruction ranges verify these calls against the original
image bytes; see [numeric coverage](wake-admission-cases.json). The numeric meanings match the
[SDK sleep definitions](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_hw_support/include/esp_sleep.h).
The normal path then calls the unified scheduler. A timer configured earlier in the wake
session is therefore not enough; the final scheduling step must restore it.
The caller ignores the EXT1 setter's result, so the log saying both wake
sources are armed is not an independent readback of actual hardware state.

The storage-sleep path performs its model-specific EXT1 setup but does not call
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

### Timer selection, arming and wake reason are separate operations

The 30-second rule belongs to candidate selection, not every timer request.
If neither candidate qualifies, unified scheduler `0x42016274` sends the loaded
maintenance record to timer helper `0x42014bac` anyway. A maintenance target
20 seconds ahead therefore requests about 20 seconds; an elapsed/equal target
requests 60 seconds. This fallback does not update `wake_reason` and discards
the timer helper's result. A previous album reason can remain in NVS.

For a selected candidate, the scheduler calls the timer helper, checks its result,
then attempts to save `app_data/wake_reason` **even if timer setup failed**.
Set/commit errors are ignored. Conversely, successful timer setup followed by a
failed reason write can leave the previous reason. At the next timer wake,
`0x42015dac` returns the saved U8, defaulting to zero on read failure; the main
loop treats exactly 1 as album wake and other values as maintenance. A persisted
reason or “Timer set” log is not an atomic acknowledgement of the whole plan.

The timer helper reads wall time again. If a target chosen more than 30 seconds
ahead has become elapsed before this second read, the helper requests its
60-second fallback while the outer scheduler still saves the chosen reason.
Clock steps and delays between selection and arming therefore need separate
handling from the initial margin.

For a future target, the helper computes
`(target - now) * (1.0 - correction) * 1,000,000` in double precision before
integer conversion and timer setup. The maintenance record supplies the double
at byte offset 8; an album candidate explicitly supplies zero. The record also
contains its I64 target at offset 0 and interval/hour/minute fields at 16/20/24,
within a 32-byte blob. The setter preserves a nonzero correction and does not
validate its range here. This does not establish that the device learns drift
or currently stores a nonzero value. Synthetic ±0.125 fixture values only verify
the arithmetic, not a recommended calibration or measured clock behavior.

Unified scheduling first requires a nonzero maintenance target. If absent, it
creates the default schedule before examining album candidates. Failure to create
or arm that default returns immediately, even when the album deadline itself
would be usable. The default setter saves its record before arming the timer;
an arming failure does not roll back that saved schedule. It also returns zero
without doing work when its global “scheduling in progress” byte is already set.
That return is not a wait for the other call to finish.

An existing nonzero maintenance target is reused by this scheduler; it does not
recalculate it merely because the local timezone or current time has changed.
Other explicit rescheduling calls remain distinct. These are static findings
with host boundary/fault models, not physical wake or induced storage failures.

### Maintenance timing

`0x42016274` creates a schedule with `(interval_days=4, hour=3, minute=0)` when
none is stored. `0x42015f2c` accepts intervals 1–30 days, hours 0–23 and minutes
0–59. The caller audit below finds only fixed default arguments; these accepted
parameter ranges are not a public setter API.

`0x42014dcc` calculates in local calendar time. The initial target can be today's
03:00 if at least 15 minutes away; otherwise it adds the configured day interval.
It uses the stored POSIX timezone, with `EST5EDT` fallback. This is not always a
96-hour interval, and the fallback may not match the owner's location.

The awake USB-powered read on 21 October actually reported `EST5EDT` in `/info`;
the synchronized log time was UTC−04:00. This confirms that timezone on this
unit at the time of the read, not merely a static fallback. No timezone was
changed. Album UTC epochs and maintenance local-calendar times must stay distinct.

### Maintenance parameters have only fixed default callers

A raw instruction scan of the pinned Large application finds **eight direct calls**
to setter `0x42015f2c`. Every call loads `(4, 3, 0)` immediately before invoking
it; none passes request, poll, UI or stored-parameter values:

| Caller context | Call sites |
| --- | --- |
| Scheduled maintenance workflow, entry `0x420126f8` | `0x42012790` |
| Time-invalid/default fallback helper `0x42016144` | `0x42016218` |
| Unified maintenance/album scheduler `0x42016274` | `0x420162b4` |
| Wi-Fi recovery task `0x420166c8` | `0x4201671a` |
| System initialization/wake branches `0x420167b4` | `0x42016da9`, `0x42016e2e`, `0x42016f5e`, `0x42016fa5` |

The 32-byte `app_data/refresh_sched` writer `0x42014d48` has one direct caller,
inside that setter at `0x420160b4`. The image contains one terminated occurrence
of the key string at `0x3c0fcec8`; its recovered references belong to the record
loader `0x42014ad4` and writer. No exact pointer words to either the setter or
writer occur in the application image. GNU checks verify all nine calls and the
literal argument loads, with bytes checked against the original app.

This supports a **bounded negative result**: no configurable maintenance interval
or hour/minute entry point is established in the stock local/cloud interface.
The full-image direct-call/pointer search complements the 42 registered routes
and known poll-field parser; it cannot exclude an arbitrary computed indirect
call or dynamically assembled NVS key. In particular, a function that accepts
1–30 days is not evidence that an emulator can request those values.

The record's correction double is preserved by the setter rather than learned
from elapsed sleep here; no additional direct record writer supplies a recovered
drift estimator. This is not a measurement of the installed correction or RTC
accuracy. A pre-existing nonzero target can be reused, but whenever these callers
recalculate maintenance they again supply the fixed four-day/03:00 parameters.

For stock emulation, use `next_image_utc` for album deadlines and retain maintenance
as a separate firmware-owned schedule. Custom maintenance timing, an explicit
disable switch and timezone-change recalculation need a verified firmware setting
and persistence design. No schedule, timezone or NVS contents were changed in
this audit. The [Standard caller audit](standard-model-comparison.md#fixed-maintenance-callers-also-match)
now confirms eight corresponding fixed-argument calls there too; physical timing
and persistence remain unverified.

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
normalizes and writes the flag again. The
[setter caller audit](#maintenance-parameters-have-only-fixed-default-callers)
now narrows the missing public-setting question; persistence, timezone-change
recalculation and physical timing keep S05 open.

The subsequent [Standard comparison](standard-model-comparison.md#calendar-and-led-follow-up)
confirmed matching relevant calendar, DST-correction and POSIX-parser branches,
plus byte-identical onboarding timezone options. Physical timing remains untested
on both frames.

### Album wake has two result windows, not a delivery retry

After successful task creation, the album path waits up to 6,000 ticks for the
background completion token. A timeout skips directly to deadline selection.
On completion it allows **two result windows**, each with at most 30 readiness
queries and a 100-tick delay after every false query. The first window waits for
the background poll already started elsewhere; it does not dispatch a new poll.

Before the second window, it queries station connectivity up to 15 times, with
100 ticks after each false answer. If none succeeds it leaves the result phase.
Otherwise it clears the shared result, calls the poll dispatcher once, then
waits again **without checking whether a request was started**. The dispatcher
can skip for OTA, disconnected Wi-Fi or an unregistered identity. Large also
has the previously documented verification-running and Get Started exclusions;
Standard lacks those two exclusions. A rejected task start likewise does not
prevent the caller's second result window.

| Scripted outcome | Result queries | Requested delay ticks, excluding the initial completion wait |
| --- | --- | --- |
| Idle result in the first window | 1 | 0 |
| Pending result with empty URL | 1 | 0; no image helper call |
| Pending result, image helper returns an error | 1 | 0; no second album attempt |
| First result reports an error, retry returns idle | 1 + 1 | 0 |
| Both result windows time out, Wi-Fi already connected | 30 + 30 | 6,000 |
| First timeout, Wi-Fi never reconnects | 30 | 4,500 |
| Wi-Fi reconnects on query 15, both result windows time out | 30 + 30 | 7,400 |
| First result becomes ready on query 30 | 30 | 2,900 |

Both pinned builds use 10 ms ticks. These sums describe requested delays, not
elapsed boot/wake time: the initial completion wait, HTTP, image processing,
callbacks and scheduling add separate work. A result arriving during the final
delay is not queried again within that window. The fixture scripts readiness
and does not execute such a race.

A successful idle result exits the result phase immediately. A pending nonempty
URL calls the image helper, clears the shared result and exits regardless of the
helper's return. Consequently this is a retry of result acquisition, **not an
image-delivery guarantee**. Later sleep behavior still depends on the stored
deadline, including the separate five-minute path below. An emulator should
prepare complete assets before offering them, retain its intended next deadline
and keep consumption distinct from confirmed rendering.

The [twenty cases per build](album-poll-cases.json) execute the byte-checked main
region, result-copy/clear helpers and dispatcher, stopping before deadline
selection. [Validation](validation-2026-10-22.md#album-wake-result-and-retry-boundaries-s06c02e01e02)
records entries, coverage and stub limits. No physical wait or image fault was
induced.

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

The album-retry branch is separate from ordinary unified selection. With a
positive album deadline at or before `now + 30`, it requests 300,000,000 µs,
attempts to save album reason 1, performs shutdown and requests the same timer
again immediately before sleep. It does not compare a nearer maintenance target
in that branch. Both timer results and reason set/commit results are ignored.
Clearing the album deadline on a successful idle poll removes this branch;
retaining an overdue positive deadline after a failed poll can preserve it.

### The advertised 24-hour fallback has a conditional retry path

When time is invalid, wrapper `0x42016248` skips fallback if there are no Wi-Fi
credentials. Otherwise it calls `0x42016144(1)`. While the time-valid flag remains
false, that helper requests exactly 86,400,000,000 µs and logs success without
checking the timer result. It does not save a new wake reason.

If the helper instead sees valid time, it calls the ordinary default schedule
setter. On failure it logs “using 24h fallback” but recursively calls itself with
argument 1. **Valid time still selects ordinary scheduling again.** Persistent
schedule-save or timer errors, while the flag remains valid, can therefore repeat
the call rather than reach the 24-hour timer branch. GNU at `0x42016242` confirms
a real self-call, with a 32-byte function frame, not a tail-loop or a bounded retry.
This is a conditional static failure path; no device stack exhaustion was induced.

The host model covers transient failures that eventually succeed and persistent
failure stopped by an explicit harness depth limit. That limit is not present in
the firmware. A future firmware change should make fallback finite, check timer
results and preserve a coherent reason/deadline transaction. A local backend
should retain its intended future album epoch on idle responses and allow enough
time for actual download/render latency, rather than depend on these fallback logs.

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

`0x4202ed80` attempts a nonblocking TCP connection to `8.8.8.8:53`, with a
three-second socket-readiness wait. A successful connection or `ECONNREFUSED`
(111) returned by the subsequent socket-error query counts as reachable.
An immediate refusal takes a different branch, described below. This is neither
a DNS lookup nor ICMP ping, and three seconds is not a whole-operation deadline.

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
retry after exhaustion. Success handler `0x4202f294` clears three failure counters,
marks healthy, disables fallback AP and records channel/BSSID information.
It preserves the separate failover-cycle counter, as detailed below.
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

### Reachability result branches and timeout scope

The full probe and selected supporting routines were checked against GNU-decoded
bytes from the pinned Large app. It creates an IPv4 stream socket, requests
`F_GETFL` / `F_SETFL(flags | 0x4000)`, converts the numeric address and calls
`connect`. It sends no DNS request, HTTP request, TLS handshake or application
payload. Its decision table is:

| Socket outcome | Reachability result |
| --- | --- |
| Socket creation fails | False |
| `connect` returns zero immediately | True |
| `connect` fails with anything except `EINPROGRESS` (119), including immediate 111 | False |
| In-progress connection, readiness wait returns zero or negative | False |
| Positive readiness result, queried `SO_ERROR` is zero or 111 | True |
| Positive readiness result, queried `SO_ERROR` has another value | False |

After a positive readiness result, the app initializes the error output to zero,
calls `getsockopt(SOL_SOCKET, SO_ERROR)`, ignores that call's return value, closes
the socket and decides from the output integer. If the query fails without
writing the output, the retained zero is classified as reachable. This is a
conditional static path, not an observed false-positive probe. The same applies
to both ignored `fcntl` results: the app requests nonblocking mode but does not
verify that it was installed.

The compiled error-query wrapper `0x42055aec` posts a callback through
`0x42055f24` and waits using `0x420675bc` with timeout zero, meaning indefinite
completion wait in this port. Callback allocation/enqueue failure returns
without writing the app's error output. This matches the pinned
[lwIP socket implementation](https://github.com/espressif/esp-lwip/blob/fa4dffdfac52587a26c1f29258376df750cf8474/src/api/sockets.c)
and the already traced [queue semantics](#sntp-control-queue-ordering-and-allocation-failures).
Therefore the three-second `select` timeout cannot bound the entire probe;
post-selection callback/queue waiting is outside it. No socket, queue or
allocation fault was injected in this pass.

For backend emulation, TCP reachability is a separate stock dependency, not a
health check for the replacement API. Do not infer that DNS queries, TLS or
generation work merely because the cached flag is true. A future firmware
probe should validate its own API calls, use an overall deadline and track
local-backend health separately from WAN reachability.

### Recovery thresholds and retained cycle count

The failure handler uses counters, rather than measuring time since the outage.
The state numbers below correspond to the wait table above. These transitions
require a probe to run; disconnected and first-time-user iterations can skip
the handler entirely.

| State before failed probe | Counter/action and next state |
| --- | --- |
| Healthy (1) | Set failure count to 1; enter suspect (2), clear internet flag and enable fallback AP |
| Suspect (2) | Increment failures; on the third, reset that count, increment failover cycles and invoke AP failover |
| After that failover call | Return zero enters verify (3); any other result enters wait/retry (4), clears its retry count and requests reconnection |
| Verify (3) | A failed check enters wait/retry when cycles are below 2; otherwise enters passive (5) |
| Wait/retry (4) | Every second failed check resets the retry count, resets the portal's failover-attempt budget, increments manager cycles and tries failover; success enters verify, failure with cycles at least 2 enters passive |
| Passive (5) | Every third failed check clears passive/failure/cycle counts and the blacklist, then enters suspect with failure count zero |

The manager's cycle count at `0x3fcaca80` is separate from its failure,
wait/retry and passive counters. Reset helper `0x4202ed68`, called after a
successful probe, clears only those three other counters. Initialization clears
cycles; the passive-to-suspect branch also clears them. The monitor's ordinary
start/stop paths do not reset them. These are RAM values, not evidence of
persistence across reboot.

Consequently, a recovered connection need not begin the next outage with a
fresh two-cycle budget. For example, failover cycle 1 can succeed, return to
healthy, and remain recorded; a later outage can increment it to 2 and enter
passive if the replacement AP then fails verification. This is a branch-level
consequence, not a reproduced sequence on the owner's network.

Some log durations are arithmetic labels: the third suspect failure prints
`60 + 3 × 15 = 105` seconds, while ordinary waits before three successive
failures sum to `60 + 15 + 15 = 90` seconds. Wait/retry logs use 60 seconds per
failure even when keep-awake/charging selects 30-second waits. Probe time,
failover work, event wakeups and skipped checks also change elapsed time.
Use timestamps and state/counter transitions, not those labels, to analyze a
capture. The [Standard comparison](standard-model-comparison.md#reachability-probe-and-recovery-counters-also-match)
confirms the selected probe and recovery branches in both builds.

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

### Outbound local names and blocking resolution

Both pinned builds can issue one-shot multicast DNS queries for a backend or
artifact hostname ending in lowercase `.local`. This is the **outbound resolver**,
separate from the frame's [own mDNS advertisement](local-api.md#local-discovery-and-hostname-lifetime).
It does not establish DNS-SD service browsing, an editable API origin, TLS trust
for a new hostname or multicast reachability across the owner's VLANs.

Large resolver entry `0x42057844` first handles numeric addresses and cache hits.
For a fresh name it subtracts one final dot from the effective length, then
compares the **first case-sensitive `strstr(name, ".local")` result** with the
position six bytes before that effective end. The ROM call is identified by
Espressif's ESP32-S3 symbol map; the instructions and `.local` literal are checked
against the pinned application.

| Fresh lookup, with a unicast DNS server configured | Selected route |
| --- | --- |
| `homeassistant.local` or `homeassistant.local.` | Multicast |
| `HOMEASSISTANT.local` | Multicast |
| `homeassistant.LOCAL` or `homeassistant.Local` | Ordinary DNS |
| `foo.local.bar.local` or `foo.localhost.bar.local` | Ordinary DNS: the first substring is not the final suffix |
| `homeassistant.local..` | Ordinary DNS: only one final dot is removed |

An eligible multicast name bypasses the configured-DNS-server presence check.
Sender `0x420567e0` uses UDP port 5353 and the checked constants `224.0.0.251`
for IPv4 or `ff02::fb` for IPv6. Other names use the selected DNS server on port
53. The multicast flag occupies offset `0x127` of each 296-byte cache/query record.
On exhausted timeout retries, `0x42056a40` fails a multicast query instead of
advancing it to another unicast server. Its nominal retry counters are described
[below](#dns-fallback-and-cached-destinations); they are not a wall-clock guarantee.

Cache lookup `0x42056d2c` and pending-query matching in `0x42056f44` are
case-insensitive. Neither uses the multicast flag as part of its hostname match.
Consequently a cached lowercase name can satisfy an uppercase request before
suffix classification or server availability is checked. With a server configured,
concurrent requests of the same address type also share the first pending query:
lowercase after uppercase can inherit ordinary DNS, and uppercase after lowercase
can inherit multicast. Different requested address types do not merge. This
explains why a warm-cache test alone would not establish fresh-name compatibility.

The recovered transport chain is synchronous:
`0x420c314c` (`esp_tls_hostname_to_fd`) → `0x420c5040` (`getaddrinfo`) →
`0x42068368` (netconn resolver) → TCP/IP-thread dispatcher `0x42069b48` →
`0x42057844`. The netconn wrapper uses a thread semaphore and
`0x42055fb8`, which posts a stack-backed message and waits without a finite
semaphore timeout. The dispatcher signals immediately for a cached/error result;
an in-progress query relies on its completion callback. No HTTP timeout value
is passed down this chain. Therefore an HTTP transport timeout must not be
treated as an independently enforced DNS deadline; normal resolver retries,
TCP/IP scheduling and callback progress remain relevant. This is a static
boundary, not an observed deadlock or measured frame delay.

Twenty-three isolated host cases pass under AddressSanitizer and
UndefinedBehaviorSanitizer. They compile unchanged `dns_gethostbyname_addrtype`,
`dns_lookup` and `dns_enqueue` from the
[IDF v5.4.1-pinned lwIP source](https://github.com/espressif/esp-lwip/blob/fa4dffdfac52587a26c1f29258376df750cf8474/src/core/dns.c),
with reconstructed configuration/layout and stubbed sends, allocation and timers.
Cases cover the table above, no-server behavior, cache precedence, both pending
route-inheritance orders, distinct address types, four-query/four-callback limits,
255/256-byte names, final-dot trimming, null/empty names and PCB-allocation cleanup.
The 255-byte test establishes enqueue acceptance, not legal DNS-label lengths
or successful packet delivery. These tests exercise neither UDP packets, actual
elapsed waits, TLS nor either frame.

For an emulator, use one consistent lowercase hostname. A `.local` URL is a
candidate when multicast reaches the frame; a hostname served consistently by
its configured unicast resolvers is another option. Validate fresh resolution,
cache expiry, address changes and certificate identity independently. Neither
choice removes the separate public connectivity/time dependencies. All ten
selected functions [match in Standard](standard-model-comparison.md#outbound-local-resolution-also-matches).

### DNS replies for a local backend

The outbound multicast path expects a reply to its active lookup. It is not a
continuous mDNS cache populated by arbitrary announcements. Large receive handler
`0x42057274` requires an active query with the same transaction ID, the response
flag, exactly one echoed question, question class exactly IN and the requested
A/AAAA question type. Name comparison `0x42057144` is case-insensitive but rejects
a compressed question name. Unicast DNS checks the source IP against the selected
server; multicast queries skip that source-IP check. The parser does not inspect
its source-port argument. These are parser checks, not a claim about every lower
UDP/netif filter or network exposure.

Answer parsing skips each owner name through `0x42057208`, then accepts at most
one address of the selected family with class exactly IN and the expected 4/16-byte
payload. In particular, class `0x8001` with the mDNS cache-flush bit is not consumed
as IN. With an IPv4-only request and no other usable answer, that produces a
failure callback; a dual-family request can restart as AAAA. A zero-question or
unmatched-ID announcement is ignored earlier. For compatibility, a local responder
must support the queried reply format, not merely advertise an address.

Twenty-six host cases compile unchanged receive/name-skip/name-compare/completion
functions from the same pinned lwIP source used above. They pass with address and
undefined-behavior sanitizers. Relevant distinctions include:

| Response condition | Host result, with matching static branches |
| --- | --- |
| Matching ordinary DNS or multicast reply with an A answer | Success |
| No echoed question, two questions, wrong ID, wrong question type/name, compressed question or non-IN question class | Packet ignored; query remains pending |
| Multicast answer class has cache-flush bit | No usable address; IPv4-only request fails |
| AAAA question and matching 16-byte answer | IPv6 success |
| TTL greater than seven days | Capped at 604,800 seconds |
| TTL zero | Address delivered to callback, then removed from cache |
| Truncated flag set but complete usable A answer present | Accepted; this path does not require a TCP retry |
| Different answer owner, or a question containing only a leading label of the queried name | Accepted in the tested cases; neither is a complete binding check |

The last row is permissive parsing, not a format an emulator should depend on.
Use an exact echoed question and a correct owner/address relationship. Likewise,
the absence of a source-port check here does not remove TLS hostname/trust checks.

Partial answer processing is not transactional. If a packet declares two answers
but ends exactly after a complete first answer, the parser can report success.
If it instead includes an incomplete second answer, the parser can discard the
packet **after** storing the first address, while leaving the query pending and
without notifying its callback. The fixture then supplies a complete valid reply:
the one-address slot is already full, no new address is added, and the IPv4-only
request takes the failure callback. This is a source-fixture sequence corroborated
by the binary's count/store/exit branches, not an observed frame failure. Timer,
dual-family and concurrent-callback variants remain separate questions.

The fixture uses in-memory packets, bounded pbuf-access stubs and callback capture.
Backup-server availability is fixed false; timer/retry scheduling, packet chains,
real UDP delivery, TLS, callback re-entry and actual elapsed time are not tested.
All four selected functions [match in Standard](standard-model-comparison.md#dns-reply-acceptance-also-matches).
No DNS service, routing policy or physical device changed.

### DNS fallback and cached destinations

Large has a separate hardcoded use of `8.8.8.8`: **DNS server slot 2**. This is
not the TCP/53 internet probe. DNS initialization `0x420577bc`, called during
lwIP initialization, parses the string at `0x3c110628` and installs it through
`0x42057780`. The resolver has three 24-byte server slots at `0x3fcad994`.
The actual fallback address comes from the binary, not an assumed SDK default.

DHCP ACK application installs the first two advertised DNS addresses but skips
index 2. The inspected DHCP-client-start path also clears slots 0/1 while keeping
slot 2 (`0x4206a398(1)`). Offering a third local resolver through DHCP therefore
does not overwrite the public fallback in this path.

The resolver's behavior depends on how a lookup fails:

| Situation | Recovered Large behavior |
| --- | --- |
| New lookup with empty primary slots | Starts at the first populated slot, potentially the public fallback |
| No response | Retries, skips empty later slots, then advances to the next populated server |
| Matched response with nonzero DNS response code | Immediately advances only when the directly following slot is populated |
| Error response from slot 0 with slot 1 empty | The immediate backup check fails even if slot 2 is populated; this differs from timeout handling |
| Accepted answer already cached | Lookup can return the cached address before making a new request |

State machine `0x42056a40` sends immediately, then retries after nominal intervals
of 1, 1 and 2 timer ticks, and changes server after another 3 ticks when no
response arrives. The timer is scheduled in 1,000 ms increments. This describes
counter transitions, not a measured seven-second wall-clock deadline: task delay,
an already-running timer, sends and replies affect actual timing. Response handler
`0x42057274` and immediate-backup predicate `0x42056434` establish the distinct
error-response path. These branches align with the
[pinned lwIP resolver](https://github.com/espressif/esp-lwip/blob/fa4dffdfac52587a26c1f29258376df750cf8474/src/core/dns.c).

The DNS setter only copies the selected address; it does not invalidate the
four-entry hostname/address cache at `0x3fcada0c`. Cache lookup `0x42056d2c` precedes
new-query allocation. Accepted TTLs are capped at 604,800 seconds; TTL zero can
satisfy the current request but is removed after its callback. Completed entries
can also be evicted for new names. Changing the DNS server list alone therefore
does not establish that the next API or NTP lookup uses a new local answer. This
does not rule out cache clearing by another path, loss across reboot or changes
to an already-open connection.

For a stock local backend, provide consistent answers through the resolvers the
frame actually uses, and include DNS fallback and cache state in a controlled
cutover test. A custom firmware should make the fallback configurable alongside
the API and time-server origins. No DNS service, firewall, lease or frame state
was changed here. The [Standard comparison](standard-model-comparison.md#dns-fallback-cache-and-late-callbacks-also-match)
confirms these selected static paths and constants on that model too. Actual
fallback traffic and a complete WAN-free cutover remain untested.

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

### SNTP server selection and startup delay

Large's server-name setter `0x42056420` accepts only slot **0**, backed by the
32-byte record at `0x3fcad96c`. The four application names above are therefore
rotated through one slot, not installed as four simultaneous SDK fallbacks.
Request helper `0x42056168` prefers a non-null name over the stored IP address:
it clears that address and resolves the name, with DNS caching still applicable.
The name setter stores a borrowed pointer; the application's literal strings
have sufficient lifetime. This is not a recovered custom-server setting.

Initializer `0x42056314` schedules the first request after **0–4,999 ms**. The
actual instructions take the hardware-random result modulo 5,000, using multiply
constant `0xd1b71759`, a 44-bit quotient shift and divisor `0x1388`. This value
comes from the application binary, not an assumed SDK default. The delay precedes
the request helper, so it precedes even DNS resolution. The binary's structure
also matches the startup-delay and one-slot branches in the
[pinned lwIP implementation](https://github.com/espressif/esp-lwip/blob/fa4dffdfac52587a26c1f29258376df750cf8474/src/apps/sntp/sntp.c).

Stop helper `0x4205639c`, when a UDP client exists, removes the pending request
and retry timers before removing that client. Timer cancellation at `0x4205ead4` matches both callback
and argument. Each application retry stops and initializes the client again,
choosing a fresh startup delay. Consequently the first two application budgets
(2 and 4 seconds) can expire before any NTP request is sent; a healthy server
cannot answer a request that the next attempt cancels before dispatch. This is
a **conditional static timing problem**, not measured failure frequency. Task
scheduling, DNS/UDP latency and callback-queue behavior affect the actual timing.
The later 8/10/10-second budgets exceed the configured startup delay, but still
include lookup and response time.

The application does not stop SNTP when all five waits expire. A remaining SDK
request/retry may therefore run after the application has logged synchronization
failure and entered recovery. Conversely, the stop/init/mode wrappers discard
the enqueue result from `tcpip_callback` (`0x42055f24`), which can fail to allocate
its message. The later [control/lifecycle model](#time-control-and-overlapping-waiters-host-cases)
exercises selected late-success and allocation-failure orderings; none was induced
on a frame or should be inferred from an ordinary timeout log alone.

For future firmware, keep a selected time client alive long enough to cover its
startup delay, DNS and response budget, and make recovery account for outstanding
callbacks. For stock emulation, accurate local NTP service remains a candidate;
the DHCP follow-up below rules out option 42, while physical offline boot is
still untested.

### SNTP control queue ordering and allocation failures

Large's retry loop mixes asynchronous control messages with a synchronous
hostname operation. The relevant sequence is:

| Application operation | Wrapper | Completion semantics |
| --- | --- | --- |
| Stop | `0x4205311c` | Allocates and queues a callback; does not wait for its execution |
| Set polling mode | `0x420530fc` | Same queue path; the callback checks that the client is stopped |
| Set server name in slot 0 | `0x4205312c` | Posts a stack-backed API message and waits for its completion semaphore |
| Set time notification callback | `0x420530d0` | Updates the SDK callback pointer directly |
| Initialize | `0x4205310c` | Allocates and queues a callback; the application then starts its response wait |

The server-name call is therefore an ordering barrier for earlier messages that
were successfully posted by this caller. Dispatcher `0x42055dc0` executes its
setter, stores the result and signals completion before that call returns.
Stop, mode and name are not an atomic transaction: other producers and network
timers can run between them. In particular, this barrier does not invalidate the
pending DNS callbacks described below.

TCP/IP initialization `0x42056054` creates a **32-entry mailbox**, whose handle
is stored at `0x3fcad95c`. Entries are four-byte message pointers, not copied
messages. Posting `0x4206766c` passes send-to-back position zero and
`0xffffffff` wait ticks to the FreeRTOS queue. The checked timeout helper
`0x403847b4` treats that value as no ordinary timeout; explicit task-delay abort
is a separate branch. A full mailbox waits for space rather than returning an
ordinary queue-full result. An unsuccessful queue-send result reaches an
assertion. These identities agree with the
[pinned FreeRTOS port](https://github.com/espressif/esp-idf/blob/v5.4.1/components/lwip/port/freertos/sys_arch.c),
but the capacity, arguments and branches above come from the application bytes.

The synchronous name operation also waits without an ordinary timeout, through
`0x42056010` and `0x420675bc`. Both its queueing and completion occur **before**
the application's 2/4/8/10/10-second response waits. After init is posted, its
dispatch delay is inside the corresponding response wait. Those five waits are
therefore not an overall bound on synchronization time. This establishes no
measured stall or deadlock on the frame.

Callback enqueue `0x42055f24` asks allocator `0x42057b68` for pool index **8**.
This is not an eight-byte allocation: the descriptor at `0x3c3c46d0` requests
**16 bytes** through the heap-backed allocation path. The separate 16-element
limit in that allocator belongs to a different descriptor and does not cap this
callback pool. The dispatcher invokes the callback and frees the message.
Allocation failure returns an error byte; all three asynchronous SNTP wrappers
discard it. Consequences depend on which allocation fails:

| Conditional event | Recovered consequence |
| --- | --- |
| Stop allocation fails while an earlier client is still active; mode allocation succeeds | Mode callback `0x420563e4` reaches the assertion that the client must be stopped, even though the requested mode remains polling |
| Mode allocation fails | Previous mode is retained; the application still sets the hostname and requests init |
| Init allocation fails after a successful stop | No new client is created by that request, while the application still waits for a time notification |
| Both stop and mode allocations fail with an active client | Hostname setting can complete; a later init sees an existing client and does not recreate it or choose a fresh startup delay |

The hostname path avoids allocating a callback message, but needs a per-thread
completion semaphore. Getter `0x420678b4` creates it through `0x42067840` when
absent. Failure to allocate its four-byte storage or semaphore returns null.
The API-call path forwards that null without a guard to wait/signal helpers
that dereference the storage pointer. This is a separate conditional allocation
failure, not a cleanly reported synchronization timeout.

The original findings were static; the later
[host control cases](#time-control-and-overlapping-waiters-host-cases) reconstruct
selected allocation failures, bounded mailbox saturation and callback orderings.
They do not execute the RTOS or reproduce a device crash. The [Standard queue comparison](standard-model-comparison.md#sntp-control-queue-and-failure-paths-also-match)
now confirms these relevant static paths there too. The earlier TLS
memory-allocation error is not evidence that any of
these paths occurred. A future implementation should report control-request
failure, use an acknowledged stop/configure/start operation with an overall
deadline, and retain safe message ownership if that deadline expires. A local
cloud server cannot repair the stock client's internal queue handling.

### Time control and overlapping waiters: host cases

Twenty-five bounded Bun cases reconstruct the recovered control-message and
application-wait policies. Nine complete Large control-flow bodies, including
the full application synchronization routine and notification callback, were
recovered across 541 instructions and 25 ranges and verified against the pinned
image. This pass models the queues, allocation outcomes and selected event orders;
it does not execute firmware, SDK C, FreeRTOS scheduling or network/time services.

The application completion semaphore is binary. A valid notification sets the
synchronized flag and offers one token; it does not broadcast completion to all
callers. The overlapping-caller branch waits for that same token for 3,000 ticks,
then returns without applying timezone or setting completed-this-wake. Only the
initiator's successful wait does those final steps.

| Chosen host event/fault | Result and scope |
| --- | --- |
| Stop/mode/name succeed; init still queued | The name barrier has finished, but the client has not started; the init message remains owned until dispatch |
| Stop message allocation fails while a client exists | The later mode callback reaches its stopped-client assertion; the callback's normal message-free path is not reached |
| Mode or init message allocation fails | Prior mode remains, or the client remains stopped, respectively; the wrappers do not report the failure to the application |
| Stop and mode message allocations both fail | Init sees the existing client; it does not create a new client or draw a new startup delay |
| UDP-client allocation fails during init | Reaches an assertion boundary, rather than a clean application timeout |
| Mailbox has 32 entries | The next producer and its message remain blocked/alive; after dispatch frees space it can progress in FIFO order. A modeled aborted send reaches the port assertion |
| Per-thread semaphore storage or kernel object allocation fails | The hostname message can still be posted; the subsequent null-storage wait/signal boundary is unsafe. Kernel-allocation failure frees the temporary storage |
| Another producer queues init between stop and mode | The mode callback can see an active client and assert. Successful hostname completion also does not prevent another producer changing the name before init |
| Joining caller consumes the only valid notification | It returns success, but the initiator can exhaust its waits and clear the synchronized flag. Neither applies the initiator's successful-completion bookkeeping in this ordering |
| Initiator consumes the only notification | It completes normally; an already-waiting joiner can still time out despite the successful synchronization |
| Init dispatch or a valid notification arrives after the final application timeout | The client can start afterward, or the synchronized flag can become true without completed-this-wake/timezone bookkeeping |
| Two notifications precede consumption | They coalesce to one binary token; a new initiator drains a stale token before clearing the synchronized flag and retrying |

The twenty-five cases include normal completion, reused per-thread semaphore,
invalid-year/no-semaphore notification and callback-before-response-wait controls.
Assertion and null-dereference paths are explicit model fault markers; no invalid
memory access, panic or indefinite blocking is executed. A full-mailbox case
observes a bounded blocked state rather than claiming a measured deadlock.

The semaphore winner and absence of a further notification are chosen inputs.
Actual caller overlap, task priorities, callback frequency, scheduler decisions
and simultaneous flag loads remain unmeasured. In particular, these examples
do not establish a race occurred on either owned frame. The previous Standard
comparison covers selected queue/control paths; this new application-level
fixture is based on Large and is not a complete Standard lifecycle comparison.

For custom firmware, one synchronization owner should publish a persistent
completion result to every waiter, with explicit attempt identity and a bounded,
acknowledged control sequence. A local backend can make DNS/NTP responsive but
cannot change these stock message-ownership or completion rules.

### Pending DNS callbacks survive SNTP stop

Large's stop helper does **not cancel an outstanding DNS lookup callback**.
Resolver enqueue `0x42056f44` stores a callback, argument and query index in its
four 12-byte callback records at `0x3fcad9dc`. SNTP request `0x42056168` supplies
the shared callback `0x42056200` with a null argument, so the registration has no
SNTP attempt identifier. Resolver completion `0x4205652c` invokes that callback
and then clears its registration; it does not check whether SNTP was stopped or
the application's selected server changed.

The SNTP callback ignores the returned hostname and argument. A successful
lookup copies the address into the current server slot, then calls send helper
`0x420560ec` using the **current global UDP client**. A failed lookup calls retry
helper `0x42056098`. Neither path checks that the originating attempt is current.
This permits several conditional event orderings:

| Event order | Result established by static tracing and the host fixture |
| --- | --- |
| Lookup A pending; stop; initialize B; A succeeds | Sends to A's address through B's new client. The stored name remains B, so a later B request can replace the address again. |
| Lookup A pending; stop; initialize B; A fails | Retry cancels B's startup-request timer and replaces it with a 15-second request timer. |
| Lookup pending; stop without replacement; lookup succeeds | UDP send sees a null client and returns an argument error. SNTP ignores the return and still schedules its 15-second retry callback. |
| Lookup pending; stop without replacement; lookup fails | Retry schedules a request after 15 seconds despite the absent client. |
| Late callback rearms work; stop again while the client is null | Stop's client guard skips timer removal. A later request can enqueue DNS again while stopped. |

The null-client guard is explicit in UDP entry `0x4205f570`; this is **not an
established null dereference**. The send helper also schedules a 15-second
request if packet-buffer allocation fails. A late callback's effect depends on
the actual ordering of DNS completion, stop/init messages and timers. The host
fixture validates selected orderings, not their probability on the frame or a
cause of the observed battery/TLS problems.

Eight isolated cases use seven unmodified functions from the
[pinned SNTP source](https://github.com/espressif/esp-lwip/blob/fa4dffdfac52587a26c1f29258376df750cf8474/src/apps/sntp/sntp.c),
with deterministic DNS/timer/UDP/buffer stubs and the relevant compiled branches
checked against GNU disassembly. They include normal completion, cancellation
before any lookup, replacement and no-replacement callbacks, allocation failure
and a repeated stop. No packets, clocks or frame state were changed.

For future firmware, keep one time client alive across its lookup/response budget,
associate callbacks with an attempt, and make shutdown invalidate outstanding
callbacks as well as remove timers. A local backend should provide responsive DNS
and time service, but cannot enforce callback ownership inside stock firmware.
The [Standard comparison](standard-model-comparison.md#dns-fallback-cache-and-late-callbacks-also-match)
confirms these relevant static branches there too. Physical event timing remains open.

### NTP response contract and clock application

Large's request initializer `0x420560d4` emits a 48-byte packet: first byte
`0x23` (version 4, client mode), all remaining bytes zero, including the transmit
timestamp. Send uses UDP destination port 123. Receive callback `0x4205624c`
applies these checks in the application's poll mode:

| Field or condition | Compiled receive behavior |
| --- | --- |
| Total payload length | Must equal 48 bytes; even a valid base header with extra bytes is rejected here |
| Low three bits of the first byte | Must be server mode 4; broadcast mode 5 is rejected in poll mode |
| Stratum byte | Zero takes the Kiss-of-Death retry path; all nonzero byte values pass this check |
| Leap/version bits | Not validated by this callback |
| Source address/port arguments | Not compared by this callback |
| Originate/receive timestamps | Not read; no request-timestamp match or round-trip compensation |
| Transmit timestamp | Copies exactly eight bytes at offset 40 for clock conversion; no nonzero/freshness test |

The absent source/port check concerns a datagram **already delivered to this UDP
callback**. It is not evidence of off-LAN reachability or a full network-stack
acceptance test. A local service should send proper responses from its configured
NTP endpoint, rather than depend on missing validation. Header checks and clock
conversion match the relevant branches in the
[pinned lwIP SNTP implementation](https://github.com/espressif/esp-lwip/blob/fa4dffdfac52587a26c1f29258376df750cf8474/src/apps/sntp/sntp.c).

Conversion `0x42056224` decodes both network-order words, adds `2,085,978,496`
to the seconds word with 32-bit wrap, and converts the fraction with
`floor(fraction * 1,000,000 / 2^32)`. Wrapper `0x420530e8` zero-extends the
resulting seconds into a 64-bit time value and invokes `0x42052fec`.
Thus an all-zero transmit timestamp becomes **2036-02-07 06:28:16 UTC**;
`0xffffffff` seconds becomes one second before that. Half and maximum fractions
become 500,000 and 999,999 microseconds. Zero-filled placeholder time is not a
harmless failure response.

The SDK's immediate-mode branch calls `settimeofday` (`0x4200af88`), marks its
own status complete, and then invokes the application callback. Its clock-setting
return is not used as an additional success check. The application callback
`0x42014728` independently reads the resulting clock and tests local year >= 2020
before setting its synchronized flag and signaling completion. It has no upper
year bound or drift check; the early-year warning branch also does not clear a
previously true flag. A successful SDK packet parse therefore does not establish
accurate time or a newly completed application attempt.

After a nonzero-stratum response passes the parser, the receive path resets retry
delay to 15 seconds and schedules the next SDK request using interval getter
`0x420530dc`. Its stored initial value is **3,600,000 ms**. This one-hour timer is
distinct from the application's startup retry budgets and does not prove that
the frame stays awake for an hour. Invalid length/mode leaves existing retry
work alone; stratum zero uses the current retry backoff. The application may
stop/reinitialize the client independently, as described above.

Eighteen isolated host cases validate these receive/conversion boundaries using
four unmodified pinned functions and buffer/timer/clock-recording stubs. They
perform no actual clock setting or network I/O. The local-backend requirement is
an **accurate time service returning plain 48-byte server responses**, alongside
working DNS and the separate connectivity gate. The subsequent
[Standard comparison](standard-model-comparison.md#ntp-receive-and-clock-application-also-match)
confirms the same selected receive/clock branches there. Physical local-NTP
compatibility remains untested.

### DHCP does not configure the stock time server

Large 0.2.29 **does not consume DHCPv4 option 42 as an NTP configuration**. This
conclusion follows the compiled request builders, response parser and extension
hooks, rather than the SDK's default build settings:

- The parameter-request list at `0x3c3c4f14` contains exactly four bytes:
  `01 03 1c 06` (subnet mask, router, broadcast address and DNS). Five message
  builders use a four-byte loop and advertise length four for option 55.
- Their append hook `0x42067360` can add client identifier option 61; it does not
  append an NTP request or extend that parameter list.
- Reply parser `0x4206044c` has no option-42 case. That value takes its unknown
  option path at `0x420605cb`. The extension hook `0x420672e4` immediately returns
  for every option except 26, so it also ignores 42. The parser then skips the
  supplied payload without storing it in its decoded-option table.
- ACK application `0x420607ec` consumes lease, subnet, router and DNS fields, with
  no time-server installation. The recovered SNTP address references likewise
  lead to its request/DNS paths, not this DHCP path.

The option identities and conditional SDK feature align with the
[pinned DHCP implementation](https://github.com/espressif/esp-lwip/blob/fa4dffdfac52587a26c1f29258376df750cf8474/src/core/ipv4/dhcp.c).
The binary checks establish that enabling NTP advertisement on the router alone
will not replace the application-selected names in this build. Unsolicited option
42 does not provide a workaround. This is a static IPv4 DHCP result; it is not
a DHCP packet experiment or a claim about DHCPv6. The separate
[Standard comparison](standard-model-comparison.md#stock-time-service-also-matches)
confirms the same option-42 handling, one-slot selection and startup timing there.

For stock emulation, resolving the four configured names to an accurate local
NTP service remains the candidate to validate. A later custom firmware can expose
an explicit time-server setting or deliberately implement DHCP-based selection.
Keep this separate from the public TCP reachability dependency.

### HTTP Date does not supply a fallback clock

The shared cloud-event callback has a `Date` header branch, but it **does not read
the header value**. Large `0x420234cc` compares the header name at event offset
`+0x14` with exact-case `Date`. On a match it calls `time()` at `0x420d0d48` into
a stack temporary, then `localtime_r()` at `0x420cfa1c` into another temporary,
and returns without using the result. It neither parses server time nor sets the
clock or application synchronization flags.

Standard callback `0x42021f7c` has the same branch, with corresponding time-helper
targets `0x420d102c` and `0x420cfd00`. This static comparison rules out this
callback as an HTTP-time fallback; it is not a physical cold-boot experiment or
an assertion about every SDK clock source. Adding an accurate `Date` header to a
local poll/setup/verification response does not remove the separate SNTP
dependency through this path. Keep time service in the offline-backend design.

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
started SNTP. The host model reproduces the latched flag and a later timed-out
joiner under injected allocation failure. It is not a reproduced device failure
or an explanation of the earlier TLS allocation errors.

An overlapping caller waits 30 seconds, while the initiator's five wait budgets
sum to 34 seconds, excluding control-operation waits. The
[bounded overlap cases](#time-control-and-overlapping-waiters-host-cases) now
exercise either caller consuming the single signal and later notifications.
Whether those orderings occur on a frame remains untested; the budgets alone
do not establish a runtime race.

### Setup and identity

The account/setup screens have server fetches even when local filesystem support
exists. Web/authentication selectors are separate from the central API selector.
For the first emulator, preserve the already-paired identity and supply required
system assets. A factory reset is not a harmless way to test local-cloud support.
