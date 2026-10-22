# Standard model comparison and live capture

[Research index](README.md) · [Model metadata and schemas](model-comparison.json)

This page reconciles the 21 October 2026 Standard-frame research handoff with the
Large-frame investigation. The handoff's redacted API trace contains 24 complete
exchanges; its capture report includes device-log results and owner confirmation.
The preserved Standard application hash was checked again when importing this
report. The live tests below were owner-directed vendor-proxy tests on the
Standard frame, not a replay against the Large-frame local emulator.

The earlier static comparison described unfinished setup and untested Standard
TLS acceptance. The later live capture supersedes those two statements:
registration completed and persisted across restart, and the frame accepted the
test chain for its normal API hostname. Neither frame has been flashed.

## Model and application identity

| Property | Standard | Large |
| --- | --- | --- |
| Vendor model | `133` | `315` |
| Live version/build | `0.2.28 / 4654a1d8` | `0.2.29 / f1555ee5` |
| Application bytes | 2,589,216 | 4,123,920 |
| Descriptor version | `v0.2.28` | `v0.2.24-33-gf1555ee` |
| Descriptor build time, zone unspecified | 6 July 2026 17:19:50 | 16 July 2026 10:17:43 |
| Chip / SDK | ESP32-S3 / ESP-IDF 5.4.1 | ESP32-S3 / ESP-IDF 5.4.1 |
| Image flash header | 16 MB, DIO, 80 MHz | 16 MB, DIO, 80 MHz |
| Panel payload | 960,000 bytes | 2,304,000 bytes |
| Controller transfers | 2 × 480,000 bytes | 8 × 288,000 bytes |
| Local method/path pairs | 42 | Same 42 pairs |

Standard SHA-256:
`d31870cca2c6ef7395a80be4466c9c3424867dc42cfa39a34d1c60492f7c5ce7`.
Large SHA-256:
`a75914caba6f5f35936a40e394b1d55eb88de4be4e76aa6d6bdabc061486a64f`.

These are matching vendor application downloads, **not installed-flash dumps or
full backups**. The Standard image passed checksum and appended SHA-256 checks;
no additional Secure Boot v2 signature sector followed its image hash. Bootloader,
partitions, NVS, eFuses, flash encryption and custom-image boot acceptance remain
unproven. Do not infer cross-flash compatibility from a shared chip or SDK.

The Large application is 1,534,704 bytes bigger; its read-only data segment is
1,535,660 bytes bigger, while executable IROM differs by only 816 bytes and
combined IRAM by 32 bytes. This supports a shared software base with substantial
model data/assets, not instruction-by-instruction equivalence. Hardware model
and firmware release differ together, so their effects cannot always be separated.

The preserved metadata maps 195 corresponding functions, including the subsequent
account-setup, `/dev`, calendar, orientation, album-body, task/conditioning,
maintenance, LED, status-image, cancellation and SNTP/DHCP/DNS comparisons. The poll paths share 86
referenced strings apart from their model/version literals; selected presign and
finalize paths share 32 and 44 strings respectively. Control-flow inspection
supports a shared cloud contract. Identical routes/strings alone do not prove
all handlers behave identically.

The `/dev` POST handlers use the same embedded seven-byte password and the same
length/byte comparison structure after form decoding. The value was supplied
privately to the owner. Neither device was switched to development mode; the
[detailed transition and error-path trace](storage-and-configuration.md#vendor-environment-switch)
is for Large unless explicitly stated otherwise.

### Physical input paths match within the audited scope

The [physical-input comparison](input-and-gestures.md) covers seven complete
function pairs and 33 instruction cases per model. Tap windows, held-input
admission, double-tap handling and the selected monitor/result lifetime branches
match. This is separate from physical gesture tolerance or whole-main-loop
equivalence.

### Boot cable classification and wake masks differ

The [boot admission comparison](boot-and-scheduling.md#boot-classification-and-first-recording-admission)
finds a Standard-only GPIO 1 sample on EXT1 wake. Low sets its boot cable flag;
Large's recovered entry only clears the equivalent flag. The shared 82-instruction
classifier consumes a one-byte `deep_sleep` marker before testing that flag.
Erase/commit failures do not alter the returned classification.

Both normal and storage-sleep paths request any-low EXT1 with mask 6 on Standard
(GPIOs 1 and 2), versus mask 4 on Large (GPIO 2). The selected main-loop cases
on both models enter idle input waiting before recording. Pending sleep can
survive that wait's admission result to the outer recording wrapper. The
[26 instruction cases per build and six call ranges](wake-admission-cases.json)
use synthetic dependencies; these are not physical wake measurements, complete
main-loop equivalence or battery-monitor diagnosis.

### Early startup errors and readiness policy also match

The [startup comparison](startup-and-readiness.md) adds a 413-instruction fast
initializer pair, with one diagnostic source-line difference. NVS, PSRAM and
existing-user recording initialization errors propagate to application entry;
flash-cache/instruction failures follow different continuation branches. Selected
main-loop cases share the cold-boot completion-wait timeout, button-wake path
without that wait and album task-creation-failure sleep. Standard's cable branch
also reaches idle without the wait. The [24/25 bounded cases](startup-admission-cases.json)
do not execute the background worker or prove network/service readiness.

The later [background-completion pass](startup-and-readiness.md#the-completion-token-carries-no-readiness-result)
adds 35 instruction cases per build. Both normal workers signal after many
component failures, but exit without signaling after selected Wi-Fi errors.
Both AP/setup workers instead continue after a Wi-Fi-start error. Completion
is a one-token semaphore with no result payload; the normal worker's signaled
notice ignores the give result. Allocation is unchecked at its store boundary,
and the selected cold consumer can pass null into the SDK take boundary.
The AP bodies match across 264 instructions. The 963/964-instruction normal
workers are interpreted separately, without a whole-body equivalence claim.
Actual semaphore faults, service availability and timing remain untested.

### Cancellation retention has the same startup boundary

The [flag-lifetime audit](voice.md#cancellation-flags-have-different-reset-boundaries)
identifies the same processing/recording roles and byte-access counts on both
builds. Eighteen instruction cases each confirm that monitor start/stop and a
new recording do not clear processing cancellation, selected voice exits retain
it, and the upload worker checks it only after presign. Both normal application
entry prefixes unconditionally zero a BSS region containing both flags, before
the deep-sleep-specific RTC branch. This bounds the stale flag to the current
wake session when normal startup is used; it does not demonstrate physical
concurrency, reset behavior or complete driver equivalence.

### All identified foreground poll consumers share the copy limits

The [consumer audit](cloud-protocol.md#four-foreground-consumers-do-not-acknowledge-image-success)
recovers four direct getter calls per model, including album/cold sites missing
from the earlier Ghidra reference list. Three main calls copy at most 511
settings bytes; button wait copies at most three. Twenty instruction cases per
build observe no local-settings read within their consumer boundaries. Album
checks for an empty image URL; cold/ordinary paths call the helper with it.
All three main paths clear the shared result despite a helper error. Button
wait instead leaves a successful pending result for main. These are bounded
consumer cases, not actual image faults or whole-main equivalence.

### Album result retry boundaries match despite dispatcher differences

The [album-wake audit](boot-and-scheduling.md#album-wake-has-two-result-windows-not-a-delivery-retry)
adds twenty instruction cases per model. Both allow two 30-query result windows,
with at most fifteen station-connectivity checks before the retry. They leave
the result phase after idle, empty pending URL or an image-helper error, and wait
again even if dispatch suppresses the retry. The dispatcher bodies differ:
Large has 123 recovered instructions, Standard 99; only Large blocks the tested
verification-running/Get Started states. The cases stub external helpers and do
not establish complete startup, network or sleep equivalence.

Four additional [publication schedules](cloud-protocol.md#an-album-retry-can-discard-a-just-published-result)
per model execute the actual worker/starter and main together. Both can clear a
result published in the final first-window delay, reject retry creation while
the old worker cools down, and then time out without an image. Publishing before
the final query or after the retry clear instead permits consumption. These
scripted schedules establish the control-flow possibility, not physical timing
or observed image loss.

The [task-admission follow-up](cloud-protocol.md#the-poll-starter-guard-does-not-reserve-ownership)
finds seven direct dispatcher sites in four recovered bodies per model. Three
scripted cases each show sequential exclusion, admission of two callers that
both passed the zero-handle check, and a first worker clearing a newer handle
on exit. Together these cases cover 87 distinct starter/worker/cooldown
instructions per build with modeled task creation. Actual scheduling and
concurrent HTTP remain untested.

### Saved memory states constrain extra buffers

The [memory comparison](rendering-and-concurrency.md#exclusive-ownership-versus-a-snapshot)
also differs by model. Saved Standard logs report 2,100,716 free PSRAM bytes and
a 2,097,152-byte largest block, sufficient in that recorded state to not exclude
an additional 960,000-byte image. Large's saved state excludes its larger image
copy. Neither result is an allocation/stress test or a reason to remove ownership.

### Controller commands remain model-specific

The [panel-command audit](rendering-and-concurrency.md#controller-commands-and-waveform-limits)
finds sixteen fixed initialization writes on Large and twenty-one on Standard,
with different payloads and refresh failure handling. Both identified artwork
paths send their full model-specific buffers. No waveform-table upload or
partial-window selection caller was identified within the audited roots;
hardware capability and unexamined I/O paths remain unproven. The
[command ledger](panel-command-coverage.json) preserves the exact short writes
without publishing a firmware image.

### Outbound-service inventory also matches

The [Standard inventory](standard-outbound-dependencies.json) independently maps
eleven HTTP-client constructor sites at `0x4206d590`, covering the same roles as
the [Large inventory](outbound-dependencies.json). The three selectors are
`0x42017a20` (API), `0x42017a38` (dashboard) and `0x42017a50` (authentication).
Their ten, two and one direct calls respectively match the Large role counts;
two API calls only log the chosen origin. All six production/development origins
are identical across these builds.

Both apps contain 43 printable HTTP(S) URL occurrences across eleven hosts,
including 29 SVG namespace declarations and local/navigation links. Neither
app has a recovered reference or serialized exact pointer to its legacy
`http://192.168.1.145` / manifest-path literals. Returned image, audio-upload and
firmware URLs remain dynamic; the four NTP names, DNS fallback and TCP
reachability probe are separately traced dependencies.

Thirty Standard GNU ranges cover 874 unique instructions, with exact bytes
checked against the pinned app and complete coverage of each requested range.
This recovers the multipart constructor omitted by Ghidra and rejects one
misaligned call-encoding match inside another instruction. No traffic was sent,
and no additional host protocol fixture was run. The comparison supports one
backend adapter with separate model renderers; it does not establish all
indirect callers, complete offline boot or recursive consumer/TLS equivalence.

### Local discovery and hostname setup also match

The [discovery trace](local-api.md#local-discovery-and-hostname-lifetime) compares
the setup-name helper, complete Wi-Fi/IP event handler, mDNS initialization,
hostname/instance/delegated-host setters and address-list copier. Seven pairs
match across 1,189 GNU instructions, 148 branch destinations and 39 contiguous
ranges per build, with 37 direct-call pairs and 101 literal pairs reviewed.
External callees and runtime RAM values are not recursively proven equivalent.

Both derive the usual setup suffix from only the last two MAC bytes, request
`fraimic.local` plus `fraimic_<decimal>.local`, ignore mDNS return values and
set a one-time initialization flag even on error. The delegated address is
copied once; subsequent IP events skip that application block. Neither image
contains a terminated `_http` literal, and the recovered setup calls no service
registration. This does not establish the service records HA's zeroconf matcher
expects. Actual discovery packets, conflicts, address changes and worker/heap
failures remain untested; no network or HA configuration was changed.

### Calendar and LED follow-up

Two independently hash-validated application images contain exact copies of:

| Data | Bytes | Large address | Standard address |
| --- | --- | --- | --- |
| All 41 LED state records | 984 | `0x3c13ff68` | `0x3c1401dc` |
| Create-account timezone select element | 1,165 | `0x3c107a30` | `0x3c107b44` |

Each byte range occurs once in the Standard app. Range hashes are in
[comparison metadata](model-comparison.json); these are hashes of the selected
ranges, separate from whole-app identities. Standard's lookup `0x420210f8`
references its LED table with the same 24-byte stride and 41-entry search.
Its create-account page handler `0x420191f8` serves the corresponding HTML.
Thus the table values and timezone dropdown choices are shared in these builds;
physical colors/timing and the whole LED arbitration state machine are not
established by byte equality alone.

A separate [LED arbitration comparison](led-and-workflow-state.md#standard-comparison-and-host-scope)
now checks thirteen corresponding functions and 826 GNU-decoded instructions,
with relocated addresses accounted for. Setter gates, the single pending slot,
protection latch, worker completion/duration branches and getter defaults match.
Twenty-two reconstructed host case groups exercise those branches, including
same-state timer reuse and stale completion after a failed mutex acquisition.
This does not prove identical physical timing, all caller behavior or recursively
equivalent SDK/output-driver implementations.

Standard calendar routine `0x42014dec` also copies the current 36-byte `struct tm`,
replaces only time of day, and adds the day interval after a target falls inside
the 900-second margin. It preserves the old DST flag across both conversions.
Its `mktime` at `0x420d00f8` contains the corresponding supplied-DST correction;
GNU decoding at `0x420d0332`–`0x420d0366` covers the branch beyond Ghidra's
unsupported instruction. The POSIX parser at `0x420d1238` has the same default
US rules and IANA-name parse-error path. The [Large-supported host fixtures](boot-and-scheduling.md#dst-flag-survives-the-calendar-calculation)
therefore have matching relevant static paths in Standard too. No physical
timezone/DST experiment was performed on either frame.

### Fixed maintenance callers also match

A separate full-image Standard scan finds eight direct calls to maintenance
setter `0x42015f4c`. All load `(4, 3, 0)` immediately before calling: four days,
03:00. The sites are `0x420126f0`, `0x42016238`, `0x420162d4`, `0x420166f6`,
`0x42016d7d`, `0x42016e02`, `0x42016f32` and `0x42016f79`.
Record writer `0x42014d68` has one direct caller, `0x420160d4` inside that setter.
The sole terminated `refresh_sched` key is at `0x3c0fd0a8`; recovered references
belong to loader `0x42014af4` and the writer. No exact setter/writer pointer words
occur in the application image; analysis-ELF symbols are not firmware pointers.

Three functions and the eight argument/call regions were independently decoded
in 19 GNU ranges; all 324 instruction byte sequences match the Standard app.
This supports the same [bounded interface conclusion as Large](boot-and-scheduling.md#maintenance-parameters-have-only-fixed-default-callers):
the discovered stock callers expose no custom interval or hour/minute selection.
It does not exclude computed indirect calls or assembled NVS keys, read installed
correction values, or validate physical timing. Album `next_image_utc` deadlines
remain a separate backend-controlled mechanism.

### Stock time service also matches

Standard `0x42014eb0` uses the same four time-server names from `0x3c13be18`.
Its background initializer passes five attempts, and the synchronization routine
uses the same 2/4/8/10/10-second waits. SDK initializer `0x42055340` introduces the
same random 0–4,999 ms delay before requesting time. Stop `0x420553c8` removes
request/retry timers when a UDP client exists, and name setter `0x4205544c` accepts only slot zero at
`0x3fcad9fc`. The [early-attempt timing problem](boot-and-scheduling.md#sntp-server-selection-and-startup-delay)
therefore has the same relevant static branches on both models. The final
application timeout also leaves SNTP running in Standard.

Standard's DHCP request list at `0x3c24debc` is again `01 03 1c 06`, without NTP.
Five builders use exactly four requested options. Reply parser `0x4205f478` sends
option 42 through the unknown-option hook `0x42066310`, which returns immediately
unless the option is 26; the parser skips the payload without storing it. ACK
application `0x4205f818` has no time-server installation, and append hook
`0x4206638c` adds client identifier option 61, not a time-server request.
This corroborates the [Large DHCP result](boot-and-scheduling.md#dhcp-does-not-configure-the-stock-time-server).

The parser comparison covers 324 decoded instructions and 111 internal branches
per image. All non-`l32r` instruction bytes match at corresponding offsets; 17
literal loads retain their registers but have model-specific addresses. The
relevant constants, tables, hook and ACK paths were checked separately. This is
not full SDK equivalence or a physical packet test. Both stock models need the
same candidate local DNS/NTP compatibility plan; DHCP option 42 alone will not
configure their time source. Cold boot, retained RTC behavior, actual retry
timing and WAN-free operation remain open.

### SNTP control queue and failure paths also match

Standard mode/init/stop wrappers `0x42052128` / `0x42052138` / `0x42052148`
use callback enqueue `0x42054f50`, discarding its allocation result. Hostname
wrapper `0x42052158` instead calls synchronous API helper `0x4205503c` and waits
for completion. The [Large ordering and failure analysis](boot-and-scheduling.md#sntp-control-queue-ordering-and-allocation-failures)
therefore applies to these checked Standard paths too: the hostname operation
orders earlier successfully posted controls, but does not cancel pending DNS
callbacks or make stop/configure/start atomic.

Initialization `0x42055080` creates the same 32-entry pointer mailbox, with its
handle at `0x3fcad9ec`. Pool table `0x3c24d60c` contains 18 descriptors with sizes
matching Large; index 8 selects the 16-byte API callback descriptor `0x3c24d678`.
Posting `0x42066698` waits for queue space, and the synchronous call waits for
its per-thread semaphore. The compared RTOS timeout helper `0x403847d4` has the
same maximum-ticks and explicit-delay-abort branches. The application response
waits again do not bound the whole operation.

Mode setter `0x42055410` asserts if a client remains active, including after a
lost stop message followed by a successfully queued mode request. Semaphore
initializer `0x4206686c` can return null; getter `0x420668e0` and the API caller
do not add a guard before the wait/signal dereferences. These are conditional
static paths, not observed Standard crashes or a diagnosis of the captured TLS
allocation error.

The comparison covers 34 functions, 944 instructions and 145 internal branches
in 57 GNU ranges per image, including queue send/copy, semaphore take and the
RTOS timeout check. Non-literal/non-call instruction bytes and their offsets
match. The 52 direct-call pairs and 95 literal pairs are checked or mapped
separately; equal pool sizes and diagnostic strings are verified rather than
assuming relocated data is identical. External helpers are not all recursively
compared. There is no new host behavioral execution, queue/heap fault injection
or device test, and this does not establish WAN-free boot.

### Outbound local resolution also matches

The [outbound `.local` trace](boot-and-scheduling.md#outbound-local-names-and-blocking-resolution)
also applies to Standard. This concerns resolving the backend, independently of
advertising the frame's own name or HTTP service.

| Function | Large | Standard |
| --- | --- | --- |
| Hostname classification/cache dispatch | `0x42057844` | `0x42056870` |
| DNS/multicast packet sender | `0x420567e0` | `0x4205580c` |
| Cache lookup | `0x42056d2c` | `0x42055d58` |
| Query enqueue/coalescing | `0x42056f44` | `0x42055f70` |
| Query retry/cache state | `0x42056a40` | `0x42055a6c` |
| TCP/IP resolver dispatcher | `0x42069b48` | `0x42068b74` |
| Netconn resolver | `0x42068368` | `0x42067394` |
| TCP/IP message/semaphore barrier | `0x42055fb8` | `0x42054fe4` |
| `getaddrinfo` | `0x420c5040` | `0x420c5320` |
| ESP-TLS hostname-to-socket helper | `0x420c314c` | `0x420c3424` |

Complete GNU control-flow recovery checks **1,339 instructions, 246 branches and
52 contiguous ranges per image**. Instruction bytes/offsets match apart from
relocated literal loads and direct calls. The 29 distinct direct-call pairs and
50 literal pairs are mapped separately; multicast IP structures, strings and
numeric values match. Each function's entry prologue, reachable branch targets
and bytes are verified against the pinned app. Do not derive Standard entries
from one global relocation: the transport helper and `getaddrinfo` have different
offsets even within the same SDK region.

The 23 host cases are one shared source-fixture run, not additional device or
Standard machine-code executions. They support the lowercase-suffix, cached-name,
pending-query and capacity boundaries described in the linked trace. Multicast
packets, IPv4/IPv6 routing, DNS response faults, actual wait durations, TLS and
fresh local-backend operation remain untested. External helpers are not all
recursively compared. No device or network configuration changed.

### DNS reply acceptance also matches

Four additional complete comparisons support the
[local-backend DNS reply contract](boot-and-scheduling.md#dns-replies-for-a-local-backend):

| Function | Large | Standard |
| --- | --- | --- |
| Echoed-question name comparison | `0x42057144` | `0x42056170` |
| Answer owner-name skip | `0x42057208` | `0x42056234` |
| DNS response parser | `0x42057274` | `0x420562a0` |
| Successful response/cache completion | `0x420566cc` | `0x420556f8` |

All **652 instructions, 122 branches and 11 contiguous ranges per image** match
apart from relocated calls/literal loads. Nine direct-call pairs and nine literal
pairs are checked separately, including all 256 bytes of the character-classification
table used by question comparison. This covers the parser's single-address limit,
exact IN-class checks, ignored packet branches, IPv4/IPv6 selection, TTL handling
and partial-answer count/state behavior. It does not prove every pbuf/UDP/helper
implementation equivalent.

The 26 shared host cases use unchanged pinned resolver functions with bounded
packet-access stubs. They are not executions of either firmware image. They
confirm the selected legacy-query reply requirements and distinguish an ignored
packet from a failure callback. A malformed second answer can leave a stored but
unpublished first address; the tested next valid IPv4 reply then fails. No such
packets were delivered to either frame. Actual multicast interoperability, timer
and callback interleavings, transport faults and network exposure remain untested.

### Connection address selection and errors also match

Nine more paired functions cover transport allocation/initialization, plain/SSL
connectors, the common connect path and synchronous TLS progress. They preserve
the [address-selection boundary](cloud-protocol.md#address-selection-does-not-recover-from-a-bad-ipv4-destination):
default unspecified family becomes IPv4-preferred DNS, while a later TCP/TLS
failure does not restart the attempt with another address family.

| Function | Large | Standard |
| --- | --- | --- |
| Zeroed transport context allocation | `0x420c2bd8` | `0x420c2eb0` |
| Base transport initialization | `0x420c2bf4` | `0x420c2ecc` |
| SSL transport initialization | `0x420c2e04` | `0x420c30dc` |
| Plain TCP transport initialization | `0x420c2e74` | `0x420c314c` |
| SSL connect wrapper | `0x420c2afc` | `0x420c2dd4` |
| Plain TCP connect wrapper | `0x420c2dac` | `0x420c3084` |
| Common address/socket connect | `0x420c34cc` | `0x420c37a4` |
| Synchronous TLS loop | `0x420c3a58` | `0x420c3d34` |
| Low-level TLS progress | `0x420c3748` | `0x420c3a24` |

Complete GNU recovery verifies **728 Large / 729 Standard instructions, 101
branches and 26 ranges per image**. One reviewed encoding difference accounts
for the extra instruction: Large directly calls socket-connect helper
`0x420550e4`; Standard loads corresponding `0x42054110` from a literal and calls
it indirectly. Normalizing that single load/call pair preserves register use and
all internal branch destinations. All other normalized operations match. The
31 distinct direct/equivalent-call pairs and 49 literal pairs are mapped separately;
this does not recursively prove socket, select, allocator or TLS-library internals.

Large's complete HTTP initializer and common-options helper are additionally
checked across 525 instructions and 20 ranges. Those two HTTP bodies are not
included in this nine-function Standard comparison. No new host fixture, live
connection, network fault or device request was performed. IPv6 interoperability,
physical timeout behavior and application retry sequences remain open.

### DNS fallback, cache and late callbacks also match

Standard initializer `0x420567e8` installs the same `8.8.8.8` fallback in DNS
slot 2. Its resolver table is at `0x3fcada24`; DHCP-start clearing helper
`0x420693c4` and the previously compared ACK path preserve that slot while
replacing the primary slots. This is the same separate DNS dependency described
in the [Large resolver trace](boot-and-scheduling.md#dns-fallback-and-cached-destinations),
not evidence that the earlier observed TCP connectivity probe was a DNS query.

The resolver has four 296-byte query/cache records at `0x3fcada9c`, with the same
seven-day TTL ceiling, zero-TTL removal and cache retention across server-address
changes. Timeout handling skips empty server slots; a nonzero response code
requires a populated immediate next slot before fallback. Stock-backend cutover
therefore needs the same cache and consistent-local-DNS considerations on both
models. No DNS cutover or outage was performed.

Standard also retains pending DNS callbacks after SNTP stop. Its four callback
records are at `0x3fcada6c`; SNTP callback `0x4205522c` ignores the returned name
and argument, copies an address to `0x3fcada00`, and sends through the current
client at `0x3fcada1c`. Stop's null-client guard and UDP's safe argument-error
return have the same branches. The [eight callback-ordering host cases](boot-and-scheduling.md#pending-dns-callbacks-survive-sntp-stop)
thus have matching relevant static paths in Standard too; they were not eight
additional device or host executions.

The comparison covers 27 functions, 2,189 instructions and 380 internal branches
per image. Instruction offsets and all bytes except relocated literal loads and
direct calls match. All 47 distinct direct-call pairs have the same relocation;
the 70 distinct literal pairs have equal numeric values, equal pointed-to strings
or address constants, or consistent RAM/code pointer mappings. This is scoped
branch/data-flow evidence, not a proof that all external helpers or the entire
SDK are equivalent. Physical timing and the proposed local DNS/NTP setup remain
unverified.

### NTP receive and clock application also match

Standard receive callback `0x42055278` and timestamp converter `0x42055250`
have the same relevant [packet/clock contract](boot-and-scheduling.md#ntp-response-contract-and-clock-application)
as Large. They require exactly 48 bytes and the matching response mode, handle
stratum zero as a retry, and apply the transmit timestamp without the additional
source/port, leap/version, originate-match or freshness checks discussed there.
The epoch offset and fractional conversion match, including zero time becoming
7 February 2036.

Wrapper `0x42052114` zero-extends seconds into a 64-bit time value; SDK sync
`0x42052018` invokes clock setter `0x4200aedc` in its immediate branch and then
the registered callback. Application callback `0x42014748` reads the resulting
clock and checks local year >= 2020 before setting flag `0x3fca6bbc` and signaling
the semaphore at `0x3fca6bb8`. Its early-year branch does not clear a previously
true flag. Interval getter `0x42052108` reads `0x3fca1320`, initialized to the same
3,600,000 ms. None of this proves that the frame remains awake for that interval.

Nine functions, 256 instructions and 31 internal branches were compared, including
request initialization, SDK/application callbacks and the clock-setter entry.
The existing 18 host receive/conversion cases have matching relevant branches on
both builds; they are not additional executions. The static comparison does not
replace a physical cold-boot, local-NTP or clock-correction test.

### Orientation and album-body follow-up

Both hash-validated apps contain the same seven decoded accelerometer probe
records: addresses, identity registers, expected values and sensor labels match.
The tables are at Large `0x3c140378` and Standard `0x3c1405e0`; this comparison
resolves their string pointers rather than comparing relocated pointer bytes.
Standard's alternative probe `0x42027c24` also returns zero after a match, and
initializer `0x42027d60` treats zero as failure. GNU confirms both branches.
The candidate list therefore does not establish working alternative drivers on
either build, nor identify the fitted physical part.

Standard's register writer `0x4202799c` uses the same fixed sensor address;
reader `0x42027aa4` performs separate status and six axis-byte reads. Classifier
`0x42027f94` uses the same absolute-X-versus-Y comparison, landscape-on-tie rule
and portrait-on-failure fallback. Wrapper `0x42028110` is called with the
keep-powered argument by both poll and voice. Voice samples after upload and
before finalize, matching the [Large orientation contract](hardware-and-layout.md#accelerometer-target-and-orientation-semantics).
These are matching software branches, not physical rotation or coherent-sample
tests.

Standard album helper `0x4202ec48` likewise accepts 1–4,096 incoming bytes,
allows five consecutive receive timeouts, parses JSON without an object-root
guard, adds/replaces the device-key field without checking that operation's
result, then serializes without another size cap. Its cJSON parse/add/replace
wrappers have the corresponding call structure. This supports sharing the
[adapter validation requirements](local-api.md#body-transformation-is-not-schema-validation).
The 19 host cases remain a fixture of the recovered Large helper and pinned
cJSON source; this comparison does not represent another executed firmware test
or establish equivalence of every Standard proxy/error branch.

### Reachability probe and recovery counters also match

Thirteen function pairs cover the TCP probe, three-counter reset, powered-state
selector, intervals, manager initialization/start, success/failure handlers,
monitor loop, state setter, channel save, failure event and socket-error query.
GNU checks compare **1,022 instructions in 40 Standard ranges**, including
**128 internal branches**. Non-relocated instructions and their offsets match;
direct calls, code/data pointers, strings and constants were checked separately.
This is not a recursive comparison of the external Wi-Fi/transport implementation.

Standard probe `0x4202d4ac` has the same immediate-error versus asynchronous
`SO_ERROR` distinction, ignored error-query return and three-second readiness
timeout as [Large](boot-and-scheduling.md#reachability-result-branches-and-timeout-scope).
Its compiled query wrapper `0x42054b18` also uses a networking callback followed
by an indefinite completion wait, so that timeout is not an overall deadline.

Standard reset helper `0x4202d494` clears failure/retry/passive counters but
preserves manager cycles at `0x3fcacad8`. Success `0x4202d9c0`, failure
`0x4202da1c` and monitor `0x4202dda0` retain the same
[recovery thresholds](boot-and-scheduling.md#recovery-thresholds-and-retained-cycle-count).
Its cached reachability byte is `0x3fcacae7`, separate from its station-event
byte `0x3fcacae6`. The earlier live transfer interruption remains the physical
evidence; no refusal, repeated-outage, queue or allocation experiment was added.

### Separate recording and image allocations

Standard allocator `0x42027734` makes **two separate PSRAM allocations**. This is
a material difference from Large's single backing block, verified through the
allocator, pointer accessors, recording start and display initialization.

| Storage | Standard | Large |
| --- | --- | --- |
| Recording backing allocation | 2,120,000 bytes at pointer global `0x3fcabd8c` | Shares the 2,304,000-byte image allocation; recorder capacity is 2,120,000 |
| Image backing allocation | 1,048,576 bytes at pointer global `0x3fcabd80` | 2,304,000 bytes at pointer global `0x3fcabd28` |
| Display pointer alias | `0x3fca7644`, initialized from image accessor `0x42027898` | `0x3fca75d4`, initialized from image accessor `0x42028e88` |
| Packed panel asset | **960,000 bytes** | **2,304,000 bytes** |

Standard recording start `0x4201fea0` gets the audio pointer from `0x42027874`;
WAV helper `0x420201a4` writes the 44-byte header in that allocation. Startup's
call/store at `0x42014642` / `0x42014648` instead installs the image pointer as
the display alias. The voice download context in `0x42011a3c` uses this display
pointer with a **960,000-byte** limit. Render worker `0x42020488` copies into the
same image alias and later sends two 480,000-byte blocks. The spare allocation
capacity does not change the backend's required panel payload size.

The allocator prechecks total free PSRAM against **3,168,576 bytes**, then makes
the two allocations separately. That check does not establish two sufficiently
large free blocks. It zeroes each allocation; failure of the second allocation
frees and clears the first and its ready flag. The transient recording-ready
flag is initialization state, not a job ownership lock.

Thus Large's specific audio-versus-image alias hazard must **not** be generalized
to Standard. Standard still shares one image allocation among image producers
and rendering, and one audio allocation among recordings/uploads. Separate
allocations alone do not prove safe overlapping jobs or fix the shared HTTP
response/abort state. No concurrent operation or allocation fault was exercised.

### Capture loss and stop behavior also match

Nine paired functions compare the capture worker, start/stop/interrupt/state
helpers, WAV writer, recording orchestration, button-control task and SDK I2S
reader. GNU checks cover **1,226 instructions in 30 Standard ranges**, with
matching normalized operations, register operands and **107 internal branches**.
Task-entry pointers, relocated state pointers and direct helper calls were
mapped separately; this does not recursively compare every external SDK helper
or microphone configuration path.

Standard capture worker `0x4201f9f8` and SDK reader `0x4204ecc4` retain the same
4,096-byte requests, 50 ms per-wait timeout, positive-success-only admission and
whole-block capacity check. Partial timed-out reads advance the SDK buffer
position but are discarded by the app. The cumulative failure count and its
non-timeout-only abort check also match. The nine earlier
[SDK host groups](voice.md#capture-reads-can-lose-audio-without-invalidating-wav-structure)
are one fixture run, not nine new Standard executions or a measured dropout.

Stop `0x42020060` clears Standard's active byte at `0x3fca7640` and waits without
a deadline for the task handle at `0x3fca763c`. Its recording-state getter
`0x42020120` can report false on a mutex timeout. Button-control task
`0x42011274` then has the same exit without a completion signal, while outer
orchestration `0x420106d0` waits 6,000 ticks and uses the same generic timeout
handling. The recording-completion semaphore handle is at `0x3fca6ba0`.

Separate audio/image allocations therefore do not remove these capture/stop
limitations. Keep that memory-layout difference explicit while sharing the
backend interpretation: WAV byte duration is stored audio, and missing presign
does not reveal the recording's stop reason. No new physical recording or
cancellation test was performed.

### Voice transport comparison

The Standard presign, multipart and finalize functions (`0x42025124`,
`0x420255ec`, `0x42025dd0`) have the relevant client branches already documented
for Large:

- Multipart builds separate framing storage and streams the existing WAV in
  chunks of at most 4,096 bytes, requiring exact write counts. Its transport
  timeout is 120,000 ms. Abort registration occurs after the final body write,
  immediately around header fetch, rather than covering audio transmission.
- The upload acknowledgment path requires header fetch to return zero before
  checking for a 200–299 status. A positive declared response length takes the
  error path. Use an empty success response; the earlier Standard live capture
  observed HTTP 204. This is not a claim that every possible empty/chunked
  response has been physically tested.
- Presign and finalize each make one body-read call capped at 4,095 bytes before
  parsing, without requiring complete HTTP-body consumption. Finalize requests
  a 600,000 ms transport timeout, which is not an absolute end-to-end deadline.
- Worker `0x4201005c` samples orientation after upload, calls finalize
  synchronously, and copies its URL on success. It does not implement a status
  polling loop. Missing status defaults to completed in the parser, consistent
  with the observed successful Standard response that omitted it.

The comparisons below extend coverage to the complete recovered application
paths, not every external SDK helper or a new fault-injection run. Host fixtures
remain Large-derived. Keep the synchronous adapter contract shared and the
renderers, capacities and ownership models explicit per build.

### Presign copying and member lookup also match

A focused comparison covers ten function pairs: the complete presign routine,
formatted-print wrapper and allocation context, value/object printers,
object-member wrapper and walker, case-insensitive string comparison,
string-value getter and object-type predicate. GNU checks compare **875
instructions in 35 ranges**, with matching normalized operations, register
operands and **146 internal branch destinations**. Relocated calls and literals
are mapped separately. This does not claim every external parser, transport or
allocator helper is equivalent.

Standard presign `0x42025124` has the same 5,888-byte result layout and silent
byte truncation: URL 1,535, object key 255, and formatted fields 4,095 bytes plus
their terminators. Its call to `0x42038108` selects formatted printing, whose
object printer `0x42037a54` adds the same indentation/newlines. Complete compact
wire JSON can therefore expand beyond the fields buffer. Missing/non-object
fields or print-allocation failure leave an empty fields string without changing
presign's successful return. The three initialized allocator-hook pointers were
mapped; allocator behavior and physical memory pressure were not exercised.

Member walker `0x42037bc4` stops at the first matching child, using comparator
`0x42036e74` through the case-insensitive wrapper. The 256-entry character table
reachable by its unsigned-byte loads matches Large; only ASCII `A`–`Z` take the
lowercase conversion. Duplicate or case-variant `url`, `key` and `fields` names
therefore have the same first-match behavior. This is byte-oriented matching,
not general Unicode case folding.

The earlier [25 presign host groups](voice.md#presign-copying-and-field-reserialization)
remain one Large-derived fixture run. This comparison extends static support for
the shared field-copying/printing contract; it does not count those cases again,
test Standard's hardware, or recursively compare the whole JSON parser and
multipart writer. Both models should receive short, unique ASCII field names,
a short upload ticket and a stable object key within the byte limit.

### Complete multipart upload paths also match

The earlier decompiler stopped at Xtensa unsigned-comparison instructions in the
multipart builder. A GNU control-flow walk now follows every direct branch from
the application entry to its returns, checks each decoded byte against the pinned
image, and rejects gaps, overlapping instruction starts or out-of-function
branches. The recovered uploaders each contain **749 instructions**:
Large `0x42026b9c` and Standard `0x420255ec`.

Including SDK writer `0x4206d930` / `0x4206cf28`, the comparison covers **771
instructions and 67 branches**, over 21 Large and 19 Standard contiguous GNU
ranges. Normalized operations, registers and internal branch destinations match.
Seventeen direct-call pairs and 59 literal pairs are tracked separately; matching
strings/constants do not establish recursive equivalence of every external
allocator, formatter, HTTP/TLS or transport helper.

Both application paths have the same field ordering/filtering, raw `%s` framing,
length calculation, framing-only PSRAM allocation, bounded formatting checks and
4,096-byte maximum audio writes. The network timeout is 120,000 ms per transport
call; it is not an overall upload deadline. The SDK writer can accumulate positive
short writes, but returns a later zero/error without including earlier progress.
The application requires the exact requested count and stops on a failed prefix,
audio chunk or footer instead of resuming from a partial offset.

| Stage | Large call | Standard call |
| --- | --- | --- |
| Prefix write | `0x420270b3` | `0x42025b03` |
| Audio-loop write | `0x42027133` | `0x42025b83` |
| Footer write | `0x420271a4` | `0x42025bf4` |
| Abort registration, after footer | `0x420271f3` | `0x42025c43` |
| Fetch response headers | `0x420271f8` | `0x42025c48` |

The post-body cancellation, acknowledgment/status, cleanup and return branches
also match. Neither body loop queries cancellation. The same
[empty upload acknowledgment requirement](voice.md#upload-acknowledgment-must-have-an-empty-body)
and [partial-write consequences](voice.md#host-checked-write-failures-and-framing-length)
therefore have static support on Standard. Those eight host groups remain one
Large-derived fixture run, not additional device tests. The earlier successful
Standard vendor upload remains its physical positive control.

One local multipart handler can serve these two stock builds. It should validate
the entire form, retain the upload by job key, return an empty acknowledgment,
and wait for finalize before generation. Separate recording-buffer ownership,
model-specific panel rendering and outer-worker lifetimes still apply.

### Presign and finalize application paths also match

The complete recovered direct-branch control flow now matches for presign
`0x420266d8` / `0x42025124` and finalize `0x42027380` / `0x42025dd0`.
The comparison covers **1,056 instructions per image and 88 branches**, over
26 Large and 25 Standard GNU ranges. Each decoded instruction matches the pinned
app bytes; normalized operations, registers and internal branch destinations
match. Twenty-three direct-call pairs and 80 literal pairs were mapped separately.
This does not prove every called HTTP, TLS, allocation or JSON helper equivalent.

Both JSON request paths reject a negative write return but proceed after zero,
including the SDK's zero-after-partial-progress result. Both make one bounded
response-body read after a positive fetched length, rather than requiring whole
HTTP-body completion. The selected presign empty-read initialization hazard also
has matching instructions; it remains unexercised.

Finalize requires HTTP 200 and a string URL, copies at most 1,535 URL bytes and
63 status bytes, and defaults missing/non-string status to `completed`. It does
not validate a nonempty URL or consult `success`, `message` or a job ID. Its
32-bit processing-time field is sampled after headers and before reading the
body. The handler has no application-level retry/status-polling loop. The outer
voice worker's existing cancellation/lifetime rules still apply.

The [31 combined HTTP/JSON cases](voice.md#finalize-http-status-framing-and-failure-ordering)
use the already-compared finalize branch, with no additional function-pair
count. They verify the body read before status rejection, skipped cached
chunked JSON, informational-response read boundaries and signed-low-word
length test. They are one host run, not separate tests of each physical model.

The [allocation-ownership follow-up](voice.md#json-request-allocation-failures-can-lose-ownership-or-fields)
also compares seven cJSON helpers: 145 instructions, 26 branches and ten ranges
per build. The complete callers plus these helpers support the same conditional
unattached-child leaks and ignored field-attachment failures on both versions.
Fifty host allocation cases use reconstructed callers and the pinned library;
they do not measure either device's heap or explain its observed TLS failures.

The [JSON write checks](voice.md#json-request-writes-can-proceed-after-zero) and
[finalize parser groups](voice.md#finalize-response-fields-and-host-parser-checks)
exercise SDK/reconstructed behavior on the host. No new traffic, malformed
responses, timeouts or recordings were sent to either frame. Keep the local
finalize endpoint synchronous and return a short complete response only when
the panel asset is ready.

### Poll result ownership also matches

Seven function pairs and two foreground caller regions match across 425
GNU-decoded instructions and 39 branch comparisons, accounting for relocated
literals/calls and equivalent narrow/move encodings. Standard's 18 bounded
ranges and the corresponding Large ranges were checked byte-for-byte against
their pinned apps. This is static comparison, not a new host or device test.

| State / helper | Large | Standard |
| --- | --- | --- |
| Result region, 13,744 bytes | `0x3fca8680` | `0x3fca86d8` |
| Separate ready byte | `0x3fca867c` | `0x3fca86d4` |
| Semaphore / worker handle | `0x3fcabc30` / `0x3fcabc34` | `0x3fcabc88` / `0x3fcabc8c` |
| Worker / starter | `0x42025aec` / `0x42025c84` | `0x42024538` / `0x420246d0` |
| Ready / running getters | `0x42025d84` / `0x42025d90` | `0x420247d4` / `0x420247e0` |
| Copy / clear helpers | `0x42025da0` / `0x42025e10` | `0x420247f0` / `0x42024860` |

Both workers clear the result region, perform the request with one EAGAIN retry,
attempt recording interruption for a successful pending result, publish readiness
and signal the semaphore. They then wait 200 ticks / two seconds before freeing
the copied argument, clearing the handle and deleting themselves. The ready byte
is outside the cleared region; neither a new starter nor its worker resets it.
Copying checks neither readiness nor ownership, and clearing does not join or
cancel the worker. The located semaphore references cover creation/giving,
without a recovered foreground take/join.

The initial comparison covered two `user_settings` consumers. The subsequent
[four-site audit](#all-identified-foreground-poll-consumers-share-the-copy-limits)
also recovers the album and cold-start sites omitted from Ghidra's references;
none reads the copied settings within its bounded consumer region.
The button path copies at most three URL/settings bytes
plus NUL and preserves a successful pending result for main. Main retrieves the
1,536-byte URL / 512-byte settings destinations, calls its image helper, then
clears the result. These shared signals cannot acknowledge a particular displayed
image. The [conditional stale-result and late-clear hazards](cloud-protocol.md#poll-completion-is-one-shared-result-not-a-delivery-receipt)
therefore apply to both builds, without demonstrating a physical race. Complete
parser/loop equivalence and computed references remain outside this comparison;
the known dispatcher exclusions still differ as described below.

### Complete poll request and response control flow matches

The complete application routines, Large `0x4202475c` and Standard `0x420231b4`,
each recover **1,878 instructions**. A paired control-flow traversal matches
1,807 instructions and follows all 71 unconditional jumps per build, including
119 matched conditional branches. No recovered instruction remains unvisited.
The traversal accounts for short encodings, register-copy encodings and jump
layout across 40/37 contiguous ranges; raw Ghidra function extents are not used
as the completeness criterion.

The comparison maps 32 distinct direct-call target pairs and 131 literal-value
pairs separately. Ninety relocated NUL-terminated byte sequences match exactly,
as does one empty string. The only differing compared read-only strings are:

| Role | Large | Standard |
| --- | --- | --- |
| Fallback version when its getter fails | `0.2.29` | `0.2.28` |
| Display type in all three request URL formats | `315` | `133` |

This extends application-branch compatibility to request construction, URL size
checks, status/error handling, pending/URL/settings field selection, four-switch
application calls, verification promotion, firmware-offer handling, deadline
selection and cleanup order. It supports one shared stock-protocol adapter with
model-specific assets and telemetry. It does not make the two panels, image
sizes or firmware images interchangeable.

The [numeric comparison](poll-full-comparison.json) retains CFG hashes, call and
literal mappings. External functions are mapped, not recursively proven
equivalent by this pass; six corresponding RAM addresses do not establish equal
installed contents. The Large-derived parser host cases are not relabeled as
new Standard hardware tests. [Validation](validation-2026-10-22.md#complete-two-model-poll-body-comparison-c02e01e02)
records normalization and coverage limits.

### Settings persistence also matches

Three application functions and two bounded caller regions were compared with
GNU Xtensa disassembly: **431 instructions per image, 49 branches and 22 Standard
ranges**, all byte-matched against the pinned apps with complete range coverage.
Normalized instructions/registers and internal branch destinations match; eleven
direct-call pairs and 32 literal pairs were mapped separately. This does not
compare every external helper or the full boot sequence. The later
[complete poll comparison](#complete-poll-request-and-response-control-flow-matches)
extends the application-body coverage beyond these bounded caller regions.

| Role | Large | Standard |
| --- | --- | --- |
| Load four switches | `0x42014780` | `0x420147a0` |
| Save four switches | `0x42014968` | `0x42014988` |
| Apply changed snapshot | `0x420158cc` | `0x420158ec` |
| Poll call to apply | `0x4202513a` | `0x42023b8a` |
| Startup call to load | `0x42016898` | `0x42016874` |
| Startup fallback save | `0x420168b8` | `0x42016894` |

Both builds update RAM before saving, stop at the first failed I32 write, and
skip the saver when an incoming snapshot already matches RAM. Thus an identical
poll snapshot does not retry a previous failed save. Both poll callers log a save
error and continue response processing. The startup loaders return the namespace
open result even when individual reads fail; only a nonzero loader result enters
the default-save branch, whose result is ignored. See the
[full persistence trace](storage-and-configuration.md#failed-settings-saves-are-not-retried-by-an-identical-snapshot).

This extends static support to Standard; it is not a fault-injection or reboot
test. The following pass separately compares selected SDK dispatch/storage bodies.

### NVS handle dispatch and storage writes also match

Seventeen complete paired bodies cover namespace opening, handle construction and
lookup, I32 setter dispatch, the typed setter/storage writer, commit, close,
destruction and manager-list removal. All **507 instructions, 95 internal branches
and 33 ranges per image** match after normalization. Twenty-three direct-call
pairs and 23 literal pairs are recorded separately; called functions outside the
selected bodies are not recursively compared.

| Selected role | Large | Standard |
| --- | --- | --- |
| Default open / named-partition open | `0x42049e60` / `0x42049de8` | `0x42048f38` / `0x42048ec0` |
| Handle construction / lookup | `0x4204b840` / `0x4204981c` | `0x4204a918` / `0x420488f4` |
| I32 API / locked wrapper / virtual dispatch | `0x42049f68` / `0x42049f3c` / `0x420e34a4` | `0x42049040` / `0x42049014` / `0x420e3788` |
| Typed setter / storage writer | `0x4204b29c` / `0x4204af28` | `0x4204a374` / `0x4204a000` |
| Commit API / virtual method | `0x42049974` / `0x4204b258` | `0x42048a4c` / `0x4204a330` |
| Close / API-entry destructor | `0x42049d9c` / `0x420e3390` | `0x42048e74` / `0x420e3674` |
| Handle destructor / deleting destructor | `0x4204b26c` / `0x4204b288` | `0x4204a344` / `0x4204a360` |
| Manager removal / list unlink | `0x4204b788` / `0x420e377c` | `0x4204a860` / `0x420e3a60` |

The constructors store actual vtable addresses `0x3c3c3cc4` and `0x3c24cc80`.
Reading those tables from the pinned images confirms destructor slot `+0`,
deleting-destructor slot `+4`, commit slot `+0x28` and typed-setter slot `+0x30`
point to the compared methods. The temporary base-table stores also correspond;
their remaining methods are not claimed equivalent.

Both commit methods only inspect the handle's valid byte and return success or
`0x1107`; they contain no flush or rollback. I32 dispatch supplies type `0x14`
and four bytes to the typed setter, which calls storage immediately for a valid
writable handle. The storage writer has the same existing-value comparison,
page-write retry and old-item-removal branches. A replacement can be written
before old-item removal fails with `0x1108`. Closing the handle does not undo the
earlier setters. Thus the [per-key persistence consequences](storage-and-configuration.md#nvs-commit-does-not-make-the-four-switches-atomic)
also apply to these selected Standard paths.

This is static support for the save contract, not a downgrade/cross-flash test,
complete NVS schema, measured durability or power-loss recovery. Page/partition
callees, encryption, runtime RAM values and unselected SDK keys retain their
explicit limits. No device storage was read or changed by this comparison.

### SDK Wi-Fi configuration descriptors also match

Both builds register the same 73 Wi-Fi NVS descriptors, including the thirteen
blob capacities, scalar types/ranges/defaults and two conditional `opmode`
defaults. Five complete bodies match across 1,233 instructions, 149 branches and
17 ranges per image, with fourteen direct-call pairs and 165 literal pairs
reviewed. The [storage findings](storage-and-configuration.md#wi-fi-registers-73-configuration-keys-outside-app_data)
and [schema](wifi-nvs-schema.json) distinguish internal kinds from actual NVS
types and initialized defaults from stored values. A subsequent eleven-body
[normalizer/writeback comparison](storage-and-configuration.md#wi-fi-normalization-changes-ram-before-optional-writeback)
adds 330 instructions, 38 branches and 15 ranges per model, with eight direct-call
and seventeen literal pairs reviewed. Those selected paths also match, including
RAM-first writes and ignored commit results. Physical restoration and complete
Wi-Fi/regulatory state-machine equivalence remain untested.

### Standard has an additional display-health namespace

The [NVS reference audit](storage-and-configuration.md#nvs-consumer-coverage-and-compatibility-boundary)
finds 316 direct API calls on Large and 330 on Standard, with the same twelve
Wi-Fi API-pointer words. Standard's fourteen additional calls are in two
`disphealth` helpers storing string `tag` and U32 counters `att`/`fail`. Their
166 instructions establish per-build reset, RAM-first tally updates and unchecked
persistence. These counters are aggregate diagnostics, not image/job receipts.

Four PHY NVS read/write/open helpers separately match across 236 instructions,
27 branches and nine ranges per model, with eleven direct-call and 23 literal
pairs reviewed. Both validate selected calibration records against the current
PHY version and chip MAC; no cross-device calibration transfer is implied.

### Device-key selection and regeneration also match

Five [identity-related bodies](storage-and-configuration.md#device-key-selection-and-regeneration)
match across 356 GNU instructions, 40 branch destinations and 13 ranges per
image. The selector, key reuse/migration/generation, embedded-material helper,
digest lookup and HMAC wrapper have the same operations. Nineteen direct-call
pairs and 26 literal pairs were reviewed; the embedded material matches but
remains private. NVS/crypto implementation and physical failure behavior are
not recursively validated by this comparison.

Both prefer a nonempty environment-specific stored key, conditionally fall back
to the shared legacy key, and otherwise derive the same key for the same valid
MAC. Migration write/commit errors are ignored; fresh-generation save errors
are returned. Separate NVS slots are therefore not proof of different production
and development credentials or of rotation after reset. Existing stored values
can still differ. No frame credentials, modes, accounts or storage were changed.

### Opposite-environment reset backups also match

Both [reset helpers](storage-and-configuration.md#reset-erases-nvs-before-restoring-the-other-environment)
match across 969 GNU instructions, 60 branch destinations and 17 ranges per
build. The helpers back up six fields from the opposite environment, erase NVS,
reinitialize and attempt restoration. Backup failures do not stop erasure;
individual restore writes are unchecked. Development reset also attempts to
restore mode 1 and the first-time override. Production reset makes no such writes.
The later selected SDK/caller comparison below extends this application-only
pass. Neither establishes physical recovery after faults. No reset was performed.

### Identity persistence and reset handoff comparison

Twenty-one additional paired bodies cover the identity saver and legacy-field
migrator, HTTP action handler, three NVS initialization/erase wrappers, and fifteen
cached-account, credential, statistics, timestamp and Wi-Fi teardown helpers.
Across **1,573 instructions, 155 branches and 66 ranges per build**, normalized
opcodes/register operands and internal branch destinations match. Seventy
direct-call pairs and 172 literal pairs are mapped separately. Matching strings
and event-base names were checked; RAM pointers establish corresponding accesses,
not equal runtime state. One diagnostic source-line argument differs.

| Selected role | Large | Standard |
| --- | --- | --- |
| Identity saver | `0x42018af0` | `0x42018ac4` |
| Legacy-field migration | `0x42017350` | `0x42017324` |
| HTTP action/reset handler | `0x4201c740` | `0x4201c714` |
| NVS initialization wrapper | `0x42049c00` | `0x42048cd8` |
| Named-partition erase / default-`nvs` wrapper | `0x42049d40` / `0x42049d8c` | `0x42048e18` / `0x42048e64` |
| Initialized identity cache accessor | `0x4201912c` | `0x42019100` |
| Wi-Fi credential predicate / user reevaluation | `0x4201ea80` / `0x42015264` | `0x4201ea54` / `0x42015284` |
| Network teardown / dirty-statistics flush | `0x4201eae0` / `0x4202e9b0` | `0x4201eab4` / `0x4202d0dc` |

This supports the same selected save order, unchecked legacy aliases, reset
error handoff, cached-account behavior, credential fallback after deinitialization
and later statistics/timestamp writes. The API-boundary host fixture remains a
reconstruction; matching helpers do not execute Standard NVS or prove power-loss
behavior. The [separate N02 SDK pass](#nvs-handle-dispatch-and-storage-writes-also-match)
now covers selected storage-writer/vtable bodies; other indirect key consumers
remain outside this reset comparison.

The main-loop reset handoff **does differ**. Large's bounded region
`0x42014079`–`0x4201421a` has 152 instructions in four ranges; Standard's
`0x42013ff7`–`0x420141d6` has 177 in three. End addresses are exclusive, and
neither is a whole-function comparison.

| Reset handoff operation | Large | Standard |
| --- | --- | --- |
| Initial delay after clearing pending flag | 200 ticks (2 s) | 200 ticks (2 s) |
| Additional wait before reset LED and network teardown | None in this region | 1,000 ticks (10 s) |
| Wait after accepted wake-image submission | Up to 12,000 ticks (120 s) for shared completion signal | Same wait value |
| Additional wait after successful completion signal and wake-image marker call | None in this region | 1,000 ticks (10 s) |
| Final handoff | Storage-sleep helper `0x42010674` | Model-specific sleep helper `0x42010db4` |

The extra waits are compiled delay requests, not measured wall-clock durations
or guaranteed maximums. A successful shared completion wait is not proof of the
requested pixels reaching the panel. Final sleep/display implementations and
the code outside these two regions are not recursively compared by this pass.
No reset, HTTP request, storage mutation or device timing experiment was performed.

### Cache recovery and persistence boundaries also match

Nine complete functions cover legacy-key format permission, filesystem-manager
initialization, file existence/size, last-image write/load/presence and the SDK
mount/format wrappers. All 796 instructions, 84 branches and 29 contiguous ranges
per model match after reviewing 24 direct-call pairs and 70 literal pairs.
Seven new pairs bring the public function map to 238 entries.

The substantive literal difference is the maximum save length: 2,566,144 bytes
on Large versus 1,048,576 on Standard. Neither is exact panel-size validation.
Both discard flush/close results, retain partial cache files after short writes,
and can return load failure with a modified destination and unchanged output
length. These are static application boundaries, not a tested flash failure.

The shared [recovery policy](storage-and-configuration.md#formatting-permission-is-not-proof-that-formatting-happened)
allows a fourth formatting-enabled mount attempt after three failures. Only two
FAT error classes enter the formatter, and its successful format can precede a
failed remount. Twenty-four isolated host groups check the SDK helper and
reconstructed application decisions once, not once per model. Actual FAT
corruption, wear-leveling/resource cleanup, interruption and frame recovery
remain untested; no artwork or storage was changed.

Three further pairs verify wear-leveling mount and VFS/disk-registration cleanup:
232 instructions, 24 branches and six ranges per model, with four direct-call
and 26 literal pairs reviewed. The map now contains 241 pairs. These support the
[late-failure handle-retention trace](storage-and-configuration.md#failed-mounts-can-retain-wear-leveling-handles):
both allocators use eight slots and do not deduplicate a partition. The already
compared SDK wrapper omits wear-leveling unmount on later error paths. Twelve new
host groups check that wrapper with slot accounting, without executing the full
driver or reproducing a physical memory/storage failure.

The registration helper is now compared as well: 83 instructions, 13 branches,
four ranges, four direct-call pairs and eight literal pairs. Both leave the
filesystem output untouched on an already-registered error, although the mount
wrapper accepts that status and consumes its uninitialized local pointer.
Both request 25,392 bytes for the four-file FAT context/flags, before other
overheads. The first twelve core/directory operation slots and sixteen directory
callbacks are mapped separately; their bodies are not all compared. This adds
one function pair, bringing the map to 242. No duplicate-registration crash or
actual heap-pressure failure was induced.

Seven cache-replacement primitives are compared next: FAT/VFS rename, sync and
close plus FAT error mapping. All 384 instructions, 93 branches and sixteen
ranges per model match, with twenty direct-call and thirteen literal pairs
reviewed. The map reaches 249 pairs. Both reject renaming over a different
existing object and clear the file-modified flag after the late filesystem sync
call even on error. Six unchanged-source RAM-filesystem groups distinguish
metadata failure from retryable file-buffer failure; they do not establish
the installed partition layout or physical power-loss behavior.

Three allocation helpers add 68 instructions, seven branches and four ranges
per model, with two direct-call and six literal pairs reviewed. Both FatFs ports
prefer `DEFAULT | SPIRAM` and fall back to `DEFAULT | INTERNAL` for each allocation.
The map now has 252 pairs. This establishes allocation policy, not actual runtime
placement, fragmentation or the cause of an earlier TLS allocation error.

### Buffer references and external cleanup ownership

The [ownership reference ledger](ownership-reference-coverage.json) accounts for
the same sixteen buffer-reference functions per build. Both have nine accessor
calls. Large has 25 recovered root instruction references and two exact global-
address words; Standard has 29 and three because its audio allocation is separate
and its renderer performs two controller transfers. All identified functions map
to the documented allocation, recording, upload, cache, image, health-check and
rendering paths. This census does not exclude computed aliases.

Seventeen paired transport bodies add 368 instructions, 58 branches and 27 ranges,
with 27 direct-call and ten literal pairs reviewed. Close can release TLS connection
storage without freeing the HTTP client; full teardown remains a separate path.
Thirteen paired task-local bodies add 331 instructions, 55 branches and 22 ranges,
with eleven direct-call and 37 literal pairs reviewed. Identified registrations
cover semaphore/runtime state, not automatic HTTP-client cleanup on task deletion.

The task-local reference census independently resolves seven call sites and four
exact API/callback words on each build. It rejects four Ghidra callback-argument
references per build as actual calls after checking the invoked registers.
Runtime lifetimes, computed registrations, external allocator/socket internals and
physical cancellation remain untested. These findings extend the static ownership
map, not a claim of a reproduced leak or crash on either model.

### Cancellation ownership and download timeouts also match

Two additional Standard reference passes compare fifteen function pairs covering
the six cancellation-manager helpers, HTTP prepare/close/connect/cancel/cleanup,
task deletion, download worker, voice orchestration and common image downloader.
GNU checks compare 2,346 Standard instructions in 63 ranges, including three
additional voice-header regions. The paired functions have matching register
operations and 210 internal branch targets after accounting for relocation,
alignment and equivalent narrow instruction encodings. External helper pointers
are mapped separately; this is not whole-firmware equivalence.

Standard's active-client record is at `0x3fcabd28`, with the same 24-byte layout
and ten-tick lock waits. Register/unregister are `0x42021e60` / `0x42021f14`;
abort is `0x420248f8`, aborted-read/reset are `0x42024a10` / `0x42024a60`.
A separate raw call scan finds the same **4 register + 7 unregister + 5 read +
5 reset** direct sites, all verified in caller context. It also retains the same
discarded registration/unregistration/reset results, preserved abort byte on
unregister and false result on failed aborted-byte reads.

Thus the [Large slot-ownership findings](voice.md#active-client-ownership-and-failed-unregistration)
also have matching Standard static paths: unregistration without an expected
client, double unregister in the downloader, open failure reaching unregister
without registering, and failed unregister followed by client cleanup. None has
been reproduced as a memory failure on either model.

Standard SDK cancellation `0x4206d174` has the same state gate, direct transport
close, prepare/connect call and synthetic processed-count assignment. Prepare
`0x4206cae0` preserves connection state, and connect `0x4206d018` tests that state
after prepare. The earlier ten-case host fixture remains host evidence; this
comparison adds compiled branch agreement, not ten additional tests or measured
socket behavior.

Voice orchestrator `0x42011a3c` passes the same 1,556-byte stack context to download
worker `0x420103fc`, with the same caller-stack result/count/handle offsets. Its
completion semaphore is at `0x3fca6b98`, and its processing flag at `0x3fca6b88`.
It discards task-creation status, waits 300 seconds, requests abort, then gives
the worker five seconds before potentially deleting the retained handle through
`0x40384c34`. Success during the grace period still returns failure without
rendering. The worker gives its semaphore before self-deletion and never clears
the retained caller handle. The same conditional stale-handle and skipped HTTP
cleanup concerns therefore apply despite Standard's separate image allocation.

Two numeric differences in the compared functions remain explicit:

| Voice-workflow parameter | Standard | Large |
| --- | --- | --- |
| Image download destination capacity | 960,000 bytes | 2,304,000 bytes |
| Wait for render completion after successful download | 9,000 ticks, about **90 seconds** | 18,000 ticks, about **180 seconds** |

The render-timeout diagnostic also differs accordingly. These waits are separate
from the maintenance helper's 60/90-second waits below. Neither voice-render
timeout branch cancels or joins the renderer; it returns failure before that
voice branch's cache save. A later display completion is therefore not excluded
by the caller's timeout. Scheduling and physical outcomes remain untested.

The shared backend should preserve completed jobs/artwork across interrupted
delivery, issue reusable exact-size model assets and avoid treating a closed
connection, timeout log or LED as a per-job render/cancellation acknowledgment.
This comparison changes no physical test status and does not identify the cause
of the earlier Standard TLS allocation error.

### Maintenance refresh differences

Standard `0x42026a18` powers on, sets the manager busy, and requests FULL
white/black/white conditioning before restoring an image. Large `0x42027f84`
hands a nonempty image directly to the ordinary render worker, whose own
conditioning selection still applies. This is a difference between these two
pinned releases, not proof that either panel permits different waveforms.

Both helpers drain the shared render semaphore before starting with DROP policy
and convert invalid-state/drop to success. Their accepted-image completion waits
differ: **60 seconds on Standard, 90 seconds on Large**. Neither timeout joins or
cancels the renderer. Standard returns on restoration error/timeout without the
final ready-state update; Large attempts that update on both. The signal still
has no content identity or per-job result.

Without an image, Standard completes its FULL cycle and marks ready; that helper
contains no explicit shutdown after the cycle. Large intends one white clear and
explicit discharge/off cleanup, but its busy-before-power-on ordering can cause
a self-induced ready timeout under otherwise uncontended state operations. The
[Large maintenance trace](rendering-and-concurrency.md#maintenance-refresh-has-separate-completion-rules)
details this conditional static finding. No blank, failure or maintenance-cycle
experiment was run on either frame.

### Polling, instruction tasks and conditioning differ

The 22 October follow-up compares the pinned Standard 0.2.28 and Large 0.2.29
branches, not merely their shared strings. Three Standard reference passes and
GNU checks establish these differences:

| Behavior | Standard | Large |
| --- | --- | --- |
| Poll dispatch while registered but unverified | Logs the state and continues toward the poll starter | Skips while the verification-running getter is true |
| Get Started pending flag/deadline | Created with a 120-second deadline; recovered getter caller is the OTA safety check | Also consulted before starting a new poll |
| Background instruction task creation | One task-creation call, without the Large heap-size precheck/retry loop | Requires at least a 10,240-byte largest internal block, up to eight creation cycles with 250 ms gaps |
| Temporary clear-pattern allocation | **2,048 bytes**, reused to stream a 480,000-byte block to both selected controllers | **288,000 bytes**, broadcast to all eight selected controllers |
| MIN conditioning | Black clear, 500 ms extra delay, logs errors but returns success | Black clear, 100 ms extra delay on success, propagates power/clear result |
| MID conditioning | White/black clears, 500 ms after each, returns success despite clear errors | Same pattern/delays and unconditional success, through a separate helper |

Both instruction starters copy the two arguments to an 8-byte heap context;
their workers copy/free it before use and wait up to 90 seconds on the global
render semaphore. Both instruction dispatchers write into the shared image
allocation before WAIT/DROP arbitration and can cache the image after render-start
but before completion. These common structures do not make panel rendering or
task scheduling identical.

Standard's verification task/start pair (`0x42022124` / `0x4202309c`) has the same
unescaped credential JSON and token-substring exit behavior traced in Large. Its
starter lacks Large's running-byte publication, and its poll dispatcher
`0x42016590` does not consult a verification-running getter. The shared HTTP event
callback at `0x42021f7c` has the same destination/length/capacity globals and
whole-event overflow skipping; it does not provide client-scoped response memory.

The Standard Get Started getter `0x42029aa4` is **not unused**: the recovered
reference is from OTA safety function `0x42016420`. It is absent from the compared
poll dispatcher. This narrows the concurrency protection without claiming that
all Standard activity is unguarded. None of these differences independently
explains the captured Standard `mbedtls_ssl_setup` allocation failure; no
simultaneous-request or heap-fault experiment isolated its cause.

The elapsed conditioning selector at `0x4202c038` uses the same EXT1/timer,
time-valid, stored timestamp and 12/48-hour boundaries as Large. Standard's
internal conditioner `0x420267b4` also contains a mode 2 labelled
`FULL (WHITE→BLACK→WHITE)`, called by refresh/restore helper `0x42026a18`.
These are full-panel pattern cycles, not custom waveform or partial-refresh
capabilities. Other Large maintenance paths and physical behavior remain separate
research questions.

**Firmware idea:** Standard demonstrates a small reusable buffer for a constant
clear pattern. A similar streaming change is a candidate for reducing Large's
temporary allocation by 285,952 bytes. Its actual heap placement, driver/power
constraints and physical correctness need validation before implementation; it
does not by itself provide enough memory for another full Large image snapshot.
Because both model and release differ, these differences cannot be attributed
solely to the panel size or solely to the version increment.

### Embedded status images and markers

The [Standard RLE comparison](storage-and-configuration.md#standard-status-assets-use-different-row-geometry)
now covers the decoder and show/restore/persistence helpers. Standard expands a
26,958-byte embedded low-battery asset into two 480,000-byte halves; Large expands
216,382 bytes into eight 288,000-byte blocks. Eighteen Standard host cases pass,
and an independent decode matches the complete vendor-asset output. They share
the malformed-run checks, partial writes and unchecked colour/trailing-pair rules,
but use different strip geometry and cannot share encoded status artwork.

Both builds write the image allocation before DROP arbitration and update
`sys_img` on render acceptance, without awaiting physical completion. Both can
clear the marker after a failed cache load without restoring the artwork. The
comparison adds no physical display, overlap, storage-fault or recovery evidence.

## Keep model renderers and power paths separate

The Standard renderer sends two 480,000-byte blocks. Its resolution command uses
1200 × 800 per controller, consistent with the integration's 1600 × 1200 profile.
Its exact panel part number remains unidentified. Large uses EL315TW1 with a
portrait-native 1440 × 2560 layout and eight padded controller blocks. Packing,
rotation, waveforms, GPIOs and power sequencing belong to the model profile.

The Standard local upload handler rejects lengths above 960,000. A downstream
render-start tolerance of ±1,024 bytes is not a format specification: produce
exactly the model's expected payload. Both local handlers can report `rendering`
before physical completion.

Static power differences also matter: the Standard voltage getter returns the
gauge reading without Large's doubling and has an ADC fallback. Large's examined
path doubles the gauge result and returns zero on gauge failure. Post-update
health accepts 2,000–6,000 mV on Standard and 5,000–9,000 mV on Large; both
pre-update percentage helpers retain the 3,000–4,200 mV calculation and nominal
30% threshold. This supports the documented Large OTA-voltage mismatch, without
establishing its development history or testing a low-battery update.

## Enrollment and setup screens

The complete [setup metadata and fetch paths](cloud-protocol.md#setup-metadata-comparison-and-host-boundaries)
now match across three function pairs, 422 GNU instructions and 38 branch
destinations, apart from the expected `133` / `315` model literal. Both accept
chunked metadata after a zero header-fetch result and reject URLs of 1,536 bytes
or more instead of truncating them. Nineteen isolated reader/parser host cases
cover those boundaries and partial-response acceptance; they do not add a new
physical setup test or prove every external SDK/driver helper equivalent.

The trace records these owner-initiated API calls:

| Route | Result |
| --- | --- |
| `GET /api/v1/upload/global/133/create_account?ip=…` | HTTP 200 and `presigned_url` |
| `POST /api/v1/account/setup`, twice | HTTP 200, `success: true`, successful setup message |
| `GET /api/v1/upload/global/133/get_started` | HTTP 200 and `presigned_url` |

Setup sends string fields `email`, `password`, `device_key`, `mac_address` and
`display_type`. Its 764-byte responses contain `success`, `message` and
`device_info`; the latter includes identity, `user_id`, settings, pending
settings, public ID and telemetry. The exact **type-only** response shapes are in
[model-comparison.json](model-comparison.json). Registered/account-created flags
changed false → true and survived restart. Minimum required emulator fields and
complete independent enrollment remain untested.
The later [static parser trace](cloud-protocol.md#enrollment-boundary) narrows
the response fields consumed by both models; it does not turn the vendor capture
into a minimum-response experiment.

Both setup-screen URLs pointed to the vendor's S3 bucket. Capturing the URL
response does not establish local caching or offline availability of those
screens.

During setup the UI reported a wrong password, while device logs showed
`mbedtls_ssl_setup` failing with `-0x7F00` before a subsequent sign-in connection.
Espressif identifies that code as SSL allocation failure in its
[Mbed TLS troubleshooting reference](https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/advanced-development/protocol/mbedtls-troubleshooting.html).
Registration had already succeeded; another image connection also hit allocation
failure. This does not independently validate the password or identify the
source of memory pressure. Concurrent downloads, diagnostics and proxy overhead
were not isolated. Inspect the underlying error before interpreting a UI label.

## Public reachability caused a real transfer failure

The existing IoT policy blocked Standard's TCP connection to `8.8.8.8:53`.
The frame treated that as no internet, repeatedly switched APs, and stopped an
otherwise working image download at **556,592 / 960,000 bytes**. An owner-approved
temporary exception for that frame and destination, ordered before the block,
restored internet-available state and stabilized the connection.

This is an observed TCP reachability gate, not an observed Google DNS query.
Changing the API origin alone cannot make the frame fully local. A future fork
needs backend-aware connectivity policy and configurable/local time services.
This Standard observation supports the Large static trace without proving every
Large outage/recovery transition. All temporary exceptions were removed; the
original policy again blocks Standard's probe. No permanent exception was approved.

## Poll and voice observations

Eighteen captured polls were HTTP 200. Idle cadence was about 30 seconds, with
extra checks on taps/restarts. Query fields were `display_type`, `orientation`,
`is_periodic_poll`, `current_version`, `battery_pct`, `wifi_ssid` and `ip`.
Idle results contained false upload, null image/firmware/deadline/account and a
settings object with `style`, `keepAwakeEnabled`, `chargingLedEnabled` and
`voiceRecordingEnabled`. `autoUpdateEnabled` was absent in these responses.
This does not override the static full-snapshot/defaulting behavior or justify
omitting a future deadline in an emulator response.

Voice initially failed before upload because cloud settings disabled recording.
The subsequent generic timeout/no-upload log did not prove a microphone timeout.
The owner enabled voice, the setting was verified and the frame restarted. That
sequence demonstrates a working enabled state, not that restart is always required.

The ensuing vendor-backed workflow completed:

| Stage | Observed result |
| --- | --- |
| Recording | 192,556 WAV bytes: 44-byte header plus 192,512 audio bytes, about six seconds |
| Presign | HTTP 200; 3,553-byte JSON with `success`, `url`, `fields`, `key`, null `upload_id`, `message` |
| Multipart form | Fields included Content-Type, encryption setting, key, access-key ID, session token, policy and signature |
| Direct storage upload | HTTP 204; about 13.1 seconds |
| Finalize | `{device_key,user_id,key,orientation}`; about 26.265 seconds at proxy, about 28 seconds in device measurement |
| Finalize response | HTTP 200; 1,542 bytes with `success`, `message`, null `upload_public_id`, `presigned_url`; **no `status` field** |
| Image download | HTTP 200, all 960,000 bytes; about 90 seconds |
| Display | `Render OK` about 35 seconds later; 0 failures / 3 attempts; owner confirmed the generated image appeared |

The omitted `status` is live evidence for Standard's default-to-completed path.
The direct 204 upload is an additional observed success status; its encrypted
storage response body was not captured by the API proxy. Large's local test
separately established HTTP 200 with an empty acknowledgment and `{}` form fields.
The 3,553-byte vendor presign response fits under the recovered 4,095-byte JSON
read limit, but leaves limited space for added fields.

The slow image transfer bypassed the API proxy. Its bottleneck was not isolated;
do not attribute it to the proxy or generalize it to local delivery. Standard's
`last_refresh` remained null after successful display, independently reinforcing
that maintenance history is not an image acknowledgment.

## Prompt visibility and HA reuse

The API capture did not recover spoken words or the final AI prompt: the recording
went directly to storage over HTTPS, and presign/finalize contained neither.
A subsequent private correlation did identify this exact creation in the
authenticated gallery. The finalize image URL and gallery original share the
same generation directory and non-user UUID, which also matches the audio job's
object key. The gallery record was created at 18:52:44.626 UTC, immediately before
the captured finalize completed at 18:52:44.748 UTC; matching object identity,
not timestamp proximity alone, establishes the link.

That gallery record contains a nonempty transcript and the original 1200 × 1600
PNG. It is the same 4,016,864-byte original used in the verified expired-URL
[refresh test](validation-2026-10-21.md#authenticated-gallery-and-album-reads-c10c12e03).
The API's gallery upload ID is not literally the object-key UUID, so retain an
explicit mapping rather than assuming those identifiers are interchangeable.
No recording was decrypted, and neither transcript text, job identifiers, signed
URLs nor artwork is published here. The final vendor generation prompt remains
unknown; a transcript alone does not establish it.

The owner is interested in prompt visibility. A shared adapter can retain
recording, transcript, interpreted intent, final generation prompt, model/style
and original artwork under one stable job ID, then expose the result in HA's
library and playlists. Keep model-specific packed assets derived from that
canonical original. The local job record is a proposed feature, not recovered
vendor prompt data or an implemented integration.

## TLS setup allocation and configuration also match

Fourteen complete function pairs match across 644 instructions, 100 branches
and 36 GNU ranges per image. Forty-three direct-call and 48 literal pairs are
mapped; seven fixed configuration tables are compared at their actual lengths,
and both allocator dispatch slots select the compared helpers. The public map
now contains 266 pairs. This does not establish every external callee's behavior
or equivalence of runtime configuration values.

Both builds have the same [TLS 1.2 configuration and setup memory requirements](cloud-protocol.md#tls-setup-needs-internal-ram-before-authentication),
including 16,717/4,429-byte record buffers, 220/144/584-byte negotiating
structures, and allocator mask INTERNAL | 8BIT. Unlike the separately traced
FatFs allocator, this initial TLS allocation route has no PSRAM fallback.

The eight host groups are one shared source-fixture run with target-sized opaque
allocation objects and stubbed configuration, crypto and pointer-reset helpers.
They do not execute Xtensa code, establish heap fragmentation, perform a TLS
handshake or reproduce the observed Standard failure. That failure's exact
allocation and runtime cause remain unknown.

## Compiled TLS cipher and name capabilities also match

Six additional complete function pairs cover cipher lookup/list filtering,
the removal predicate, hostname/ALPN setters and ESP-TLS client configuration.
They match across 425 instructions, 69 branches and 21 GNU ranges per image,
with sixteen direct-call and 37 literal pairs mapped. The public function map
now contains 272 pairs.

All 58 cipher-definition records match after their names are dereferenced, and
all 185 preference IDs plus the terminator match byte-for-byte. The resulting
[compiled inventory](tls-capabilities.json) and [hostname/configuration limits](cloud-protocol.md#compiled-cipher-suites-and-hostname-configuration)
are shared by these builds. No new host fault fixture or device handshake was
run. Follow-ups below check selected cipher/SNI/ALPN writers and HTTP
construction. Negotiated choice and trust/credential interoperability remain
separate.

## ClientHello field serialization also matches

Six complete paired bodies cover SNI, ALPN and cipher-list writers, the body
writer that calls them, cipher version validation and the EC-use predicate.
They match across 427 instructions, 97 branches and 28 ranges per model,
with ten direct-call and three identical scalar/ROM literal pairs. The public
map now contains 278 function pairs.

The [fourteen source host groups](validation-2026-10-22.md#clienthello-field-serialization-c03e01e02)
are one shared run using the compared cipher definitions and selected unchanged
Mbed TLS functions. They confirm the default 58-suite field plus initial SCSV,
SNI name copying, null/empty extension distinctions and short-buffer results.
They do not send a ClientHello, negotiate TLS or exercise all extensions. The
following static pass checks how the HTTP client configures ALPN.

## HTTP construction and ClientHello submission also match

Twenty-four complete function pairs cover the HTTP constructor/common options,
two wrapper helpers, fifteen TLS/context setters, the separate port setter,
and four ClientHello submission/header helpers. They match across 727
instructions, 121 branches and 42 ranges per model, with 21 direct-call and
53 literal pairs mapped. The public function map now contains 302 pairs.

The [construction/submission findings](cloud-protocol.md#stock-http-construction-leaves-alpn-unset)
establish null ALPN through this stock HTTP path, a 4,092-byte body buffer and
failure-before-finish behavior. This is static evidence with no new host fault
fixture or device request. It does not cover complete record/socket retries,
all extension helpers, arbitrary external configuration writes or physical
no-ALPN interoperability.

## OTA write lifecycle also matches

Six complete paired functions cover OTA begin/write/end/abort, handle lookup
and the partition-type predicate. Their 326 instructions, 69 branches and
20 ranges per model match, with seven direct-call and eighteen literal pairs
mapped. The public function map now contains 308 pairs.

The shared [22 source-level host groups](ota-and-recovery.md#ota-handle-and-write-fault-fixtures)
reproduce erase-before-reject, error/context ownership and a conditional
encrypted partial-block erase gap. They use RAM and stubbed image validation;
neither unit's flash encryption, partition contents, custom-image acceptance or
physical rollback is established. External partition/verification callees are
mapped, not recursively proved equivalent by these six pairs.

## Upload acknowledgment SDK callbacks also match

Five complete function pairs cover header fetching, headers-complete, body
caching and message-begin/end callbacks. Their 194 instructions, 22 branches
and seven ranges per image match, with four direct-call and fifteen literal
pairs mapped. The public function map now contains 313 pairs. The previously
compared complete multipart bodies supply the caller's return/status branch.

The [24 acknowledgment cases](voice.md#upload-acknowledgment-parser-and-early-success-boundaries)
are one host run with the matching SDK parser source and callback functions,
scripted transport and a reconstruction of that immediate caller branch.
They do not prove live response segmentation, cancellation races, all parser
configuration/callbacks or external-helper equivalence on either model.

## HTTP response-cache cleanup also matches

Two additional complete function pairs cover cache cleanup and client cleanup:
88 instructions, ten internal branches and two ranges per image. Six direct
call pairs and the free-helper literal pair are mapped; external callees are
not all recursively compared. The function map now contains **314 pairs**.

Together with the already compared body/fetch callbacks, these establish the
same lost-cache-ownership branch after failed `realloc` growth on both apps.
The [twelve isolated allocation cases](voice.md#http-response-cache-growth-can-lose-an-allocation)
are one host fixture with pinned SDK/parser code and a tracked allocator, not
two device tests. No live heap-pressure, fragmentation or TLS-cause claim follows.

## Microphone and LED configuration

The subsequent [audio-output audit](hardware-and-layout.md#audio-output-audit-across-both-models)
checks both microphone initializers and three LED bodies. Both microphones use
RX-only I2S0 PDM at 16 kHz/16-bit mono; clock/data GPIOs are **41/42 on Large** and
**4/8 on Standard**. LED channel GPIOs are **38/47/13** and **38/13/12** respectively.
The LED bodies share 5 kHz/eight-bit inverted RGB duty behavior after these pin
substitutions. This adds no physical output-hardware or cross-flash evidence.
The separate [coverage record](audio-output-coverage.json) retains this bounded
comparison without treating the different microphone initializer bodies as
instruction-for-instruction equivalents.

## Coverage and cleanup

The 24 decoded origin-API exchanges were complete and all HTTP 200: one
create-account asset, two setup requests, one get-started asset, 18 polls,
one presign and one finalize. Direct S3 bodies were not decrypted. AP captures
include DNS/NTP/connection metadata, duplicate interfaces and substantial bulk
traffic omissions; they are not a complete packet record. Diagnostic reads can
keep the device awake, so this is not a battery or ordinary sleep baseline.

The handoff records removal of both NAT redirects, both temporary allow policies
and the generated return policy. The original DNS block was restored to index
10000 with only its pre-existing Large exception; configuration matched baseline
apart from counters. Proxy, sampler, six long AP captures, expiry worker and
task-owned SSH masters were stopped. Owner-enabled voice/keep-awake settings were
preserved. No HA deployment or firmware update occurred. This import made no
additional changes to the Standard frame or its network rules.

Raw flows, logs, recordings, firmware binaries and packet captures remain private.
Only report-derived observations and type-only schemas are published here.
