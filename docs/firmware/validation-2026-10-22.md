# Static and host validation: 22 October 2026

[Research index](README.md) · [Checklist](research-todo.md)

This continuation uses the same hash-pinned Large 0.2.29 application. It does not
change the running frame, its network routing, accounts or artwork. The deferred
physical cancellation test remains deferred.

## HTTP server and factory diagnostics: H05/S06/E01

The 88-byte server configuration was read directly from the application at
`0x3c13bd98`, then combined with startup writes at `0x4201a69c`. Ghidra exports,
GNU instruction decoding and IDF 5.4.1 source comparison distinguish configured
client capacity from actual handler concurrency. The constant, exports and
bounded decoder are retained in the private research set.

Confirmed statically:

- Seven client slots share a single server task. Its blocking upload, scan and
  proxy handlers can delay other requests; 60-second socket timeouts are not a
  whole-request deadline.
- The 42 registrations occupy a configured 43 slots. Portal errors are ignored,
  account-registration errors abort, and battery/API registration errors can
  leave a partially available server. The already-running path does not retry.
- Server stop waits for the task; application teardown clears the handle even
  if stop fails to send its shutdown message. Neither failure was induced.
- A failed or oversized factory GET query can fall through to entering factory
  mode. This happens before HTML allocation and bypasses LED protection.
- Factory microphone statistics are a separate diagnostic state, not ordinary
  voice-recording activity or a streaming-audio interface. POST success/error
  bodies and stop/task-creation limitations are mapped separately.
- `/api/info` exposes preferences and maintenance dates rather than job state.
  Local timestamps lack an offset, and field/object allocation failures can
  leave a partial JSON snapshot. Factory amplitude is block peak-to-peak.

The [local API contract](local-api.md#server-capacity-and-lifecycle) contains
addresses, field values, response shapes and linked upstream corroboration.
No socket-exhaustion, blocked-handler, allocation-failure, factory-mode or
microphone experiment was performed. H05/S06 remain open for their remaining
schemas, boot states and physical behavior; E01 remains open for the rest of the
incomplete analysis corpus.

Two previously undefined Ghidra entries, Wi-Fi/IP event handler `0x4201ab08`
and factory microphone task `0x4201fca4`, were recovered after independently
checking their entry instructions and bounds. Only the analysis database was
changed; the original firmware bytes remain unchanged.

## Poll parser and error semantics: C02/S03/C08

The IDF v5.4.1 submodule reference pins cJSON to
[`acc76239bee01d8e9c858ae2cab296704e52d916`](https://github.com/DaveGamble/cJSON/tree/acc76239bee01d8e9c858ae2cab296704e52d916),
version 1.7.18. The host fixture compiles that source with a small model of the
recovered Large field-selection branches. It uses actual cJSON parsing, lookup,
type predicates and serialization; it does not execute the Xtensa application.

Compiled on Omarchy with `cc -std=c11 -Wall -Wextra -Werror` and address/undefined
behavior sanitizers. **All 25 cases passed**, with no sanitizer report. Coverage
includes boolean/legacy precedence, missing URLs, case-insensitive and duplicate
keys, non-object roots, trailing text, empty/truncated JSON, numeric versus string
epochs, fractional seconds, settings object/type behavior, verification booleans,
scalar/null `user_settings` and bounded URL copying.

| Private artifact | SHA-256 |
| --- | --- |
| Pinned `cJSON.c` | `75c51de8fa40ac9d7a99319c6330719bd692eb81c0a869265f3d4c682533f9b9` |
| Pinned `cJSON.h` | `0578cc29132912edbc88f83207a8fc76e5db3db0605497e909a9384ef3cc474b` |
| Poll JSON fixture | `470a69bba30bc00e9113071ce24b9c9adcbce548d4e91872a65dea9554276f10` |

Firmware helpers `0x4203962c`, `0x4203953c`, `0x4203966c`, `0x42039100` and the
type predicates were inspected alongside caller branches. GNU checks cover
pending-flag selection, URL copying, signed 64-bit deadline comparison and error
returns. This supports the particular behaviors in the
[poll contract](cloud-protocol.md#field-selection-and-permissive-json-parsing),
not whole-library equivalence or proof of the vendor's unmodified source revision.

Separately, static error-path checks show connection-open error `0x7002`, HTTP
404 and statuses 500 or above returning empty internal success while skipping
settings/deadline updates. HTTP 401/403 return an error, and the worker retries
only EAGAIN once after a one-second delay. No HTTP fault was sent to the frame.

The model omits HTTP accumulation/framing, allocation faults, NVS, the ROM
conversion implementation, callback concurrency, recording interruption and
scheduler execution. Numeric inputs are finite and within signed 64-bit range.
C02/S03/C08 remain open for device behavior and persistence/lifetime cases.

Source inspection also found that HA's current timestamp sensor parser assigns
its default timezone to naive frame timestamps. A frame configured with different
rules therefore needs explicit timezone handling; no integration code was changed.

## Direct OTA failure boundaries: R12

The Large direct updater `0x4202c514` and its HTTP/OTA SDK callees were inspected
in the matching binary. Separate GNU disassembly checked the timer/length loop
and erase-before-magic ordering. Literal reads confirm 30,000 ms transport timeout,
4,096-byte buffers and the 600,000,999 µs post-chunk threshold.

The [OTA contract](ota-and-recovery.md#direct-download-framing-and-failure-boundaries)
now corrects an earlier MIME-filter claim: `0x4206d664` reads request headers,
not response headers. Zero/unknown-length bodies skip downloading and fail SDK
finalization; negative reads do not receive an in-function retry. Sequential-write
mode delays erasure until a write, but the first write can erase inactive-slot
sectors before rejecting a non-ESP first byte. Abort does not restore those bytes.

SDK source corroborates the identified functions; the conclusions are tied to
the recovered application instructions rather than assumed SDK defaults. Private
exports are `ota-download-pass1.txt`, `ota-timeout-length-gnu.txt` and
`ota-first-write-gnu.txt`. No host flash simulator, device update, fault injection,
boot-policy read or rollback test was performed. R12 remains open.

## Album body and transport contract: C12/H05/A05

Large handlers `0x4203042c`, `0x420304b8`, `0x420306c8` and `0x42030790`, body
helper `0x4203051c`, ID extractor `0x4202ff14` and common proxy `0x42030064` were
revisited. The proxy's Ghidra flow stops at unsupported `SALT`; GNU instructions
cover that body-selection branch and the remaining stream/error logic. Separate
decoding at `0x4203039c` and `0x420303d0` avoids padding misalignment in the
older linear export. No firmware bytes or analysis function bodies were patched.

The host fixture uses the same pinned cJSON 1.7.18 source as the poll pass above.
It runs the actual parse, case-insensitive existence/replacement, string addition
and unformatted serialization calls from the recovered body helper. **All 19
cases passed** under address/undefined behavior sanitizers and warnings-as-errors.
They include root types, duplicate/case-varied identity fields, trailing input,
embedded NUL, malformed JSON and post-injection expansion beyond the incoming
4,096-byte cap. The maximum-size test used only a fake key and ordinary text.

Fixture SHA-256: `ae4b3db85b95be1a0965f2fce5d5b715fda87152031c61d9154f275340a4437a`.
Private evidence: `album-json-fixture.c`, `album-json-results.jsonl`,
`album-proxy-pass1.txt`, `album-proxy-pass2.txt`, `album-json-helpers.txt` and
`album-response-tail-gnu.txt`. The [album contract](local-api.md#album-proxy-contract)
records the resulting limits and implementation implications.

No create/update/delete request, duplicate credential, altered URL, forced
allocation failure or transport fault was sent to either frame or vendor cloud.
The fixture omits HTTP framing, NVS, heap failure, backend permissions and device
concurrency. Static proxy observations do not prove a vendor authorization bypass.
C12/H05/A05 remain open for their broader device/design questions.

## Diagnostic retention and access: H05/N05/E01

Static analysis traced log handlers, visibility filtering, the capture hook,
record writer, saved-file reader/writer and clear helper. Capture entry
`0x4202ded8` was missing from Ghidra's function list. GNU verified its prologue,
branch targets and return before an analysis-only script defined it; the app
bytes were not changed. Separate GNU checks confirm the whole-history reset
and unchecked flush writes/close. Literals confirm 65,536-byte history capacity,
2,048-byte current-page fallback and file magic `0x464c4f47`.

The [diagnostics page](diagnostics-and-logs.md) documents these limits. The
redactor's seven-key table and address/email handling were inspected; its
remaining unsupported-instruction branch is not represented as a complete
redaction audit or tested privacy guarantee. Existing raw artifacts stay private.

Private evidence: `log-controls-pass1.txt` through `log-controls-pass3.txt`,
`log-hook-gnu.txt`, `log-ring-reset-gnu.txt`, `log-flush-gnu.txt` and
`DefineLogEntry.java`. No live log requests, clear, cookie bypass, flush, memory
stress or storage corruption were performed in this pass. The open checklist
items retain those runtime and fault-validation requirements.

## Orientation sampling and sensor target: H02/C07/E01

The Large accelerometer initialization, primary/alternative identification,
register reads, classifier, resume/power-down helper and both cloud-facing
callers were traced. GNU checks confirm absolute signed-16-bit X/Y comparison,
landscape on equality, and the alternative probe's shared zero return followed
by the caller's failure branch. A bounded binary table read recovered seven
candidate records; the table is not a list of supported working drivers.

The [hardware trace](hardware-and-layout.md#accelerometer-target-and-orientation-semantics)
ties the LIS2HH12TR software label to address/register literals and manufacturer
documentation. The existing saved Large log reports landscape but supplies no
physical part identification. No new frame read, rotation, sensor fault or
hardware access was performed. No arithmetic-only fixture is claimed as hardware
validation. Private evidence is `orientation-pass1.txt`, `orientation-pass2.txt`,
`orientation-probe-table.json` and the four `orientation-*-gnu.txt` branch exports.
H02 and the broader cloud/compatibility items remain open.

## Standard orientation and album comparison: E02/H02/C12

Both complete app hashes were rechecked before decoding the seven-record sensor
tables. All address/register/expected-value/name fields match; pointer bytes were
resolved independently. Standard initialization, byte reads, classification,
power wrapper and poll/voice call sites match the relevant Large branches.
Separate GNU ranges confirm the alternative probe's zero return, its caller's
failure branch and landscape-on-tie comparison. The physical part remains unknown.

Standard's album body helper and selected cJSON wrappers were also inspected.
Input length, consecutive-timeout handling, absent object-root check, unchecked
key injection and unbounded post-injection serialization match the Large helper.
GNU ranges start at confirmed basic-block entries to avoid decoding padding as
instructions. No device request, new host-parser fixture or sensor experiment
was performed, and the comparison does not claim full binary equivalence.

Private evidence: `standard-orientation-album-pass1.txt`,
`standard-orientation-album-pass2.txt`, `standard-orientation-album-gnu.txt`,
`orientation-table-comparison.json` and `compare-orientation-tables.mjs`.
The public [model map](model-comparison.json) now has 34 function pairs and the
decoded probe-table comparison. The broader checklist items remain open.

## Voice response completeness and timeouts: C05/C07/C08

The Large presign/finalize callers and matching SDK header/body readers were
traced again. GNU confirms their single 4,095-byte read, lack of declared-length
comparison, positive-prefix return on later transport failure, and reuse of the
configured timeout on each transport read. It also distinguishes presign's missing
zero-read buffer initialization from finalize's explicit termination. No undefined
presign-buffer read was executed by the host fixture or sent to the frame.

**Twelve host cases passed** with C11 warnings-as-errors and address/undefined
behavior sanitizers. The fixture extracts seven unchanged functions/callbacks
from ESP-IDF v5.4.1's HTTP client, uses that release's actual HTTP parser, and uses
the same pinned cJSON source as the earlier fixtures. Transport/event/connection
environment is stubbed; fixed-length HTTP messages go through the real parser.
The recovered finalize caller's read-cap, termination and URL-field check are
modeled around those functions. Delays are virtual and do not sleep.

The [voice contract](voice.md#body-completeness-and-timeout-scope) records the
results. This is a selected-source host harness, not an ESP-IDF application or
Xtensa emulator. It omits TLS, sockets, cancellation concurrency, allocation
failure, the 15-minute outer wait and watchdogs. Positive JSON-prefix results do
not establish physical display or a reliable recovery behavior.

Reproducibility SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| HTTP client source, ESP-IDF v5.4.1 | `7aabd415f3a39675e59f591919b9e88e31213e548b010cb0809a888d2b0ceef2` |
| HTTP parser source, same release | `c164edcb06099b026e7ed853ed4d25536e83b4463d5e79921b28621e16588455` |
| Selected unchanged SDK functions | `965c4cf08b3eec4b2cfea18f69b72b189ec007dd60b55af663de55e55aac0e24` |
| Host fixture | `251d40db44b67efe9d3678bf81ad643cf775dad53c3c53f240eed4e87843a5e9` |

Sources: [HTTP client](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c)
and [HTTP parser](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/http_parser/http_parser.c).
Private artifacts include `voice-http-read-pass1.txt`,
`voice-http-boundaries-gnu.txt`, `voice-http-fixture.c`,
`prepare-voice-http-fixture.mjs`, `voice-http-results.jsonl` and
`voice-http-source-hashes.json`. C05/C07/C08 remain open for broader coverage.

## Task-watchdog coverage: D06/E01

Large SDK startup, task add/delete/reset, idle hooks, runtime object references,
timeout ISR/handler and the rendering caller were inspected. GNU verifies the
12-byte zeroed configuration, 5,000 ms literal, idle mask 3, copied false panic
flag, render add/delete call ordering and the timeout handler's returning
non-panic branch. It independently confirms the one-tick power-good loop.

The renderer unsubscribes before power setup and never resubscribes in its
recovered long-operation path. Its add/delete results are ignored. The reference
pass found the render worker and idle-subscription helper calling task add, plus
an I2C initialization helper and idle hook calling reset. This is evidence about
the recovered references, not proof that all dynamic/indirect behavior is known.

The [rendering page](rendering-and-concurrency.md#the-task-watchdog-does-not-bound-the-long-panel-sequence)
now separates those static limits from physical recovery. No watchdog setting,
task subscription or frame operation was changed. No deliberate stall, panic or
reset was induced. Interrupt-watchdog and hardware fallback coverage remain open.
Private evidence: `watchdog-pass1.txt` through `watchdog-pass3.txt`,
`watchdog-boundaries-gnu.txt`, `watchdog-literals.jsonl` and `watchdog-gnu.mjs`.

## Conditioning and elapsed-time selection: H04/D06/S05

Four Large Ghidra/reference passes cover render selection, MIN/MID dispatch,
clear/power helpers, the all-controller chip-select helper, elapsed-time selection
and timestamp writers. GNU checks independently confirm the 288,000-byte malloc,
clear patterns/command, MID's unconditional zero return, caller timestamp update,
64-bit time arguments, 3,600 divisor, 12/48-hour float constants and skip branches.
The disassembler ranges start at verified basic-block entries to avoid padding.

The [rendering trace](rendering-and-concurrency.md#conditioning-adds-full-panel-clear-cycles)
separates full-panel clear cycles from partial-refresh capability. Timestamp
references include sleep preparation and conditioning completion before artwork;
the timestamp commit result is ignored. This invalidates interpreting that key
as exclusively a sleep-entry record or a successful panel acknowledgement.

This was static inspection of the pinned Large app. No panel operation, induced
failure, clock/NVS change, Standard-mode equivalence test or waveform experiment
was performed. H04/D06 remain open. Private evidence: `conditioning-pass1.txt`
through `conditioning-pass4.txt`, `conditioning-boundaries-gnu.txt`,
`conditioning-literals.jsonl` and `conditioning-gnu.mjs`.

## Account response ownership and verification: C01/C11/D01

Two new Ghidra/reference passes extend the earlier HTTP callback exports with
the poll dispatcher, verification-running byte, both task starters and local
form callers. GNU verifies the unverified-only polling exclusion, running-byte
publication after task creation, direct credential formatting, token-substring
exit, per-client backing-memory assignment and selected cleanup/return branches.
Bounded literal reads confirm the fixed poll buffer and JSON format string.

The [cloud contract](cloud-protocol.md#shared-response-ownership-and-verification-guard)
now records the real guard as well as its limitations. No global mutual exclusion
was recovered across account setup, verification and polling. That absence and
stale response pointers support possible failure schedules; they do not establish
an observed use-after-free, memory corruption or reproduction of a setup failure.
No credentials were submitted, pairing changed, duplicate worker started or
physical request made. The owner's actual password was not examined.

Private evidence: `json-ownership-pass1.txt`, `json-ownership-pass2.txt`,
`json-ownership-boundaries-gnu.txt`, `json-ownership-literals.jsonl` and
`json-ownership-gnu.mjs`, alongside `http-redirect-pass5.txt`. These are static
Large findings; no additional host-case count or Standard equivalence is claimed.

## Instruction downloads and task lifetime: C01/D01/D04

Two Ghidra/reference passes cover the metadata client, instruction downloader and
dispatcher, cache/no-cache wrappers, background starter/worker, pending deadline
and display-manager state accessor. Sixteen bounded GNU ranges confirm the
metadata read/rejection/termination branches, shared-memory writes before render
arbitration, cache ordering, heap threshold, task argument copy/free, retry count,
120-second deadline comparison and 9,000-tick completion wait. The low-word
unsigned comparison at `0x4202b3a3` was checked directly because Ghidra had removed
it as unreachable in its decompilation.

The [instruction lifetime trace](rendering-and-concurrency.md#setup-screen-tasks-and-the-two-minute-poll-hold)
distinguishes a poll hold from cancellation or buffer ownership. The metadata
reader accepts nonnegative header results before reading; it does not inherit
voice JSON's positive-length gate. Its empty-read rejection differs from the
presign uninitialized-buffer branch. Those are static distinctions, not new
physical chunked/timeout experiments.

No frame request, pairing change, display update, task-allocation fault or
concurrent producer was exercised. Private evidence: `instruction-lifetime-pass1.txt`,
`instruction-lifetime-pass2.txt`, `instruction-lifetime-boundaries-gnu.txt`,
`instruction-lifetime-literals.jsonl` and `instruction-lifetime-gnu.mjs`, plus
the earlier render-start export in `concurrency-pass3.txt`.

## Onboarding GET contracts and identity cache: H05/N03/C11

Two reference passes and twelve GNU instruction ranges cover the completion/form/
verification/root/captive-page handlers, lazy accessor, default copy and identity
loader. GNU confirms that the loader retains the namespace-open result in its
return register while per-field read errors take fallback branches. It also
confirms initialized-before-load ordering and the unchecked default-save call on
the lazy accessor's open-error path. Bounded literal reads establish empty default
identity strings and the form template without reading any installed credentials.

The [local route contract](local-api.md#onboarding-page-reads-and-local-verification)
and [cache semantics](storage-and-configuration.md#identity-cache-and-read-errors)
separate ordinary cached GET behavior from the conditional first-use fallback.
No live GET, page script, NVS failure or account write was exercised. This does not
claim every status read writes storage, that a transient read necessarily erases
identity, or that a cached verified flag proves current cloud authentication.

Private evidence: `onboarding-reads-pass1.txt`, `onboarding-reads-pass2.txt`,
`onboarding-reads-boundaries-gnu.txt`, `onboarding-reads-literals.jsonl` and
`onboarding-reads-gnu.mjs`. Ghidra's loader `void` prototype is superseded by the
return-register check; no firmware bytes were changed.

## Standard task and conditioning comparison: E02/H04/D01

Three new Standard Ghidra/reference exports and 23 bounded GNU ranges were
compared against the Large instruction/verification/conditioning exports.
The Standard app hash is checked by both the disassembly driver and literal
reader. Eleven corresponding function pairs bring the public map to 45; a mapped
pair identifies corresponding roles, not identical implementations.

GNU confirms Standard's unverified-state branch reaching the poll starter,
one-shot instruction task creation, 120-second stored deadline, 90-second worker
wait, 2,048-byte pattern allocation with a 480,000-byte streaming loop, unconditional
conditioning success, 12/48-hour constants, shared callback append logic and
verification token-substring exit. Reference analysis locates the Standard pending
getter in OTA safety, rather than the poll dispatcher. A 2 KiB clear-buffer idea
for Large remains a proposal; no code was ported or flashed.

The [comparison](standard-model-comparison.md#polling-instruction-tasks-and-conditioning-differ)
separates version/model differences from the observed Standard TLS-memory error.
No new device, timing, memory-pressure, conditioning or concurrency test was run.
Private Standard artifacts: `standard-instruction-pass1.txt` through
`standard-instruction-pass3.txt`, `standard-instruction-boundaries-gnu.txt`,
`standard-instruction-literals.jsonl`, `standard-instruction-gnu.mjs` and
`read-standard-values.mjs`.

## Maintenance refresh and history: D04/D07/D08/S05/E02

Two Large reference exports, the existing Standard conditioning export and
29 bounded GNU ranges cover the refresh/restore helpers, manager state transitions,
ready waiter, default timeouts, saved-image fallback and scheduled history call.
Both app hashes are checked before disassembly. Bounded literal reads distinguish
the Standard 6,000-tick maintenance wait from Large's 9,000 ticks; the earlier
90-second Standard instruction-task wait is a different caller.

The [maintenance trace](rendering-and-concurrency.md#maintenance-refresh-has-separate-completion-rules)
documents dropped work translated to success, the unwaited Large fallback and the
blank branch's busy-before-ready-wait ordering. The 30-second self-wait consequence
assumes successful state operations and no concurrent writer, not every runtime
schedule. GNU also confirms that scheduled maintenance discards the helper result
before appending history and requesting the default schedule. Ghidra's merged
pre-sleep/maintenance boundary and incomplete wrapper decompilation were not used
as sole evidence for those conclusions.

The model map now contains 46 corresponding function pairs. No new frame request,
refresh, state fault, history write, flash or hardware experiment was performed;
D04/D07/D08/S05 retain their physical validation requirements. Private artifacts:
`maintenance-render-pass1.txt`, `maintenance-render-pass2.txt`,
`maintenance-render-gnu.mjs`, `maintenance-render-boundaries-gnu.txt` and
`maintenance-render-literals.jsonl`, plus the latter two names under `small-frame/`
for Standard and `small-frame/standard-instruction-pass1.txt`.

## Embedded setup pages: C01/C11/H05

The hash-checked extractor follows literal pointers from the GET and successful
POST handlers and saves eight selected page assemblies plus their script blocks.
Dynamic owner email, status and dashboard URL fragments are omitted; assembly
hashes identify these research artifacts, not exact runtime HTTP responses.
The Wi-Fi and Get Started assets use their recovered start/end lengths.

Seven host cases run the unchanged extracted scripts in a JavaScript VM with
stubbed DOM, fetch and timers. They cover delayed verification polling, redirect
despite an HTTP error status, overlapping checks and rejection handling, immediate/
periodic battery requests, both encoded form submissions and HTML error-body
insertion, and create-account confirmation logic. All seven passed; zero actual
network requests were performed. The fixture does not emulate the firmware or
validate browser HTML parsing, navigation, password-manager behavior or storage.

The [route/script map](local-api.md#embedded-setup-scripts-use-local-routes)
distinguishes device-side authentication from browser-local requests and user
navigation. There was no frame access, password submission, pairing change or
external-dashboard request. Private evidence: `embedded-pages-pass1.txt`,
`extract-embedded-pages.mjs`, `embedded-page-fixture.mjs`, and
`embedded-pages/manifest.json`, extracted HTML/scripts and `host-results.json`.

## Account form parsing: C11/H05

One reference export and eleven bounded GNU ranges cover both account handlers,
the URL-value decoder, SDK field lookup and request receiver. The binary confirms
the single 511-byte receive call, 128-byte encoded temporary buffers, conditional
decode only after lookup success, and truncation constant `0xb004`. The timezone
copy path differs from email/password decoding. The stock HTML's 19 timezone
values were inspected separately; custom-rule encoding was not tried on-device.

Thirteen host cases use the unchanged IDF v5.4.1 `httpd_query_key_value` function
and a reconstruction of application decode/returned-prefix handling. C11 builds
with `-Wall -Wextra -Werror`, AddressSanitizer and UndefinedBehaviorSanitizer pass
all cases. The fixture supplies a receive prefix; it does not execute the actual
receiver, browser constraints, vendor authentication or persistence. The SDK
receive source and binary support the possibility of a short positive read,
without claiming a physical fragmented-request reproduction.

Private artifacts: `form-parser-pass1.txt`, `form-parser-boundaries-gnu.txt`,
`form-parser-literals.jsonl`, `form-parser-gnu.mjs`, `form-parser-fixture.c`,
`prepare-form-parser-fixture.mjs` and `form-parser-fixture/`. The SDK source is
hash-pinned to `5c9da08c9bb502d25269bcb059017b553ae2fe4880216a1e6c6e4c664d6e1fbd`;
the unchanged extracted helper hash is
`633c3df2b90f8c0dbd411edcfa9a7f8b6ab08ea02a7d75e68abfde4153d30a9c`.
No credentials or crafted forms were sent anywhere and no identity was changed.

## Multipart upload streaming: C05/C08/D01

Nineteen bounded GNU ranges recover multipart construction and transmission past
the point where the older Ghidra export stopped on unsupported `SALTU` handling.
The earlier export remains useful for references and initial field iteration,
but it does not describe the complete upload function. Literal reads confirm
the form templates, audio MIME type, 120,000 ms timeout, 8,192-byte transmit-buffer
value and 4,096-byte application chunk size. SDK-write ranges are split at padding
and the following function boundary.

The [streaming trace](voice.md#multipart-construction-and-streaming) records
framing-only PSRAM allocation, bounded-format failure checks, complete-count
checks on each application write, repeated transport timeout and abort-manager
registration after the footer. Presign's existing export supplies object/type and
URL/key-copy boundaries. No new field variant, partial upload, cancellation,
allocation failure, recording or network request was sent to a frame.

Private artifacts: `voice-multipart-gnu.mjs`,
`voice-multipart-boundaries-gnu.txt`, `voice-multipart-literals.jsonl`,
`http-redirect-pass3.txt` and `voice-http-read-pass1.txt`.
`voice-multipart-exploratory-gnu.txt` contains misaligned exploratory ranges and
is superseded by the bounded export for the consequential branches.
