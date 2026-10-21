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
found a byte-identical table and matching lookup stride, but physical LED timing
and the complete Standard arbitration state machine remain untested/unmapped.

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

A firmware/backend extension should report recording, upload/finalize, download,
render and terminal result explicitly under one job ID. LED indication can then
follow those events without becoming the source of truth for HA scheduling.
