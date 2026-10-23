# Wi-Fi candidate selection and retry limits

[Research index](README.md) · [Connectivity policy](boot-and-scheduling.md#offline-dependencies) · [Static coverage](static-coverage.md)

**Static and instruction-fixture evidence, 23 October 2026.** This follows the
application's second-tier connection routine, Large `0x42019ce8` / Standard
`0x42019cbc`, through its full 764 decoded instructions. Ghidra's earlier body
stopped after 294 instructions; the remaining branches were recovered with GNU
decoding and checked against each pinned image. No Wi-Fi settings were changed.

## Priority and full scans share five connection attempts

The routine disconnects, requests RAM-only Wi-Fi configuration and reads the
saved station configuration. It performs blocking scans on **channels 1, 6 and
11**, using scan-time fields 80 and 100. It retrieves at most five records from
each scan, collecting at most ten candidates in total. It filters by the desired
SSID, rejects channels above 14 and excludes BSSIDs in its blacklist.

Candidates are sorted by signed RSSI, with **25 added to the score when the AP
uses the saved channel**. Equal scores retain their previous order. For example,
an AP at −60 on the saved channel outranks one at −40 on another channel.
The failover argument clears the saved-channel preference before selection.

Each attempt requests a 4,000 ms wait through the helper described below. After
priority candidates fail, the routine performs a full scan, retrieves at most
ten records into a temporary allocation and filters the same SSID/blacklist.
This stage excludes channels 1, 6 and 11, which were already scanned, and sorts
the remaining candidates with the same score rule.

**The attempt counter is shared across both stages and stops at five.** Four
failed priority attempts leave one full-scan attempt. Five failed priority
attempts leave none, although the full scan and candidate preparation still run.
The fixture checks both boundaries. No candidates, full-scan failure and
allocation failure return `-1`; the inspected exits restore the requested
storage mode to flash.

On ordinary connection success, the routine clears BSSID locking and saves
the winning channel. In failover mode it restores flash storage without that
same configuration write. These are SDK requests, not proof of successful
persistence when the SDK itself returns an error.

## Connection success comes from an asynchronous flag

Helper Large `0x42019c0c` / Standard `0x42019be0` writes the selected BSSID and
channel into a station configuration, requests that configuration, clears the
connection flag and starts connection. The immediate configuration and connect
return values are not checked. It polls the flag in 100 ms increments, with
ten-tick delays in the inspected 100 Hz build.

The timeout comparison precedes the flag check. A synthetic flag change after
the 39th delay succeeds; one after the 40th delay reaches the 4,000 ms timeout
branch, requests disconnect and adds another ten-tick delay. This is a control-
flow boundary, not a measured four-second overall operation deadline: SDK call
duration and scheduling are outside these counters. Even injected immediate
SDK errors do not change the helper's eventual decision when a later synthetic
connection event sets the flag.

The two-entry blacklist predicate is Large `0x42019bd8` / Standard `0x42019bac`;
it compares six-byte BSSIDs against the active count. The separate reset helper
at Large `0x4201d9cc` clears the count, attempt bookkeeping and twelve stored
BSSID bytes. Neither helper establishes that the backend itself is unavailable.

## Implication for a local backend

An emulated API cannot choose a more suitable AP through the poll response.
The existing public-connectivity and time-recovery policies can invoke these
Wi-Fi changes independently of a working local server. The frame may exhaust
its five attempts before reaching another useful channel; a saved-channel
preference is also not the same as choosing the strongest signal.

A future firmware backend-health policy should keep API/time failures separate
from AP selection. This pass identifies the stock behavior and adds no patch.

[Paired evidence and 27 cases per build](wifi-gauge-cases.json) include thirteen
Wi-Fi scenarios and fourteen fuel-gauge scenarios. Seven paired bodies total
1,125 instructions per model; normalized operations and internal branches
match. The cases execute 1,010 distinct sites per build. External SDK behavior,
RF results, physical timing and all concurrent event schedules remain outside
these synthetic cases.

## Background retry has a separate lifetime

The worker is Large `0x4201a580` / Standard `0x4201a554`; its stop helper is
`0x4201a650` / `0x4201a624`. Their 106 instructions match after mapped calls and
data relocation. [Seven cases per build](wifi-retry-cases.json) execute every
selected instruction site with synthetic notification and Wi-Fi outcomes.

The worker first requests a notification wait of 6,000 ticks, nominally
60 seconds, **before** checking whether retry is active or Wi-Fi is connected.
Each retry increments a shared attempt counter, requests AP+station mode if
needed, and reads station configuration. On a successful configuration read it
clears BSSID locking, the BSSID bytes and selected channel, then requests the
modified configuration. A failed configuration read skips that write but still
attempts connection. Mode/configuration/connect errors do not themselves stop
the loop. Another notification wait precedes the next active/connected checks.
Notifications can end waits early, so this is not a guaranteed 60-second cadence.

Stopping clears the shared active flag, notifies the retained task handle when
nonnull and resets the attempt counter. It does **not** wait for the worker to
exit. The worker clears the global handle immediately before deleting itself,
without comparing that handle to its own task identity.

Two instruction schedules expose the ownership consequences:

- Stop returns, then a replacement sets the same active flag before the old
  worker resumes: the old worker can enter another connection attempt.
- The old worker has decided to exit, then a replacement publishes its handle:
  the old worker's unconditional cleanup clears the replacement's global slot.

The replacement publication in these cases is explicitly modeled at call
boundaries; the complete starter and real scheduler are not executed. The
Large reference audit identifies both setup and Wi-Fi-event paths creating the
worker. Both set active before creation and discard its return value. Acquiring
an IP calls the stop helper, so the worker's failure to clear active itself is
not evidence that normal successful connections always leave it set.

A future firmware should own retry through one persistent worker or distinguish
worker generations and acknowledge shutdown. Backend recovery must not infer
that a retry task is alive from its startup log, or that it is gone merely
because stop returned. This is a static design consequence, not a deployed fix.

## Connection-page errors preserve a ranked reason

Large's Wi-Fi event callback stores the latest disconnect reason separately
from a retained ranked reason. Classifier `0x420e2948` assigns these ranks
(lower wins); its Standard counterpart `0x420e2c2c` has matching instructions:

| Rank | Numeric disconnect reasons |
| --- | --- |
| 1 | 15, 202, 203 |
| 2 | 5, 13, 17–20, 201 |
| 3 | 2, 16, 204–207 |
| 4 | 3, 4, 6–8 |
| 5 | Other values |

The retained reason changes only for a **strictly lower** rank. Equal-ranked
later events leave the earlier reason selected. First-tier connection setup
initializes the rank to 10 and both reason words to sentinel 1. `GET /connect`
uses the retained reason, falling back to the latest reason when the retained
value is still 1. Its password/network message therefore need not describe the
last disconnect, and remains a reason-code mapping rather than an independent
credential check. These Wi-Fi diagnostics are distinct from cloud-account
authentication and the captured TLS memory-allocation error.
