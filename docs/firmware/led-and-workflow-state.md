# LED state and workflow protection

[Research index](README.md)

Large 0.2.29 has **41 LED state records**, each 24 bytes, at `0x3c13ff68`.
[Extracted records](led-states.json) preserve RGB bytes, numeric pattern, duration,
period, priority, count and automatic-off field in the original table order.
IDs are unique 0–40 but the table is not sorted by ID; lookup `0x42022648`
searches it. Unknown IDs in that lookup fall back to the first/off record.
The internal state setter separately rejects IDs above 40.

Field roles were traced through worker `0x42022860` and timeout check
`0x4202276c`. Durations and periods are milliseconds based on the 10 ms tick.
The timeout check treats nonzero duration as expired when elapsed time is at
least that duration; GNU decoding recovered the `SALTU` comparison omitted by
Ghidra. Pattern-specific completion can occur earlier. The table is software
configuration, not a photometric measurement or physical timing test.

## Useful state associations

The [hardware audit](hardware-and-layout.md#audio-output-audit-across-both-models)
traces the actual three-channel LED PWM configuration on both builds, including
their different GPIOs, 5 kHz timer and inverted eight-bit duty. These references
do not identify an audio-output driver.

These meanings come from recovered call sites, not original enum names. A state
can be used by more than one workflow:

| State | Recovered use | Configured indication |
| --- | --- | --- |
| 0 | Off / clear workflow indication | Off |
| 23 | Recording started, including ordinary microphone workflow | Solid red |
| 24 | Explicit recording completion | Green, three flashes with 300 ms period |
| 25 | Processing cancellation paths | Orange, three flashes with 400 ms period |
| 26 | Manual/display maintenance refresh entry | White breathing, 2,000 ms period |
| 28 | Poll-image announcement before state 29 | Blue, three flashes with 600 ms period |
| 29 | Poll-image download/render workflow | White breathing, 5,000 ms period |
| 30 | Success indication in display/maintenance paths | Green double-flash pattern |
| 36 | Voice reachability/Wi-Fi failure | Red, one flash per error group |
| 37 | Voice upload/finalization or WAV-preparation failure | Red, two flashes per error group |
| 38 | Voice/poll image-download failure or timeout | Red, three flashes per error group |
| 39 | Render-start failure or render wait timeout | Red, four flashes per error group |

States 36–39 use 2,000 ms error groups, a 20-second overall duration and an
automatic-off field. A color alone does not identify the stage: several states
share colors, and one failure state can cover multiple causes. State 30 is not a
per-image acknowledgment; the [render completion limitations](rendering-and-concurrency.md)
still apply. A later [Standard comparison](standard-model-comparison.md#calendar-and-led-follow-up)
found a byte-identical table and matching lookup stride. The subsequent comparison
below also covers the setter, worker and protection logic; physical LED timing
and complete call-site meanings remain untested.

## Protection is a UI state latch

The manager at `0x3fca7664` stores current state at offset 0, pending state at 4,
start time at 8 and workflow protection at `0x14`. Its mutex is at
`0x3fca7660`. Classifier `0x420e2ac0` recognizes states 22–27, 29 and 30 as
workflow states. Helper `0x42022690` latches protection on entry and clears it
when a permitted off transition is processed. Although its non-workflow branch
also mentions state 30 as a clearing case, the classifier above treats 30 as a
workflow state, so that case does not establish clearing on success. Worker
completion and timeout can subsequently transition to off.

Setter `0x42022f48` uses priorities, workflow protection and a separate urgent
classifier (`0x420e2aec`: state 25 and states 31–39). It may ignore a requested
lower-priority or disallowed transition and still return success. A successful
setter call is therefore not proof the requested LED state appeared. Changes can
also be deferred through the pending-state field before the worker applies them.

Getter `0x420231d0` reads the protection byte with a one-tick mutex wait. Missing
mutex or a failed acquisition returns false. `/api/refresh` uses this getter,
alongside recording state, for its busy response. This latch does not identify
buffer owner, job, downloaded content or physical panel completion; its API guard
must not be promoted into a concurrency guarantee.

## Pending transitions and completion

The setter writes one pending-state slot, not a queue. It compares priority with
the **current** state, not an earlier pending request. A later accepted request
can therefore replace a pending request before either is shown. The worker
applies pending state under a zero-wait mutex acquisition and resets its start
time only when pending differs from current. Re-requesting the same current state
does not restart its duration. Its ordinary loop delays five ticks, nominally
50 ms; that is not a measured upper bound on response time.

Protection can change before the worker applies the requested indication:

- Requesting workflow state 29 from off immediately latches protection while
  current remains off. A subsequent ordinary off request is ignored because the
  off exception requires a **current workflow state**. The pending 29 remains.
- Requesting off from current workflow state 29 clears protection immediately,
  while current remains 29 until the worker applies off. A false protection
  reading consequently does not establish that a workflow or even its LED has
  finished.
- An urgent error, such as 38, skips the setter's protection update. Applied
  after state 29, it preserves the existing latch; an ordinary off request is
  then blocked because 38 is not a workflow state. The worker's completion path
  clears it after the configured 20 seconds. The same error entered from idle
  does not create a latch. Error color alone cannot reveal protection state.

The worker has a separate completion byte at manager offset `0x13`. Pattern
completion and duration expiry are different branches:

| State/path | Recovered software behavior |
| --- | --- |
| 24, recording confirmation | Three 300 ms periods complete at 900 ms, before its 1,500 ms duration |
| 25, cancellation | Three 400 ms periods complete at 1,200 ms and release protection |
| 30, success | Its two 200 ms double-flash periods have a 400 ms pattern window; this pattern does not set the completion byte, so state/protection remain until the 1,000 ms duration expires |
| 9–11, Wi-Fi diagnostics | Pattern completion changes current and pending to state 5, rather than off |
| 36–39, workflow errors | Pattern completion changes current and pending to off and releases any retained latch |

Clearing completion also requires a zero-wait mutex acquisition. If it fails,
the completion byte remains set. Neither the setter nor the pending-state apply
branch resets that byte. A reconstructed host sequence therefore reproduces:
state 24 completes → completion mutex fails → state 29 is accepted → next worker
pass applies 29 → the stale completion byte immediately clears 29. This is a
**conditional state-machine result**, not an observed device race. Actual task
interleavings, LED output calls and FreeRTOS scheduling were not executed.

The emergency-off wrapper uses a separate zero-valued task notification
(`0x42022d48`). The worker consumes that notification before its ordinary
state-mutex section, updates protection/current/pending and resets the start time.
The wrapper checks for a task handle but does not await application of off. It is
neither a render cancellation API nor a guarantee of immediate physical darkness.

## Other setter gates

Before acquiring the mutex or checking urgency, the setter checks factory-test
mode (`0x4201ea44`). In that mode only states 0, 4, 23, 29, 30 and 33 proceed;
other valid requests return zero unchanged, including ordinary urgent-error IDs
36–39. This is a factory-mode exception to the urgent classifier's later bypass.

Background classifier `0x42022674` uses mask `0x18f080` for states 7, 12–15,
19 and 20. These requests cannot replace a current workflow state even if the
protection byte is false. Other nonurgent requests still need equal/higher
priority, a current off state, or an off request after the preceding protection
check. Invalid IDs return `0x102`, missing manager mutex returns `0x103`, and
failure to acquire it within one tick returns `0x107`. The current-state getter,
like the protection getter, instead returns its off/false default on contention.

## Standard comparison and host scope

The Standard manager is at `0x3fca76bc`, with mutex `0x3fca76b8`. Its setter
`0x420219f8`, worker `0x42021310` and protection getter `0x42021c80` have the
corresponding branches above. Thirteen function pairs, including classifiers,
timeout, latch, getters, emergency notification and factory-mode getter, match
across **826 GNU-decoded instructions** after explicitly accounting for relocated
function/global addresses and comparing referenced strings. This checks branch
destinations, registers and constants; it is not a recursive equivalence proof
of SDK calls, LED output drivers, all callers or the two complete applications.

Twenty-two reconstructed C host case groups passed with AddressSanitizer and
UndefinedBehaviorSanitizer, using the extracted 41-record table, scripted mutex
outcomes and virtual milliseconds. They cover the sequences above plus ID bounds,
factory filtering, priority rejection, unsigned clock wrap and delayed completion.
They do not simulate actual light, concurrency, task-notification delivery or
hardware. [Validation details](validation-2026-10-22.md#led-arbitration-and-standard-comparison-e02h05d01d07)
retain the evidence and limits.

A firmware/backend extension should report recording, upload/finalize, download,
render and terminal result explicitly under one job ID. LED indication can then
follow those events without becoming the source of truth for HA scheduling.
