# Rendering, buffer ownership and completion

[Research index](README.md)

This follow-up traces Large 0.2.29's buffer aliases, render task and status
reporting. Unless labelled observed, findings are **static**, with consequential
instructions checked in GNU ESP32-S3 disassembly. Later bounded poll/voice tests
observed the normal completion path. No concurrent-upload, fault-injection or
modified-firmware experiment was performed.

The [voice cancellation follow-up](voice.md#cancellation-and-scheduled-content-races)
maps a second shared resource: the HTTP-abort manager stores one active client,
without job-scoped ownership. It also distinguishes the pre-render cancel check
from a refresh already running. Its lifetime/fault cases remain untested.
The [timeout and two-job follow-up](voice.md#timeout-and-error-boundaries-still-needing-validation)
also traces unchecked task creation, a WAV cleanup helper that does not release
ownership, and a candidate cancellation flag left over for the next recording.

## The display pointer is another alias

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
Protect the bytes until the display driver has finished consuming them. Releasing
ownership merely because the worker started or passed the copy call is unsafe.
Holding through the full render is the simpler initial design. The transfer
lifetime is now traced below; an earlier release would still need a verified
boundary across all controllers and other consumers.

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

**Observed sample:** immediately before multipart streaming in the successful
fixed-image voice test, firmware reported 1,347,188 bytes of free PSRAM and a
largest block of 1,343,488 bytes. The streaming headers needed only 163 bytes;
the 159,788-byte WAV remained in the shared allocation. A second 2,304,000-byte
panel snapshot would not fit in that reported free PSRAM. This is one allocation
state, not a peak-memory, fragmentation or stress study. Buffer isolation would
need a broader allocation/lifetime redesign or a smaller staging strategy.

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

The lack of a deadline in the power-good loop is local to that routine; overall
watchdog behavior has not been established. Do not interpret it as proof that the
whole device can never reset or recover.

The refresh routine's completion log occurs before the worker's remaining
power-down sequence. Normal cleanup includes a 150-tick delay, then the existing
5 + 5 + 3 second discharge sequence in `0x42021bd8`, GPIO cleanup, semaphore give
and busy clear. Keep driver completion, power-safe idle and visual success distinct.

Adding a webhook at the current semaphore-give point alone would therefore report
failed work as completed. A reliable event needs propagated errors, content/job
identity, and a bounded hardware sequence before declaring driver success.
Even that is driver-observed completion, not optical verification of every pixel.

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

## `display.last_refresh` is maintenance history

`/api/info` calls `0x42015ef8`, which loads `app_data/refresh_hist` through
`0x42014b48`. The 48-byte record contains five 64-bit timestamps, a next-write
index and a count. The API reports the latest valid ring entry or null.

The recovered append routine `0x42015e5c` has one call site, `0x42012757`, in the
maintenance-refresh flow beginning at `0x420126f8`. It is not called by the common
render worker or the raw local-upload handler. The append persists through
`0x42014d14` and carries a timestamp, not image identity or a render result.

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
