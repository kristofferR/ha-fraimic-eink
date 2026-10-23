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
| Model-specific initialization and excluded allocators/drivers | In progress | [Helper and driver audit](initialization-helpers.md): ten initial roots, Large PMIC/expander/SPI and both LED initializers; [38 additional driver cases](driver-initialization-cases.json); continue dependencies found by the census |
| Application function and callback coverage census | Main regions and eight outlying helpers reconciled per build; dependency review continues | [Function ledger](static-function-census.json): 481 Large / 455 Standard main-region entries, plus eight outliers each; all 64 entries per region lacking a direct caller have identified pointer-word uses |
| Remaining reachable application gaps found by that census | In progress | [Wi-Fi selection/budget](wifi-recovery.md), [fuel-gauge acceptance and model-specific presentation/error policy](fuel-gauge.md), [52 battery-policy cases](battery-policy-cases.json), and [130 Large helper roles](application-helpers.md) now audited; continue model/callback reconciliation |

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

## Reconciled function inventory

The [machine-readable census](static-function-census.json) records these bounded
results, with per-function instruction counts and hashes of private CFG exports:

| Inventory | Large | Standard |
| --- | --- | --- |
| Main candidate region | `0x4200f770`–`0x42031e78`, end exclusive | `0x4200f6c4`–`0x4203093c`, end exclusive |
| Canonical entries in that region | 481 | 455 |
| Byte-checked reachable instruction sites | 52,049 | 50,116 |
| Entries without a direct caller inside the region | 64 | 64 |
| Those entries with an initialized pointer word and identified use | 64 | 64 |
| Separately recovered outlying application helpers | 8 | 8 |
| Instructions in those eight helpers | 206 | 206 |

No recovered direct call targets an unclassified interior address in either
main region. That statement covers direct `call8` instructions; it is not a
solution for every computed `callx8` target. Exact pointer-word uses cover tasks,
callbacks and registration helpers that a direct-call-only index would miss.
They establish references, not that every callback runs on every boot.

The raw prologue scan found five additional Large entries: maintenance sleep,
DNS, Wi-Fi retry, recording and temporary red-LED workers. Other apparent Large
prologues were five matches inside existing instructions. Standard's 24
empty/fragment index entries resolve to two actual entries, eight interior
instruction boundaries and fourteen interior bytes. Seven apparent Standard
prologues were instruction-interior matches. None remains an unexplained gap in
this selected-region reconciliation. Several repaired entries were already
documented in earlier passes; this is an index correction, not five new features.

The outliers include Wi-Fi reason classification and scan escaping, LED
classifiers, instruction-type and SHA-character predicates, a zero-return log
filter and a label-taking power-transition hook compiled to entry/return.
Their instructions match between builds after relative branch relocation.
Ghidra truncated the instruction and SHA predicates; GNU recovers seven and 26
instructions respectively. These helpers demonstrate why the main region alone
cannot be described as all vendor code.

### Shape matching is a research aid

The main-region comparison finds 354 uniquely paired instruction shapes,
46 ambiguous Large entries and 81 Large / 55 Standard entries without a matching
shape. Literal addresses and direct call destinations are masked for this
search, so these are **candidate relationships**, not 354 equivalence proofs.

A follow-up compared 9,122 literal-load occurrences in the unique pairs. There
are 37 changed scalar occurrences: seven panel-size values, one render-wait
budget, five log capacities, seventeen error-check source-line numbers, four
image-cache bounds and three voltage-policy thresholds. The sixteen changed
string occurrences are model/version/build identifiers and the 90/180-second
render-timeout message. These differences agree with the detailed model work;
relocated data tables and external callee bodies still require their own evidence.

The voltage-policy thresholds add a useful qualification: the fallback
percentage helper saturates at 100 from 8,400 mV on Large and 4,200 mV on
Standard, and at zero through 6,000 / 3,300 mV respectively. The settled-trend
classifier uses 8,200 / 4,100 mV as its high-voltage threshold. These are compiled
policy constants, not validated battery calibration or replacements for the
separate OTA preflight calculation.

### Supplemental checklist

- [x] Recover full microphone producer and interrupt paths, with bounded cases.
- [x] Analyze the initial selected manager/allocator roots and model differences.
- [x] Follow Large PMIC, expander, SPI and both LED initializer failure paths.
- [x] Reconcile the main candidate regions, false prologues and nonreturning boundaries.
- [x] Check function-pointer references for all 64 roots per build lacking direct callers.
- [x] Recover and compare eight identified outlying application helpers per build.
- [x] Audit changed scalar/string literals in the 354 unique shape candidates.
- [x] Compare the model-specific battery summary and voltage-reader error policies.
- [ ] Finish the remaining dependency/state-lifetime questions exposed by this pass.
- [ ] Reconcile final static limits against the original research checklist.

Physical recording/cancellation, recovery, flashing, installed eFuses/partitions,
provider selection and implementation remain separate. This pass does not turn
their unchecked criteria into completed static results.
