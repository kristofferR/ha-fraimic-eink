# Static and host validation: 22 October 2026

This is a chronological evidence record. Later results can supersede an earlier
“remains open” statement. Use the [reconciled checklist](research-todo.md#current-status)
for current completion and remaining criteria; C05, C10, R11 and E03 were closed
against their original bounded scope after these passes.

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

## Connectivity cache and fallback DNS: S01/C01/C11

Four Ghidra passes and nineteen bounded GNU ranges trace the monitor lifecycle,
station notifications, fallback AP and DNS service. The DNS entry `0x420199b0`
was independently identified from its task-function pointer and GNU entry/loop,
then defined only in the read-only analysis session. The resulting export covers
the complete receive/reply loop and socket/bind-failure exits. Firmware hashes
remain unchanged.

The [offline follow-up](boot-and-scheduling.md#reachability-cache-and-monitor-lifecycle)
distinguishes cached reachability from station state, initial optimistic health,
first-time-user suppression, non-joining monitor stop and handle-gated restart.
The first-time-user flag was checked against its setter and is not the separate
factory-test flag.

Fallback's AP configuration precedes its mode change, unlike ordinary setup;
return values are ignored. The SDK API contract supplies an interface-enabled
requirement, but actual AP configuration/failure has not been observed. The
recovered `esp_wifi_set_config` wrapper dispatches the request internally; this
pass does not claim a complete trace of the driver's final configuration handler.

DNS binds wildcard IPv4 UDP port 53 and constructs fixed `192.168.4.1` answers.
The loop has no shutdown path after a successful bind; AP-disable does not close
its socket. Initial setup discards the task handle, while fallback's saved handle
is not cleared by worker error exits. Remaining LAN reachability, bind conflicts,
retry suppression and actual cleanup across Wi-Fi stop/deep sleep are untested.
No live DNS queries, frame HTTP reads, AP changes or routing changes were made.

Private artifacts: `offline-fallback-pass1.txt` through
`offline-fallback-pass4.txt`, `offline-fallback-gnu.mjs`,
`offline-fallback-boundaries-gnu.txt` and `offline-fallback-literals.jsonl`.
The bounded export supersedes `offline-dns-exploratory-gnu.txt` for final evidence.

## HTTP configuration audit: C01/C03/D01/R11

Forty-seven bounded GNU ranges cross-check configuration construction for ten
current consumers and the older manifest updater, plus the SDK config mapper,
constructor and URL setter. Literal reads establish timeouts and buffer sizes.
Existing Ghidra exports supply the surrounding application control flow.

The [configuration table](cloud-protocol.md#http-buffers-trust-precedence-and-url-scheme)
separates HTTP RX/TX allocations from application response arrays. It corrects
the earlier system-metadata description: that client's 4,096-byte field is TX;
RX is zero in config and becomes the binary's 512-byte SDK default. Image download
and direct OTA really set both RX and TX to 4,096 bytes.

The SDK constructor checks the bundle callback before the global-CA flag, so the
earlier wording that a set flag enables that store alongside the bundle was too
broad. Ten current consumers use the bundle branch; the older updater supplies
neither bundle nor global/explicit CA in its config. URL parsing can override the
configured transport's default scheme. None of these static findings supersedes
the earlier physical hostname/trust controls or demonstrates an untested TLS
consumer's acceptance behavior.

Private artifacts: `http-config-gnu.mjs`, `http-config-boundaries-gnu.txt`,
`http-config-literals.jsonl`, `http-redirect-pass5.txt`,
`voice-http-read-pass1.txt`, `ota-download-pass1.txt` and the multipart export.
No device request, certificate installation, network change or firmware update
was performed. No new host fixture was needed for these config-store corrections.

## SPI staging and shared driver state: D01/D03/D06

Three focused Ghidra exports and 32 bounded GNU ranges across 17 functions
cross-check the application transfer/select helpers, bus initialization, SDK
queue, DMA staging, completion cleanup and blocking wrapper. Literal reads
establish the direct-DMA address range, 10 MHz request, 4,800-byte chunk size and
shared globals. The compiled bus initializer supplies four-byte DMA alignment.

The [transfer follow-up](rendering-and-concurrency.md#dma-staging-protects-only-the-current-chunk)
distinguishes a copied current chunk from unsent shared pixels. It also traces
original-descriptor references through SDK completion, the two logical device
handles, manual select/DC operations, low-byte error truncation and later-error
overwrite. No new full-image snapshot, private per-call application descriptor
or finite wrapper deadline was found in these paths. This is not a complete
interrupt/HAL or higher-level exclusion audit, nor a physical concurrency test.

Private artifacts: `spi-lifetime-pass1.txt` through `spi-lifetime-pass3.txt`,
`spi-lifetime-gnu.mjs`, `spi-lifetime-boundaries-gnu.txt`,
`spi-lifetime-literals.jsonl`, `spi-dma-literals.jsonl` and the earlier
`checklist-pass7.txt`. No frame request, image change, hardware fault, modified
firmware execution or routing change was performed. D03 remains open for measured
memory/fragmentation and design evaluation; D01/D06 retain their broader scope.

## Shutdown ordering and wake setup: S06/D01/D06

Four focused Ghidra passes and 35 bounded GNU ranges across 15 functions trace
ordinary/storage sleep, service stops, panel shutdown, state mutexes, BUSY polling,
power-off and the final wake-source call. The pre-sleep export incorrectly merges
code after its nonreturning deep-sleep call with the next maintenance function;
the consequential GNU range stops at `0x420126f6`. No conclusion uses the spurious
decompiled continuation. The EXT1 wrapper is also checked in GNU past Ghidra's
unsupported `SALTU`, with the final error block disassembled at its real boundary.

The [shutdown follow-up](boot-and-scheduling.md#display-shutdown-suppresses-its-own-failure-evidence)
establishes ignored BUSY results, unconditional power-wrapper success and the
absence of another force-off operation in the caller's timeout-log branch.
The default 30,000 ms polling budget was read from configuration constructor
`0x42028204`. It is not a bound on all hardware/service cleanup. No overlap,
shutdown failure, battery experiment, sleep request or wake-source change was
performed on a frame.

Private artifacts: `sleep-lifecycle-pass1.txt` through
`sleep-lifecycle-pass4.txt`, `sleep-lifecycle-gnu.mjs`,
`sleep-lifecycle-boundaries-gnu.txt`, `sleep-lifecycle-literals.jsonl`,
`sleep-config-literals.jsonl` and prior `concurrency-pass4.txt`.
The fourth pass inspects an additional network cleanup callee without claiming
complete SDK resource-lifetime coverage. Hardware state and late-worker effects
remain open despite the statically recovered success logs.

## App-side rollback and metadata: R02/R05/R09

Three Ghidra passes and 40 bounded GNU ranges across 17 entries/call sites trace
NEW-state selection, confirmation, alternate-image checks, invalidation/restart,
state lookup and the application's health-failure return. Literal targets resolve
the NEW-state helper, record selector, CRC primitive and `0x1505` rollback error.
The metadata rewriter and record-invalid predicate are checked past truncated or
misaligned exploratory disassembly at their actual branch boundaries.

The [rollback follow-up](ota-and-recovery.md#app-side-confirmation-is-real-but-is-not-a-recovery-guarantee)
separates app-compiled support from unknown installed bootloader/eFuse state.
The selected app-side branches lack the SDK's optional secure-version checks/
confirmation update; this is not evidence that the physical unit accepts arbitrary
downgrades. The health caller discards a failed rollback request, and its counter
increments before the attempt. Initialization confirms before its Wi-Fi start.
No app was executed, flashed, invalidated, confirmed or rebooted by this pass.

Private artifacts: `rollback-selection-pass1.txt` through
`rollback-selection-pass3.txt`, `rollback-selection-gnu.mjs`,
`rollback-selection-boundaries-gnu.txt` and `rollback-literals.jsonl`.
The metadata trace describes code and record format, not a dump of actual OTA
records or a backup of either installed slot. No new host fixture was needed.

## Standard voice and buffer ownership: E02/D01/C05/C07

Two Standard Ghidra passes, its earlier renderer/instruction exports, and 67
bounded GNU ranges across 13 entries/call sites trace the allocator, accessors,
recording start/WAV header, startup display pointer and voice transport worker.
Literal reads are pinned to the Standard app hash. The presign branch at
`0x420253e4` crosses a spurious synthetic-ELF symbol boundary; GNU `-D` decodes
the actual three-byte conditional instruction, rather than treating its last
byte as a separate function. Uploader blocks were checked at this build's actual
branch targets, including its final status/return branches.

The [model comparison](standard-model-comparison.md#separate-recording-and-image-allocations)
records separate 2,120,000-byte audio and 1,048,576-byte image allocations, the
display alias and the distinct 960,000-byte voice-download/panel limit. The same
pass checks empty upload acknowledgment, post-body abort registration, 4 KiB WAV
writes, the 120/600-second transport settings, single 4,095-byte JSON reads and
the synchronous finalize worker. It does not promote the earlier Large host
fixtures into Standard execution evidence or establish full SDK equivalence.

Private artifacts: `small-frame/standard-voice-lifetime-pass1.txt`,
`standard-voice-lifetime-pass2.txt`, `standard-voice-gnu.mjs`,
`standard-voice-boundaries-gnu.txt`, `standard-voice-literals.jsonl` and earlier
`standard-instruction-pass2.txt`. Model metadata now maps 54 function pairs.
No frame request, recording, image change or firmware execution occurred.

## HA pull-asset reuse and cache boundaries: A03/A05

Six isolated checks passed on Omarchy against the real library, parameter
resolver, model and converter. Integration source still matches
[`e5450665`](https://github.com/kristofferR/ha-fraimic-eink/commit/e5450665ddbb57c2542c883375ba68c0aefbb1b1).
The fixture supplies synthetic PNGs, temporary library storage and minimal HA
imports/executor support. It loads the actual resolver from `helpers.py`, while
the entry's runtime raises on any attribute access and the send helper raises
if called. This extends the earlier experiment's pre-resolved parameters.

Four cases cover Standard/Large at mount rotations 0/90, exact packed lengths,
palette nibbles, original retention and preview dimensions. Each reuses its cache
under all three delivery-mode option values with the converter forbidden.
Two more cases damage only temporary cached panel files: 17-byte truncation and
an invalid `0x44` byte in an otherwise full-length buffer. Both return unchanged
as cache hits, retaining the previous preview and untouched original.

The initial fixture expected larger/swapped preview bounds. Inspection of
`_indices_to_png` showed rotation precedes a thumbnail into the unchanged half
native-size box; corrected expectations match that implementation. The final
result was **6 passed in 8.40 seconds**. No product change was needed for this
expectation correction, and no cache validation fix was implemented.

Separate source inspection traces the existing send helpers, overlay composition,
Hybrid transport guard, vendor art/wake album methods and external-upload count/
hold transitions. These are not executed concurrency, account or overlay tests.
They identify the adapter's missing delivery-state integration and distinguish
asset publication from confirmed display.

Private artifacts: `test_pull_asset_reuse.py`, `pull-asset-reuse-results.txt` and
`pull-asset-reuse-source-hashes.txt`. Reproduce with the repository's
`test_library_manager` fixture on `PYTHONPATH`, using `uv run --with pillow
--with numpy --with pytest --with voluptuous --with resvg_py pytest` and the
research file. No live HA storage, device, vendor endpoint or paid model was used.

## Status RLE and marker ordering: N08/D01/D07

A new Ghidra/reference pass and 18 bounded GNU ranges across six functions trace
the decoder, show/restore wrappers and NVS marker helpers. Literal reads confirm
the 2,304,000-byte capacity threshold, 288,000-byte controller stride and marker
global. The packing instructions use unsigned byte loads, a four-bit shift, OR
and byte store, with no colour masking or validation.

The reconstructed C decoder passed **16 cases** with AddressSanitizer and
UndefinedBehaviorSanitizer, including exact output, unused trailing pairs, odd/
empty/truncated input, zero/overlong runs, odd-run pairing, invalid colours,
high-bit contamination, null arguments and insufficient capacity. The exhausted
input case checks that earlier output remains modified while the length sentinel
remains unchanged. Guard bytes after the output stayed intact in the cases run.

The final case decodes the hash-pinned embedded vendor asset and reproduces the
previous output SHA-256:
`a1db1ecf37389628588baf3c2d44912318087759eb55558dfaa4b834236721be`.
The compressed asset SHA-256 is
`2ffaf8238d0bd202019be6318057d5812effaab440edf419b01b656bf0363278`.
No artwork bytes are published. These host cases exercise the recovered algorithm,
not native firmware execution or panel behavior.

Static wrapper checks separately establish decoding/loading before DROP, drop
converted to success, marker changes at render acceptance, clearing after failed
cache load, and unreported NVS commit failure. Neither a marker nor the wrapper's
success is a physical display acknowledgment. No frame request, battery-state
change, asset installation or reset occurred.

Private artifacts: `status-rle-pass1.txt`, `status-rle-gnu.mjs`,
`status-rle-boundaries-gnu.txt`, `status-rle-literals.jsonl`,
`status-rle-fixture.c`, `status-rle-fixture-results.txt`,
`status-rle-fixture-hashes.txt` and `extract-status-rle.mjs`.

## Wi-Fi forms and scan escaping: H05/N03

Two Ghidra passes and 18 bounded GNU ranges across six functions trace `/connect`,
`/scan.json`, their decoding/escaping helpers and background-retry cancellation.
Literal targets establish the substring keys and scan JSON format; instruction
checks establish the final 31/63-byte copies, pre-read cancellation and station
authentication-threshold write. The latter's field/value interpretation uses the
[versioned SDK type definition](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_wifi/include/esp_wifi_types_generic.h).

The reconstructed C fixture passed **15 cases** under AddressSanitizer and
UndefinedBehaviorSanitizer: ordinary/reversed fields, substring-name matching,
case sensitivity, first duplicate, encoded delimiters/NUL, malformed escape,
short receive, missing fields, 31/32-byte SSIDs, 64-byte password truncation,
split UTF-8 and maximum quote expansion. All values are synthetic.

Three exported scan-escape results were then wrapped in the recovered JSON
shape and parsed with Bun: quote/backslash and supported control escapes round-
tripped; the raw `0x01` case raised a JSON syntax error as expected. These are
**three additional host checks**, not three more C cases or actual AP scans.
No driver was invoked, no Wi-Fi configuration was saved, and no page was submitted.

HTML escaping and ignored AP-count/record return values are separately traced
statically. The fixture does not reproduce all driver behavior, asynchronous
retry shutdown, live browser display or every invalid byte sequence.

Private artifacts: `wifi-form-pass1.txt`, `wifi-form-pass2.txt`,
`wifi-form-gnu.mjs`, `wifi-form-boundaries-gnu.txt`, `wifi-form-literals.jsonl`,
`wifi-form-fixture.c`, `wifi-form-fixture-results.txt`,
`wifi-scan-json-fixture.mjs`, `wifi-scan-escaped.hex` and
`wifi-scan-json-results.json`.

## OTA offer queue and failure bookkeeping: R10/R11/N02

Two Ghidra passes and 21 bounded GNU ranges cover nine helpers and selected
branches in three callers. Instructions, pinned literals and the matching ROM
symbol map distinguish signed 64-bit division from the unsigned comparison of
its low result word. In particular, the valid zero-time branch at `0x4202bac2`
must not be discarded based on Ghidra's unreachable-block warning.

A C reconstruction passed **22 case groups** with AddressSanitizer and
UndefinedBehaviorSanitizer. It fixes the 56-byte blob layout with compile-time
offset assertions and checks the 24-hour boundary, future timestamps on both
sides of one hour, zero/negative clocks, two-versus-three failures, null/empty
inputs, pending replacement/retention, long versions and URL truncation. A
long-version case models the actual callers passing the truncated pending
version to the failure writer, then receiving the full version again.

Additional cases exercise an injected read failure leaving a zeroed destination,
a failed clear, an ignored save failure, low-32-bit timestamp storage, reason
truncation and a synthetic 255-count wrap. These are supplied persistence outcomes
in a host model, not a complete NVS emulator or executed ESP error paths. The
count-wrap case does not claim ordinary operation reaches that starting state.

Static poll inspection separately shows that omitted/null/unusable firmware
does not clear a prior pending offer. Queue getters return RAM pointers; the
failed-install callers record their failure before clearing those buffers.
The [OTA contract](ota-and-recovery.md#failure-tracking-and-reporting) records
the boundaries and implications. No device poll offer, update, clock change,
reboot, NVS mutation or flash write was performed. R10/R11 remain open for their
remaining reporting, persistence, other-build and physical questions.

Private artifacts: `ota-queue-pass1.txt`, `ota-queue-pass2.txt`,
`ota-queue-gnu.mjs`, `ota-queue-boundaries-gnu.txt`, `ota-queue-literals.jsonl`,
`ota-queue-fixture.c`, `ota-queue-fixture-results.txt` and
`ota-queue-evidence-hashes.txt`.

## Wake selection and timer/reason failures: S03/S04/S05/S06

Two Ghidra passes, pinned constants and 29 bounded GNU ranges cover ten helpers
plus selected album-wake caller branches. The selector's 64-bit return and reason
registers were read directly; Ghidra's inferred void return and removed-branch
warnings are not a sufficient account of this function. The lower timer helper
also returns the SDK result despite its decompiled void signature.

A C host reconstruction passed **33 case groups** under AddressSanitizer and
UndefinedBehaviorSanitizer. Cases cover 29/30/31-second margins, equal/competing
deadlines, a low-word epoch carry, overdue and cleared album state, timer/reason
write failure combinations, default-schedule failure, time invalid with/without
credentials, and a clock advancing between selection and arming. Synthetic
maintenance correction values verify the arithmetic and album's zero correction.

The separate fallback model covers invalid time, transient scheduling failures,
persistent scheduling failures and the busy guard's no-work success. Persistent
failure stops at a **host-only depth limit of 16**; this avoids deliberately
exhausting a stack and does not assert an on-device failure threshold. The
firmware's real recursive call and missing retry limit are static evidence.

The [scheduling contract](boot-and-scheduling.md#timer-selection-arming-and-wake-reason-are-separate-operations)
now distinguishes selected deadlines, requested timer intervals, persisted wake
reasons and logs. The 30-second candidate cutoff is not a global minimum sleep:
the no-candidate maintenance fallback can arm a nearer future target. Missed-album
retry bypasses that selection and requests five minutes again after shutdown.

These fixtures do not execute the Xtensa application, NVS, SNTP, RTC calibration,
sleep hardware or concurrent tasks. No schedule/timezone/clock was written and
neither frame was polled or woken. S03–S06 remain open for their physical,
persistence and concurrency portions. The correction field's active calibration
source and actual value remain unverified.

Private artifacts: `wake-scheduling-pass1.txt`, `wake-scheduling-pass2.txt`,
`wake-scheduling-gnu.mjs`, `wake-scheduling-boundaries-gnu.txt`,
`wake-scheduling-literals.jsonl`, `wake-scheduling-extra-literals.jsonl`,
`wake-scheduling-fixture.c`, `wake-scheduling-fixture-results.txt` and
`wake-scheduling-evidence-hashes.txt`.

## Poll result ownership and settings consumers: C02/C08/D01/D07

Two reference/decompiler passes and 17 bounded GNU ranges cover seven helpers and
the two foreground result-consumer branches. Direct pointer references confirm
the separate result, completion-byte, semaphore and task-handle locations.
The serialized `user_settings` copy still has no recovered local member consumer;
the button path's exact four-byte destination is now checked in instructions.
It returns on pending content while preserving the result for main's larger copy.

New lifecycle evidence distinguishes publication from task exit: the worker
publishes completion, gives the semaphore, delays 200 ten-millisecond ticks, then
frees its argument and clears its handle. New-poll initialization does not clear
the separate completion byte. The result getter/clearer have no generation check,
request lock or worker join. Conditional stale-ready/late-clear consequences are
static inferences, not observed races or a claim that ordinary polling overlaps.

No new host concurrency fixture or physical request was run for this pass. It
does not convert the earlier successful render into a reliable poll receipt.
See [the poll result contract](cloud-protocol.md#poll-completion-is-one-shared-result-not-a-delivery-receipt)
for the local adapter implications. C02/C08/D01/D07 remain open for the outstanding
physical, lifetime, indirect-reference and per-job acknowledgement questions.

Private artifacts: `poll-settings-pass1.txt`, `poll-settings-pass2.txt`,
`poll-settings-gnu.mjs`, `poll-settings-boundaries-gnu.txt`,
`poll-settings-literals.jsonl` and `poll-settings-evidence-hashes.txt`.

## Image HTTP framing and progress timeouts: C03/C07/C08/D06

The download loop was rechecked in 14 bounded GNU ranges. A new host fixture
reuses the seven unchanged SDK callbacks/readers and HTTP parser pinned in the
[earlier voice harness](#voice-response-completeness-and-timeouts-c05c07c08),
then reconstructs the Large header/status/capacity checks and body-read loop.
Transport reads, error codes and delays are scripted. It makes no network call.

**Nineteen cases passed** with C11 warnings-as-errors, AddressSanitizer and
UndefinedBehaviorSanitizer. Exact/short/truncated declared lengths, chunked and
close-delimited framing, early output-count preservation and timeout streaks
are covered. Two cases allocate the real 2,304,000-byte Large destination:
an exact declared transfer and a chunked transfer with more data after capacity.
The latter returns success with the HTTP parser still incomplete and those bytes
unread. This promotes the earlier bounded inference to host reproduction, not
to a physical-frame observation.

The small-capacity cached-body control is documented separately because its
destination is smaller than a header receive. It must not be generalized into
an oversized whole-image header cache. Six scripted timeout events interleaved
with progress complete after 269,997 virtual ms; three consecutive no-progress
events fail after 90,000 virtual ms. These times do not include the real caller's
outer wait, cancellation, TLS or hardware.

The [download contract](image-downloads.md#host-results-with-the-matching-sdk-reader)
lists results and limitations. All destination guards remained intact. No display,
cache, firmware, route or backend was changed; broader checklist items remain open.

The fixture SHA-256 is
`4a8182c12863b11250beeee8ab3548f74fd73c66c071ea97f9ff22b8d3826f8e`.
Parser and selected-SDK hashes match the earlier pinned values. Private artifacts:
`image-http-pass1.txt`, `image-http-gnu.mjs`, `image-http-boundaries-gnu.txt`,
`image-http-fixture.c`, `image-http-results.jsonl`, `image-http-source-hashes.txt`
and the isolated `image-http-fixture/` source/build directory on Omarchy.

## LED arbitration and Standard comparison: E02/H05/D01/D07

Two reference/decompiler passes per build and 39 bounded GNU ranges per build
cover thirteen corresponding functions. A reproducible comparison checks 826
instructions, preserving relative offsets, registers, constants and branch
destinations. Direct helper/global addresses are mapped by their inspected role;
IRAM targets use the build relocation offset, and referenced string bytes are
compared. All thirteen pairs match. This does not recursively compare SDK bodies,
PWM/output helpers or every caller. The 41-record table remains byte-identical.

A C fixture reconstructs setter, latch and worker completion transitions with
that extracted table. **Twenty-two case groups passed** with C11 warnings-as-errors,
AddressSanitizer and UndefinedBehaviorSanitizer. Mutex outcomes and milliseconds
are scripted. Checks include factory suppression before urgency, ignored-success
requests, pending replacement, latch changes before state application, same-state
timer reuse, different pattern/duration completion, error-latch retention,
Wi-Fi-diagnostic fallback, delayed/stale completion and unsigned clock wrap.

The stale-completion case establishes a conditional control-flow consequence:
a failed completion mutex leaves the byte set, and a later applied state can be
cleared by that byte. It does not show that a physical frame has experienced this
interleaving. Neither host code nor instruction comparison measures light,
executes FreeRTOS scheduling or proves physical task-notification delivery.
No frame request, factory mode, recording, display or network change was made.
E02/H05/D01/D07 retain their outstanding physical and broader comparison scope.

Private artifacts: `led-arbitration-pass1.txt`, `led-arbitration-pass2.txt`,
`led-arbitration-gnu.mjs`, `led-arbitration-boundaries-gnu.txt`,
`compare-led-instructions.mjs`, `led-instruction-comparison.json`,
`prepare-led-fixture.mjs`, `led-fixture-records.inc`, `led-arbitration-fixture.c`,
`led-arbitration-results.jsonl`, `led-arbitration-evidence-hashes.txt`, and the
Standard `standard-led-pass1.txt`, `standard-led-pass2.txt` and
`standard-led-boundaries-gnu.txt` counterparts.

## Enrollment JSON and event boundaries: C11/C01/D01

Two reference/decompiler passes and 28 bounded GNU ranges revisit nine functions:
the setup request, shared event callback, parse/lookup wrappers and boolean/string
predicates. The 259-byte setup-result layout, 64/64/127-byte copies, boolean-success
selection, case-insensitive lookup and permissive parse-end option match the
host reconstruction. The existing Standard field-parser comparison is retained;
this new accumulation fixture is based on the Large paths.

**Thirty case groups passed** with C11 warnings-as-errors, AddressSanitizer and
UndefinedBehaviorSanitizer. They use the same pinned cJSON source hashes as the
[poll parser pass](#poll-parser-and-error-semantics-c02s03c08). Cases cover minimal
parser success versus empty identity, types, case/duplicates, decoded NUL,
byte truncation, a split UTF-8 character, extra JSON/text, one-byte event assembly,
4,095/4,096-byte boundaries, skipped-middle content and retained redirect bodies.

All modeled data events are at most 512 bytes. One constructed oversized valid
response returns failure before accumulation, success after one event grouping
silently removes a middle member, and parse failure after another grouping.
This tests the recovered skip-and-continue rule with the real JSON library;
it does not execute the SDK transport or establish those exact events on a frame.
There was no account submission, credential use, identity save, NVS change,
verification request or frame contact. C11 remains open for complete independent
enrollment and the persistence/boot/verification portions.

Private artifacts: `enrollment-parser-pass1.txt`, `enrollment-parser-pass2.txt`,
`enrollment-parser-gnu.mjs`, `enrollment-parser-boundaries-gnu.txt`,
`enrollment-json-fixture.c`, `enrollment-json-results.jsonl` and
`enrollment-parser-evidence-hashes.txt`.

## Upload worker context lifetime: C07/C08/D01/D07

Three reference/decompiler passes and 22 bounded GNU ranges cover the upload
worker, orchestration, no-op cleanup, task creation/initialization/stack setup and
the main-loop return site. GNU decoding is used where Ghidra truncates task
creation at an unsupported `SALTU` instruction or has no initializer entry.
The source corroboration is the pinned IDF 5.4.1 Xtensa port, not a claim that the
entire SDK binary was rebuilt or proved identical.

The caller-stack context is 220 bytes, with a separate local status word. The
URL buffer and completion semaphore are global. Tracing follows the original
context pointer into the new task's initial register frame, with no context copy.
After the 90,000-tick wait expires, the caller returns without joining the upload
worker. All recovered success/error/cancel exits later read through that context
to publish status and give the semaphore. Main resumes without checking the
orchestration return and prints its generic workflow-complete message.

This narrows the earlier lifetime question to a concrete **conditional static
use-after-return path** if the worker survives the caller. It does not reproduce
an expired-stack write, a late result consumed by another job, or any crash on a
frame. No additional host lifetime simulation was substituted for device evidence;
the prior SDK response fixture already shows transport reads can exceed the
outer wait. No recording, stalled request, task fault or device action was induced.

Private artifacts: `upload-lifetime-pass1.txt`, `upload-lifetime-pass2.txt`,
`upload-lifetime-pass3.txt`, `upload-lifetime-gnu.mjs`,
`upload-lifetime-boundaries-gnu.txt`, `upload-lifetime-literals.jsonl` and
`upload-lifetime-evidence-hashes.txt`.

## Standard status RLE and restoration: N08/D01/D07

One reference/decompiler pass and 25 bounded GNU ranges examine nine Standard
functions: asset resolution, marker save/reload/query/clear, RLE decode, show,
restore and render-start. The 960,000-byte output, 480,000-byte half offset,
two-half/1,600-strip/600-pixel loops, unmasked packing, error paths and marker
ordering are instruction-backed. This compares these application paths with the
earlier Large trace; it does not prove complete SDK or renderer equivalence.

**Eighteen C host cases passed** with C11 warnings-as-errors, AddressSanitizer and
UndefinedBehaviorSanitizer. They adapt the earlier malformed-size/run, palette,
partial-write and trailing-pair checks to Standard, then add distinct strip/half
contents and unchanged allocation-tail checks. An independent decoder consumes
all 26,958 embedded bytes, emits 960,000 bytes and matches the C output exactly.
Asset and output hashes are recorded in the
[format notes](storage-and-configuration.md#standard-status-assets-use-different-row-geometry).
An initial host-fixture transcription error in the half offset was caught by the
uniform-output assertion and corrected to the binary's 480,000-byte constant
before the passing run; it was not a firmware failure.

This is host reconstruction and static tracing, not a new panel render or an
execution of the Xtensa application. No frame contact, battery-state experiment,
storage fault, marker change or artwork replacement occurred. N08/D01/D07 remain
open for their physical, persistence and concurrency portions.

Private Standard artifacts: `standard-status-rle-pass1.txt`,
`standard-status-rle-gnu.mjs`, `standard-status-rle-boundaries-gnu.txt`,
`standard-status-rle-literals.jsonl`, `extract-standard-status-rle.mjs`,
`standard-status-rle-fixture.c`, `standard-status-rle-results.txt`,
`standard-status-rle-asset.json` and `standard-status-rle-evidence-hashes.txt`.

## Redirect status and URL boundaries: C01/C03/C11

Two reference/decompiler passes and 50 bounded GNU ranges cover seven Large
functions: URL replacement, redirect scheduling, status checking, string
assignment, URL parsing/character-state selection and the `perform` replay loop.
Checks include the five redirect codes, the ten-redirect boundary, counter reset
before the 2xx return, distinct callback/event-loop branches, root-relative path
handling and the absence of browser-style relative URL resolution.

**Twenty host cases passed** with C11 warnings-as-errors, AddressSanitizer and
UndefinedBehaviorSanitizer. Three IDF client functions are extracted without edits
from the same pinned source used in the earlier HTTP-reader fixtures, together
with its pinned URL parser. Header storage, successful string allocation,
connection close and event dispatch use stubs. The request contains only fixture
data. Tests check destination state and retained method/body/custom-header fields;
they do not transmit a replayed request, execute the complete client state machine
or demonstrate physical cross-host credential forwarding. Allocation failure,
authentication retry, TLS and real event/task scheduling remain outside this pass.

The earlier source fingerprints remain unchanged: client SHA-256
`7aabd415f3a39675e59f591919b9e88e31213e548b010cb0809a888d2b0ceef2`,
parser SHA-256
`c164edcb06099b026e7ed853ed4d25536e83b4463d5e79921b28621e16588455`.
The [protocol notes](cloud-protocol.md#redirect-url-handling-differs-from-a-browser)
record the practical consequence: direct device-route responses and final asset
URLs avoid behavior that differs between `perform` and manual consumers.

Private artifacts: `redirect-boundaries-pass1.txt`,
`redirect-boundaries-pass2.txt`, `redirect-gnu.mjs`,
`redirect-boundaries-gnu.txt`, `prepare-redirect-fixture.mjs`,
`redirect-fixture.c`, `redirect-results.jsonl`, `redirect-source-hashes.json`
and `redirect-evidence-hashes.txt`. No frame contact, account action, DNS/proxy
change or credential-bearing network request occurred.

## Poll request encoding and report consumption: C01/R10/E01

Two reference/decompiler passes and 15 bounded GNU ranges examine four Large
functions/call regions: the SSID encoder, current-version snapshot, destructive
OTA-result getter and poll construction through client initialization. Ghidra
truncates the encoder at `SALTU`; GNU decoding starts at the real loop target
after padding and covers the complete classification/percent-write body. Literal
reads supply all three URL formats, reporting globals and compiled version.

**Twenty-seven reconstructed C host cases passed** with C11 warnings-as-errors,
AddressSanitizer and UndefinedBehaviorSanitizer. Cases cover unreserved/reserved
bytes, UTF-8 bytes, embedded NUL, empty SSID, conservative small-buffer behavior,
32 fully escaped bytes, delimiter containment, report states/error categories,
compiled versus overridden version, repeated consumption and 511/512-byte URL
limits. The fixture's three format strings are checked against the extracted
firmware literals. Long API origins are synthetic inputs for the length check,
not a claim that an ordinary stock request exceeds the buffer.

The report getter clears terminal RAM state before URL/client/transport success;
host checks establish that ordering, not an actual failed HTTP transaction.
No Wi-Fi configuration, SSID, identity, NVS, firmware or network state changed.
There was no device request or update. Generalized short-buffer misuse, malformed
identity storage, physical report loss and cross-model behavior remain outside
this pass.

Private artifacts: `poll-request-pass1.txt`, `poll-request-pass2.txt`,
`poll-request-gnu.mjs`, `poll-request-boundaries-gnu.txt`,
`poll-request-literals.jsonl`, `poll-request-fixture.c`,
`poll-request-results.txt` and `poll-request-evidence-hashes.txt`.

## HTTP Date callback and offline time: S02/C01/E02

One reference/decompiler pass per model and eight bounded GNU ranges cover both
complete cloud callbacks, Large's time reader and its calendar-conversion entry.
Literal reads establish the exact `Date` name and indirect-call targets. The
header branch reads the name, never loads the value, passes stack temporaries to
the clock/calendar helpers and discards the result. Standard has the same branch
with relocated helper targets. The time/calendar identification also agrees with
the earlier SNTP callback and calendar research.

This answers the specific fallback question without simulating a clock update:
the inspected callback does not derive time from HTTP. The pass does not re-prove
the entire libc DST implementation, exercise NTP/RTC behavior, inspect installed
bootloader state or test a frame with an invalid clock. No host clock, device,
network or backend response was changed, and no additional host fixture was
needed for the absent header-value data flow.

Private artifacts: `http-date-pass1.txt`, `http-date-gnu.mjs`,
`http-date-boundaries-gnu.txt`, `http-date-literals.jsonl`,
`http-date-evidence-hashes.txt`, and Standard's `standard-http-date-pass1.txt`,
`standard-http-date-boundaries-gnu.txt` and `standard-http-date-literals.jsonl`.

## SNTP server slot and startup timing: S02

Five reference/decompiler passes, literal reads and 34 bounded GNU ranges cover
20 Large functions/call regions, including the earlier application retry routine.
The setter accepts only index zero. The request function prioritizes its name;
initializer arithmetic encodes a 0–4,999 ms random delay; stop removes both
request/retry timers; the timer list unlinks by callback and argument. The
application's 2/4/8/10/10-second waits and lack of a final stop are checked against
the same instructions, not inferred from SDK defaults.

This establishes a conditional mismatch between startup delay and early retry
budgets, without simulating network timing or assigning a failure probability.
No clock, frame, DHCP lease, DNS, router or service configuration changed. Standard
timing, real callback ordering, resource failures, DHCP time-server support and
WAN-free cold boot remain unverified. No host fixture was needed to establish
the explicit timer calls and constants.

Private artifacts: `sntp-selection-pass1.txt` through `sntp-selection-pass5.txt`,
`sntp-selection-gnu.mjs`, `sntp-selection-boundaries-gnu.txt`,
`sntp-selection-literals.jsonl`, `sntp-more-literals.jsonl` and
`sntp-selection-evidence-hashes.txt`. SDK names are analytical identifications;
the binary is still the pinned Large application, not recovered vendor source.

## DHCP time-server handling: S02

Four reference/decompiler passes and 52 bounded GNU ranges cover ten Large
functions/call regions: five request builders, reply parsing, ACK application,
receive dispatch and two extension hooks. A hash-checked segment scan found the
four-byte request list; its callers confirm both the list length and byte values.
Ghidra truncates the parser at `SALTU`, so the GNU pass resumes at verified branch
targets and separately decodes blocks after padding. The unknown-option branch,
hook's immediate non-26 return and zero decode length establish that a supplied
option 42 is skipped, rather than merely absent from the request list.

The ACK path contains no time-server installation. The append hook adds a client
identifier, not a time-server request. The option-26-specific hook body is outside
this question; its early return is sufficient to determine option-42 behavior.
This is static evidence for Large's DHCPv4 client only. No synthetic DHCP traffic,
lease renewal, router change, frame contact, DHCPv6 conclusion or Standard-model
equivalence is claimed. Local DNS/NTP compatibility still needs a bounded physical
test; the broader S02 item remains open.

Private artifacts: `find-dhcp-table.mjs`, `dhcp-table-candidates.json`,
`dhcp-time-pass1.txt` through `dhcp-time-pass4.txt`, `dhcp-time-gnu.mjs`,
`dhcp-time-boundaries-gnu.txt` and `dhcp-time-evidence-hashes.txt`.
`dhcp-parser-exploratory-gnu.txt` is discovery output with padding misdecodes;
use the bounded output as the instruction evidence.

## Standard time-service comparison: S02/E02

Three Standard reference/decompiler passes and 80 bounded GNU ranges cover 25
functions/call regions, including the first/recovery background call sites,
application synchronization, SDK wrappers and the relevant SNTP/DHCP helpers.
Hash-checked literals establish the four time-server names, startup-delay
constants, one server record and the four-byte DHCP request list.

The DHCP parser has 324 decoded instructions and 111 internal branches per model.
A comparison verifies every internal target is present in the bounded output,
the instruction offsets match and all bytes other than 17 relocated literal
loads are identical. The literal registers match; relevant constants and data
uses were inspected separately. The hook's non-26 return and ACK/append paths
were checked too, so the option-42 result does not rest on parser similarity
alone. No whole-SDK equivalence is claimed.

The function map now contains 82 pairs. Both models have the same relevant
one-slot selection, startup-delay/retry mismatch and DHCP time-server limitation.
No host clock, DHCP lease, device, DNS or network configuration changed. Physical
offline boot, late-callback timing, DHCPv6 and live failure frequency remain
outside this comparison; it supersedes the earlier Standard-untested scope for
these specific static SNTP/DHCP findings.

Private Standard artifacts: `find-standard-time.mjs`,
`standard-time-candidates.json`, `standard-time-pass1.txt` through
`standard-time-pass3.txt`, `standard-time-literals.jsonl`,
`standard-time-gnu.mjs`, `standard-time-boundaries-gnu.txt`,
`compare-dhcp-parser.mjs`, `standard-dhcp-parser-comparison.json` and
`standard-time-evidence-hashes.txt`.

## DNS fallback and cache lifetime: S02/C01

Four reference/decompiler passes, literal reads and 59 bounded GNU ranges cover
18 Large functions/call regions. They trace resolver initialization, its three
server slots, the DHCP-start clearing helper, new/pending/cached states, DNS send
and response paths, immediate backup selection and the on-demand timer. The
eight-byte timer callback is a Ghidra label; its GNU entry and direct call were
verified separately. The prior DHCP ACK evidence supplies the index-2 exclusion.

The firmware installs `8.8.8.8` as DNS fallback independently of the public TCP
probe. Timeout handling skips empty slots, whereas nonzero-response-code handling
first requires a populated immediate backup. Setter/cache separation, four cache
entries, zero-TTL removal and the seven-day TTL ceiling are instruction-backed;
they do not demonstrate actual resolver traffic, a cache-flush API or runtime
failure frequency. Counter-derived retry intervals are not measured deadlines.

No network fixture, frame request, DNS/routing change or DHCP renewal occurred.
Standard's DNS internals and complete offline cutover remain to compare/test.
Private artifacts: `dns-fallback-pass1.txt` through `dns-fallback-pass4.txt`,
`dns-fallback-literals.jsonl`, `dns-fallback-gnu.mjs`,
`dns-fallback-boundaries-gnu.txt` and `dns-fallback-evidence-hashes.txt`.

## SNTP pending-callback lifetime: S02

Two new reference/decompiler passes and earlier SNTP/DNS passes supply ten
functions across 30 bounded GNU ranges. These check the resolver callback
registration/completion, SNTP stop/request/DNS/send/retry/init and packet
initialization paths, plus UDP's early null-client guard. The resolver retains
the callback after stop. The SNTP callback uses shared state without an attempt
identifier or hostname check; stop's timer removal is conditional on a client
still existing. UDP returns an argument error for a null client, while SNTP's
send path ignores that return and rearms its timer.

Eight deterministic host cases passed with Clang AddressSanitizer and
UndefinedBehaviorSanitizer, warnings treated as errors. The fixture extracts
seven unmodified functions from pinned lwIP commit
`fa4dffdfac52587a26c1f29258376df750cf8474`: packet initialization, retry, send,
DNS callback, request, init and stop. Source SHA-256:
`8695155c80c807d7ac949801b023d4e2f27db7975f78bcbba726bcdc012020e7`.
The selected source retains its license header. Relevant compile branches were
checked against the Large instructions rather than assumed from default SDK
configuration.

The cases cover normal completion; stop before startup dispatch; a late positive
lookup using a replacement client; positive/negative completion without a client;
a late negative lookup replacing the new startup timer; packet-allocation failure;
and a repeated stop followed by a rearmed request. Assertions check destination,
client identity, stored name/address, timer callbacks/delays and DNS count.

DNS, timers, UDP and packet buffers are host stubs; addresses are simplified to
IPv4 and startup delay is fixed at 1,000 ms within the verified firmware range.
The fixture does not run the complete resolver, TCP/IP task queue, socket stack,
clock or network. It establishes consequences of selected event orderings, not
physical frequency, actual battery impact, concurrent task behavior or Standard
equivalence. No frame, backend, DNS, router or clock state changed. S02 stays open.

Private artifacts: `sntp-lifetime-pass1.txt`, `sntp-lifetime-pass2.txt`,
`sntp-lifetime-gnu.mjs`, `sntp-lifetime-boundaries-gnu.txt`,
`prepare-sntp-lifetime-fixture.mjs`, `sntp-lifetime-fixture.c`,
`sntp-lifetime-source-hashes.json`, `sntp-lifetime-results.txt` and
`sntp-lifetime-evidence-hashes.txt`. The generated fixture directory contains
the pinned source and selected functions.

## Standard DNS and SNTP callback comparison: S02/C01/E02

Two Standard reference passes and 80 bounded GNU ranges compare 27 selected
functions with the prior Large resolver/callback traces. The checker verifies
2,189 instruction addresses/bytes and all 380 internal branch targets per image.
Non-call/non-literal instruction bytes match; all 47 distinct direct-call pairs
have the same relocation. The 70 distinct literal pairs are checked as equal
values, identical terminated strings or 24-byte address constants, or consistent
RAM/code pointer mappings. Every decoded instruction byte is also compared with
the respective hash-validated vendor application, rather than trusting the ELF
alone. External helper equivalence is not established by a pointer mapping.

The first comparison run exposed a symbol inside an instruction in the older
Standard analysis ELF. GNU obeyed that symbol boundary and split the instruction.
A separate symbol-stripped analysis copy removes that artifact; instruction
offsets and firmware bytes then match across the entire selected set. The
original ELF/project and vendor application were preserved. This was an analysis
artifact, not a discovered difference in the firmware's resolver behavior.

Manual branch review connects the matching constants and pointers to fallback
installation, DHCP clearing, cache lookup/expiry, callback registration and the
SNTP stop/send/retry paths. Both models share the relevant fallback/cache and
late-callback behavior. Twelve function pairs were added, bringing the public map
to 94. The existing eight isolated callback cases are applicable to these matched
branches; no additional host cases, physical packets, clocks, frame requests or
network changes are claimed. S02 and C01 remain open for broader dependency and
physical offline validation.

Private Standard artifacts: `standard-dns-pass1.txt`, `standard-dns-pass2.txt`,
`compare-standard-dns.mjs`, `standard-dns-boundaries-gnu.txt`,
`standard-dns-comparison.json`, `standard-dns-literals.jsonl` and
`standard-dns-evidence-hashes.txt`. The symbol-stripped ELF is a private analysis
copy, not a flashable replacement or a changed vendor firmware image.

## NTP response acceptance and clock conversion: S02

Four Large reference/decompiler passes and 12 bounded GNU ranges cover nine
functions: request initialization, receive, timestamp processing, interval getter,
time wrapper, SDK synchronization, callback registration, application callback
and the clock-setter entry. Literal reads establish the epoch offset,
microsecond multiplier, callback/mode/status locations and the initialized
one-hour update interval. The receive path has no source/port, leap/version,
originate-timestamp or timestamp-freshness check; its explicit guards are length,
operating/response mode and stratum-zero handling. This describes callback-level
behavior, not arbitrary packet delivery through the network stack.

Eighteen host cases passed under Clang AddressSanitizer and
UndefinedBehaviorSanitizer with warnings treated as errors. Four unmodified
functions from pinned lwIP commit `fa4dffdfac52587a26c1f29258376df750cf8474`
are extracted with their license header: receive, timestamp processing, retry
and request initialization. Source SHA-256 remains
`8695155c80c807d7ac949801b023d4e2f27db7975f78bcbba726bcdc012020e7`.
Macro branches and the timestamp-recording boundary follow the inspected binary.

Cases cover normal time, half/max fractions, 47/49-byte lengths, client/broadcast
modes, stratum 0/16/255, alarm leap bits, version 0/7, unrelated originate/receive
fields, zero/last-before-era transmit seconds, Unix epoch conversion and the
zero-filled client request. Every receive case uses synthetic source arguments
with port 9999; the callback ignores them. Assertions check conversion values,
packet release, reachability, retry reset/backoff and timer scheduling calls.

Buffers are contiguous host stubs and timers only record calls. The timestamp
setter records arguments; neither the host clock nor the actual SDK time setter
is invoked by the fixture. Application flag behavior and SDK clock invocation
are separate static findings, not simulated full boot/TLS/scheduler behavior.
No sockets, frame requests, DNS/routing/backend changes or real NTP response
occurred. Standard reception and physical local-time compatibility remain open.

Private artifacts: `ntp-response-pass1.txt` through `ntp-response-pass4.txt`,
`ntp-response-gnu.mjs`, `ntp-response-boundaries-gnu.txt`,
`ntp-response-literals.jsonl`, `ntp-response-fixture.c`,
`prepare-ntp-response-fixture.mjs`, `ntp-response-source-hashes.json`,
`ntp-response-results.txt` and `ntp-response-evidence-hashes.txt`.

## Standard NTP receive and clock comparison: S02/E02

One Standard reference pass and 12 bounded GNU ranges compare nine functions,
256 instructions and 31 internal branches with the Large response/clock pass.
Every instruction's offset and bytes are checked against the hash-validated
application image. Non-call/non-literal instruction bytes match. Fifteen distinct
direct-call pairs and 26 literal pairs are reviewed as corresponding pointers,
equal constants or identical strings; this does not establish all external
helper implementations as equivalent. The application callback and clock-setter
entry have different relocation offsets from the lwIP helpers and were compared
at their own verified entries.

Separate literal reads confirm the 3,600,000 ms interval at Standard
`0x3fca1320`, epoch/fraction constants and application flag/semaphore addresses.
The comparison extends the existing 18 receive/conversion host cases to matched
static paths in Standard; no additional cases or physical packets are claimed.
Six function pairs bring the public map to 100. Actual local time service,
clock correction, cold boot, retained RTC and full offline operation remain open.
No frame, backend, host clock, DNS or router setting changed.

Private Standard artifacts: `standard-ntp-pass1.txt`,
`compare-standard-ntp.mjs`, `standard-ntp-boundaries-gnu.txt`,
`standard-ntp-comparison.json`, `standard-ntp-literals.jsonl` and
`standard-ntp-evidence-hashes.txt`.

## Outbound clients and literal-host inventory: C01

Three reference passes and 28 bounded GNU ranges cross-check 24 direct call
sites: ten to the API selector, two to the web selector, one to authentication
selection and eleven to the HTTP-client constructor. A separate raw Xtensa
call-encoding scan examines every possible byte offset in executable segments;
its candidates are checked against GNU and recovered call context. A scan for
exact pointer words finds no additional serialized pointers to the four target
functions. This is not a proof against arbitrary computed indirect calls.

Ghidra's constructor-reference list omits the multipart call at `0x42026fdd`.
The raw scan and its already-traced configuration block recover that call; it
is not an additional previously unknown transport. Two API-selector calls were
confirmed as logging only by following return values into their format calls.
The other eight calls belong to the six request-building consumers already
documented. The eleven constructors include the separate older updater.

A hash-checked printable-string scan records 43 HTTP(S) URL occurrences across
eleven hosts. All 29 W3C occurrences are explicitly SVG namespace attributes;
four other occurrences are direct HTML navigation links. Portal handlers and
selector data flow establish the remaining categories. The older LAN origin and
adjacent manifest path have neither recovered references nor exact pointer words
in the application image. This bounded negative result does not prove a literal
could never be addressed through computed arithmetic. Their presence is not a
reason to add that host to the backend configuration.

The new public JSON includes only static call-site/role/host metadata, with no
credentials, private captures or firmware bytes. Dynamic server-returned URLs,
bare non-HTTP names, runtime endpoint selection and full Standard comparison are
outside the literal scan. No address was contacted, resolved or routed, no live
device state changed, and no fixture was needed for these reference/byte checks.
C01 remains open for its broader dependency and state-dependent validation scope.

Private artifacts: `inventory-url-hosts.mjs`, `url-host-inventory.json`,
`url-host-pointer-counts.json`, `scan-client-calls.mjs`,
`client-call-candidates.json`, `dependency-audit-pass1.txt` through
`dependency-audit-pass3.txt`, `dependency-audit-gnu.mjs`,
`dependency-audit-boundaries-gnu.txt`, `dependency-audit-log-literals.jsonl`
and `dependency-audit-evidence-hashes.txt`.

## HTTP cancellation state and synthetic completion counts: C08/D01

Five reference passes and 24 bounded GNU ranges cover eight functions plus a
reader-loop region: client register/unregister, frame abort wrapper, SDK prepare,
ordinary HTTP close, connection helper, cancellation and transport-close dispatch.
Cancellation closes transport directly, so it does not perform ordinary HTTP
close's state reset or disconnect-event dispatch. Prepare resets parser state
and response bookkeeping but leaves connection state alone; reconnect is gated
on that state. Accepted cancellation then copies content length into processed
count. The reader-loop comparison is checked separately around alignment padding.

Ten host state cases passed with Clang AddressSanitizer and
UndefinedBehaviorSanitizer, warnings treated as errors. Four unmodified IDF
5.4.1 functions are extracted with their license header: prepare, connect,
cancel-request and the SDK completeness predicate. Source SHA-256:
`7aabd415f3a39675e59f591919b9e88e31213e548b010cb0809a888d2b0ceef2`.
The active branches are cross-checked against the application instructions.

Cases cover null and pre-connected clients; unchanged connected/header/body
states; transport-close failure; a synthetic state reduction followed by connect
success/failure; unknown-length counters; and incomplete chunked state. Assertions
check close/connect/event counts, preserved or reset state, cached-string release,
parser-reset calls and processed counts. No HTTP send operation is invoked.

Transport, parser initialization and event delivery are stubs. Cached strings use
real host allocation/free under the sanitizers; the complete HTTP parser, TLS,
socket stack, FreeRTOS scheduling and authentication branches are not exercised.
The synthetic state reduction models an ordering boundary, not an observed race.
The standalone SDK completeness predicate is a host observation; the firmware
reader loop's corresponding counter/flag branches are separately static evidence.
No physical cancellation, network traffic, frame state or backend was changed.
Standard equivalence and actual worker/transport cleanup remain open.

Private artifacts: `http-cancel-pass1.txt` through `http-cancel-pass5.txt`,
`http-cancel-gnu.mjs`, `http-cancel-boundaries-gnu.txt`,
`http-cancel-fixture.c`, `prepare-http-cancel-fixture.mjs`,
`http-cancel-source-hashes.json`, `http-cancel-results.txt` and
`http-cancel-evidence-hashes.txt`.

## Download timeout, task handle and cleanup: C08/D01/D07

Five Ghidra/reference passes and 46 bounded GNU ranges cover twelve functions
across the download worker/caller, HTTP unregister/client cleanup, task deletion,
list removal, task reclamation, port callbacks and C-runtime cleanup. All 1,965
decoded instruction byte sequences were checked against the hash-pinned Large
application, not only the synthetic ELF. The thread-local callback dispatcher
required a manual GNU continuation through unsupported SALTU instructions;
alignment padding was excluded.

The [download ownership map](image-downloads.md#voice-download-timeout-and-forced-task-deletion)
records the 1,556-byte borrowed context, separate caller result/handle slots,
8,192-byte task stack, discarded creation result and 300-second wait followed
by an abort and five-second grace wait. Grace-period success still takes the
failure branch without rendering. Worker completion publishes status before
giving the semaphore and self-deleting, with no recovered context use after give.

The caller's nonzero handle is not cleared by the worker or revalidated before
forced deletion. Kernel list removal uses that pointer directly. A worker that
finishes after the second wait times out can therefore overlap the deletion
decision; the actual scheduler ordering and consequences have not been reproduced.
Deleting during HTTP work can also skip unregister/close/client cleanup. Kernel
reclamation runs registered thread-local and C-runtime cleanup plus stack/control-
block frees, rather than unwinding the downloader's epilogue. Runtime callback
registration and resulting resource retention are not fully established.

This is a static follow-up, with no new host execution or device test. It does
not measure leaked memory, reproduce a crash, prove a socket remains open, or
explain the captured TLS allocation failure. No timeout was induced and no frame,
backend or routing state changed. C08/D01/D07 remain open.

Private artifacts: `download-delete-pass1.txt` through `download-delete-pass5.txt`,
`download-delete-gnu.mjs`, `download-delete-boundaries-gnu.txt`,
`download-delete-literals.jsonl` and `download-delete-evidence-hashes.txt`.

## Active HTTP-client slot and lock failures: C08/D01/D07

One targeted reference pass covers the six manager helpers and their recovered
callers. A separate byte-wise Xtensa direct-call scan finds 21 candidates: four
register, seven unregister, five aborted-read and five reset sites. Each matches
GNU instructions in its caller context, including the multipart acknowledgment
tail omitted by Ghidra. No exact pointer words for these four helper addresses
were found; computed indirect calls remain outside that negative result.

The nine full functions plus multipart-tail region span 56 bounded GNU ranges.
All 2,009 decoded instruction byte sequences match the pinned application.
Register, unregister and reset callers discard their return values. Missing mutex
and ten-tick acquisition failure are therefore not a stop condition for HTTP work
or client cleanup. The aborted getter returns false on those failures.

The [ownership trace](voice.md#active-client-ownership-and-failed-unregistration)
adds the 24-byte record layout, diagnostic-only label/time, preserved abort byte
on unregister and reset on registration. The image downloader unregisters after
body reading and again in the common epilogue. Its open-failure branch also reaches
that epilogue without having registered this invocation. Unregister failure can
leave the slot unchanged while the worker proceeds to client cleanup.

The resulting stale-client, other-client clearing and cross-request abort-state
cases are conditional static interleavings. There is no new host concurrency
test, physical cancellation, measured memory fault or socket-lifetime result.
These findings do not establish the cause of captured TLS allocation failures.
No frame, network policy, backend or HA implementation changed. C08/D01/D07
remain open, including Standard equivalence and runtime timing.

Private artifacts: `http-slot-pass1.txt`, `scan-http-slot-calls.mjs`,
`http-slot-call-candidates.json`, `http-slot-gnu.mjs`,
`http-slot-boundaries-gnu.txt` and `http-slot-evidence-hashes.txt`.

## Standard cancellation, ownership and timeout comparison: E02/C08/D01/D07

Two Standard Ghidra/reference passes and a hash-checked comparison cover fifteen
function pairs: six slot helpers, five HTTP SDK helpers, task deletion, download
worker, voice orchestrator and common downloader. There are 2,346 Standard
instructions in 63 GNU ranges including three extra header/cancellation regions.
Every decoded byte sequence is checked against its application image. The
symbol-free Standard ELF avoids known candidate labels inside instructions.

The paired functions match normalized operations, register operands and all 210
internal branch destinations by instruction index. Two functions differ in
alignment and equivalent narrow/move encodings; these are checked explicitly
rather than ignored wholesale. Fifty-three direct-call pairs and 183 literal
pairs are recorded separately. Constants/strings match except the 960,000 versus
2,304,000 panel limit, 9,000 versus 18,000 render-wait ticks and corresponding
90/180-second timeout diagnostic. Pointer relocations do not by themselves prove
every external helper implementation equivalent.

A fresh Standard raw direct-call scan finds 21 register/unregister/read/reset
sites, all independently checked against GNU caller instructions, with no exact
helper-pointer words found. Multipart's header tail is checked separately from
its truncated Ghidra function. The three additional voice regions establish the
discarded helper results around header reading and cancellation cleanup.

The [model comparison](standard-model-comparison.md#cancellation-ownership-and-download-timeouts-also-match)
records the shared slot/abort semantics, stack-context lifetime, completion-before-
self-delete ordering and failure after grace-period success. It distinguishes
voice render-completion waits from maintenance waits. Kernel list removal and
full Standard task-reclamation helpers remain outside this comparison, as do
runtime thread-local hooks, actual concurrency, resource retention and physical
timing. The earlier ten SDK host cases were not rerun or counted as new evidence.
No frame, backend, network rule or HA source changed. E02/C08/D01/D07 remain open.

Private artifacts: `standard-cancel-pass1.txt`, `standard-cancel-pass2.txt`,
`scan-standard-http-slot-calls.mjs`, `standard-http-slot-call-candidates.json`,
`compare-standard-cancel.mjs`, `standard-cancel-boundaries-gnu.txt`,
`standard-cancel-comparison.json`, `standard-cancel-literals.jsonl` and
`standard-cancel-evidence-hashes.txt`.

## Maintenance setter reachability and fixed arguments: S05/S02

Three reference passes cover the maintenance setter, record writer and sole
terminated `refresh_sched` key. A hash-checked full-image direct-call scan finds
eight setter calls plus one writer call, with no exact pointer words to either
function. All eight setter invocations load four days, hour three and minute zero
immediately before the call. The writer's only direct caller is that setter;
recovered key references belong to the loader and writer.

Nineteen GNU ranges cover those eight argument/call regions and three full
functions. All 324 decoded instruction byte sequences match the original pinned
Large app. The maintenance call at `0x42012790` belongs to entry `0x420126f8`,
after ordinary sleep's nonreturning call; the older Ghidra export's overextended
`0x42012338` function boundary is not used as its identity.

The [interface conclusion](boot-and-scheduling.md#maintenance-parameters-have-only-fixed-default-callers)
is deliberately bounded: these references establish no configurable stock
maintenance setter, not proof that arbitrary computed code/key construction is
impossible. The correction field is preserved by the setter, with no other direct
record writer supplying a learned value. This does not read installed NVS or
measure RTC drift. Standard caller equivalence, persistence/clock-change behavior
and physical wake timing remain open under S05/S02. No host behavioral fixture
was added for these literal/reference checks, and no device setting changed.

Private artifacts: `schedule-api-pass1.txt` through `schedule-api-pass3.txt`,
`scan-schedule-api-calls.mjs`, `schedule-api-call-candidates.json`,
`schedule-api-gnu.mjs`, `schedule-api-boundaries-gnu.txt`,
`schedule-api-string-hits.json` and `schedule-api-evidence-hashes.txt`.

## SNTP control mailbox, ordering and allocation failures: S02

Seven targeted reference passes follow the application retry loop through its
SNTP wrappers, shared TCP/IP dispatcher, allocation/free path, mailbox and
per-thread semaphore. Thirty-six selected functions span 66 GNU ranges, with
all 1,213 decoded instruction byte sequences checked against the pinned Large
application. Constants independently establish the 32-entry pointer mailbox,
16-byte API callback allocation, distinct pool descriptor and wrapper targets.

The [queue trace](boot-and-scheduling.md#sntp-control-queue-ordering-and-allocation-failures)
shows that hostname setting waits for its API callback to finish, whereas stop,
mode and init only post callbacks and discard allocation errors. Queue posting
and hostname completion use no ordinary timeout; the checked RTOS timeout helper
recognizes the maximum tick value separately from a task-delay abort. Application
response waits begin afterward, so their sum is not a total synchronization bound.

The compiled mode setter calls the assertion handler when a client remains
active. This gives a conditional lost-stop/successful-mode failure path, rather
than a claim that queued operations reorder. Missing init can leave the caller
waiting without a newly created client. The separate per-thread semaphore
allocator returns null on failure; the synchronous API path does not guard it
before wait/signal helpers dereference the storage pointer.

No host behavioral fixture, allocation fault, queue saturation, device request
or clock/network change was performed. These static paths do not establish a
runtime crash, deadlock, failure frequency or the cause of captured TLS memory
pressure. Standard queue equivalence and physical offline timing remain open;
S02 is not closed.

Private artifacts: `sntp-queue-pass1.txt` through `sntp-queue-pass7.txt`,
`sntp-queue-gnu.mjs`, `sntp-queue-boundaries-gnu.txt`,
`sntp-queue-literals.jsonl` and `sntp-queue-evidence-hashes.txt`.

## Standard time-control queue and fixed maintenance callers: E02/S02/S05

The [Standard queue comparison](standard-model-comparison.md#sntp-control-queue-and-failure-paths-also-match)
checks 34 paired functions in 57 GNU ranges: 944 instructions and 145 internal
branches per app. All decoded bytes match their respective pinned images.
Instruction offsets and non-literal/non-call bytes agree; paired callees and
95 literal pairs are handled separately. The 18 pool descriptors have matching
sizes, including the 16-byte API message. Four compared RTOS helpers cover send,
copy, semaphore take and timeout checks rather than assuming wrapper arguments
alone establish their behavior.

The checked paths preserve the synchronous hostname barrier, 32-entry pointer
mailbox, ignored asynchronous allocation errors, active-client mode assertion
and unchecked null per-thread semaphore. External helpers are mapped but not
all recursively compared. There are no additional host behavioral executions,
queue/heap fault injections or physical observations.

Separately, two Standard reference passes and a raw direct-call scan find eight
maintenance-setter calls with fixed `(4,3,0)` arguments, plus the sole direct
record-writer call. All nine sites and the three setter/load/save functions are
checked in 19 GNU ranges against 324 application instruction byte sequences.
The sole terminated key's recovered references belong to load/save. No exact
setter/writer pointers occur in the app; Ghidra's analysis-ELF symbol entries are
excluded from that result.

This extends the [fixed maintenance interface finding](standard-model-comparison.md#fixed-maintenance-callers-also-match)
to Standard without claiming an exhaustive computed-call/key search. Installed
correction, persistence under faults/clock changes, physical startup and wake
timing remain open. No frame, backend, routing policy or HA source changed.
E02/S02/S05 remain open.

Private artifacts: `compare-standard-sntp-queue.mjs`,
`standard-sntp-queue-boundaries-gnu.txt`, `standard-sntp-queue-comparison.json`,
`standard-sntp-queue-evidence-hashes.txt`, `standard-schedule-api-pass1.txt`,
`standard-schedule-api-pass2.txt`, `scan-standard-schedule-api-calls.mjs`,
`standard-schedule-api-call-candidates.json`, `standard-schedule-api-gnu.mjs`,
`standard-schedule-api-boundaries-gnu.txt`, `standard-schedule-api-string-hits.json`
and `standard-schedule-api-evidence-hashes.txt`.

## Presign field copying, reserialization and multipart projection: C05/D01

Three reference passes trace Large presign parsing through formatted cJSON
serialization and the upload's second parse. Eight functions and five multipart
prefix regions span 34 GNU ranges; all 1,076 decoded instruction byte sequences
match the pinned app. Result offsets, copy capacities, format flag, object
indentation/newlines and raw form-field format strings are checked explicitly.

Twenty-five host case groups passed with `clang -std=c11 -O1 -g -Wall -Wextra
-Werror -fsanitize=address,undefined -fno-omit-frame-pointer`, using the same
hash-pinned cJSON 1.7.18 source as earlier parser fixtures. The surrounding
positive-read HTTP-200 parser and string-part projection are reconstructed from
the checked branches, not executed vendor machine code. The fixture checks the
5,888-byte result layout and destination guards; no undefined empty-response
read is invoked.

The [contract findings](voice.md#presign-copying-and-field-reserialization)
include formatted fields growing beyond their 4,095-byte copy limit even when
the complete wire response fits the reader. A 3,249-byte response produces
exactly 4,095 field bytes and succeeds; a one-byte-longer variant produces 4,096,
is silently truncated and fails the subsequent fields parse. A separate 293-field
case grows from a 3,255-byte response to 4,104 field bytes with the same result.
Presign's parse return alone does not establish an upload-ready result.

Other groups verify required types, ignored `success:false`, empty URL/key
acceptance, case/duplicate selection, missing/non-object fields, decoded-NUL
shortening, UTF-8 splitting and collisions after URL/key truncation. Projection
retains duplicate string fields, reserved `file`, quotes and CRLF while skipping
non-strings. A custom cJSON allocation hook fails only the fields-print stage;
presign still succeeds with an empty fields string, which the later parse rejects.

No HTTP socket, TLS session, WAV body, frame, backend or network policy was
involved. The projection omits full multipart allocation/append/write behavior;
the host allocator is not the frame's PSRAM allocator. Physical response faults,
Standard parser equivalence and complete transport/cleanup behavior remain open.
C05/D01 are not closed.

Private artifacts: `voice-presign-pass1.txt` through `voice-presign-pass3.txt`,
`voice-presign-gnu.mjs`, `voice-presign-boundaries-gnu.txt`,
`voice-presign-literals.jsonl`, `voice-presign-fixture.c`,
`voice-presign-results.jsonl` and `voice-presign-evidence-hashes.txt`.

## Outbound local-name resolution: C01/S02/E02

Ten complete paired functions cover hostname classification, query/cache state,
the TCP/IP-thread handoff and the ESP-TLS hostname-to-socket helper. Both pinned
images pass byte, entry, contiguous-range and internal-target checks across
1,339 instructions, 246 branches and 52 ranges each. All 29 direct-call pairs
and 50 literal pairs are reviewed separately. This extends the public map to
219 function pairs without claiming complete firmware equivalence.

The [local-name findings](boot-and-scheduling.md#outbound-local-names-and-blocking-resolution)
include case-sensitive multicast classification despite case-insensitive cache
and pending-query matches, four query/four callback limits and the absence of an
HTTP deadline argument at the blocking DNS barrier. A mistaken constant-offset
candidate for Standard's transport helper was rejected; its verified entry is
`0x420c3424`, while `getaddrinfo` is `0x420c5320`. Correct entries, bytes and
complete paths are checked independently.

Twenty-three host cases passed with `clang -std=c11 -Wall -Wextra -Werror
-fsanitize=address,undefined -g`. Three unchanged functions are extracted from
lwIP commit `fa4dffdfac52587a26c1f29258376df750cf8474`, the submodule pinned by
ESP-IDF v5.4.1. The fixture reconstructs the applicable configuration and asserts
the 24-byte IP-address and 296-byte cache-record layouts. Sends, timers and PCB
allocation are stubs; numeric-address parsing uses the host library and is not
the subject of these cases. Case comparison uses the host case-insensitive
routine for the ASCII test names. No resolver response packets or real waits
are simulated, and vendor machine code is not executed.

| Private artifact | SHA-256 |
| --- | --- |
| Pinned `dns.c` | `9bd5eb675274eb9e0025cc6af76afe16eb3328de22fab3bb202a9f3bb13ab0d7` |
| Three extracted functions | `093bb08ab357c30fcc0015af11e9a4606bd658dd0ff2ca07b36b7ae7b49b882f` |
| Host fixture | `835639368c582326bb3a10d2b5c66e1227cb2ab323195a15ad85b20cbc3efaa3` |
| 23-case JSONL results | `089932ec470b2939411d42b1e10c8b8461f1822ed115b10efca415683c3feb96` |

Private artifacts also include `local-resolver-pass1.txt` through
`local-resolver-pass5.txt`, per-function `local-resolver-*-cfg.json`/`.txt`,
`compare-standard-local-resolver.mjs`, `standard-local-resolver-comparison.json`,
`standard-local-resolver-boundaries-gnu.txt`, `extract-local-resolver.mjs` and
`local-resolver-fixture.c`. No physical frame, DNS/router policy, HA source or
deployment changed. C01/S02/E02 remain open for packet/transport faults, fresh
local-backend resolution, multicast/TLS compatibility and actual offline behavior.

## DNS reply acceptance: C01/S02/E02

Four complete paired GNU bodies cover question-name comparison, answer-name
skipping, response parsing and successful completion. All 652 instructions,
122 branches and 11 ranges per image match after call/literal relocation.
Nine direct-call pairs and nine literal pairs are reviewed, including the complete
256-byte character-classification table. The public function map now has 222 pairs.

Twenty-six host packet cases passed with the same compiler/sanitizer settings
as the hostname fixture. Four unchanged functions come from the same pinned
lwIP source; bounded pbuf-access stubs and callback capture replace packet buffers
and application callbacks. The single address slot and family/state fields match
the recovered layout. Backup-server availability is fixed false. Network delivery,
chained buffers, elapsed time, callback re-entry and retry scheduling are excluded.

The [reply contract](boot-and-scheduling.md#dns-replies-for-a-local-backend)
distinguishes ignored packets, failure callbacks and successful cache publication.
It includes exact IN-class requirements, missing question/transaction rejection,
TTL handling, permissive question/owner checks and a two-packet partial-state
sequence. These are host results with matching static branches, not physical
multicast or frame-failure observations. No DNS/router/HA/device changes were made.

| Private artifact | SHA-256 |
| --- | --- |
| Four extracted functions | `2e9f0d14cc1a417944aad726cb91fb960d58e3b32969d06392289f50eb879f3d` |
| Reply host fixture | `0ee21af9289d54c0213edadd1ed9fd90a25b609f9b60e7470bf120b4d9ec8eba` |
| 26-case JSONL results | `da9daec750abdf5cf51dd530036e82e6694819428ae0aa31e462a2b00085d926` |

Private artifacts: `dns-reply-pass1.txt`, `extract-dns-reply.mjs`,
`dns-reply-selected.inc`, `dns-reply-fixture.c`, `dns-reply-fixture-results.jsonl`,
per-function `dns-reply-*-cfg.json`/`.txt`, `compare-standard-dns-reply.mjs`,
`standard-dns-reply-comparison.json`, `standard-dns-reply-boundaries-gnu.txt`
and `dns-reply-evidence-hashes.json`. The earlier hostname fixture was rerun after
adding an explicit successful return so its definitions can be reused by this
harness; all 23 results remain identical. Its source hash above is updated, and
the earlier copied DNS-source checksum is corrected to the full verified SHA-256.
C01/S02/E02 remain open for real-network behavior and the excluded fault paths.

## Connection address families and timeout scope: C01/C03/S02/E02

Nine selected transport/TLS functions are compared across 728 Large and 729
Standard instructions, 101 branches and 26 contiguous ranges per model. One
Standard literal-load/indirect-call pair replaces a Large direct socket-connect
call. Its pointer value and consecutive instruction bytes are verified before
normalization; every other operation and internal branch relationship matches.
The public model map now contains 231 pairs. An additional Large-only pass
verifies the complete HTTP initializer and common-options helper across 525
instructions and 20 ranges.

The [connection findings](cloud-protocol.md#address-selection-does-not-recover-from-a-bad-ipv4-destination)
separate IPv4-preferred DNS and empty-A-response fallback from later TCP/TLS
errors. The recovered attempt uses one address, with no alternate-family restart
after connection failure. The synchronous TLS deadline check cannot interrupt
a lower-level blocking operation and is skipped on a successful return. These
are static boundaries supported by the pinned SDK call structure, not measured
deadlines or induced failures. No additional host test, physical frame request,
network-policy change or HA deployment was performed.

Private artifacts: `transport-family-pass1.txt` through
`transport-family-pass4.txt`, `standard-transport-family-pass1.txt`,
per-function `transport-family-*-cfg.json`/`.txt`,
`compare-standard-transport-family.mjs`,
`standard-transport-family-comparison.json`,
`standard-transport-family-boundaries-gnu.txt` and the pinned
`transport-family-ssl.c` / `local-resolver-esp-tls.c` references.
The socket/select/allocator/TLS callees are not all recursively compared; actual
IPv6 compatibility, retry sequences, network faults and timing remain open.

## Reset cache checks and subsequent writes: N02/N03/H05/C11

Fifteen complete Large helper bodies were checked against the pinned application
with GNU disassembly: 661 instructions, 68 branches and 31 contiguous ranges.
Entry prologues, instruction bytes, reachable branch destinations and coverage
are checked independently of Ghidra's inferred function ends. The additional
storage-sleep caller establishes the order of marker writes, repeated teardown
and the final timestamp attempt.

The [reset follow-up](storage-and-configuration.md#cached-identity-and-later-writes-after-reset)
separates initialized account RAM from persisted identity and SDK credentials.
Successful driver deinitialization prevents the STA getter from simply returning
old configuration; the fallback checks the SDK SSID blob length. The configured
branch and first-time-flag erase require both credential and account predicates.
Dirty statistics can be written after the NVS erase, with a second attempt on
storage-sleep entry if the first failed. Later sleep markers and timestamp are
separate unchecked/partly checked writes, not an account restore transaction.

Private artifacts: `reset-cache-pass1.txt` through `reset-cache-pass4.txt`,
`run-reset-cache-cfg.mjs`, `reset-cache-summary.json` and per-function
`reset-cache-*-large-cfg.json`/`.txt`. These are static results only: no reset,
live HTTP request, network change, new host fault fixture or firmware write was
performed. Standard comparison, recursive SDK cleanup, concurrent writes and
final state after interrupted shutdown/reboot remain open.

## Image-cache persistence and FAT recovery: N04/N05/E02

Nine complete paired application/SDK bodies cover 796 instructions, 84 branches
and 29 contiguous GNU ranges per image. Bytes, prologues, full reachable paths,
24 direct-call pairs and 70 literal pairs are checked. The save-capacity literal
is model-specific; selected control flow otherwise matches after relocation.
Seven additional pairs bring the public map to 238 entries. External stdio, FAT
and wear-leveling implementations are not recursively proved by this comparison.

The [cache and recovery findings](storage-and-configuration.md#formatting-permission-is-not-proof-that-formatting-happened)
separate permission, actual formatting, later mount success and the application's
log. Twenty-four host case groups passed with C11, Wall/Wextra/Werror and
AddressSanitizer/UndefinedBehaviorSanitizer. One unchanged function is extracted
from ESP-IDF v5.4.1's pinned `vfs_fat_spiflash.c`; application provisioning/retry
branches are reconstructed from the GNU trace. FAT calls and allocation outcomes
are controlled stubs. The helper's allocation-unit clamp matches the recovered
4,096–524,288-byte bounds. No actual filesystem image, wear-leveling driver,
stdio write/read failure, interrupted flash operation or elapsed wait is tested.

| Private artifact | SHA-256 |
| --- | --- |
| `last-cache-vfs_fat_spiflash.c` | `d74685433df3f0c083668c66e17941f09321db97a668724357ef5d63149a6063` |
| `last-cache-sdk-selected.inc` | `3f126b991e12d83bbbf9b86ec75a33599bfe2969d809a79ebcf2f732f40361ef` |
| `last-cache-fixture.c` | `aa9767afab37dca849e109461a75454777fe4a0b3a9ee0d8d95b58e048e2983c` |
| `last-cache-fixture-results.jsonl` | `0247daa01fdea72b730bfe288101ace26590164997ff4fb4b0f20f1a67ea43a0` |

Other private artifacts: `last-cache-pass1.txt` through `last-cache-pass3.txt`,
per-function `last-cache-*-cfg.json`/`.txt`,
`compare-standard-last-cache.mjs`, `standard-last-cache-comparison.json`,
`standard-last-cache-boundaries-gnu.txt` and `extract-last-cache.mjs`.
No frame request, artwork change, reset, firmware write, network-policy change
or HA deployment occurred. N04/N05 stay open for actual filesystem/storage
faults, cleanup, concurrency and final recovery on the installed layout.

## Failed-mount resource ownership: N04/E01/E02

Three additional complete paired GNU functions verify wear-level allocation,
FAT VFS unregistration and disk I/O cleanup: 232 instructions, 24 branches and
six ranges per model. Four direct-call pairs and 26 literal pairs are reviewed;
the public map now has 241 pairs. The allocator has eight slots and publishes
only after its own initialization succeeds, while the previously compared FAT
wrapper has no wear-level release in its later error cleanup.

Twelve host case groups passed with the same C11 warning/sanitizer settings as
the recovery fixture. An unchanged SDK wrapper is extracted from the same
SHA-pinned `vfs_fat_spiflash.c` and reuses the unchanged format helper. The
wear-level dependency models the verified slot allocation, and the VFS/disk
operations record registration state. Controlled failures show which exits
retain a slot, a later successful retry with an earlier retained slot, and eight
retained slots preventing a ninth FAT attempt. This is resource accounting, not
execution of the driver, flash operations or a measurement of retained heap.
Fixture contexts are freed explicitly after assertions; sanitizer success is
not a claim that the firmware releases these resources.

| Private artifact | SHA-256 |
| --- | --- |
| `last-cache-sdk-wrapper.inc` | `2c61d84376dffe7a9545005bf841e3eb3b9b2890682cd481d67a3924f9724549` |
| `last-cache-cleanup-fixture.c` | `cc5f8fb8171f83f706223e0c08ca80a4c803787155ec7534e97a29f13922c865` |
| `last-cache-cleanup-fixture-results.jsonl` | `a3fbab478efa1e701eed50df13b02a520d28492f758c98e74ebe5e1acffb8f8d` |
| `last-cache-wear_levelling.cpp` | `880e32476dd5ef0ed1319dac44b732685dc6ca87330e6aa804d95ba31278b740` |

Other private artifacts: `last-cache-cleanup-pass1.txt`,
`last-cache-{wl-mount,diskio-clean,vfs-clean}-*-cfg.json`/`.txt`,
`compare-standard-last-cache-cleanup.mjs`,
`standard-last-cache-cleanup-comparison.json`,
`standard-last-cache-cleanup-boundaries-gnu.txt` and
`extract-last-cache-cleanup.mjs`. No device, artwork, network or HA changes were
made. Remaining cleanup callers, actual allocator/driver behavior, concurrency,
interrupted storage and physical recovery remain untested. No causal connection
to the earlier observed TLS allocation failure has been established.

## FAT registration error output and allocation requests: N04/E01/E02

A complete paired registration body adds 83 instructions, 13 branches and four
GNU ranges per image, with four direct-call and eight literal pairs reviewed.
The public map now contains 242 pairs. First twelve core/directory slots and
sixteen directory callbacks are checked as pointer tables rather than treating
a binary table as a terminated string; callback bodies and optional table tails
are not all validated.

The [registration output trace](storage-and-configuration.md#existing-vfs-registration-does-not-supply-a-filesystem-pointer)
shows the accepted `0x103` path leaves the filesystem pointer unset. The mount
wrapper's stack slot is not initialized before that call. This is static
evidence of a conditional uninitialized-value handoff, not an induced crash.
The earlier cleanup fixture's injected-invalid-state case supplies a valid
pointer, so it is only a wrapper status test. Its label is clarified and all
twelve groups rerun successfully; the two affected hashes above are updated.
No host execution of an uninitialized pointer was attempted.

The four-file configuration requests 25,376 bytes for the FAT context and file
structures, plus sixteen flag bytes. Other allocations, allocator overhead and
memory placement are excluded. No causal link to observed TLS memory errors is
established. Private artifacts: `cache-registration-pass1.txt`,
`cache-registration-{large,standard}-cfg.json`/`.txt`,
`compare-standard-cache-registration.mjs`,
`standard-cache-registration-comparison.json` and
`standard-cache-registration-boundaries-gnu.txt`. No device, storage, network
or HA changes were made; runtime reachability, concurrency and recovery remain open.

## FAT cache replacement and late sync errors: N05/E01/E02

Seven complete FAT/VFS rename, sync, close and error-mapping bodies match across
384 instructions, 93 branches and sixteen ranges per model. Twenty direct-call
and thirteen literal pairs are reviewed. The function map reaches 249 entries.
The [replacement/sync findings](storage-and-configuration.md#rename-does-not-replace-an-existing-cache-file)
connect existing-destination rejection with the file-modified flag cleared after
a failed late filesystem sync, and distinguish the earlier retryable buffer-write
error. These are selected function comparisons, not whole-driver equivalence.

Six host case groups passed using unchanged ESP-IDF v5.4.1 FatFs sources, C11,
Wall/Wextra/Werror, AddressSanitizer and UndefinedBehaviorSanitizer. The fixture
uses an 8 MiB RAM FAT12 image with 4,096-byte sectors, two FAT copies, heap
255-character long names, per-file sector buffers, no shared-file lock table
and single-thread mutex stubs. ASCII paths avoid dependence on the selected
437 code page. The target's relevant branches match; the fixture does not claim
all firmware build settings or the target ABI are reproduced.

The metadata failure is targeted to the file's directory sector, rather than
the first arbitrary write during sync: earlier FAT/data writes can take different
error branches. After this failure, a successful second sync and close perform
no additional write, and unregister/remount discards the filesystem window; the
RAM image still contains the old zero-length entry. A separate file-buffer fault
remains retryable. A CTRL_SYNC error case confirms lack of retry without claiming
media loss, because the RAM disk stores completed writes immediately.

| Private artifact | SHA-256 |
| --- | --- |
| `fat-cache-fixture/ff.c` | `b6511bc0102f42b941897cd9f96f75206b6851fedbebc6dcb17c220cb1d4bede` |
| `fat-cache-fixture/ff.h` | `90d3efa38c24078651702dd5997ac022ddef127f336f25b9aac1eafcdbb660fc` |
| `fat-cache-fixture/ffconf.h` | `27e92e97b5744d7cd0b5e9e82a885601c8eb358fbf22f1a9baec0c1246bd7f3a` |
| `fat-cache-fixture/diskio.h` | `60beaaca712a9d5126f41362fa68ce7f30e26e115b310a20d79e5639b6fcc3b5` |
| `fat-cache-fixture/ffunicode.c` | `f2e03e97fccd9d7b0614b48ee02b7e49fb21c5196d3ff77ba5d8e4558a064d5d` |
| `fat-cache-fixture/sdkconfig.h` | `80451c4e17c5f8d9adf9ce3d2d44cc6033192d80a1a37537dc8ce6652d69c503` |
| `fat-cache-fixture/cache-fixture.c` | `a9f433858ecb09f31bc7a92298cb7b2c1ea4cf799945186bb063963c0231f3a6` |
| `fat-cache-fixture/results.jsonl` | `335b7217177912468e30baf8a0884bf57d52655440b43b94542576c87347b4e7` |

Other private artifacts: `cache-replace-pass1.txt`/`cache-replace-pass2.txt`,
`run-cache-replace-cfg.mjs`, per-function `cache-replace-*-cfg.json`/`.txt`,
`compare-standard-cache-replace.mjs`, `standard-cache-replace-comparison.json`,
`standard-cache-replace-boundaries-gnu.txt` and the fixture's
`evidence-hashes.json`, which also pins its two FreeRTOS compatibility headers.
No frame, artwork, flash, network or HA changes were made. Installed FAT geometry,
wear leveling, torn writes, concurrency and physical power-loss recovery remain
open; successful RAM remounts are not a power-loss atomicity guarantee.

## FatFs allocation-region preference: N04/E01/E02

Three paired allocation/free/preference helpers add 68 instructions, seven
branches and four GNU ranges per model. Two direct-call and six literal pairs
are reviewed, including identical masks `0x1400` then `0x1800`. The allocator
stops on first success; FatFs requests PSRAM/default capability first and
internal/default second. The public map now contains 252 pairs.

This refines the four-file 25,392-byte allocation accounting: the two allocations
independently prefer PSRAM rather than always consuming internal memory. It does
not establish actual placement, allocator fragmentation, failure-handler behavior
or a causal link to TLS memory pressure. No additional host/device fault test
was run. Private artifacts: `cache-allocator-pass1.txt`/`cache-allocator-pass2.txt`,
per-function `cache-allocator-*-cfg.json`/`.txt`,
`compare-standard-cache-allocator.mjs`, `standard-cache-allocator-comparison.json`
and `standard-cache-allocator-boundaries-gnu.txt`. No frame, network or HA
changes were made.

## TLS setup allocation and version boundaries: C03/E01/E02

Fourteen paired GNU bodies cover handle construction, SSL setup, negotiating
allocation, allocator dispatch/port, checksum setup, digest allocation, defaults,
configuration/version validation and selected outer/SSL cleanup. All 644
instructions, 100 internal branches and 36 reachable ranges per image match
after address normalization. Forty-three direct-call and 48 literal pairs are
mapped separately. Seven immutable preset/profile tables are byte-compared at
their explicit lengths; RAM configuration references remain runtime values.
Both allocator slots' initial function pointers select the compared internal-only
port. Reference audits found their dispatch readers and no direct writer.

The matching Mbed TLS source is ESP-IDF v5.4.1's submodule commit
`98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8`. Two functions, `mbedtls_ssl_setup`
and `ssl_handshake_init`, were extracted unchanged from
[the pinned source](https://raw.githubusercontent.com/espressif/mbedtls/98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8/library/ssl_tls.c).
The host fixture selects their recovered TLS 1.2 allocation branches with
target-sized opaque structures. Configuration checks, checksum initialization,
object initialization and derived-buffer-pointer reset are explicit stubs.
It does not reproduce the target's complete configuration, struct layout, ABI,
crypto, heap regions or any socket operation.

Eight groups passed under C11, Wall/Wextra/Werror, AddressSanitizer and
UndefinedBehaviorSanitizer: successful ordered allocation, independent failure
at each of five sites, propagated checksum failure, and a pre-allocation
configuration error. Each of the first five failure cases returns `-0x7f00`
with the traced allocations freed and pointers cleared. A checksum error retains
the three negotiating objects for outer cleanup; assertions inspect that state
before explicit harness disposal. This is not evidence that every real cleanup
path is leak-free. No allocation was failed on either frame.

Private artifacts include `tls-allocation-pass1.txt` through `pass7.txt`, Standard
reference passes, `run-tls-allocation-cfg.mjs`, per-function
`tls-allocation-*-cfg.json`/`.txt`, `compare-standard-tls-allocation.mjs`,
`standard-tls-allocation-comparison.json`, `extract-tls-allocation.mjs` and
`tls-allocation-evidence-hashes.json`. No frame, network, artwork or HA change
was made. Actual failure identity, fragmentation, concurrent-request effects,
full external cleanup and negotiated TLS behavior remain open.

| Private artifact | SHA-256 |
| --- | --- |
| `tls-allocation-ssl_tls.c` | `32bd6c6b487dd4a67998ced23a03e641eba7d4e54f5ba4887c4cf199d8716df6` |
| `tls-allocation-esp_tls_mbedtls.c` | `ad6f9f8e3224e546f62f61925ced0221c9d16c66d14554fea8b47e0c4c6cbdfe` |
| `tls-allocation-esp_mem.c` | `5b4d710ddb779b83c36aadb861bbfa1e59dac236e72f4b545fad2fb2f5154bb0` |
| `tls-allocation-selected.inc` | `b3f3f1e90b55d35bb8c358b83abf06d49e720c664395ea54bb307b8510b65056` |
| `tls-allocation-fixture.c` | `0eeac85c3ca86a09146425856068fa39a18fe177aecf29546e89e8bc5c67af8e` |
| `tls-allocation-fixture-results.jsonl` | `ff5ac7b37c19562bf0f32cfac18a9085001f1e1b62db2b9245accddda3e5dd85` |

## Compiled TLS cipher inventory and name handling: C03/E02

Six complete paired GNU bodies add 425 instructions, 69 branches and 21 ranges
per image. Sixteen direct-call and 37 literal pairs are mapped. Definition
records are sixteen bytes each: ID, name pointer, cipher/hash/key-exchange/flags
bytes and two version fields. All 58 records were compared after dereferencing
the names; all 185 preference IDs and their zero terminator were independently
byte-compared. The list's 58-entry capacity and zero-return removal predicate
retain all definitions in the reconstructed filtered preference order.

The sanitized [cipher inventory](tls-capabilities.json) contains only cipher IDs
and names, model hashes and evidence limits. It does not export arbitrary binary
data. No new source fault fixture or live TLS test was run. Static hostname and
ALPN setter boundaries are distinguished from current application configuration,
ClientHello serialization, later filtering and negotiated interoperability.

Private artifacts: `tls-ciphers-pass1.txt`/`tls-ciphers-pass2.txt`,
`tls-ciphers-standard-pass1.txt`, `run-tls-ciphers-cfg.mjs`, per-function
`tls-ciphers-*-cfg.json`/`.txt`, `read-tls-ciphers.mjs`,
`tls-ciphers-decoded.json`, `compare-standard-tls-ciphers.mjs` and
`standard-tls-ciphers-comparison.json`. The reference structures and selection
algorithm are from [pinned Mbed TLS](https://raw.githubusercontent.com/espressif/mbedtls/98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8/library/ssl_ciphersuites.c).
No frame, network, artwork or HA change was made.

## ClientHello field serialization: C03/E01/E02

Six complete paired GNU bodies add 427 instructions, 97 branches and 28 ranges
per model. Ten direct-call pairs are mapped; all three literal values are equal.
The body writer's complete branches establish calls to the SNI, ALPN and cipher
writers and propagation of their errors. Other extension and outer send helpers
are not recursively covered by these six pairs.

Fourteen host case groups use five unchanged functions from pinned Mbed TLS
`98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8`: the three field writers, cipher
validator and EC-use predicate. The lookup fixture uses the 58 decoded records;
small host structures expose only consumed fields, and a compatible bounded-write
macro replaces the original header context. The selected TLS 1.2/renegotiation
branches match the binary. This is not the complete target ABI or build config.

Cases check absent/normal/255-byte/empty SNI and insufficient capacity; absent,
two-name and empty ALPN lists plus partial-output failure; all 58 cipher IDs and
initial SCSV, renegotiation omission, unknown-ID filtering and partial-buffer
failure; and null/version-range validation boundaries. C11, Wall/Wextra/Werror,
AddressSanitizer and UndefinedBehaviorSanitizer passed. Test protocol names and
hostnames are synthetic and do not imply application configuration or server
acceptance. No cryptographic handshake, socket, TLS record or live device is
involved.

Private artifacts: `tls-hello-pass1.txt`/`tls-hello-pass2.txt`,
`run-tls-hello-cfg.mjs`, per-function `tls-hello-*-cfg.json`/`.txt`,
`compare-standard-tls-hello.mjs`, `standard-tls-hello-comparison.json`,
`extract-tls-hello.mjs` and `tls-hello-evidence-hashes.json`. Source writers are
from [pinned ssl_client.c](https://raw.githubusercontent.com/espressif/mbedtls/98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8/library/ssl_client.c).
No frame, network, artwork or HA change was made. Physical negotiation, remaining
extensions, application ALPN settings and outer send handling remain open.

| Private artifact | SHA-256 |
| --- | --- |
| `tls-allocation-ssl_tls.c` | `32bd6c6b487dd4a67998ced23a03e641eba7d4e54f5ba4887c4cf199d8716df6` |
| `tls-ciphers-ssl_ciphersuites.c` | `c1ea9c74805e037bc1f67eca7aecfcc4e9151bd5dfc944ecbc688c2b0c624ca7` |
| `tls-ciphers-ssl_client.c` | `3e3b58651f7a22ab988831904b0d13d21d593b26dce1a3b36c23112595b7b9ab` |
| `tls-hello-selected.inc` | `8570aa42e819c72916d54aec6ccb42f3384ecd60c8de8a3e26e51d10ece1a1bd` |
| `tls-hello-ciphers.inc` | `f5560c9a3fe35bf7b5d4c7ea0b0d6643a823b18369db54d3e27d524df3cddd69` |
| `tls-hello-fixture.c` | `f0d307422c330766a9d1994f65904852354f32a99a7dfdc047defcbff1df7247` |
| `tls-hello-fixture-results.jsonl` | `0ce86837c4bc990cace5df7b01723101e7d1ec2ad9d17240e7b2bdcfb956ec7c` |

## Stock HTTP ALPN configuration and submission boundary: C03/E01/E02

Twenty-four complete paired GNU bodies add 727 instructions, 121 branches and
42 ranges per image. Twenty-one direct-call and 53 literal pairs are mapped;
code-pointer literals either name compared setters or separately identified
runtime/HTTP callbacks. This extends the earlier Large-only HTTP constructor
and common-options analysis to Standard and audits their relevant option writes.

The earlier paired zero-initialized transport allocation leaves its config's
first pointer, ALPN, null. Fifteen resolved TLS/context setters modify other
fields; two keep-alive/interface wrappers call the compared setters, and the
default-port setter writes the separate transport object. The recovered HTTP
construction therefore does not set ALPN. This bounded negative finding is not
an audit of every computed memory write or every possible TLS consumer.

Four ClientHello helpers establish 4,092 bytes available after the four-byte
header, checked body/transcript construction before finish, and advancement to
ServerHello only after finish success. No new host fixture was run. The previous
field fixture's partial memory output is not evidence of transmission: this
caller skips finish after a body error. Full record buffering/retry and socket
delivery were not recursively validated.

Private artifacts: `tls-hello-send-pass1.txt`/`tls-hello-send-pass2.txt`, Standard
reference passes, `tls-http-options-pass1.txt`/`tls-http-options-pass2.txt`,
`tls-http-port-pass1.txt`, `run-tls-http-cfg.mjs`, per-function
`tls-http-*-cfg.json`/`.txt`, `compare-standard-tls-http.mjs` and
`standard-tls-http-comparison.json`. No frame, network, artwork or HA change
was made. Physical interoperability, complete record/socket faults, other
extensions and other TLS construction paths remain open.

## OTA write lifecycle and encrypted boundary fixtures: R12

Six complete GNU function pairs cover begin, write, abort, end, handle lookup
and the OTA-partition predicate: 326 instructions, 69 branches, 20 ranges per
image, seven direct-call pairs and eighteen literal pairs. Entry prologues and
all recovered instruction bytes were checked against the pinned application
images; normalized operations and internal branch targets match. Standard
write/begin were located from their own log-string references. Handle lookup
has a different relocation from write/begin and was followed from its actual
call target. External partition, image-verifier and allocator bodies are not
recursively compared here.

The host fixture extracts the six unchanged functions and their original list
structure/globals from ESP-IDF v5.4.1 `esp_ota_ops.c`. It uses the rollback-enabled
branch, Linux list macros, native host pointers/size_t, an 8 KiB RAM partition
with 4 KiB sectors, and stubs for partition identity, running-image state,
encryption enablement, allocation, erase, write and image verification. The
target allocates a 44-byte OTA context; the host layout is not a target-ABI
emulation. Bounded test lengths avoid host/target size_t overflow differences.

Twenty-two case groups pass under Clang address/undefined-behavior sanitizers.
They cover pre-mutation guards, state-read failure, erase modes, allocation and
erase errors, bad first magic, zero/invalid handles, ordinary two-sector writes,
write failure, end/abort cleanup, verifier failure, buffered encrypted writes,
end-flush errors, the 4,095 + 2 boundary with two controls, independent handle
removal and the distinction between begin's erase hint and a write-size limit.
All cases explicitly finish/abort their test-owned handles; this is not a
whole-firmware leak audit or a real image-verification test.

The [OTA findings](ota-and-recovery.md#conditional-encrypted-write-sector-gap)
record the missing sector-one erase before the encrypted final block. The RAM
write stub records erase coverage but deliberately allows the copy; it neither
encrypts nor models flash bit transitions. First partial-buffer tail bytes also
start zeroed from calloc; after a successful buffered-block flush the code fills
the scratch block with `0xff`. This byte-detail assertion is not a conclusion
about valid-image padding or physical acceptance.

Private artifacts: `ota-write-refs.txt`, `ota-write-*-cfg.json`/`.txt`,
`compare-standard-ota-write.mjs`, `standard-ota-write-comparison.json`,
`extract-ota-write.mjs`, selected source, fixture and result manifest below.
No frame, router, flash, artwork or HA state was changed. R12 stays open for
outer updater faults, safety gates and deferred physical validation.

| Private artifact | SHA-256 |
| --- | --- |
| `ota-write-esp_ota_ops.c` | `e26eed5adce220a6283c74d02b7935a495391389632708c7e4c3557c2d454677` |
| `ota-write-esp_ota_ops.h` | `3180b53e56804f95d69f0fa3037c571f6548a908fc97b02c9a1c09e20e030779` |
| `ota-write-selected.inc` | `69118251a0be1812a50822ec40ffc58b430c7bc47b9cd53a9e32bf2ccc11f4a6` |
| `ota-write-fixture.c` | `3056628571b2e95ff7d871d07a339397f6ae0c9636f00ea56095b3d9d1a6a5ac` |
| `ota-write-fixture-results.jsonl` | `7e473d09573eeb73d70928fb035604b438deb7b36cb11ec4e13a0cef8f42f887` |

## Upload acknowledgment framing and early success: C05/C08

Twenty-four isolated cases use the matching SDK HTTP parser source, unchanged
header-fetch/read/cache-cleanup/completion helpers and selected unchanged
message/headers/body callbacks. Only header fetching is called by the exercised
uploader branch; the fixture does not read the acknowledgment body afterward.
The application return/status/abort decision is a bounded reconstruction of
`0x420271fb` through `0x420272b8`, covered by the earlier complete multipart
comparison. It narrows the 64-bit SDK return with an explicit 32-bit bit-pattern
copy rather than relying on host signed-conversion behavior.

Five additional complete GNU pairs validate headers-complete, body caching,
message-begin/end and fetch: 194 instructions, 22 branches, seven ranges per
model, four direct-call and fifteen literal pairs. Instruction bytes and entry
prologues match the pinned images. External HTTP event/header handling, parser
internals, allocator and transport helpers are not recursively compared here.

The fixture uses a 4,096-byte receive buffer, the uploader's 120-second per-read
timeout argument, scripted byte groups and the real parser for HTTP framing.
Message-begin resets chunk flags as in the app. Header-storage/event callbacks
are stubbed; unused chunk notifications are omitted. Shared-client registration,
unregistration, socket close, full HTTP cleanup and outer-worker cancellation
are not executed. Cached-body allocations are released explicitly by the SDK
cache cleanup after each assertion; this is not a complete cleanup/leak audit.

Cases cover nine explicit-zero status variants, ordinary positive JSON length,
three chunked-body boundaries, two close-delimited bodies, invalid chunk syntax
after headers, separated/coalesced 100/200 responses, two abort-flag combinations,
two header timeouts and two oversized length values. All 24 pass with warnings
treated as errors and Clang address/undefined-behavior sanitizers. The
[voice contract](voice.md#upload-acknowledgment-parser-and-early-success-boundaries)
records acceptance separately from HTTP completion and recommends one final
200/zero-length response after complete WAV storage.

Private artifacts: `voice-ack-*-cfg.json`/`.txt`,
`compare-standard-voice-ack.mjs`, `standard-voice-ack-comparison.json`,
`voice-ack-prefix.c`, `voice-ack-cases.c`, assembled fixture and hashes below.
R12 remains deferred at the owner's request; no unfinished OTA fixture results
are included in this C05 pass. No frame, router, recording, artwork or HA state
was changed.

| Private artifact | SHA-256 |
| --- | --- |
| `voice-http-fixture/esp_http_client.c` | `7aabd415f3a39675e59f591919b9e88e31213e548b010cb0809a888d2b0ceef2` |
| `voice-http-fixture/http_parser.c` | `c164edcb06099b026e7ed853ed4d25536e83b4463d5e79921b28621e16588455` |
| `voice-http-fixture/http_parser.h` | `21fcfe834198349472a878e0334dd74b8571fafc70c6dd701169f525dd463041` |
| `voice-http-fixture/selected-sdk-functions.inc` | `965c4cf08b3eec4b2cfea18f69b72b189ec007dd60b55af663de55e55aac0e24` |
| `voice-ack-message-begin.inc` | `7a7c4827a4e12a0c5287e87947e2fb654de4741e9a2270f3164cabb9c67009a2` |
| `voice-ack-fixture.c` | `20c66a33c0cdcc6764226c0567e2081ea58c253f7b57b8491ffe6183a5ba42a0` |
| `voice-ack-fixture-results.jsonl` | `e373113189033e8d53550dbf13e1750be180f88cf7c0e78c7c3f15813cbd784c` |

## Finalize HTTP status and framing: C07/C08

Thirty-one host cases combine the unchanged SDK parser and selected
header-fetch/body-read/cache-cleanup/message callbacks from the
[acknowledgment pass](#upload-acknowledgment-framing-and-early-success-c05c08)
with pinned cJSON 1.7.18. A bounded reconstruction follows the response branch
after successful request transmission in Large `0x42027380`: retain the low
32 bits of fetched length, conditional abort read, sample status/time, one
4,095-byte body read, exact-200 decision, termination, JSON lookup and result
copying. Register/unregister, logging, socket close, full client cleanup and
worker execution remain outside the fixture. Rejected output records stay
unchanged, checked byte-for-byte.

The existing complete 607-instruction finalize comparison with Standard
`0x42025dd0` covers these application branches; no new function-pair count is
claimed. The SDK callbacks/fetch comparison from C05 and the earlier reader
trace supply the transport/parser linkage. Header storage/events are stubbed,
chunk notification callbacks are omitted, and the transport supplies scripted
byte groups with virtual delays. `Retry-After` behavior is grounded in the
static worker/caller path and SDK header handling, not a modeled retry engine.

Cases cover ten statuses carrying the same ready JSON, two empty responses,
two misleading success/status combinations, a pending-job response, three
chunked/close-delimited cases, four informational-response groupings, a slow
503, four oversized-length/abort combinations, two header timeouts and two
post-header abort-flag cases. All 31 passed on Omarchy with Clang 23.1.3, C11,
`-Wall -Wextra -Werror`, AddressSanitizer and UndefinedBehaviorSanitizer.
The [voice contract](voice.md#finalize-http-status-framing-and-failure-ordering)
separates parser acceptance, complete HTTP reception and worker implications.

The 1,198-second error-body delay is simulated; no real delay, task lifetime,
watchdog or device behavior is established. Tests of declared multi-gigabyte
lengths supply only short messages. No allocation fault, TLS/socket delivery,
concurrent cancellation or actual image handoff is exercised. No frame,
network, artwork or HA state changed. C07/C08 retain their physical unknowns;
R12 remains deferred.

Private artifacts: `finalize-http-cases.c`, assembled `finalize-http-fixture.c`,
`finalize-http-results.jsonl`, `finalize-http-hashes.json`, the earlier complete
`finalize-large-cfg.txt`, `standard-finalize-comparison.json` and upload-worker
traces. SDK/parser hashes are unchanged from the acknowledgment pass; cJSON
source/header hashes are recorded in the
[field-parser contract](voice.md#finalize-response-fields-and-host-parser-checks).

| Private artifact | SHA-256 |
| --- | --- |
| `finalize-http-fixture.c` | `41dd9717b4973b65209576ce069e6ee63115423b4615d4c29c21251c29e21ef4` |
| `finalize-http-results.jsonl` | `f7ecae23a1cf6bca0852eb68952cb014a993b451aab8c13e9fc2440704d0dda3` |

## Backend deployment boundaries: A05

Read-only HA-MCP overview, Supervisor app inventory, the `http` YAML fragment
lookup and version-pinned `http/config` WebSocket read establish HA 2026.10.2,
available app management and the active plain-HTTP 8123 configuration. No
configuration write, integration reload, app installation, device request or
network rule change was performed. Integration source is still release
`e5450665ddbb57c2542c883375ba68c0aefbb1b1`.

The [deployment comparison](backend-deployment.md) combines those observations
with HA 2026.10.2's HTTP server, request wrapper, config API, authentication and
SSL utilities. It recommends a companion listener and narrow HA bridge, while
retaining job/artwork ownership in the integration. TLS 1.2 support is verified
in HA's actual context builder; stock-origin certificate trust is a separate
unresolved deployment constraint.

**24 isolated checks passed** on Omarchy with Python 3.14.8 and aiohttp 3.14.5,
the dependency pinned by this HA release. They execute the extracted, unchanged
`request_handler_factory` and `server_context_modern`, with minimal substitutes
for HA application state, token recognition and URL discovery. A synthetic
standalone listener tests credential separation, limits, finite error framing
and sanitized events. The actual wrapper logs a synthetic poll key at debug
level; its waiting handler is cancelled after a loopback TLS client disconnects.

Listeners bound only loopback ephemeral ports and were stopped in `finally`
blocks. The temporary self-signed certificate/key were deleted with their
temporary directory. No real device/HA credentials, audio, artwork, STT or paid
generation were used. Synthetic bridge availability and a frozen byte string
are not a running HA integration, durable job store or model renderer. Existing
WAV and physical protocol evidence is linked separately in the comparison.

A05's original design/host question is now complete. Production implementation,
reload recovery, deployment and physical acceptance retain their own unchecked
criteria; this does not convert those requirements into verified behavior.

Private artifacts reside under `ha-backend-boundary/`:

| Artifact | SHA-256 |
| --- | --- |
| `check_boundary.py` | `59e5799eead5fc2e0e1dbd47a845c60ac11cb461683f0b706d7822afdb8840e2` |
| `results.json` | `fa0f903c379aad6ad564e6da8ff6d8d9b32b0f71e15b4a204ab4f55b465329dc` |
| HA `helpers/http.py` | `17a4c4532b043ea0497fb144c6ac233a8a3546afc819d6df33926eb44d9c6385` |
| HA `components/http/server.py` | `1589da6f3330f52b6d9cc9c6a372a43ede2633b0050fd905839b98363de22e28` |
| HA `util/ssl.py` | `a01e13013955397e13a11aa52b2ed51d3587a5f8b1c2670a2b283ad5e739fe40` |

## Local enrollment continuation: C11

The [local enrollment candidate](cloud-protocol.md#synthetic-local-enrollment-and-identity-continuation)
passed **28 isolated checks** on Omarchy. The fixture runs a loopback aiohttp
service with synthetic local credentials and two preapproved model identities.
Its minimal 64-byte response is fed to a C CLI using the unchanged parser model
from the earlier thirty enrollment groups and actual pinned cJSON 1.7.18.
The CLI was built with `clang -std=c11 -Wall -Wextra -Werror`, address/undefined
behavior sanitizers and frame pointers; no sanitizer finding occurred.

The model parser accepts the nonempty user ID without a returned device key.
Separate Python copies reconstruct the traced sign-in field selection, including
the original request key, verified flag and cleared timezone. Temporary JSON files
model a saved device candidate and a persisted backend binding. Replacing the
backend object/listener and reopening that file preserves voice identity while
leaving enrollment closed. This is not a process-crash, filesystem-durability or
ESP NVS test.

Other cases cover rejected enrollment inputs, a replay within/after the bounded
window, poll/voice identity for both models, exact-length synthetic black setup
assets, missing user ID despite apparent registration, rejection of a response
key as a rotation mechanism, absent verification endpoint, and redacted stored
state/events. The backend has no upstream HTTP client. Voice stops intentionally
after identity validation, before an upload ticket or generation request.

The real sign-in save/reload gate remains established by `0x420192c8` and the
previous GNU-checked `0x4201951a`–`0x4201954a` sequence, not by simulated storage
faults. An accepted binding can precede a failed or partial device save; retry
must preserve identity. No frame was contacted, reset, re-enrolled or changed.
All loopback listeners and temporary state were removed after the run.

C11 now waits only for its deferred physical local-provisioning/reboot criterion.
Neither parser success nor this synthetic continuation closes that criterion.

| Private artifact | SHA-256 |
| --- | --- |
| `check-local-enrollment.py` | `2a14cdbba37a98fa4f678d334e17fdf7ee7defcadbac6f0a15ec505eaf51925e` |
| `enrollment-parser-cli.c` | `01c60474bc819df2772ded221d7011145b5a235205cb1c08e49ee77d464420fb` |
| Extracted `enrollment-parser-core.inc` | `17cc488ed614a232b3229871791b6802f2a3933e40e4eba19a2cf62fbc7aa060` |
| `local-enrollment-results.json` | `01209acf2a42bdb99a092d769f6032194431c4d17a8212b8e0430649b9ae3b73` |

## Two-job and recording interleavings: C08/D05

The private `two-job-interleavings.mjs` ran on Omarchy with **11 assertions** over
bounded transition models, including 70 slot event orders and 45 recording/poll
policy orders. It reconstructs selected application transitions from the existing
GNU-checked helpers and caller traces. This is model exploration, not firmware,
SDK, RTOS, allocator or concurrent socket execution; no physical frame/network
access occurred.

The [voice ownership section](voice.md#bounded-two-job-ownership-and-completion-model)
records the exact event constraints, counts and counterexamples. Two chains of
three/four events yield 35 merges; they run with successful cleanup and with A's
unregister lock timeout injected. The model distinguishes B, live A, no target
and freed-A targets. It labels lifetimes rather than dereferencing real freed
storage. Additional traces cover double/failed-open cleanup and cleanup while
the abort operation holds the slot lock.

Late upload completion is explored separately with an expired borrowed context
and with explicitly assumed stack reuse after a subsequent job's initial drain.
The latter can misattribute status/URL/semaphore completion to the new job.
Another trace exercises the previously identified late-render cancellation flag
reaching the next successful presign. No actual stale result or device crash is
reported; scheduler timing, allocator reuse and indirect stores remain outside
the model.

The recording model preserves each event chain's order, separates backend poll
decision from device consumption and skips presign after an interruption. A
presign hold admits two interrupting orders, a hypothetical immediate recording
event admits one, and a proposed device deferral policy admits none in this
15-order set. The last result is a policy property by construction, not evidence
of implemented firmware. The counts are not probabilities or complete state-space
coverage. HA's already-dispatched sends and real event latency are not simulated.

C08 and D05 now wait for their deferred physical criteria. Stock retry/idempotency
limitations and the earlier bounded server-disconnect fixture remain distinct
from these models. A production adapter, job ownership implementation and actual
frame cancellation still require their stated validation.

| Private artifact | SHA-256 |
| --- | --- |
| `two-job-interleavings.mjs` | `b890396fdbe3854f9f5f4dcb22d5eb1e9a3dd8bcac91625cbaa90293ae92456d` |
| `two-job-interleavings.results.json` | `73b628acaf37832b853360a1f042823ba5643617bc8801d3a94316913c7d113e` |

## Extension negotiation and stock compatibility: A06

The [proposed extension contract](protocol-extensions.md) and public
[message examples](extension-examples.json) separate future capabilities from
the stock `/api/v1/` behavior. This is design research, not an implemented
protocol, backend route or firmware feature.

**26 checks passed** on Omarchy. Eight example bodies run through a C CLI that
reuses the unchanged recovered finalize parser model with pinned cJSON 1.7.18.
It was built with C11 warnings-as-errors, AddressSanitizer and
UndefinedBehaviorSanitizer. No sanitizer finding occurred. The checks distinguish
accepted legacy URLs, ignored capability/status semantics and rejected v2-only
shapes. HTTP status/framing and actual firmware execution are outside this CLI;
the earlier combined finalize pass covers the recovered HTTP layer.

Eighteen additional assertions check the proposed negotiation intersection,
sleep prerequisites, no-image result shape, duplicate/stale/wrong-job events,
cancel ownership declarations, separate render/power outcomes and PCM sequence/
size examples. They evaluate the proposal's consistency, not its implementation.
No STT, VAD, provider, command, generation or display action ran. No network
access or device changes were needed for this fixture.

A06's design/host milestone is complete. Its physical criterion remains deferred
until a selected extension exists and recovery prerequisites are established.

| Artifact | SHA-256 |
| --- | --- |
| Public `extension-examples.json` | `522e965bf67779804efc7e265373ed206b58631a43adfceb795ce307bfc6476f` |
| Private `check-extension-examples.mjs` | `c108eeebbcdcd4b821bdefeab5f4de1508eb7c732c33c2a8798fd38544f77c58` |
| Private `finalize-parser-cli.c` | `9a7958f2eb8a1e883f1849fd27f5a9dcc56187de8cd8213ff49ff889ef71f8fa` |
| Extracted `finalize-parser-core.inc` | `a299027797968f1e21392446616351c225251595d587b42798b996d19d66dfc4` |
| Private `extension-examples.results.json` | `ae6cde5c4f1f433a99f8c7ce0c013ea5ae453148c8bdcf11a0d0bc8a506f1a92` |

## Destination-inventory reconciliation: C01

The two existing hash-pinned [Large](outbound-dependencies.json) and
[Standard](standard-outbound-dependencies.json) inventories were reconciled by
role, constructor-site uniqueness and URL source. Each has eleven distinct
identified constructors; all eleven roles have matching classified sources.
There are no unclassified identified direct constructor sites.

The new [coverage ledger](cloud-protocol.md#destination-coverage-and-remaining-indirect-call-limits)
records the remaining uncertainty per role: dynamic returned URLs, redirects,
installed legacy-manifest values, and the limits of direct-call/reference/exact-
pointer searches. It retains the negative evidence for the legacy literals and
does not claim whole-program computed-call exclusion, all boot-state traffic or
offline operation. The earlier paired GNU checks remain the binary evidence;
this pass is an evidence reconciliation, not a new binary execution or fault test.

C01's bounded inventory question is complete. No device/network operation, NVS
read or OTA work was performed, and deferred R12 was not resumed.

## Voice feature reuse: A07

Six isolated scenarios passed on Omarchy against unchanged release
[`e5450665`](https://github.com/kristofferR/ha-fraimic-eink/commit/e5450665ddbb57c2542c883375ba68c0aefbb1b1)
playlist, playback-queue and scene managers. The fixture imports the repository's
HA/storage test substitutes; image conversion and upload boundaries are stubbed.
It is not a live HA, provider, durable disk or physical display test.

1. Saved playlist append survives the stubbed store reload but leaves an existing
   queue snapshot unchanged; explicit queue insertion places the new image first.
2. Duplicate playlist names are allowed, and repeated image append creates
   separate slide IDs. Stable target resolution and command deduplication are
   adapter responsibilities.
3. Playlist schema validation accepts a missing library reference. It does not
   establish that the original exists.
4. A two-frame scene prepares both mapped images before delivery. The actual
   scene method returns `ok: true` for both immediate upload and accepted-but-
   queued delivery, while releasing holds with the respective uploaded flag.
5. A render failure for one frame allows another frame to upload, with separate
   outcomes and all acquired holds released.
6. Scene lookup tolerates case/whitespace; creation rejects duplicate names and
   missing library sources.

The private fixture uses Python 3.14 with `pytest`, `voluptuous`, `pillow`, `numpy`
and `resvg_py` in a disposable `uv run --no-project` environment; the worktree's
`tests` directory supplies the helper modules through `PYTHONPATH`. Result:
**6 passed in 0.17 seconds**. No integration source changed.

The [feature proposal](voice-feature-proposal.md) captures explicit target/current-
image semantics. A07's host milestone is complete. The owner subsequently selected
all three feature groups (creation/history, editing, HA/playlist commands);
provider capability and interaction choices remain open.

| Source / private fixture | SHA-256 |
| --- | --- |
| `test_voice_feature_reuse.py` | `78cf6894b79d992c2c17266669f6c865bcb694d5b5f44fb943906d764772417c` |
| `custom_components/fraimic/playlists.py` | `9e52cca63246e2b8bf4989a58cbd98d0a2901d7e9e6cd37b7099d6db88726e1d` |
| `custom_components/fraimic/playback_queue.py` | `2ad3295fd3d392e92dcee4636ddc05aa31fe76ab2f478298c08da98989227171` |
| `custom_components/fraimic/scenes.py` | `4cae6c6cc2c0fe26e8f778c63a40566bf4223dab26a91b9e8659d403c3320d2e` |

## Response-cache allocation and cleanup: E01/E02

Two additional complete GNU control-flow comparisons match cache cleanup
(`0x4206ce3c` → `0x4206c434`, eleven instructions) and full client cleanup
(`0x4206dbd8` → `0x4206d1d0`, 77 instructions). Pinned image bytes, entry
prologues, all reachable operations and ten internal branches were checked.
Six direct-call pairs and one free-helper literal pair were reviewed as mapped
dependencies; this does not prove every external body equivalent. The map now
contains 314 selected pairs; client cleanup was already mapped, and the cache
cleanup helper adds one new entry.

The private host fixture adds a tracked allocation wrapper to the unchanged
SDK callbacks/header reader/cache cleanup used by the acknowledgment fixture.
It uses the original HTTP parser, scripted transport and the same reconstructed
immediate upload return/status branch. **Twelve cases passed** under C11,
warnings-as-errors, AddressSanitizer and UndefinedBehaviorSanitizer on Omarchy.

The cases cover no-allocation empty acknowledgment, initial allocation failure,
second/third chunk growth failures, normal cleanup, partial/full cached reads,
repeated cleanup, reads after lost ownership, fixed-length success-path cleanup,
and direct-output body copying. Failed growth leaves the earlier 3/6-byte
allocation live after SDK cleanup; the fixture measures that ownership defect
and explicitly reclaims the block afterward. Therefore a clean sanitizer exit
does not mean the modeled SDK cleanup freed it. No invalid memory-access or
undefined-behavior finding occurred in these bounded cases.

Chunked header fetching returns zero even with `HPE_CB_body`; the reconstructed
upload branch consequently reports success. The normal empty explicit-length
acknowledgment does not enter the body allocator. The full client cleanup was
compared statically, not executed in this host fixture. No live heap pressure,
firmware allocator, concurrency or device failure was induced; the earlier TLS
allocation failure's cause remains unknown. This advances ongoing E01/E02 and
does not reopen the completed C05 contract or change checklist totals.

| Private artifact | SHA-256 |
| --- | --- |
| `voice-cache-fixture.c` | `d3e05049950a710af636c3819aab47f973511e113d711ae3c129dce4c97746b0` |
| `voice-cache-results.jsonl` | `c39313987c1b1552df7573aeacbc887f66e5d4036f6f64b69017ecc588c943c7` |
| `compare-standard-voice-cache.mjs` | `946ded7a718c85ec3ce4a0b44e3dc254227c63f3d5676a5a8562a88d2cdcdd74` |
| `standard-voice-cache-comparison.json` | `6b9a9424625ccf944336be97020a151bea80da5f0c6a0aae55cfee6c126bb1b5` |
| Pinned `esp_http_client.c` | `7aabd415f3a39675e59f591919b9e88e31213e548b010cb0809a888d2b0ceef2` |

## Renderer fault and admission model: D04

Large render-start `0x420208d4`, worker `0x420204b8` and recording query
`0x42020150` were recovered as complete reachable GNU control flow with 143,
384 and 50 instructions, respectively. The fixture checks every recovered
instruction against the hash-pinned image and verifies consequential literals:
29,999 wait-counter limit, 12,288-byte requested task stack and unsigned worker
size-range constants. The three bodies total 577 instructions and 22 ranges.
The startup semaphore constructor at `0x42014600`–`0x4201460f` requests length
one, item size zero, type three. No Standard worker equivalence is inferred.

**Twenty scenario assertions and 140 event orders passed** in a private Bun
fixture on Omarchy. This is a control-flow reconstruction, with modeled heap,
task creation/deletion, binary queue, driver returns and virtual delays; it is
not an Xtensa interpreter or actual FreeRTOS execution. It exercises the cases
listed in the [renderer report](rendering-and-concurrency.md#bounded-renderer-fault-and-admission-model).
Direct invalid worker contexts are explicit branch probes, not an assertion
that normal render-start admits them. Hardware cleanup is assumed to return.

The admission enumeration preserves each caller's four modeled steps. With both
creates succeeding, 60 of 70 merges admit two workers. With B's create failing,
48 merges leave a live A with busy false and four leave no worker. Counts depend
on that abstraction and are not likelihood estimates. Additional traces show
first-completion busy clearing, a third admission, binary-token collapse, stale
completion, signal-before-busy-clear and timeout without worker cleanup. No real
concurrent producer, pixel overwrite, panel fault or physical deadlock was induced.

D04's host milestone is now checked. Its remaining physical validation stays
deferred. Ongoing E01/E02 and the separate D02 byte-overwrite/D06 driver-fault
criteria remain open.

| Private artifact | SHA-256 |
| --- | --- |
| `renderer-fault-model.mjs` | `898f28795087d1bae170fa3c5c4a1146b69d68b87fccd93287210ea44085f3dd` |
| `renderer-fault-results.json` | `970f43382ecef2e79be22a537ad83db3cafd3c11eaed9fbbe15710371f202f24` |
| `renderer-start-large-cfg.json` | `2e4960db2bbb6300bc5fa3ba5fc9fbf1cec37431322ea38beea12ef569c365de` |
| `renderer-worker-large-cfg.json` | `60a156d0382dc7c6f686a8eb0fb484e0e9f66ced1d0370795d784ad792204e8e` |
| `renderer-recording-query-large-cfg.json` | `43ac86a47fddd27ff131df0c4d8c00ccef30b356a2c6b74305a597ba468a05f4` |

## Byte-level buffer overlap: D02

Eleven host memory-copy scenarios passed on Omarchy. The fixture checks both
firmware image hashes, then instantiates the recovered Large shared 2,304,000-byte
allocation and Standard's separate 1,048,576-byte image / 2,120,000-byte audio
allocations. Its constants follow the existing SPI, capture, uploader and WAV
traces; it does not execute those firmware routines or add new whole-function
equivalence claims.

The [result table](rendering-and-concurrency.md#byte-level-overlap-fixture-and-model-controls)
records producer, consumer, exact changed half-open byte ranges, WAV structure
and the Large DMA split. Nine overlap/control cases cover one Large staged-image
transfer and four cases per model. Two additional counterfactual cases compare
exclusive ownership and a completed full snapshot. Original/result SHA-256 values
and per-controller output hashes are preserved in the private JSON; no real
recording, artwork or credential is used.

Large's selected DMA ordering retains thirteen 4,800-byte chunks and replaces
all later bytes. Its recorded/uploaded PCM cases remain structurally valid WAVs
despite changed audio. Standard's distinct audio allocation leaves those exact
cross-type cases unchanged, while a second image still replaces its image bytes
before a modeled DROP. No Large controller/DMA geometry is generalized to Standard.

The fixture assumes simultaneous producer admission and fully completed copies
at the selected event boundaries. It does not simulate intra-copy races, RTOS,
TLS/kernel buffering, actual DMA, panel pixels or physical scheduling. The full
snapshot succeeds on the workstation and is not a device memory-capacity test.
D02's host milestone is checked; physical overlap and D03 memory/ownership design
remain open.

| Private artifact | SHA-256 |
| --- | --- |
| `buffer-overlap-model.mjs` | `510c1682ed135d42231f39b626487b6849bdeb15c7039110ba228149787ba3cd` |
| `buffer-overlap-results.json` | `1c68a8933e5c764a1ef4bbf2eb1aff45b52292928349adea5735c7360c5000ad` |

## Local album mutation contract: C12

The [album/playlist proposal](album-playlist-mapping.md) defines a local
compatibility subset separately from the captured vendor schema. Nineteen
assertions passed in one isolated pytest scenario on Omarchy, using real
`FraimicCloudClient`, the art/wake payload builders and playlist/queue APIs from
unchanged release
[`e5450665`](https://github.com/kristofferR/ha-fraimic-eink/commit/e5450665ddbb57c2542c883375ba68c0aefbb1b1).
HA storage was stubbed with repository test helpers.

A disposable aiohttp server bound to `127.0.0.1` on an ephemeral port; a client
request guard rejected every other host/port, and account login was disabled.
Eighteen authorized decoded requests exercised create, list, update and delete
plus rejected schedule/reference/scope cases; duplicate JSON and missing-auth
requests were rejected before that decoded-request log. All identities and
credentials were synthetic. Nothing contacted a frame, HA or vendor service.

Both request/response shapes were checked against the saved OpenAPI components
with `jsonschema`, followed by explicit stricter fixture rules. In particular,
schema-valid incomplete intervals, `specific_days`, nullable active state,
unknown frame assignments and unresolved upload IDs are insufficient for the
local subset. Failed checks leave its album record unchanged. Random mode maps
to saved shuffle; owner multi-frame assignment stays metadata. Actual wake
payloads have no images and do not create an art playlist. Existing active queues
and reusable originals survive catalog updates/deletion in these scenarios.

Result: **19 checks, 1 pytest scenario passed in 0.17 seconds**, under Python
3.14 with the prior HA-free dependency set plus aiohttp/jsonschema via `uv`.
The test's temporary saved-playlist rebuilding is intentionally nontransactional
and replaces playlist/slide IDs; no durable/idempotent production mapping is
claimed. It does not execute scheduler activation, wake calculations, the physical
proxy, vendor mutations or production authorization. C12 now waits for its
deferred account/device criterion.

| Source / private artifact | SHA-256 |
| --- | --- |
| `test_local_album_contract.py` | `528b724646aa73e73518c256ab157a7ba47c0aeea34b85a53932c41f0cdb0f5f` |
| `local-album-contract-results.json` | `accc4e774b979802806083f8245435f3437c7260f8588dbb34a9844579806424` |
| Saved `openapi-current.json` | `3310e003e65e7d2236beab3714507533f69d86fb4917526039d1d8cfb3f5ed33` |
| `custom_components/fraimic/cloud.py` | `30b9fa1e9d206204505689c5b8b913bb0f41d1d605942d92e85d132f0bfaaaf1` |
| `custom_components/fraimic/cloud_delivery.py` | `c9f936f6ffc77f6067fb9b4e462586ff74ed1769332c444a0ae25aa1de4848a0` |
| `custom_components/fraimic/playlists.py` | `9e52cca63246e2b8bf4989a58cbd98d0a2901d7e9e6cd37b7099d6db88726e1d` |

## Recoverable cache-slot design: N05

The private C fixture extends the earlier RAM FAT12 disk harness with a proposed
two-record format and recovery scan, leaving pinned FatFs unchanged. It uses
4,096-byte sectors, an 8 MiB volume, actual Large/Standard payload sizes and
OpenSSL 3.6.5 SHA-256 for record integrity. The hash covers model/length/generation
metadata as well as the payload. This is new host design code, not recovered
stock functionality or firmware written to a frame.

Normal replacement succeeds for both payload sizes. Its disk-write call counts
are 241 for Standard and 569 for Large. The fixture then restores the baseline
and cuts before every call, plus after the last write before final sync, yielding
**242 + 570 = 812 interrupted cases**. A cut prevents that and all subsequent
writes/syncs; each successful disk call copies all requested sectors atomically
to RAM. After APIs unwind, the fixture discards filesystem state and remounts.
At every cut, the previous active record still validates. Recovery selects the
old generation except for the last cut per model, where the complete new record
exists despite the reported sync failure. No cut case is reported as a successful
save. The full positive-control writes are separate from that fault count.

Sixteen further assertions/groups test corruption, metadata hash coverage,
palette, model, equal-generation ambiguity, truncation, low space, absent records
and counter exhaustion. The space preflight is cluster-rounded with a two-cluster
fixture reserve; it does not measure installed capacity or prove a universal
space/wear bound. No-valid/ambiguous recovery is explicit rather than choosing
an unvalidated file. Proposed control failures do not erase the canonical source.

Built/run on Omarchy with C11 warnings-as-errors, AddressSanitizer and
UndefinedBehaviorSanitizer; no sanitizer finding occurred. This is one shared
FAT configuration tested at two payload sizes, not a complete comparison of the
devices' installed filesystem configurations. Torn sectors, write reordering,
wear leveling, concurrent operations and real power loss are excluded. N05's
design/host criterion is checked; physical durability waits for layout/recovery.

| Private source / artifact | SHA-256 |
| --- | --- |
| `cache-slots-fixture.c` | `d0d85d8af573a177577e7e5caf945837d570cc4aea4e8d6be2da6b00e0969037` |
| `cache-slots-results.jsonl` | `23eb1bc22717cabca1231d2773f048942370953f3875b585c8ec1a4c68a3cb66` |
| Pinned `ff.c` | `b6511bc0102f42b941897cd9f96f75206b6851fedbebc6dcb17c220cb1d4bede` |
| Pinned `ffconf.h` | `27e92e97b5744d7cd0b5e9e82a885601c8eb358fbf22f1a9baec0c1246bd7f3a` |

## Wake-asset validation and recovery: N06

Five complete Large GNU control-flow recoveries cover validator `0x42028ae8`
(80 instructions), writer `0x42028bc8` (168), version decision `0x4202a968` (82),
stamper `0x4202aa48` (56), and installer `0x4202aae0` (95). All 481 instruction
encodings were rechecked against the hash-pinned app; the bodies cover twenty
contiguous ranges. External filesystem/NVS helpers are not recursively executed
or compared by this pass, and Standard equivalence is not claimed.

Twenty-two assertions/scenarios passed through a Python 3.14 reconstruction on
Omarchy using `uv run --no-project`. It creates disposable POSIX files at the
actual 2,304,000-byte Large size, with synthetic valid/invalid palette patterns.
It reconstructs installer decisions and uses actual reads/writes/unlinks while
modeling allocation/read limits, NVS outcomes and reported sync/close failures.
This is not binary, FAT, NVS or physical storage execution.

The [case table](storage-and-configuration.md#wake-asset-validation-and-recovery-host-cases)
records same-size corruption acceptance, forced version replacement, missing-key
adoption, repair-triggering resource faults, failed post-write validation unlink,
ignored return paths, repeated failed stamping and unavailable/lost-file states.
The reported sync/close error cases assume complete bytes are already readable;
they do not demonstrate actual durable storage after an I/O error. Missing
version and file-loss cases stand in for installer inputs; they do not simulate
the complete reset or filesystem-format process. Temporary directories were
removed automatically. No vendor artwork is included in the fixture or docs.

N06's host milestone is checked. Installing custom artwork and validating
upgrade/reset persistence on hardware remain deferred with recovery prerequisites.

| Private artifact | SHA-256 |
| --- | --- |
| `check_wake_assets.py` | `2fc8dddfbed9c25e54b88f4aca148cd4b7074f3078899f1ec662b2c5de3831b3` |
| `wake-assets-results.json` | `1894ef4ac89eef52fe97158e94a9017ed4fd19a258541d4aa7ddd8e5eba12498` |
| `wake-validate-large-cfg.json` | `02ea04b38f126bafaee6aca2fc967d67cd9be9d70268c5eb8f9d244122e9926c` |
| `wake-write-large-cfg.json` | `cf79058edda00edc3ddaf710984abf9fa5e71efb80e242cc231b35821362044b` |
| `wake-version-large-cfg.json` | `8133fa3f21108494cc7fa12a537e911d6d37c3165a7a4c67702854b34cbdc5b7` |
| `wake-stamp-large-cfg.json` | `c89fbd5b52f0077251050f1124121f4b418f196f0f304bc56b124f668b2f33ed` |
| `wake-install-large-cfg.json` | `caba6795b3f4bcc370989732c8279d68b0fca5e43d68122200cfb128e3b9a55e` |

## Panel faults and interrupt watchdog: D06

Twenty-two complete Large GNU control-flow recoveries contain 993 instructions
in 34 ranges, spanning interrupt-watchdog initialization/ticks/registration and
the selected SPI, status, BUSY, PMIC, output, refresh and cleanup helpers. Combined
with D04's complete 384-instruction render worker, the pass checks **1,377
instruction encodings across 23 bodies** against the pinned image. The manifest
below fingerprints every new body. ROM function identities are corroborated by
the ESP-IDF 5.4.1 ESP32-S3 linker map; ROM implementations and panic-handler
execution are not included in the host reconstruction.

The Bun fixture passed **26 cases**: 22 nested driver/worker scenarios and four
interrupt-feed policy controls. It checks hidden versus logged SPI errors, status
suppression, true power-setup failure cleanup, one/six BUSY timeouts, PMIC failure,
power-good assertion/deassertion errors, a bounded observation of a yielding
unbounded wait, and cached output versus modeled register state after failed
writes. The [case table](rendering-and-concurrency.md#driver-faults-through-the-worker-bounded-host-cases)
records the interpretation and exclusions.

Every selected controller transfer is one command plus sixty 4,800-byte data
transactions; eight controllers yield 488 selected SPI calls. The fixture uses
virtual delay ticks and does not wait ten real minutes or send hardware commands.
Its power-register model applies the cached output byte only on an injected
successful write. It cannot infer partial I2C effects, rail discharge or optical
state. Successful early setup/conditioning and other unselected calls are
assumptions, not independently validated paths. Separate feed controls test the
reconstructed dual-core flag policy, without emulating hardware counters or panic.

No frame requests, firmware writes, GPIO changes, HA source/deployment changes
or network configuration changes were made. D06's static/host milestone is
checked; its original physical recovery/shutdown criterion remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `panel-fault-model.mjs` | `4263598986737cc20e94544eaa17d1340a7b03a20539b0f0d2541f9efa23a999` |
| `panel-fault-results.json` | `93d3173009c277bb3e9e93c4977e9094560bf9e103235f27865384257c8926b1` |
| `panel-fault-cfg-manifest.json` | `ff68b822ee17c9e8b904d177fdd0095f68cfdf1b550afea94f91f28868c99628` |
| Reused `renderer-worker-large-cfg.json` | `60a156d0382dc7c6f686a8eb0fb484e0e9f66ced1d0370795d784ad792204e8e` |
| SDK `int_wdt.c` | `7bdb472a5c7046d4c4f246830576c5dbd7153db149ea2b8c5654d337ac8e81db` |

## Time-control allocation and overlapping waiters: S02

Nine complete Large GNU control-flow recoveries contain **541 instructions in
25 ranges**: synchronization entry `0x42014e90`, notification `0x42014728`,
message dispatcher `0x42055dc0`, callback post `0x42055f24`, synchronous API
call `0x42056010`, init `0x42056314`, stop `0x4205639c`, mode `0x420563e4` and
thread-semaphore construction `0x42067840`. Every instruction encoding was checked
against the pinned firmware, with entry prologues checked. The manifest below
records the individual body fingerprints. Earlier traces supply mailbox capacity,
FreeRTOS posting/wait semantics and wrapper identities; those implementations
are not emulated by the new host fixture.

The Bun 1.4.3 reconstruction passed **25 cases** on Omarchy. It combines selected
control-message behavior with a generator reconstruction of the application's
initiator/joiner branches and a binary completion semaphore. It tracks callback
message ownership through enqueue/block/dispatch/free and keeps synchronous
stack-message lifetime separate. Fault outcomes stop at explicit assertion or
null-storage-dereference markers rather than executing invalid memory accesses.
The [case table](boot-and-scheduling.md#time-control-and-overlapping-waiters-host-cases)
records the observed model consequences and implementation implications.

Two joiner orderings are selected deliberately: whichever caller takes the only
token can succeed while the other times out. If the joiner takes it and no later
notification arrives, the initiator ultimately clears the synchronized flag.
These are conditional interleavings, not an exhaustive schedule search or a
measurement of FreeRTOS waiter priority. Delayed init, late notification, stale
token draining, coalesced callbacks and semaphore-allocation progress latching
are separate controls. Timed waits are supplied outcomes; no actual 34-second
wait, thread scheduler, timer clock, DNS, UDP or time change is used.

This is reconstructed TypeScript, not execution of the app or unmodified SDK C.
The new complete application lifecycle trace is Large-only; previously documented
Standard queue/control comparisons retain their narrower scope. No device, HA
or network changes were made. S02's host milestone is checked; physical offline
clock/TLS/sleep behavior remains deferred. N04 was owner-postponed during its
partial filesystem pass and remains unchecked/deferred, with unpublished private
artifacts preserved.

| Private artifact | SHA-256 |
| --- | --- |
| `time-control-model.ts` | `7d74f38ffc8455745488bf7d7ba93094b3703a04493060a01b1e1c003752e56c` |
| `time-control-results.json` | `d380281e86f3b96ad2f9f6ec2ea8d68d5660b785a441e9e6ffeb794dac41244a` |
| `time-control-cfg-manifest.json` | `23f7fc96c898415817f121067a243c02e9660a5c0464fa193984bee0e4956e70` |

## Identity save/reset interruption boundaries: N03

Complete Large saver `0x42018af0` covers 177 verified instructions in seven
ranges. The already recovered reset helpers cover 969 instructions in seventeen
ranges. These **1,146 instructions across three bodies** support the selected
write/return ordering, with the previous SDK and caller traces supplying the
documented commit and handoff context. The newly recovered legacy-migration body
is retained for further comparison; it is not executed by this fixture.

The Bun 1.4.3 host reconstruction passed **nineteen scenario groups**. Four groups
enumerate **34 cuts** before mutation calls or final commit: ten production-save,
six development-save, ten development-reset and eight production-reset points.
Failure groups separately inject **28 setter errors**: ten checked save writes,
four unchecked legacy aliases and fourteen reset restore writes. Other groups
cover backup loss, empty/short readable values, legacy fallback, init/open/commit
errors, an earlier handler recovery erase, caller RAM divergence and selected
later sleep/statistics writes.

The [persistence case table](storage-and-configuration.md#identity-saves-and-reset-restoration-host-cases)
records mixed identity, hidden restore failure and shared-state consequences.
All data are synthetic. The store is an in-memory map with whole immediate
successful mutations and before-effect injected errors. It is not an NVS, flash,
wear-leveling or reboot emulator. A cut means the application stops at that API
boundary; it does not claim the same records survive physical power loss. The
fixture does not model the known write-then-old-item-removal error path, string
buffer/type checks, whole HTTP form parsing or concurrent writers.

No device, network or HA state was changed. N03's previous combined host/comparison
step is split into a checked bounded-host milestone and the remaining Standard
SDK/caller comparison, making the partial completion explicit. Physical identity,
Wi-Fi/timezone and reenrollment validation remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `identity-persistence-model.ts` | `09f1c22cf1e05964c457ef0dc86511f5d55e70deadb0109dba3bb301642a76a3` |
| `identity-persistence-results.json` | `842889db631bdd5b3655276f20b78bce822e08d274c3452f8f0eabede2da9ee9` |
| `identity-save-large-cfg.json` | `78e5e19b168c4bfcfafaa212995bb38968eaf094d2163a766e3c828f6880374f` |
| `reset-development-large-cfg.json` | `434b9de12df1c47d42cdb91f70b49b880d8e50fecf35da73e65ad9278798c7b5` |
| `reset-production-large-cfg.json` | `546c111b326025ca907050e0db73a55bf3733d915c4fe33f4d325f58bd02a2fb` |

## Standard identity persistence and reset lifecycle: N03/E02

Twenty-one complete paired bodies cover the saver, legacy-field migrator,
HTTP action handler, three SDK NVS initialization/erase wrappers and the fifteen
cached-state/credential/teardown helpers from the earlier Large pass. Each build
contributes **1,573 instructions, 155 internal branches and 66 ranges**. GNU
control-flow recovery checks instruction encodings against the pinned images;
the comparison checks prologues, normalized opcodes/registers and branch
destination indices. Seventy direct-call and 172 literal pairs are reviewed
separately. A source-line argument to the erase-error diagnostic differs;
terminated strings and pointed-to Wi-Fi/IP event names match. Corresponding RAM
and external code pointers do not prove runtime values or recursively equivalent
callees. The private comparison JSON fingerprints every complete body.

The main-loop reset regions are unequal and are not forced through the matching
body assertion. Separate bounded CFG recoveries cover Large `0x42014079` through
exclusive `0x4201421a` (152 instructions/four ranges) and Standard `0x42013ff7`
through exclusive `0x420141d6` (177 instructions/three ranges). An explicit region
exit terminates traversal; this is not a claim of whole-main-loop coverage.
The recovered Standard sequence adds 1,000-tick waits before teardown and after
successful wake-image completion. Both use 200 initial delay ticks and a 12,000-tick
completion wait. The [comparison table](standard-model-comparison.md#identity-persistence-and-reset-handoff-comparison)
states branch conditions and the distinction between shared completion and render
acknowledgment. Tick conversions use the previously established 10 ms tick.

The check script asserts the selected delay loads/call targets, their placement
in the decoded regions and the absence of the two added waits in Large. No sleep
helper, RTOS, display or flash behavior is executed. Final sleep callees, deeper
NVS storage internals, unselected indirect references and physical final state
retain their explicit remaining criteria. N03's bounded comparison milestone is
checked; its physical reset/isolation criterion remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `compare-reset-lifecycle.mjs` | `0c4c4c76bc865a2a2bf78140821c0bb8450b022b31caba7c4894d23aa93059be` |
| `standard-reset-lifecycle-comparison.json` | `a0b9bd1a4a7568f2bd9f4b425a934b93dbd16bd3528e8368b2699c12c4188520` |
| `check-reset-handoff.mjs` | `1f66ff82ab0a0e6dd3625b57e6d7154908da2775042fa845732c031257b91202` |
| `reset-handoff-summary.json` | `5b8fd7ab729242482cd591e46e3104c9958bd44fe977ac685c6ff1ce0658c52c` |
| `reset-handoff-large-cfg.json` | `0c73bc1c0976be0af188d8b26aba9ade5e6cbcdb6f9abe5ace55faac8318509f` |
| `reset-handoff-standard-cfg.json` | `4bf407bd4d1d5fc0ea081861b7d1be84b16b8928db0b9120b1cc2bc7c0631bad` |

## Standard NVS dispatch and per-key storage: N02/E02

Seventeen complete functions per image were recovered with GNU control-flow
traversal and checked against the pinned image bytes: **507 instructions, 95
internal branches and 33 ranges per build**. Prologues, normalized operations,
register operands and branch destinations match. Twenty-three direct-call pairs
and 23 literal pairs were reviewed separately. The private comparison JSON
fingerprints every complete body; the [public table](standard-model-comparison.md#nvs-handle-dispatch-and-storage-writes-also-match)
gives all seventeen entry pairs.

Constructor stores resolve to Large vtable `0x3c3c3cc4` and Standard
`0x3c24cc80`. Pinned-byte reads assert slots `+0`, `+4`, `+0x28` and `+0x30`
target the compared destructor, deleting destructor, commit and typed setter.
The base-table addresses are classified only as corresponding constructor/
destructor stores. External code pointers and RAM accesses are mapped roles,
not evidence that all callees or runtime contents match.

Both builds' selected paths apply setters individually, omit a storage flush in
the commit method and provide no rollback on close. The storage writer can return
remove-failed after writing a replacement. Actual page-write/erase outcomes,
encryption, reboot selection of duplicate items, other SDK keys and compatibility
with unexamined firmware remain untested. No NVS fault, frame request, reset or
storage change was performed. N02's Standard comparison is now a checked milestone;
remaining schema/migration work is still explicit and unchecked. N04 stays deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `compare-nvs-storage.mjs` | `7c5df57080e23d135732f8775ea36cc4b45af39bcca64b073bf15c8266a48c21` |
| `standard-nvs-storage-comparison.json` | `1bf75ca6dd8fcf2bfeb50a95614a13739fcd33fe56dfee93e3454fbf1fb036b7` |

## Legacy-field migration error boundaries: N02/N03

The host fixture interprets the supported arithmetic, load/store, branch and
call operations in the complete Large `0x42017350` and Standard `0x42017324`
GNU CFGs. It asserts both pinned image hashes and every instruction's bytes,
reads literals from the matching image, rejects unsupported operations or
uninitialized synthetic-stack reads, and enforces an instruction budget.
External calls are explicit hooks for NVS operations, time and logging; register
windows, the SDK, flash, scheduling and real elapsed time are not executed.

**Twenty-eight scenarios, 56 runs, passed.** Both builds produce equal synthetic
record maps and operation traces, and the union visits all 169 instructions in
each selected body. Instruction coverage is not proof of every input/interleaving.
Cases include type/capacity errors, empty and existing destinations, each of
three failed setters, two failed string rereads, one scripted between-read
change, four successful-setter cut points, resumption and commit/open errors.
The [migration table](storage-and-configuration.md#legacy-field-migration-does-not-validate-a-whole-identity)
records the resulting application contract.

Successful fixture setters mutate a typed in-memory map wholly and immediately.
Injected errors occur before output/mutation unless a case explicitly scripts
a changed source record. String capacities include NUL; failed reads leave the
destination buffer unchanged in this model. These assumptions establish bounded
caller consequences, not physical NVS error effects or replay of a device fault.
No personal identity, frame traffic or installed storage was used. N02's bounded
legacy-migration milestone is checked; SDK schema/record compatibility remains
open, and N04 remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `legacy-migration-cases.ts` | `11d0e65c41a12886c756454cd8a4389b37ab4aef6b8f0e6333ec511907569e46` |
| `legacy-migration-results.json` | `be8fbf9d3af8e2b7627096797820ad38c5043fd9da02025c7a5be916ee6904d7` |
| `identity-migrate-large-cfg.json` | `f99f023584af9a4bf89c0672bee9036dcd829a69841c3c680a9677fe1807706d` |
| `identity-migrate-standard-cfg.json` | `63639be03c43afb27f8c38068befc801c8bfc69bc65a7fd28d54b4e9ac14e873` |

## Indirect Wi-Fi NVS schema: N02/E02

The pinned images contain matching 73-entry Wi-Fi registry definitions. A
restricted success-path interpreter extracts every registration's key, ID,
internal kind, size, range, scalar default and destination from the byte-checked
GNU initialization body. Successful allocation/registration and both explicit
runtime-flag branches are fixture inputs. The resulting 73 descriptors match
after excluding relocated addresses. The zero-flag branch registers `opmode`
again with default 1 instead of the initial 2; all other entries match.

The matching SDK header identifies the twelve NVS slots in each initialized
476-byte OS adapter. Version 8 and terminal magic are checked in both binaries,
and the commit slot anchors a unique table candidate. The load/reset switch
then maps the internal descriptor kinds to U8/I8/U16/blob API calls. The
[published schema](wifi-nvs-schema.json) contains names and static metadata only.

| Role | Large | Standard |
| --- | --- | --- |
| Descriptor registration | `0x420961e4` | `0x42095888` |
| Registry initializer | `0x420964b0` | `0x42095b54` |
| Load/reset dispatch | `0x420971fc` | `0x420968a0` |
| Cleanup | `0x42097514` | `0x42096bb8` |
| Namespace open and load | `0x42097564` | `0x42096c08` |

These five complete pairs contribute 1,233 instructions, 149 branches and 17
ranges per build. Fourteen direct-call and 165 literal pairs are mapped
separately. The loader includes an indirect jump: recovery asserts the preceding
eight-way bound, table-base load and indexed access before traversing all eight
targets. The comparison checks corresponding target instruction indices, rather
than treating the jump as an ordinary return or omitting switch branches.

The registry's scalar metadata and blob capacities are established. Final
post-load normalization and writeback remain explicit N02 work. No SDK library,
radio, installed NVS state or physical fault was executed. Feature-like names
are not hardware-capability evidence. N04 remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `inventory-wifi-nvs.mjs` | `3d3b00cfa01ee6ddc51047ba7bfd9fc642b9780b94d79383e8fb7464fc63e9da` |
| `extract-wifi-schema.mjs` | `2c4396c7a27cdd47bf8a7711046564c13ce3a9a5d4f55c699442e25d2d5dda6b` |
| `recover-wifi-switch-cfg.mjs` | `937c5baa883202a726802d062707d7c52b4cda99c765072952a0bb3cbb01e59b` |
| `compare-wifi-nvs.mjs` | `19f358ed6f05c507e5b1bc442530542c696c8fca32b09ec8db3e6fc355ffd8f0` |
| `standard-wifi-nvs-comparison.json` | `eaf50b62ce2c8d349626d9217d2d096065b3837ff07d8aed89756dbdc30f71ed` |
| Large `wifi-nvs-descriptors.json` | `170adea186d602bc1d6673a11a15654f5d1d8be8b8ebcdbbb9555b0af9c9213f` |
| Standard `wifi-nvs-descriptors.json` | `dbb9dfdd266ba42d50816d7d728f761359d97537f4b464d3c4530fbdfd1736c2` |
| SDK `wifi_os_adapter-v5.4.1.h` | `044faedb4c53f32a0d65b5d3f0d8d68bf0fd05e9a15ec7beeedd3758f3c88b63` |
| SDK `esp_adapter-v5.4.1.c` | `2b122f43886082486423fbead6942437e5a00725b84c0ec485a69aff278bed2d` |

## Wi-Fi normalization and persistence handoff: N02/E02

Eleven additional complete paired CFGs cover all eight direct post-load helpers,
the nested AP SSID initializer, shared typed setter and commit wrapper. Across
330 instructions, 38 branches and 15 ranges per image, normalized operations
and branch targets match. Eight direct-call and seventeen literal pairs are
reviewed separately. The setter's bounded eight-entry dispatch table is checked
before traversing its targets and comparing their instruction indices.

| Selected role | Large | Standard |
| --- | --- | --- |
| Station password cleanup | `0x420970e8` | `0x4209678c` |
| Listen-interval repair | `0x420971d8` | `0x4209687c` |
| Country repair | `0x42097124` | `0x420967c8` |
| AP SSID check / initializer | `0x42097094` / `0x42097054` | `0x42096738` / `0x420966f8` |
| AP password cleanup | `0x420970b0` | `0x42096754` |
| AP primary-channel repair | `0x42097174` | `0x42096818` |
| AP-switch byte clamp | `0x420971c0` | `0x42096864` |
| AP secondary-channel adjustment | `0x42096e84` | `0x42096528` |
| Shared setter | `0x42096d38` | `0x420963dc` |
| Conditional commit | `0x42096ce0` | `0x42096384` |

The [storage trace](storage-and-configuration.md#wi-fi-normalization-changes-ram-before-optional-writeback)
records the password sentinel cleanup, AP SSID length word, selected country
repair bytes, optional writes after RAM changes and discarded setter/commit
results. Literal reads resolve the four ROM memory/string operations against
the pinned SDK's ROM export map. External channel-bound getters, real flags,
full radio state and persistence faults are not executed by this comparison.
No device or network configuration changed; N04 remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `recover-wifi-set-switch-cfg.mjs` | `5ab7137c7b75ed3d427ae1f633e0dc8d64cc6cc41afd7a5404b206db3539f66e` |
| `compare-wifi-normalizers.mjs` | `89612b017cab69b588c628e3f950cfc99b9eeef4854f8876d1c5922e3133fce1` |
| `standard-wifi-normalizers-comparison.json` | `5ec77f4cad558b37f8ca5288b7c74c404b76caa4ace879b2717627ba1f954796` |

## NVS consumer reconciliation and Standard display health: N02

The final bounded reference audit covers 23 identified namespace/key API roots
in each pinned image. Recovered direct references are independently decoded
with GNU and checked against the original application bytes. A separate scan
of all initialized application segments checks exact four-byte API pointers;
synthetic ELF symbol-table records are excluded.

| Coverage | Large | Standard |
| --- | --- | --- |
| Decoded direct call sites | 316 | 330 |
| Application caller functions | 50 | 52 |
| PHY caller functions | 4 | 4 |
| Internal default-open wrapper callers | 1 | 1 |
| Exact API pointer words | 12 | 12 |

All twelve pointer words per image belong to the previously mapped Wi-Fi OS
adapter. The additional Standard application callers initialize and update
`disphealth`: string `tag` and U32 `att`/`fail`. Their complete byte-checked CFGs
contain 166 instructions in four ranges. Reads and writes are unchecked; a
matching build tag is not proof that the aggregate counters were saved. These
records do not identify an image or provide a durable render acknowledgement.

Four complete paired PHY bodies add 236 instructions, 27 branches and nine
ranges per image, with eleven direct-call and 23 literal pairs checked
separately. They establish matching `phy` record shapes and validation of the
version, six-byte MAC and 1,904-byte calibration payload. Matching layouts do
not establish calibration portability between devices.

The [coverage record](nvs-reference-coverage.json) and
[compatibility boundary](storage-and-configuration.md#nvs-consumer-coverage-and-compatibility-boundary)
close N02 for the two pinned builds and identified consumers. Computed targets,
dynamically assembled names, unlinked API variants and other releases remain
explicit search limits. Installed storage, erase/init/key-provisioning internals
and physical recovery are outside this key-consumer audit. No device was read or
changed; N04 remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `AuditNvsReferences.java` | `2afb74d4ac43d15dbbf8786b8dde7424d1f4ad3604b818750597f7cc84d56d91` |
| `verify-nvs-reference-audit.mjs` | `1655239f803f4b0ce6b05bad519d58ddef805f1beef144eb903b1cd71a312ade` |
| Large `nvs-api-reference-audit.json` | `d71287d57580520084d1089f311b2f6e5829d5ae051222e988fad3a39aebd86d` |
| Standard `nvs-api-reference-audit.json` | `b77977727500e0533830332c1f8f89a9a4b82fd96f9725b4d399d4eb6ff4ce4e` |
| `display-health-init-standard-cfg.json` | `d4270c70e77d28d5ec5b52132df78394f0e01cf6191902d984758b373f6aef41` |
| `display-health-save-standard-cfg.json` | `06046bb6cc733633549e4bfc4f8c1e15171b5a60a94bb63664f3972b6e7b0ef3` |
| `compare-phy-nvs.mjs` | `c47d502229419d5ce5d730e267ec0e215a06559f8b861ae97e74074be400a18e` |
| `standard-phy-nvs-comparison.json` | `1b89cfe5968ee99ee2404e31f47932bc584338914b252c61e68eb4b4cc32a59d` |

## Buffer references and external cleanup: D01/E01/E02

A five-root buffer census covers the recording/image accessors, their allocation
globals and the display alias. Large's shared allocation makes these four distinct
addresses; Standard has five. GNU decoding checks the original image bytes at
every recovered instruction/literal-load site. An independent scan of all
initialized segments checks exact root-address words, excluding synthetic ELF
symbols. All sixteen reference-owner functions per build match the classified
workflow list in [the public ledger](ownership-reference-coverage.json).

| Reference evidence | Large | Standard |
| --- | --- | --- |
| Accessor calls | 9 | 9 |
| Unique recovered instruction sites, including calls | 25 | 29 |
| Unique literal-load sites | 16 | 18 |
| Exact initialized-segment root-address words | 2 | 3 |

Seventeen complete paired transport bodies contain 368 instructions, 58 branches
and 27 ranges per build; 27 direct-call and ten literal pairs are mapped
separately. They cover callback installation, close dispatch, list/container
destruction, selected TLS teardown and SSL read/write dispatch. Cancellation can
release TLS connection storage before complete HTTP-client cleanup. These bodies
do not join the worker or add a shared lifetime lock.

Thirteen paired task-local bodies contain 331 instructions, 55 branches and 22
ranges, with eleven direct-call and 37 literal pairs reviewed. The selected
registration/lookup/destructor paths account for the identified semaphore and
runtime-state keys; they do not install the HTTP client as a task-local cleanup
value. A separate four-root census checks seven actual calls per image: two
direct and five indirect calls whose targets resolve from preceding literal
loads. It checks six literal loads and four exact address words. Four Ghidra
references per build are rejected as calls to the cleanup callback because the
invoked function differs; that callback was passed as an argument.

These are static reference/CFG checks, not an executed RTOS/TLS stack or a
concurrent fault fixture. Computed aliases/registrations, live task-local values,
external allocator/socket/cryptographic internals, leaked bytes and physical
cleanup remain outside the result. D01 closes for the identified pinned-build
paths; deferred physical overlap and recovery criteria stay open. No frame,
network or HA configuration changed; N04 remains deferred.

| Private artifact | SHA-256 |
| --- | --- |
| `recover-transport-ownership.mjs` | `7977c27be3c37f5ad314f651bb6d55bb2d9e26aea6ccb04a3c7349e80955f033` |
| `compare-transport-ownership.mjs` | `e8174575c9ab0534522e1f484f2f46b5f7dd8ba9f1be97420ab782a76a880b4c` |
| `standard-transport-ownership-comparison.json` | `6dad4f50cf8e13c7134072e76f8bec72593108f9bcf61689730ecb3c8ce9cb42` |
| `verify-buffer-references.mjs` | `569a766a3c98416c3f4521290b78aa0d42c3951e66fc4284ea06d5612fc8315c` |
| `buffer-reference-audit.combined.json` | `8cd4638a13ebeeff295d809f6ee65b0e0cc43ca320941f02f560c213165bef33` |
| `recover-thread-ownership.mjs` | `9fd7af255cd29f3a0d6dff8ed1eaac1b3d03c77e82f706383f44352c5cbdfc61` |
| `compare-thread-ownership.mjs` | `4d655a784027e19363f517a8155a0460474adb8f6c1ee2bb3679928a5ddf14c4` |
| `standard-thread-ownership-comparison.json` | `35a996b5c0433280d80ff20bff5372f27ba059d2b1c67e1009bb6b484bc99f06` |
| `verify-thread-references.mjs` | `b08176519b2291c3d40eb0d12245a1ea06af357e2a18558c87de319f7a9ce9b0` |
| `thread-reference-audit.combined.json` | `c8a126cd0e739409435d2f2cf9403a5e601447f95923e2e5da7dc057dcd313b6` |

## Audio-output initialization and references: H03

Complete GNU CFG recovery covers the microphone initializers: 100 instructions
and three ranges on Large, 99 instructions and three ranges on Standard. Every
decoded instruction is checked against the pinned application bytes. A bounded
straight-line interpreter reconstructs the 60-byte PDM configuration after its
checked zero-fill and verifies the selected initialization-call arguments. Both
24-byte channel templates match. The microphone GPIOs differ; the result is not
a claim of whole-function instruction equivalence or execution on the frame.

Three complete LED function pairs contain 217 instructions, sixteen branches
and six ranges per build. Eleven direct-call and 25 literal pairs are mapped;
eight GPIO-immediate substitutions are checked explicitly. Remaining normalized
instructions agree. External SDK callees are not recursively compared here.

The independent nine-root reference audit checks seventeen direct call sites,
seven owner functions and zero exact initialized-segment API-address words per
build. A missing Large Ghidra owner for the ordinary I2S read is reconciled to
the existing byte-checked capture CFG at `0x4201fa24`. Synthetic ELF symbols are
excluded. Fifteen exact NUL-terminated API-name byte searches are recorded in
[the sanitized ledger](audio-output-coverage.json); absence is only supporting
evidence, not proof of absent code or hardware.

The static H03 milestone closes with RX-only microphone and RGB LED paths
identified. Physical output capability, arbitrary computed/bit-banged paths and
unexamined code remain unproven. No playback, frame read, enclosure access,
network change or HA deployment occurred.

| Private artifact | SHA-256 |
| --- | --- |
| `check-audio-configuration.mjs` | `8645454a856ab69df422472458f0ad6ede1958abcbf63bacaba24a5d2803fcfd` |
| `audio-configuration-audit.json` | `84ec09af3a5297384fd2849310902451d728e31f0c870d33635cdcbadda84f0e` |
| `verify-audio-references.mjs` | `cb18e8edf39bac65bca42a6accd8206dddab51b133d43728e69cec4f197b8f31` |
| `audio-reference-audit.combined.json` | `4a0b6cc4c0d9ba8c1a4b618ca3ed0010a488d6879fe78f5bbea3b90194efc55c` |
| `compare-audio-output.mjs` | `6b1e245453635b02592ce42610966441e1258d81a5a5428470bae3fc07415219` |
| `standard-audio-output-comparison.json` | `17cc87775e6d0624de293c15c6664bed090ee82bc9f6340066f97102d4d15f1b` |

## Handler contracts and diagnostic instruction cases: H05

The [contract ledger](route-contract-coverage.json) reconciles all 42 registered
method/path pairs, covering 39 distinct handlers, to consumed input, output,
access checks, effects and existing detailed research. Each record's method enum,
path pointer/string and handler pointer is rechecked against the pinned Large
application: 504 registration bytes plus the referenced path strings. This is a
coverage index, not a fresh physical test of all routes or a complete browser
audit. Registration failures, startup/sleep and shared-task blocking retain
their documented availability limits.

Seven additional complete GNU CFGs cover the battery JSON builder, battery status,
connection/portal/info/upload pages and AP switch: **1,628 instructions and 49
ranges**. These establish the two battery schemas, cached HTML status, activity
calls and AP configuration-before-response-allocation branch. They are not a
new battery investigation or an AP mutation experiment.

The [41 diagnostic cases](diagnostic-host-cases.json) use a bounded interpreter
over eight complete byte-checked GNU CFGs, totaling 1,043 decoded instructions
and 28 ranges; the chosen cases execute 929 distinct instruction addresses.
There are 21 redaction cases, four log-initializer allocation cases, eight flush
cases and eight log-page allocation/send cases. The hex/MAC predicates and
replacement helper are interpreted too. Buffer-boundary canaries remain intact
in the selected redaction cases, and tracked page allocations are released.

External memory/string helpers, allocations, mutexes, file calls and HTTP are
modeled. The page's current formatter, authentication/query checks and time calls
are stubs; its previous-log reader runs against one synthetic seventeen-byte
payload. Chunk capture records attempted output, not delivery. The interpreter
does not model interrupts, register-window exceptions, RTOS scheduling, actual
heap behavior or storage durability. Flush cases assume mounted storage and do
not resume N04's deferred mount/recovery work.

Results support the documented redaction gaps, omitted-history allocation
branches, ignored HTTP-send failures and successful return after failed/short
flush writes or failed close. They do not explain a particular live TLS-memory
failure or establish all Standard equivalents. H05's static/host milestone is
complete; its physical availability/mutation/concurrency criterion remains open.

| Private artifact | SHA-256 |
| --- | --- |
| `diagnostic-instruction-cases.mjs` | `2a959abc50591ec074268ed47dd81480a48b882c7163b294c9d1669bc81d9e4a` |
| `diagnostic-instruction-results.json` | `cc7ae56feecc172e0f559290d26df90a3a62b5e8b942df550eaa40121fa6963e` |
| `build-route-contracts.mjs` | `803834ef44da807f499c3910ea07a1fb2b9f0a82a67153f5790dadd5ab7a42c9` |
| `route-contract-coverage.public.json` | `e7786542020724b5a8dee1419c3fb44c89026e1022d0b8bc0565d3b55cf642fc` |
| `remaining-battery-json-large-cfg.json` | `da497a45ce61dd03ee059288954d799c4f52c30506c7b293ee70ac32f49d94a0` |
| `remaining-battery-status-large-cfg.json` | `010e090c3b1043643b2209a98bfc20241eb157c9b98b4e80f2cbc463de03ab1d` |
| `remaining-connect-page-large-cfg.json` | `856b8ef609d918b1b2dc5bc3513944699a19242f99191494a5c53b9404bc133c` |
| `remaining-portal-page-large-cfg.json` | `65ccfa48ab1092b91040dd7b9d16ca80505068d252a89d6c3f118618d4fa31cf` |
| `remaining-info-page-large-cfg.json` | `76e42eaf128b7c6f1a08e3dfd993a9d750b031bf5b08c47e091d5f5f32a7c17c` |
| `remaining-upload-page-large-cfg.json` | `7951d6a70c7dfdbe16a992991831272ad8a35bc0e6df434b12d290a30c9ccba0` |
| `remaining-switch-ap-large-cfg.json` | `7420599785e95a39c28d9df7f674d90c42b8e3e9e9fbe5bb12371aa1d4311bd0` |
