# Microphone DMA and sample-loss boundaries

[Research index](README.md) · [Voice capture](voice.md) · [Static coverage](static-coverage.md)

**Static and instruction-fixture evidence, 23 October 2026:** Large 0.2.29 /
f1555ee5 and Standard 0.2.28 / 4654a1d8. Both use the same recovered producer
logic. The earlier reader tests supplied queue contents directly; this pass
follows channel construction, ring allocation and the receive callback.

## Six reusable buffers, five queued pointers

The application's six-descriptor, 240-frame, 16 kHz/16-bit mono configuration
produces **480 bytes per DMA buffer**. PDM slot setup selects one active slot;
the two-slot hardware setting does not double the application's buffer size.
The allocator links six descriptors in a circle and allocates six 480-byte
sample buffers: 2,880 sample bytes, excluding descriptors and other metadata.

At the configured rate, each block represents 15 ms of PCM. The six blocks
represent 90 ms and the five queue entries represent 75 ms. These are nominal
audio-capacity calculations, **not measured scheduling deadlines** or guaranteed
time available to the reader.

Channel construction creates a queue of **five four-byte pointers**, not five
copies of the samples. The receive DMA registration supplies the I2S EOF
callback and leaves its other two event callbacks null. It passes the I2S
channel as callback context. The I2S user receive/overflow callbacks also start
null; the recovered application microphone initializer does not install them.
The SDK event-registration function-name string is absent from both images.
This is a bounded registration finding, not exclusion of arbitrary computed
calls elsewhere in the application.

| Function | Large | Standard |
| --- | --- | --- |
| Receive EOF callback | `0x4037afb8` | `0x4037afd8` |
| DMA size calculation | `0x4204edd4` | `0x4204deac` |
| Ring allocation | `0x4204eeac` | `0x4204df84` |
| DMA interrupt registration | `0x4204f0f8` | `0x4204e1d0` |
| Channel allocation / queue creation | `0x4204f5b4` | `0x4204e68c` |
| Channel creation wrapper | `0x4204f758` | `0x4204e830` |
| PDM slot setup | `0x4204ff48` | `0x4204f020` |
| PDM RX initialization | `0x420500e0` | `0x4204f1b8` |

## Overflow removes the oldest queued audio

The receive callback takes the completed descriptor's buffer pointer. If a user
receive callback exists, it calls that first. When the queue is full it removes
one old entry, optionally calls the overflow callback, then sends the new
pointer. Its return value combines task-yield requests; it is not an audio-loss
status. It ignores the queue-send return value.

With the default null user hooks, the recovered callback contains no application
drop counter or loss notification. Six synthetic completions without a reader
leave only completions 1–5 queued: completion 0 is discarded. Twenty leave the
latest five. A subsequent successful SDK read supplies those surviving samples
without reporting the omitted intervals.

## Reading does not reserve a DMA buffer

The SDK reader keeps the current pointer and byte offset between calls. It
copies samples from that storage; neither the producer nor reader makes a
private copy when the pointer is queued or borrowed. The reader semaphore
serializes readers, but the receive callback does not take it.

In an explicit synthetic interleaving, the reader consumes 32 bytes from buffer
0. Six further completions reuse that storage. Its next 448-byte read succeeds
from the saved pointer, now containing the newer generation. This demonstrates
that the recovered code does not guarantee a stable unread suffix under that
DMA reuse schedule. It does not establish how often, or whether, this happens
on the physical frames. The earlier
[partial-timeout loss](voice.md#capture-reads-can-lose-audio-without-invalidating-wav-structure) remains a
separate way for consumed samples to disappear from the saved WAV.

For a local backend, WAV duration still means **stored PCM duration**. The stock
presign/finalize requests contain no sequence numbers or DMA-overflow metadata
from which to reconstruct missing time. A future firmware capture event could
carry a recording ID, sample/overflow counters and timestamps; an emulator
alone cannot recover those unreported intervals.

## A DMA allocation failure is not handled consistently

The descriptor-pointer array allocation is checked. A synthetic failure returns
`0x101` after calling cleanup. The following **sample-buffer-pointer array**
allocation is stored without a null check. If it fails while the next individual
descriptor/buffer allocations succeed, the compiled loop reaches a store through
address zero before its later per-buffer check.

Both builds reach that boundary in the instruction fixture. The host interpreter
stops at the unmapped store; no ESP32 exception handler, reboot or physical heap
failure was exercised. This is also present in the pinned
[IDF 5.4.1 ring allocator](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_driver_i2s/i2s_common.c).
It is not evidence that this failure caused the earlier TLS allocation error or
the battery issue.

## Validation and remaining limits

[Numeric evidence](microphone-producer-cases.json) records eight complete paired
CFGs, **1,241 instructions per build**, and 17 mapped direct-call pairs. Their
normalized operations and branch targets match after relocation. External
callee behavior is not implied by that comparison.

Fifteen instruction cases per build execute 464 distinct sites using the actual
decoded instructions. They cover RX callback registration, PDM sizing, circular
allocation, queue construction, the two allocation-failure boundaries, normal
delivery, overflow, repeated wrap, a borrowed-buffer overwrite, partial timeout,
optional hook order/yield and a synthetic queue-send failure. Queue operations,
allocation outcomes, hardware registers and DMA writes are modeled. No device,
network, artwork or firmware was changed.

## Interrupt flags do not reach the saved recording

The follow-up traces GDMA RX registration, interrupt installation and dispatch,
plus I2S hardware start/stop. Five more paired bodies contain 324 instructions
per build. The ISR is Large `0x4037d600` / Standard `0x4037d620`; registration is
`0x420ea5f4` / `0x420ea914`, and interrupt installation is
`0x420ea07c` / `0x420ea39c`.

The installed callback set enables mask `6` (successful and abnormal EOF),
disables mask `8` (descriptor error) and disables mask `1` (receive done).
The [SDK event definitions](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_hw_support/dma/include/esp_private/gdma.h)
distinguish abnormal EOF from a descriptor error; they must not be treated as
the same fault.

On entry the ISR reads and clears raw interrupt status. Successful EOF selects
the successful descriptor; abnormal EOF selects the abnormal descriptor. If
both bits are set, the latter address wins while both flags are retained. The
I2S callback reads only the descriptor address and ignores these flags, so both
synthetic event types reach the ordinary pointer queue. A valid queue read or
WAV header therefore does not certify an entirely normal capture history.
Whether this PDM hardware produces abnormal EOF in practice remains unknown.

Descriptor-error-only, done-only and unrelated raw status cases clear status
without queuing samples under the installed null callbacks. Those are tests of
an already-entered ISR: disabled bits alone need not generate a physical interrupt.
The recovered ISR supplies no missing descriptor-error recovery callback for the
application. Actual hardware recovery is not established by this analysis.

## Hardware start contains a separate unbounded wait

RX start is Large `0x4204eb40` / Standard `0x4204dc18`; stop is
`0x4204eaf0` / `0x4204dbc8`. Start resets I2S, calls GDMA reset/start and does not
test those helpers' return values. In the ordinary non-ETM branch it sets RX
update bit 8, repeatedly reads it until it clears, then sets RX start bit 2.
There is no delay, timeout or software cancellation check inside that loop.
This matches the pinned [ESP32-S3 I2S low-level start](https://github.com/espressif/esp-idf/blob/v5.4.1/components/hal/esp32s3/include/hal/i2s_ll.h).

The fixture separately models a clearing bit and a permanently set bit. The
latter stops after four reads at the same wait boundary, before RX start is set.
It does not emulate a watchdog or demonstrate a physical hang. Stop clears the
RX start bit in its ordinary branch, invokes GDMA stop and does not test its
return. An application completion log is not a measurement of these hardware
outcomes.

[Interrupt cases](microphone-interrupt-cases.json) record thirteen cases per
build, executing 232 distinct instruction sites. Interrupt latency, physical
DMA faults, signal quality and recovery remain device questions. The
[static coverage ledger](static-coverage.md) keeps them separate from the
completed producer and dispatch traces.
