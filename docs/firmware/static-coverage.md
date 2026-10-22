# Static research coverage and remaining work

[Research index](README.md) · [Original checklist](research-todo.md)

On 23 October the owner requested the remaining microphone producer,
model-specific initialization and application-coverage work. This ledger tracks
that supplemental static scope. The original checklist's status counts describe
its 67 original questions; **zero original items labelled Research does not mean
the firmware has been exhaustively analyzed**.

## Current pass

| Work | State | Evidence / next boundary |
| --- | --- | --- |
| Microphone DMA sizing, ring, receive callback, overflow and buffer lifetime | Complete for the stated boundaries | [Producer analysis](microphone-dma.md), [15 cases per build](microphone-producer-cases.json) |
| GDMA interrupt dispatch and error-handler path | Complete for the stated boundaries | [EOF flags, callback masks and hardware start wait](microphone-dma.md#interrupt-flags-do-not-reach-the-saved-recording), [13 cases per build](microphone-interrupt-cases.json) |
| Model-specific initialization and excluded allocators/drivers | In progress | [First ten-root audit](initialization-helpers.md): portal/display/connectivity/I2C/instruction/config/abort, PSRAM, microphone and battery boundaries; continue remaining driver dependencies |
| Application function and callback coverage census | In progress | Reconcile fresh Ghidra entries, byte-checked CFGs, earlier disassembly and documented roles; prioritize actual gaps |
| Remaining reachable application gaps found by that census | Pending | Name each bounded question and its evidence before closing it |

## What the census can establish

The original function index was limited to `0x42010000`–`0x42032000` and a
separate fixed string range. It was an exploratory index, not a complete vendor
function list. Fresh Ghidra exports identify 6,884 functions/fragments in Large
and 7,519 in Standard across the imported application images. These totals
include SDK code and differences in Ghidra's analysis; they do not imply that
Standard has more vendor features.

The census must keep these evidence classes separate:

- A decoded/exported function is available to inspect.
- A byte-checked CFG establishes the selected instruction and branch boundaries.
- A documented role or call reference establishes only the claim actually traced.
- An instruction fixture checks specified branches under its explicit models.
- A recovered direct-call graph omits unresolved indirect calls and incorrectly
  split or undiscovered functions.

Address mentions, exported disassembly and a high count of passing cases are
not substitutes for semantic analysis. Conversely, an older pass without the
newer CFG JSON format is not automatically unexamined. The reconciliation is
still running; no whole-firmware coverage percentage is claimed.

Physical recording/cancellation, recovery, flashing, installed eFuses/partitions,
provider selection and implementation remain separate. This pass does not turn
their unchecked criteria into completed static results.
