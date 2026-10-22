# Rendering, buffer ownership and completion

[Research index](README.md)

This follow-up traces Large 0.2.29's buffer aliases, render task and status
reporting. Unless labelled observed, findings are **static**, with consequential
instructions checked in GNU ESP32-S3 disassembly. Later bounded poll/voice tests
observed the normal completion path. No physical concurrent-upload, fault-injection
or modified-firmware experiment was performed. The bounded renderer model below
adds isolated host fault cases.

The [voice cancellation follow-up](voice.md#cancellation-and-scheduled-content-races)
maps a second shared resource: the HTTP-abort manager stores one active client,
without job-scoped ownership. It also distinguishes the pre-render cancel check
from a refresh already running. Its lifetime/fault cases now have a bounded host
model, with physical outcomes still untested.
The [timeout and two-job follow-up](voice.md#timeout-and-error-boundaries-still-needing-validation)
also traces unchecked task creation, a WAV cleanup helper that does not release
ownership, and a candidate cancellation flag left over for the next recording.

The [status-image path](storage-and-configuration.md#status-markers-and-restoration-are-not-display-acknowledgments)
also decodes/loads into the image allocation before DROP arbitration. Its status
marker follows render acceptance or cache-load failure, not physical completion.

## The display pointer is another alias

This allocation map is for **Large**. Standard has [separate audio/image backing
allocations](standard-model-comparison.md#separate-recording-and-image-allocations),
although its display pointer still aliases its image allocation.

The PSRAM manager allocates one 2,304,000-byte block. Recording and image accessors
return it. Initialization also assigns the result of `0x42028e88` to the display
pointer at `0x3fca75d4`; the call/store are at `0x42014622` / `0x42014628`.

| Storage / accessor | Meaning |
| --- | --- |
| `0x3fcabd28` | PSRAM manager's allocation pointer |
| `0x42028e68` | Recording accessor, same allocation |
| `0x42028e88` | Image accessor, same allocation |
| `0x3fca75d4` | `epdImageDataBuffer` alias initialized from the image accessor |

The render-start function `0x420208d4` allocates only a **12-byte task context**:
input pointer, length and a third parameter. It does not allocate/copy an image
snapshot. The worker `0x420204b8` does call `memcpy` into `epdImageDataBuffer`,
but for the ordinary shared-buffer input, source and destination identify the
same allocation. A second pointer name and a copy call are not evidence of a
second backing buffer.

The worker later sends eight 288,000-byte controller blocks from this alias.
Its size check tolerates ±1,024 bytes and does not fill a missing tail. The
[download fault trace](image-downloads.md#a-short-asset-can-reach-rendering-and-replace-the-cache)
connects short declared responses to stale tail bytes and cache replacement after
worker rejection; those consequences have not been exercised on the frame.
Protect the bytes until the display driver has finished consuming them. Releasing
ownership merely because the worker started or passed the copy call is unsafe.
Holding through the full render is the simpler initial design. The transfer
lifetime is now traced below; an earlier release would still need a verified
boundary across all controllers and other consumers.

The [local refresh busy guard](local-api.md#restart-sleep-and-refresh-acknowledgments)
does not supply that ownership. It reads recording state and the LED manager's
workflow-protection latch; both getters report false if their mutex acquisition
fails. The [LED trace](led-and-workflow-state.md) separates that visible-state
policy from actual memory/driver completion.

### SPI consumes the source one blocking chunk at a time

Transfer helper `0x42021e5c` sends command `0x10`, then data in 4,800-byte chunks
plus a remainder. Its transaction points into the original source and advances
that pointer; there is no full-image snapshot. Eight 288,000-byte controller
blocks therefore involve successive reads from the shared allocation.

The indirect target at `0x4037af80` is `spi_device_transmit`: it queues a transaction,
waits indefinitely for its result, and asserts that the returned descriptor is
the one submitted. The binary assertion/function strings and call structure match
the [ESP-IDF v5.4.1 SPI implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_driver_spi/src/gpspi/spi_master.c).
Successful return releases that transaction's source lifetime, not the unsent
remainder of the image. DMA or internal staging does not create a safe snapshot
of future chunks. Keep ownership through the final consumer.

The application chunk loop also overwrites its error result on later transfers,
so an earlier error can be hidden by a later success. Its caller logs the final
result without returning a failure to the worker. Fault injection and real
free-memory/fragmentation measurements are still needed before choosing between
exclusive ownership and a separate full snapshot (D03/D06).

### DMA staging protects only the current chunk

Bus initialization `0x42022140` requests DMA auto-selection, a maximum transfer
size of 4,800 bytes and two logical devices on the same host. Both devices request
10 MHz, mode 0, eight command bits, half-duplex operation and a queue depth of ten.
Their hardware chip-select pin is `-1`; the application drives controller selects
itself. These values were read from this binary, with field/flag names checked
against the SDK [device](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_driver_spi/include/driver/spi_master.h)
and [bus](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_driver_spi/include/driver/spi_common.h)
headers. They do not establish measured clock timing or permission to increase it.

The compiled SDK setup routine `0x4037ad4c` accepts a direct TX pointer only in
the internal DMA address range `0x3fc88000` through `0x3fcfffff`, when DMA is enabled.
An ordinary PSRAM source falls outside that range. For each such transaction it
allocates a DMA-capable temporary block and copies the requested bytes before
queueing. The bus initializer sets alignment to four bytes, so a full application
chunk needs a 4,800-byte payload allocation, plus allocator overhead. This is a
separate requirement on DMA-capable memory; a large free-PSRAM figure does not
establish that the allocation will succeed.

Queue submission `0x4037ae60` stores the original descriptor pointer together with
the temporary buffer in its private context. Result retrieval `0x4037aef8` calls
cleanup `0x4037a8e4` after receiving completion; cleanup frees the temporary TX
block. The normal wrapper submits and collects one transaction before starting
the next. Queue depth ten therefore does not mean ten artwork chunks are staged
by this loop. A complete artwork uses 60 data transactions per controller, 480
across the eight controllers, excluding commands, status reads and conditioning.

This establishes the normal source lifetime more precisely: bytes already copied
into the current DMA block are isolated from later PSRAM writes, but the copy
itself and every unsent chunk still require ownership. A concurrent producer can
change subsequent chunks, even though the current DMA transfer is protected.
The blocking wrapper supplies an all-ones wait to both queue and result APIs; it
does not impose a finite panel-transfer deadline. These are static conclusions,
not induced allocation, overlap or stuck-transfer tests.

The command/data helper truncates every SDK result to its low eight bits before
returning it, in addition to overwriting earlier errors. For example, SDK
`0x101` (allocation failure) becomes `1`, and `0x102` becomes `2`. Preserve full
error codes and stop on the first failed transaction in a fork; the existing
return cannot be treated as an intact SDK error or proof that every chunk sent.

### Descriptors and manual controller selection also need ownership

The command descriptor at `0x3fca7620`, extended data descriptor at `0x3fca75f0`
and active device handle at `0x3fca75e0` are globals reused by the panel helpers.
They are not copied into a private descriptor for each caller. SDK completion
cleanup still reads the original descriptor, including its buffer pointers and
lengths. Waiting for one caller's transaction does not prevent another caller
from clearing or rewriting that same descriptor while the first caller waits.

Selector `0x420220a8` switches the active handle when driving a controller select
low. GPIOs 15–18 choose the first device; GPIOs 8, 3, 46 and 9 choose the second.
Both handles are used. Driving a select high does not change the active handle.
The command/data helper also drives both DC pins, GPIOs 4 and 5, around separate
command and data transactions. Its chunk loop reloads the shared active handle
for each call. No application mutex spans this selection, descriptor setup,
command/data sequence and final deselection in the recovered low-level helpers.

Thus SDK bus arbitration alone cannot protect the application's shared
descriptors or manual select/DC state. A firmware fork should give one panel
owner the whole operation, including conditioning, status reads and cleanup,
and keep descriptor storage alive and unchanged through result retrieval.
The existing render-busy policy is not this low-level lock. This identifies the
required boundary; it does not demonstrate that stock tasks have collided on
the physical frame or exhaust every higher-level caller's exclusion rules.

**Observed sample:** immediately before multipart streaming in the successful
fixed-image voice test, firmware reported 1,347,188 bytes of free PSRAM and a
largest block of 1,343,488 bytes. The streaming headers needed only 163 bytes;
the 159,788-byte WAV remained in the shared allocation. A second 2,304,000-byte
panel snapshot would not fit in that reported free PSRAM. This is one allocation
state, not a peak-memory, fragmentation or stress study. Buffer isolation would
need a broader allocation/lifetime redesign or a smaller staging strategy.

## Conditioning adds full-panel clear cycles

Before sending the artwork, the render worker can select a conditioning mode
through `0x420281e8`. A negative mode skips; zero calls MIN (`0x42028128`), a
black clear; a positive mode calls MID (`0x42027d88`), white then black. MIN waits
another 100 ms after a successful clear. MID waits 500 ms after each clear.
Those delays exclude the actual panel refresh and power sequence, so they are
not the conditioning duration.

The common clear helper `0x42027b34` allocates **288,000 bytes**, fills them with
`0x00` for black or `0x11` for white, selects all eight controllers through
`0x42020a78`, sends the same block, frees it, and invokes the ordinary refresh
sequence. It does not overwrite the shared artwork allocation with the clear
pattern. This temporary block is another allocation requirement during rendering.
The selected path has no rectangle coordinates or partial-image update protocol;
it does not establish panel support for partial refresh/custom waveforms.

Selection in the worker follows this order:

| Condition | Selected operation |
| --- | --- |
| Factory-test mode | Skip |
| First-flash, factory-reset or cold-boot first-time-user repaint flag | MID; consume the matching flag |
| First-time user, or cold-boot first-render flag | MIN; consume the latter flag when used |
| Otherwise | Consult the elapsed-time selector below |

Selector `0x4202d90c` only considers EXT1 or timer wakes, the numeric causes 3/4
in the matching [SDK definition](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_hw_support/include/esp_sleep.h).
It also requires the application's time-valid flag and a successful, nonzero
`app_data/last_sleep_ts` U64 read. Other wake causes, missing/zero timestamp,
NVS errors or unsynchronized time select skip. For a usable timestamp, it computes
elapsed wall-clock seconds, divides by 3,600, converts to float hours and compares:

| Computed elapsed hours | Mode |
| --- | --- |
| Below 12 | Skip |
| At least 12, below 48 | MIN |
| At least 48 | MID |

There is no separate future-timestamp rejection: a backward clock correction can
produce a negative interval and select skip. The calculation uses wall-clock
state, not measured panel temperature or a monotonic accumulated-sleep counter.

The timestamp's name/log label is misleading if treated as exclusively a sleep
entry. Writer `0x4202d860` runs in sleep preparation **and after conditioning
returns success**, before the pending artwork transfer. Its NVS commit result is
unchecked. Consequently this key does not independently prove time asleep,
successful conditioning or completion of the new artwork.

Error propagation further weakens that interpretation. MIN returns clear/power
setup errors, although deeper driver failures can still be swallowed. MID logs
white/black clear failures, attempts both, and **returns zero unconditionally**.
The worker can therefore record conditioning success and advance the timestamp
even after those logged failures; it continues to the artwork after a reported
conditioning failure too. GNU confirms the MID return and caller timestamp branch.

For a future fork, expose the selected mode/reason as diagnostics and propagate
actual results. Do not remove conditioning merely to reduce apparent refresh
latency without establishing the panel's requirements. H04/D06 retain physical
mode, failure and waveform validation; neither mode was newly exercised here.

## Readiness is not ownership

Both readiness accessors, `0x42028e7c` and `0x42028e9c`, return the byte at
`0x3fcabd20`. Allocation sets it to true. The recovered references do not show it
being cleared while recording, uploading or rendering. It means the buffer was
initialized, not that it is currently free.

Recording has its own state mutex at `0x3fca75c8`, active flag at `0x3fca75d0`,
and task handle. `0x4201fed0` checks recording state, the OTA-active getter
`0x42016564`, and buffer readiness before starting capture. These are not one
shared ownership lock covering the HTTP and renderer paths. The activity helper
`0x42011624` only updates the last-activity time; calling it does not acquire the
buffer either.

The recording-state query `0x42020150` can also return false when it fails to
acquire the recording mutex. A sampled activity flag is not a substitute for
acquiring ownership of the bytes.

## The render wait happens after HTTP reception

### Byte-level overlap fixture and model controls

Eleven isolated cases now perform real host memory copies at the recovered
allocation sizes and offsets. They use synthetic constant image/PCM bytes and
explicit operation order, with hashes and changed byte ranges recorded privately.
This is a **memory-ownership model**, not firmware/driver execution or a reproduced
frame race. It assumes the competing producers were admitted; stock scheduling
frequency and higher-level exclusion are not measured.

| Selected overlap | Large result | Standard control |
| --- | --- | --- |
| Complete second image copied before DROP rejects its render | All 2,304,000 image bytes already replaced | All 960,000 panel bytes already replaced |
| One 4,096-byte capture append at WAV offset 44 | Image bytes `[44, 4140)` changed | Image unchanged; audio has separate storage |
| Image receive writes 4,096 bytes over stored 8,192-byte PCM, then WAV header is finalized | 4,052 audio bytes `[44, 4096)` changed; resulting 8,236-byte WAV remains structurally valid | WAV unchanged |
| Image replacement after the first 4,096 WAV bytes were sent | Remaining 4,140 bytes changed; captured header and total WAV length still valid | Uploaded WAV unchanged |

The two image producers continue to share one image allocation on each model.
Standard's separate audio storage protects the cross-type cases above, not two
image producers or the global renderer/HTTP completion state. The synthetic WAV
check validates the recovered PCM header/length contract; it does not transcribe
or assess audio quality. A valid WAV alone is not an audio-integrity guarantee.

The Large DMA case sends twelve 4,800-byte chunks, copies chunk index twelve
into staging, then replaces the entire source image before continuing. The
current staged chunk remains unchanged. The outgoing 2,304,000-byte stream has
**62,400 original bytes followed by 2,241,600 replacement bytes**. Controller
zero receives 62,400 original plus 225,600 replacement bytes; the other seven
receive replacement bytes throughout. These are half-open buffer offsets in
controller transfer order, not physical pixel coordinates. The fixture assumes
the staging copy finished before the overwrite and does not model a write during
that copy. Large's DMA geometry is not assigned to Standard.

Two counterfactual controls retain all original bytes: deferring the producer
under exclusive ownership, and completing a full snapshot before mutation.
The latter allocates 2,304,000 extra payload bytes **on the host only**. It does
not show that a second panel buffer fits the frame; the measured free-memory
sample above still rules it out in that sample. D03 retains fragmentation/
pressure and ownership-design work. D02's bounded host milestone is complete;
physical overlap remains deferred. See [validation](validation-2026-10-22.md#byte-level-buffer-overlap-d02).

### Raw upload ordering

The raw upload sequence is:

```text
POST /api/image
  validate content type and length
  check buffer initialized and capacity
  receive body directly into shared buffer
  save last_image.bin
  start render with WAIT policy
  return status=rendering if task creation succeeds
```

`0x420307f8` does not acquire the recording mutex or check render-busy before its
receive loop. `0x4201727c` saves the bytes before calling the renderer. Thus the
renderer can wait for the previous task only **after** incoming data has already
overwritten shared memory and replaced the cache.

This matters even if the HTTP server processes local requests sequentially: a
previous request can return while its render worker remains active. Voice capture,
voice upload and background downloads add other users of the same allocation.
The exact timing of corruption has not been exercised on the device; the missing
early ownership guard and ordering are established from the code.

### What WAIT and DROP actually guarantee

`0x420208d4` uses render-busy byte `0x3fca75d1`:

- Policy `1` returns invalid-state (`0x103`) when a prior render is busy.
- The other branch waits in 25-tick steps, about 250 ms, for roughly five minutes.
  A still-busy task returns timeout (`0x107`).
- It allocates the small task context, sets busy, then creates the task.
- Task-creation failure clears busy and frees the context.

WAIT serializes render-task starts in the intended flow. It is not a queue of
immutable images. The check/wait/set sequence also lacks an atomic ownership
transaction in this routine; do not extend it to new concurrent producers as
though it were a mutex. DROP is not protective if the caller already wrote into
the shared buffer before requesting a render.

### Setup-screen tasks and the two-minute poll hold

Instruction dispatcher `0x4202ad38` obtains the shared image pointer, then either
downloads a server screen through `0x4202abe8` or loads a local screen through
`0x42028914`. Only **after those writes** does it call render-start with the
selected WAIT/DROP policy. Its display-manager check is a readiness/state read,
not a reservation of the shared pixels. It can log that readiness is still absent
after 50 wait cycles and proceed anyway.

Consequently, dropping a setup-screen render can still leave the prior render's
source bytes replaced. A failed download can also leave partial changes. This
extends the ownership map to system screens; no deliberate interference was
performed. Backend serialization of ordinary artwork jobs cannot protect an
independent local setup-screen trigger or recording.

The background starter `0x4202b178` copies screen type and render policy into an
**8-byte heap context**. Worker `0x4202b3cc` copies both fields and frees that
context before doing its work, so this handoff does not borrow the form handler's
stack. The starter retains no task handle and has no existing-worker exclusion.
Its creation loop is bounded to eight cycles, with 250 ms after each failed cycle.
It only attempts task creation when the largest `MALLOC_CAP_INTERNAL` block is
at least 10,240 bytes; the requested stack is 8,192 bytes, priority 3. The capability
value `0x800` matches the [SDK definition](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/heap/include/esp_heap_caps.h).
This is an allocation precheck, not a reservation or a guarantee that later TLS
allocations will succeed.

For type 2 (`get_started`) only, the starter sets a shared pending flag and a
deadline of monotonic time plus **120 seconds**, before task-creation retries.
Getter `0x4202b378` returns true only while the flag is set and current time is
strictly before that deadline. The poll dispatcher uses it to defer **new polls**,
with a log explicitly mentioning concurrent TLS. It does not stop an existing
poll, lock response/image memory, or cancel the instruction task at expiry.
The getter returns false at the deadline without clearing the stored flag.

Task-creation failure and worker exit clear the pending flag. Multiple Get Started
workers share that flag/deadline; an earlier worker's exit can clear a later
worker's hold. No corresponding hold is set for the create-account screen. The
two-minute value must not be used as a maximum setup duration: metadata fetching,
panel downloading and rendering have separate waits, and the task can outlive it.

The background worker uses the cache-saving instruction wrapper `0x4202b158`.
After render-start succeeds, the instruction path saves the shared bytes to the
current-image cache **before** the worker waits for display completion. A cache
write failure is logged without replacing the successful render-start result.
If render-start is rejected, that cache-save branch is skipped, although the
shared image bytes have already been written.

Finally, the worker waits up to **9,000 ticks / 90 seconds** on the same global
render semaphore used elsewhere, then delays 1.2 seconds on success. There is no
content/job ID or render result attached to that signal, and neither this path nor
render-start drains it before creating a new job. A timeout only logs and exits;
it does not stop or join the renderer. Success, failure, drop and timeout therefore
need separate backend diagnostics; “Get Started displayed” is not a per-image
physical acknowledgement. These concurrency/fault cases remain untested on the
frame; the host model below checks selected signal/lifetime consequences.

### Bounded renderer fault and admission model

A Large-only host reconstruction now exercises **20 scenarios and 140 bounded
event orders**. Three complete GNU control-flow recoveries cover render-start,
the render worker and recording-state query: 577 instructions with image-byte
checks. The fixture models allocation, task creation, binary semaphore behavior,
hardware returns and virtual time. It does not run FreeRTOS, a panel driver or
the firmware itself. The worker's normal self-delete is treated as terminating
the task; Ghidra's apparent fallthrough into failure cleanup is not a second
real cleanup.

| Injected condition | Modeled outcome |
| --- | --- |
| Null/zero input to render-start | Invalid argument; no context, busy claim or worker |
| Prior worker busy, DROP | Invalid state; previous worker remains live |
| Prior worker stays busy, WAIT | Timeout after 30,000 virtual ticks; previous worker/context remains live |
| Prior worker ends during WAIT | New worker starts, but its predecessor's signal remains available |
| 12-byte context allocation fails | No-memory return, no new worker or completion signal |
| Task creation fails after busy is set | Context freed and busy cleared; no completion signal |
| Worker size/pointer, I2C, expander or power-setup failure | Failure cleanup frees context and gives the same untyped signal as normal completion |
| Refresh reports an error | Error is logged; normal cleanup still gives completion |
| Worker hangs before cleanup | Waiter times out; worker, context and busy state remain |
| Recording mutex missing/timed out | Query returns false even if capture may still be active |

The WAIT counter is compared with 29,999 and advanced in 25-tick increments,
giving 1,200 modeled delays at the recovered 10 ms tick. The virtual 300 seconds
exclude real execution/scheduling overhead. The 90-second completion wait is a
separate caller policy; expiry does not join or delete the renderer.

The worker gives the binary semaphore **before clearing busy**. A waiter can
therefore consume a completion while a subsequent DROP still sees busy. Neither
render-start nor the instruction-screen waiter drains a prior signal; an old
signal can satisfy a new wait while its worker remains active. Draining removes
that stale token, but does not supply a job ID, success result or cancellation.
Two worker completions can also collapse into one binary token. Startup requests
one zero-sized queue item with semaphore type 3, matching that capacity.

The admission model splits each of two callers into check, context allocation,
busy set and task-create steps. Among 70 order-preserving merges with both
creates succeeding, 60 admit two workers and ten admit one. With only B's
creation forced to fail, 48 orders leave A live while busy is false; four leave
no worker because A dropped before B failed. These are **counts in the chosen
abstraction, not probabilities or observed schedules**. Real higher-level caller
exclusion and preemption timing were not simulated.

A separate trace lets the first of two admitted workers finish: it clears the
shared busy byte while the second is still active, admitting a third. This is
why a global boolean and an untyped completion signal cannot become a job lock
merely by checking them more frequently. For a future firmware change, one owner
must span admission, source bytes, driver work and cleanup, and completion must
carry identity and outcome. Backend serialization can limit its own offers but
cannot impose that ownership on independent stock tasks.

Hardware cleanup is assumed to return in these cases, and direct invalid-worker-
context probes do not imply ordinary render-start accepts invalid input. No actual
byte corruption, physical race, power-safe recovery or Standard equivalence is
claimed by this Large-only pass. See [validation](validation-2026-10-22.md#renderer-fault-and-admission-model-d04).

## Completion currently means the worker ended

The render worker gives the semaphore stored at `0x3fca6b24` and clears render-busy
on both its normal cleanup and early-failure cleanup paths. There is no accompanying
per-job success result in that signal. In addition, some failures below the worker
do not propagate at all:

| Path | Recovered behavior |
| --- | --- |
| `0x42021120`, controller image transfer | Logs a failed transfer and returns without a status result |
| `0x42020dd4`, controller-status check | Computes a result, but the render worker discards it |
| `0x42020ab4`, BUSY-high wait | Polls GPIO 6, logs a timeout after about 55 seconds, returns without status |
| `0x420218c4`, PMIC enable | Logs initialization failure; its caller does not receive a propagated error result |
| `0x420217e0`, power-good deassertion | Loops while the signal is high, with one-tick delays and no local deadline |
| `0x42021ba8`, power-good read | Returns zero on an I2C-read error, which also looks deasserted to that wait |
| `0x42021048`, refresh sequence | Returns zero after its sequence, including after the nonfatal BUSY timeout path |

The lack of a deadline in the power-good loop is local to that routine. The task
watchdog coverage is now traced below; whole-device fault recovery remains
unproven. Do not interpret this loop as proof that the device can never reset.

The refresh routine's completion log occurs before the worker's remaining
power-down sequence. Normal cleanup includes a 150-tick delay, then the existing
5 + 5 + 3 second discharge sequence in `0x42021bd8`, GPIO cleanup, semaphore give
and busy clear. Keep driver completion, power-safe idle and visual success distinct.

Adding a webhook at the current semaphore-give point alone would therefore report
failed work as completed. A reliable event needs propagated errors, content/job
identity, and a bounded hardware sequence before declaring driver success.
Even that is driver-observed completion, not optical verification of every pixel.

### The task watchdog does not bound the long panel sequence

Large's SDK startup `0x420ebdec` zeroes a 12-byte configuration, sets timeout to
**5,000 ms** and idle-core mask to **3**, then calls `0x42047d10`. The panic flag
at configuration offset 8 remains false. These are recovered build values, not
assumptions about SDK defaults. The initializer copies that flag into its runtime
object and subscribes both CPU idle tasks. The corresponding
[SDK implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_system/task_wdt/task_wdt.c)
identifies the configuration fields and subscription/reset APIs.

The render worker calls task-watchdog add (`0x42047c5c`) with zero, meaning the
current task, at `0x420204bd`. Its return is ignored. At `0x4202061c`, after the
early bus/controller initialization, it calls task-watchdog delete
(`0x42047ea8`) with zero, again without checking the result. The very next call
starts panel power setup. Conditioning, eight controller transfers, refresh,
power-good deassertion and discharge follow that unsubscribe point. There is no
later resubscription in the worker's recovered flow. Failure cleanup calls delete
again; if already removed, that second call does not establish new protection.

Timeout ISR `0x42047fc4` passes the runtime panic flag to `0x42047ba0`. Its false
branch prints/request backtraces and returns; the panic branch is separate.
The optional user ISR hook pointer is zero in this build. A task-watchdog message
therefore does not imply an automatic firmware restart under the startup policy.
This does not disable or fully characterize the separate interrupt watchdog,
hardware fallback stages, exception handling or boot recovery.

In the normal successful-unsubscribe path, a stuck power-good loop can continue
yielding one tick per iteration while both idle tasks run. Idle-task supervision
does not turn that loop into a bounded render operation. This is a static
consequence, not a device hang experiment. The recovered add/reset references
also do not establish a dedicated watchdog subscription for voice HTTP workers;
their outer waits need explicit cleanup rather than an assumed watchdog rescue.

A firmware fork should put deadlines and propagated failure results on the
hardware operations, keep job/buffer ownership through cleanup, and establish a
bounded power-down recovery path. Increasing a global watchdog timeout would
not supply those missing semantics. D06/D07 retain physical failure/recovery
tests and the wider watchdog audit.

### Observed poll and voice cache ordering

The [bounded device tests](backend-emulation.md) exposed different ordering for
two stock paths on the same build:

| Delivery | Observed order |
| --- | --- |
| Poll image | Download → start rendering and flash save in parallel → save complete → driver refresh complete → panel discharge → task complete |
| Voice result | Download → render → driver refresh complete → panel discharge → processing-success log → flash save → ready state |

For the voice test, driver refresh ended at 20:03:39 UTC, discharge at 20:03:54,
and flash save/ready at 20:04:12. Its 69.434-second processing timer excluded the
approximately 18.55-second save that followed. A display already showing the
result can therefore coexist with unfinished workflow cleanup/storage.

All controller-ready and normal-completion logs were present. The owner confirmed
the first poll-delivered card; the voice experiment intentionally reused that
same card, so its second refresh was not independently witnessed. These positive
tests do not validate failure propagation or convert completion logs into a
per-image acknowledgment.

## Maintenance refresh has separate completion rules

Large's refresh helper `0x42027f84` takes two different paths. With an image
pointer and nonzero length, it drains the shared completion semaphore, calls
`0x420208d4` with DROP policy, then waits **9,000 ticks / 90 seconds** if accepted.
Unlike the instruction-screen worker, this caller does drain an old signal.
It still receives no per-job result. An invalid-state/drop return is converted
to success, and a timeout resets the manager's state to ready without stopping
or joining the renderer. The separate render-busy byte can remain set.

The saved-image wrapper `0x4200fc7c` loads the cache into the shared image buffer
before this arbitration. If the advanced helper returns an error, its fallback
calls render-start again with DROP policy. A drop becomes success; an accepted
fallback reports success after a two-second LED delay without waiting for the
render semaphore. Thus this wrapper's zero result can mean worker-ended,
accepted-but-still-running, or dropped. It cannot acknowledge a particular image.
An advanced-helper timeout followed by a still-busy renderer reaches the
drop-as-success fallback; this is a static path, not an induced timeout test.

### Blank refresh can wait on its own busy state

Before choosing image or blank work, `0x42027f84` attempts to set manager state
5 (busy). Its blank branch then calls power-on `0x42027e6c`, which sees that state
and calls ready-wait `0x42027e10`. That waiter needs state 4, or exits on state 6
or timeout; it does not start any work that would make the display ready.

With successful state/mutex operations and no other task changing the state,
this path therefore waits until its configured **30,000 ms** deadline and returns
timeout before reaching the intended white clear. The caller then writes state
4 even though this power-on attempt did not run the hardware sequence. The
default configuration is recovered from `0x42028204`; the waiter's time helper
converts ticks to milliseconds. Mutex failures, concurrent state changes and a
nondefault configuration can alter the path. No blank refresh was requested.

If the clear branch is reached, it performs one white clear, discharge and GPIO
cleanup, then sets state 1 (off). A clear failure is retained in the return value
even though the branch logs that its blank cycle completed. Do not turn that log
into a success event. Standard instead powers on before setting busy and performs
its FULL white/black/white cycle; see the
[model comparison](standard-model-comparison.md#maintenance-refresh-differences).

## `display.last_refresh` is maintenance history

`/api/info` calls `0x42015ef8`, which loads `app_data/refresh_hist` through
`0x42014b48`. The 48-byte record contains five 64-bit timestamps, a next-write
index and a count. The API reports the latest valid ring entry or null.

The recovered append routine `0x42015e5c` has one call site, `0x42012757`, in the
maintenance-refresh flow beginning at `0x420126f8`. It is not called by the common
render worker or the raw local-upload handler. The append persists through
`0x42014d14` and carries a timestamp, not image identity or a render result.

The scheduled caller discards `0x4200fc7c`'s result before logging completion,
appending the timestamp and requesting the default four-day, 03:00 schedule.
History can therefore advance after a failed or dropped refresh, provided the
append itself succeeds. This is stronger than merely being maintenance-only:
it records an attempted workflow without validating the display outcome. The
manual-refresh wrapper returns the helper result but does not call this append.

Consequences for HA:

- An image upload or voice generation need not change `display.last_refresh`.
- A changed value can reflect maintenance of existing artwork.
- The field cannot acknowledge a specific delivered image or establish its success.

**Observed:** the entire exposed `display` object, including maintenance history,
was unchanged before and after the completed fixed-image voice test. The settings
object was also unchanged. This supports the distinction above without testing
all routes, reboot persistence or maintenance transitions.

Ghidra initially grouped the maintenance routine into the preceding pre-sleep
function because the deep-sleep call does not return normally. The actual entry at
`0x420126f8` was verified in GNU disassembly; treat the function boundary carefully.

## Implications for a firmware fork and adapter

1. Acquire one explicit buffer owner **before** recording or accepting image bytes.
   Include local HTTP, voice transmission, cloud downloads and system images.
2. Reject/defer a new producer before it overwrites an existing owner's data.
   Decide who may cancel whom; do not use LED state or buffer readiness as a lock.
3. Carry a stable content/job ID through reception, caching, rendering and cleanup.
4. Return structured results for cache failure, transfer failure, hardware timeout,
   successful driver completion and power-safe idle; signal termination separately.
5. Propagate driver errors and bound waits while preserving the panel's required
   shutdown sequence. Keep ownership until all consumers have released the bytes.
6. Add display-result events to HA and retain maintenance timestamps as maintenance
   telemetry. Preserve generated/downloaded/display-unconfirmed states for stock firmware.
7. Check worker creation before waiting; retain owned context and task identity
   through cancellation/timeout cleanup. A semaphore without a job ID cannot
   distinguish a late worker from the current request.

The existing HA upload lock and Hybrid delivery window are useful for cooperating
senders, but cannot prevent physical-button recording or every stock cloud action.
See the [HA roadmap](home-assistant-roadmap.md) for the application-side design.
