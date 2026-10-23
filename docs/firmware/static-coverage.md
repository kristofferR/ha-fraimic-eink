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
| Model-specific initialization and excluded allocators/drivers | Complete for the selected application helpers and driver boundaries | [Helper and driver audit](initialization-helpers.md): ten initial roots, Large PMIC/expander/SPI and both LED initializers; [38 additional driver cases](driver-initialization-cases.json); SDK/peripheral outcomes remain explicit boundaries |
| Application function and callback coverage census | Complete for the stated inventory | [Function ledger](static-function-census.json): 481 Large / 455 Standard main-region entries, plus eight outliers each; all 64 entries per region lacking a direct caller have identified pointer-word uses |
| Application gaps selected from that census | Complete for the stated questions | [Wi-Fi selection and retry-worker ownership](wifi-recovery.md), [fuel-gauge policy](fuel-gauge.md), [52 battery-policy cases](battery-policy-cases.json), [130 Large helper roles](application-helpers.md), and the data/call audits below |

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
newer CFG JSON format is not automatically unexamined. This pass reconciles its
selected application boundaries; no whole-firmware coverage percentage is claimed.

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
main region. The subsequent call audit below also resolves each main-region
`callx8` through its adjacent literal load. Exact pointer-word uses cover tasks,
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
short ASCII string occurrences are model/version/build identifiers and the
90/180-second render-timeout message. The data follow-up below finds seven more
changed string occurrences excluded by that initial text filter. Relocated
tables and external callee bodies require their own evidence; matching shape
alone does not establish their equivalence.

### Embedded data follow-up

The [data comparison](static-data-comparison.json) classifies all 443 unique
address pairs / 478 occurrences initially labelled data pointers by the shape
comparison. Of those, 371 pairs / 388 occurrences are NUL-terminated text,
including long pages and Unicode logs. Six pairs / seven occurrences differ:
upload-page size checks, the factory page, a model-size response string and
three render-error log decorations. Together with the initial sixteen short
ASCII occurrences, this makes **23 changed string occurrences in the selected
shape pairs**, not in the entire firmware.

The other 72 pairs / 90 occurrences are bounded tables, empty defaults or asset
boundaries. Comparing their actual consumer-defined extents establishes:

- All 42 URI descriptors retain the same path, method and user context. Handler
  addresses remain references, with the separate
  [handler comparison](local-handler-comparison.json) supplying its stated evidence.
- Resolved SNTP names, account-response member names, instruction names and
  descriptions, event-base names and seven sensor-probe records match.
- The 88-byte HTTP defaults, 263-byte identity defaults, 24-byte factory GPIO
  template, 984-byte LED table, 256-byte character-classification table,
  diagnostic-redaction tables and 132-byte Wi-Fi summary defaults match within
  those extents. The encoded authentication arrays also match; their values
  and per-object hashes remain private.
- The firmware-identification template and voltage thresholds differ as
  expected. The nine voltage-table percentage values and padding match, while
  the millivolt thresholds differ. No physical calibration follows from this.
- Six pointers identify asset starts/ends. Bytes after an asset end are not
  compared as if they belonged to that asset; the existing asset audits apply.

This replaces exploratory 64-byte previews with bounded comparisons. It does
not establish equivalence of all image data or all functions using these tables.

### Direct and literal-indirect call boundaries

The [call ledger](static-call-boundaries.json) examines every recovered call in
the two main regions. Large has 3,206 `call8` and 5,310 `callx8` sites; Standard
has 3,067 and 5,134. Every `callx8` immediately follows a matching `l32r` with a
constant target, with no recovered branch/loop targeting the call to bypass
that load. There are no other call instruction forms or `jx` register jumps in
these selected CFGs. Thus **no main-region call target remains unresolved by
this census**. This is a static instruction result, not a proof against runtime
corruption or arbitrary entry into the middle of code.

The literal calls reach 124 distinct targets on Large and 123 on Standard,
including the eight outlying application helpers each. Direct calls reach
163 / 164 distinct targets outside the corresponding main region. The ledger
keeps these destinations explicit: identifying an SDK/ROM entry is not a
recursive analysis of its body, its callbacks or hardware behavior.

All 1,359 Large / 1,300 Standard references found by the selected vendor-tag and
`./main/` source-path scan lie in the reconciled CFGs. This closes those anchor
gaps, including the Large workers originally missing from Ghidra's function
index. Tag matching is a heuristic and cannot prove that no untagged vendor
function exists elsewhere.

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
- [x] Classify the remaining shape-paired data references using actual object extents.
- [x] Resolve all call targets in the selected main regions and reconcile vendor anchors.
- [x] Check Wi-Fi retry stop/replacement ownership and disconnect-reason precedence.
- [x] Finish the selected dependency/state-lifetime questions: microphone producer, initialization latches, Wi-Fi retries and model-specific gauge/presentation paths.
- [x] Reconcile final static limits against the original research checklist.

## Final boundary of this pass

The supplemental checklist is complete for the two pinned application images.
That closes the selected questions, **not a proof that every possible static
question about the firmware has been exhausted**. In particular, a function
role, a complete CFG and a tested branch are three different levels of evidence.

The seven new instruction suites record **253 passing modeled scenarios**:

| Suite | Large | Standard |
| --- | --- | --- |
| [Microphone producer](microphone-producer-cases.json) | 15 | 15 |
| [Microphone interrupt/start-stop](microphone-interrupt-cases.json) | 13 | 13 |
| [Initializers](initializer-cases.json) | 18 | 21 |
| [Additional drivers](driver-initialization-cases.json) | 32 | 6 |
| [Wi-Fi selection and gauge](wifi-gauge-cases.json) | 27 | 27 |
| [Battery presentation and voltage](battery-policy-cases.json) | 24 | 28 |
| [Wi-Fi retry lifetime](wifi-retry-cases.json) | 7 | 7 |
| Total | 136 | 117 |

These interpret selected original instructions with explicitly modeled memory,
SDK results and interleavings. They are not 253 physical experiments, a complete
ESP32 emulator or a claim that all instructions in the application were tested.

There are 279 distinct call destinations per build outside the main region and
the eight identified application outliers. These include SDK, ROM and library
code. Selected consequential bodies already have detailed audits in the topic
pages, but this pass does not claim recursive analysis or model equivalence of
all 279. Their explicit addresses remain in the call ledger for a future concrete
question. The original E01/E02 evidence-discipline items remain ongoing.

The final documentation sweep reconciled the remaining unknowns with their
owning checklist items:

| Remaining question | Why these app images do not settle it |
| --- | --- |
| Installed secure boot, eFuses, full flash layout, custom-image acceptance and recovery | Requires installed-state/recovery evidence, not another application-only disassembly; R01–R12 retain their individual states |
| Real cancellation, race frequency, stale pixels, dropped audio, failed initialization and heap pressure | Static paths and synthetic schedules establish possibilities; physical outcomes remain C08/D04–D06/H03 and related device criteria |
| WAN-free cold boot, local time and independent enrollment | Stock dependencies and parser contracts are traced; actual cold-start/provisioning behavior remains C11/S01/S02 and their device criteria |
| Durable local backend, HA jobs, prompt history and artwork reuse | Protocol and reuse research is complete for its stated contract; A02–A04 require implementation |
| Physical sensor identity, battery calibration, panel requirements and alternative waveforms | Compiled targets/policies do not establish fitted parts or analog behavior; H01–H06 and S07 retain their states |
| Future vendor trust changes, indefinite gallery retention or the vendor's final AI prompt | Future/server-side behavior is not recoverable from these fixed client applications |
| R12 outer OTA host cases, N04 disposable-filesystem suite and A07 provider selection | Explicitly deferred by the owner; this pass does not silently reopen them |

### Consequences for the local-backend design

The extra analysis reinforces a shared stock-protocol adapter with separate
model renderers. It does not reveal a stock setting that replaces the hardcoded
API origin or eliminates the public reachability/time dependencies.

For a later custom-firmware effort, the most useful findings are concrete:
give asynchronous workers explicit ownership and shutdown acknowledgement;
surface microphone overflow/error and measurement-validity information;
separate resource allocation from actual component readiness; and emit
content-specific render acknowledgements. Backend/UI code should already keep
job state distinct from LED state, generic success logs and displayed battery
percentage. These are design consequences, not implemented changes.

Physical recording/cancellation, recovery, flashing, installed eFuses/partitions,
provider selection and implementation remain separate. This pass does not turn
their unchecked criteria into completed static results.
