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
