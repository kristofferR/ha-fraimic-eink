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

The preserved metadata maps 100 corresponding functions, including the subsequent
account-setup, `/dev`, calendar, orientation, album-body, task/conditioning,
maintenance, LED, status-image and SNTP/DHCP/DNS comparisons. The poll paths share 86
referenced strings apart from their model/version literals; selected presign and
finalize paths share 32 and 44 strings respectively. Control-flow inspection
supports a shared cloud contract. Identical routes/strings alone do not prove
all handlers behave identically.

The `/dev` POST handlers use the same embedded seven-byte password and the same
length/byte comparison structure after form decoding. The value was supplied
privately to the owner. Neither device was switched to development mode; the
[detailed transition and error-path trace](storage-and-configuration.md#vendor-environment-switch)
is for Large unless explicitly stated otherwise.

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

These are selected matching static branches, not full SDK/control-flow
equivalence or a new fault-injection run. The earlier host parser/timeout fixtures
remain Large-derived. Keep the synchronous adapter contract shared and the
renderers, capacities and ownership models explicit per build.

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
