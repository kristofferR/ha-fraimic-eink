# Physical input and gestures

[Research index](README.md) · [Voice cancellation](voice.md#gesture-and-cancellation-flag) · [Boot lifecycle](boot-and-scheduling.md#main-lifecycle)

**Static/Host, both pinned builds:** Large 0.2.29/f1555ee5 and Standard
0.2.28/4654a1d8. Seven complete function pairs match across 1,444 decoded
instructions after relocation, with external calls and RAM values kept outside
that equivalence claim. Thirty-three bounded instruction cases per build produce
the same results. No new button press, recording or cancellation test occurred.
See the [numeric cases and coverage](button-input-cases.json) and
[validation record](validation-2026-10-22.md#button-input-and-gesture-cases-s06e01e02).

## Input and task boundaries

Both paths sample GPIO **2**, with zero treated as pressed. Input initialization
calls three GPIO helpers, including a direction call with argument `1`, and
does not check their results. A ready log alone therefore does not verify the
electrical input or every setup call. Physical polarity, bounce and timing have
not been measured in this pass.

| Function | Large | Standard |
| --- | --- | --- |
| Input initialization | `0x42011070` | `0x42010fd0` |
| Idle button wait | `0x4201163c` | `0x4201159c` |
| Gesture monitor | `0x4200f770` | `0x4200f6c4` |
| Start monitor | `0x420110a4` | `0x42011004` |
| Stop monitor | `0x42011218` | `0x42011178` |
| Recording-control task | `0x42011314` | `0x42011274` |

The monitor is a polling task, not a queue of hardware edge events. Its normal
loop delays two ticks, approximately 20 ms at the recovered 10 ms tick period.
Mutex waits, logging, scheduling and selected branches can change its sampling
interval. Millisecond comparisons use a 64-bit microsecond clock divided by
1,000; the fixture checks a crossing of the low 32-bit millisecond word.

The start helper requests task priority 4, core 1 and stack-size argument 4,096.
It can fail on mutex creation/acquisition or task creation; starting an already
running monitor returns `0x103`. The recording-control caller does not check
that start result. In the bounded task-creation-failure case, it continues its
recording-control loop with no monitor running. The separate outer recording
timeout remains relevant; this does not prove a physical stuck recording.

## Factory mode guards idle admission, not capture ownership

Ordinary button wait checks factory mode both on entry and in its outer wait
loop. If active, it delays ten ticks and returns zero instead of admitting a
new recording. At entry this happens before any GPIO read. A normal sequence
of opening the factory page and then tapping therefore has an admission guard;
the [two-reader helper result](local-api.md#factory-and-normal-microphone-capture-can-both-be-admitted)
must not be described as proof that this usual page/tap sequence overlaps audio.

This guard reads **factory mode**, not the separate factory microphone-active
flag. Direct `POST /test?action=mic_start` does not require the landing page or
arm that mode. Nor is the outer input check a reservation: factory mode can
change after it while an already-observed press is being accepted/released.
The inner release wait has no factory-mode recheck.

Six instruction cases per model distinguish these boundaries:

| Scripted state/transition | Result |
| --- | --- |
| Factory mode active at idle-handler entry | Return zero after ten ticks; no GPIO read. |
| Factory mode enters while waiting for a button already held on entry | The later outer check catches it; return zero. |
| Factory mode off, fresh tap | Return one, recording admission. |
| Factory mode enters after the outer check as the low sample is read | Return one with factory mode now active. |
| Factory mode enters during release wait | Return one with factory mode active. |
| Recording-control task already admitted, factory mode active | It calls normal microphone start; no additional factory admission check occurs in that task. Microphone/task helpers are stubbed in this case. |

The existing main-loop trace carries a positive idle result to the outer
recording wrapper, which still checks voice enablement and can fail capture.
The factory guard, voice preference and microphone ownership are separate
boundaries. Mode changes do not retroactively cancel an admitted control task.

An exact-reference/pointer-word search identifies seven mode-getter call sites
per build: two in idle wait, plus ordinary idle/sleep, main factory expiry,
time synchronization, LED selection and rendering. The identified flag store
is the landing-page entry; neither the recovered microphone-stop helper nor
its route clears it. Leaving the page or stopping its microphone does not
restore ordinary input through a recovered factory-mode exit operation. The
search does not exclude arbitrary computed access; startup/reboot is separate.

These six cases execute 433 unique instructions per model, with the real mode
getter and synthetic GPIO/time transitions. They establish admission paths,
not physical overlap, task scheduling or measured latency. [Evidence](factory-input-cases.json).
A firmware owner must reserve capture independently of the UI mode guard.

## Three timing rules, not one tap timeout

The monitor initially samples the input and treats an already-held button as
the previous state. That held level is not a new press; release and a new edge
are needed. A later press is counted on the sampled transition to low.

| Condition | Recovered result |
| --- | --- |
| First qualifying press | Start a group, count 1, save first/last time |
| Next press less than 100 ms after the last accepted press | Reject it as debounce |
| Next press at least 100 ms later and at most 800 ms after the first | Increment count and update last time |
| Third qualifying press | Publish count 3 immediately; set the mode-specific cancellation flag |
| New press more than 800 ms after the first, before the old group was published | Replace the old group with a new count 1 |
| More than 800 ms since the last accepted press | Publish the current count and clear the in-progress group |

Exactly 100 ms is accepted. Exactly 800 ms fits the first-edge grouping window,
but exactly 800 ms of quiet does **not** publish; the quiet comparison is strict.
The quiet path does not require release. A new press held longer than the quiet
threshold can therefore publish a single tap while the input is still low.

One useful boundary example is presses at 100, 500 and 901 ms. The third is
outside the first press's grouping window but arrives before 800 ms of quiet
after the second. It replaces the previous two-press group; the selected case
later publishes only one tap. This is a consequence of the two different
windows, not a measured physical three-tap failure rate.

OTA-active and failed-mutex branches can suppress a sampled edge. The fixture
also covers an unconsumed result being overwritten by a later group. There is
no inference here that all input survives scheduler stalls or lock contention.

## Recording versus processing

The recording-control task starts microphone capture, then waits **200 ticks**
before starting the gesture monitor in mode `1`. This is about two seconds of
initial suppression. Inputs during that interval are not queued for later replay.

Once the recording-control task consumes a published result:

- Count **1** requests recording stop and normal completion.
- Count **2** clears the ready byte and continues recording.
- Count **3 or greater** sets recording cancellation and requests stop.

The third accepted edge already sets the recording-cancel byte in mode `1`.
In processing mode `2`, the third edge instead sets the processing-cancel byte
and calls the HTTP abort manager. One/two taps do not invoke that processing
abort branch. Actual socket coverage and late-worker lifetime retain the
[existing cancellation limits](voice.md#which-stages-can-abort-their-socket).

The recording consumer normally polls with a five-tick delay, approximately
50 ms, after the initial suppression. Those polling intervals do not specify
an exact audio-sample cutoff or physical response latency.

## The result is a single shared slot

The monitor record stores mode, in-progress count, two timestamps, running byte,
result-ready byte, published count and mutex. A subsequent result can overwrite
an unconsumed one; it is not a FIFO. The recording consumer clears readiness,
but does not make a per-recording copy with an owner/job identifier.

The start helper clears the in-progress count/timestamps and sets the mode, but
**does not clear the published ready/count fields**. A successful active stop
does clear them. An inactive stop returns success without clearing them.
Consequently a pre-existing pending result can survive start or an inactive
stop. The fixture deliberately seeds that state; it does not demonstrate that
ordinary physical use has produced a stale result.

Active stop clears the running byte and waits five ticks. It does not join the
monitor task or wait for an explicit exit acknowledgment. The monitor checks
that byte only after a successful mutex acquisition, then deletes itself.
Thus the stop delay is not proof of task termination before another start.

A firmware change should clear pending results when beginning a new input
session, use session identity, and establish monitor termination before reuse.
Cancellation, recording completion and processing completion should remain
distinct events; changing an LED or returning from a stop request is not a
worker-lifetime guarantee.

## Held input in the idle handler

Idle admission is a separate path from the recording/processing monitor:

1. If the button is already down on entry, poll for release every two ticks.
   After **more than 10,000 ms**, log a warning and continue anyway. The later
   released log is not a fresh proof that the level became high.
2. Wait ten ticks after that entry-held branch, then enter ordinary waiting.
3. When low input is seen, record activity and delay five ticks. Poll release
   every tick; after **more than 5,000 ms**, accept it anyway.
4. Return the recording-admission result even if the input is still low.

With external predicates held constant and exact simulated tick advancement,
the fresh-tap fixture returns at 150 ms, a new held press at 5,160 ms, and an
input held from entry at 15,180 ms. These are host-case results, not measured
device latencies. The entry-held result shows that one continuous low input can
eventually be admitted without an intervening release.

Pending sleep, server work, safe OTA and idle checks are in the outer wait loop,
not in the inner release wait. A simulated sleep request arriving during that
release wait remains pending when the handler returns recording admission.
The [main-loop follow-up](boot-and-scheduling.md#boot-classification-and-first-recording-admission)
now traces the caller on both builds: with the selected existing-user predicates,
it reaches the outer recording wrapper with sleep still pending. That wrapper
still checks voice enablement and capture can fail. These combined host cases
establish an admission path, not an observed recording/sleep race.

Keep these separate boundaries in a custom firmware design: physical wake,
new recording admission, recording stop/cancel and processing cancel. A backend
alone cannot change this local input parsing or make short/double taps into
new cloud commands.
