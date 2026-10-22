# Local HTTP API and diagnostics

[Research index](README.md)

The app contains **42 method/path registrations**, including onboarding, portal,
diagnostics and the integration-facing API. This is a static registration
inventory for Large 0.2.29, not a claim that every handler was exercised or is
available in every boot state. The [existing frame reference](../frame-api/routes.md)
records observed behavior across several releases.

## Complete registration inventory

`*` below is the registered wildcard, not a literal album identifier. Each row's
handler and registration-record file offset are in
[route-registrations.json](route-registrations.json). Descriptions summarize the
recovered role; they are not complete request schemas.

The [handler contract ledger](route-contract-coverage.json) reconciles all 42
registrations, covering 39 distinct handlers, to consumed inputs, response shape,
access checks, effects and the detailed evidence below. Its method/path/handler
triples are checked against the original registration bytes. It closes the
bounded static inventory; it does not establish live availability in every boot
state or every browser behavior. The later [complete paired-handler comparison](standard-model-comparison.md#complete-local-handler-comparison)
checks both builds and identifies two structural differences; mapped external
callees and model-dependent data are not thereby equivalent.

| Method | Path | Role / effect |
| --- | --- | --- |
| GET | `/complete` | Completion HTML; does not itself complete pairing |
| GET | `/create-account` | Account creation page |
| POST | `/create-account` | Account creation / configuration writes |
| GET | `/sign-in` | Sign-in page |
| POST | `/sign-in` | Authentication / configuration writes |
| GET | `/api/verification-status` | Cached local verification flag |
| GET | `/` | Portal entry page |
| GET | `/scan.json` | Wi-Fi scan results |
| POST | `/connect` | Wi-Fi connection configuration |
| GET | `/hotspot-detect.html` | Captive-portal handling |
| GET | `/generate_204` | Captive-portal handling |
| GET | `/connecttest.txt` | Captive-portal handling |
| GET | `/connect` | Connection page |
| GET | `/wifi` | Same embedded HTML as captive-portal probe routes |
| GET | `/upload` | Upload page |
| POST | `/upload` | Multipart image upload and render |
| GET | `/action` | Portal actions; not a generic read endpoint |
| GET | `/portal` | Portal page |
| GET | `/info` | Detailed HTML device information |
| GET | `/wifi-stats` | Wi-Fi diagnostics |
| POST | `/clear-stats` | Clear diagnostic history |
| POST | `/switch-ap` | Change Wi-Fi/AP selection |
| GET | `/check-internet` | Connectivity diagnostic |
| GET | `/logs` | Log UI; cookie controls detail visibility |
| POST | `/logs` | Log access/form handling |
| POST | `/logs/action` | Log controls |
| GET | `/get-started` | Setup page |
| GET | `/test` | Factory-test page or selected diagnostic; see side effects |
| POST | `/test` | Factory microphone, touch, accelerometer and image-upload actions |
| GET | `/dev` | Developer-mode page |
| POST | `/dev` | Password-gated vendor environment switching |
| GET | `/battery/status` | Battery status |
| GET | `/api/info` | JSON device snapshot |
| GET | `/api/battery` | Lightweight JSON battery probe |
| POST | `/api/restart` | Restart |
| POST | `/api/sleep` | Request deep sleep |
| POST | `/api/refresh` | Request display refresh |
| POST | `/api/image` | Raw image upload and render |
| GET | `/api/albums` | List albums through cloud proxy |
| POST | `/api/albums` | Create album through cloud proxy |
| PUT | `/api/albums/*` | Update album through cloud proxy |
| DELETE | `/api/albums/*` | Delete album through cloud proxy |

The integration-facing `/api/*` controls use plain HTTP without authentication
in the observed stock interface. Password-gated diagnostics do not make the
entire local server authenticated. Restrict access to the intended LAN; an
emulator should keep its owner/admin interface authenticated and use separate,
device-scoped credentials for frame traffic.

## Local discovery and hostname lifetime

Large's Wi-Fi/IP event handler `0x4201ab08` initializes mDNS on its first
station-IP event. Standard's corresponding handler is `0x4201aadc`; Ghidra split
its IP branch into a misleading separate function at `0x4201af95`, but GNU
control-flow recovery reaches that branch from the actual entry.

The application calls mDNS initialization, sets the primary hostname to
`fraimic`, and sets the default instance name to `Fraimic Device`. It then
derives a second name from the setup SSID:

| Item | Recovered construction |
| --- | --- |
| Setup SSID | `Fraimic_` followed by unsigned decimal `(mac[4] << 8) | mac[5]`, without zero padding |
| MAC source | Station MAC first; base-MAC fallback if that read fails |
| Both MAC reads fail | Cache the literal `fraimic_setup` instead |
| Additional mDNS hostname | `fraimic_` plus everything after the SSID's first underscore, normally `fraimic_<decimal>.local`; the fallback yields `fraimic_setup.local` |
| Additional address | One IPv4 address copied from `WIFI_STA_DEF` into a zeroed 28-byte address-list node |

The SSID helper (`0x42019b24` / Standard `0x42019af8`) caches its result for
the running application. The ordinary suffix has only 65,536 possibilities;
it is not a complete MAC, account identity or collision-proof identifier.
The fallback suffix is shared. No actual MAC or device-specific suffix is
included here.

The additional hostname uses **delegated-host registration**, not another
interface-bound primary hostname. Large wrapper `0x42040030` copies the supplied
address list through `0x42039dec` before queueing it. The application obtains that
address only inside the one-time initialization block. A failed netif lookup or
IP-info call skips the delegated name; a successful IP-info call is not followed
by a separate nonzero-address check.

All four mDNS return values are ignored. The application logs that mDNS started
and sets its RAM flag (`0x3fca743c`, Standard `0x3fca74ac`) even if initialization,
hostname, instance or delegated-host setup failed. Recovered references to that
flag contain only this check and final write; the disconnect/reconnect branches
do not clear it. Thus the next IP event does not retry this application setup
or recopy the delegated address. **Inferred risk:** the additional name can retain
an old address after an IP change during the same boot. This is not a packet-level
demonstration, nor a claim that the primary hostname ignores the SDK's interface
events. Collision renaming, caching and delegated-address behavior on the wire
remain untested.

The hostname-set and delegated-add wrappers queue with zero wait, then wait on
the mDNS action semaphore with `portMAX_DELAY` after a successful enqueue.
Instance-name setting queues without that completion wait. The application has
no finite timeout around these calls, and starts/reuses its HTTP server only
after this block. A stalled action worker is consequently another conditional
way to delay local-server startup; no such stall was induced.

### Hostname resolution does not establish HTTP service discovery

No service-registration call appears in this recovered application setup, and
neither pinned image contains a terminated `_http` literal. Setting a default
instance name alone does not add an HTTP service. Espressif's
[mDNS API](https://raw.githubusercontent.com/espressif/esp-protocols/mdns-v1.5.0/components/mdns/include/mdns.h)
separately defines hostname, delegated-host, instance-name and service-add
operations. That release is an API reference, not a verified dependency version
for these images.

The integration's [manifest](../../custom_components/fraimic/manifest.json)
matches `_http._tcp.local.` instances named `fraimic*`. These static findings
therefore do **not** establish that stock firmware emits the service records
needed to trigger that matcher. They also do not rule out a constructed or
unrecovered registration elsewhere. Resolving a `.local` hostname successfully
is insufficient evidence for automatic HA service discovery.

[Config flow](../../custom_components/fraimic/config_flow.py) probes `/api/info`
after a zeroconf/DHCP hint and prefers `device_key`, then `device_id`, then the
host for its unique ID. An existing matching ID updates the stored host.
[Subnet rediscovery](../../custom_components/fraimic/discovery.py) also probes
the API and matches the expected device key. This verification is more useful
than trusting the shared primary name or truncated MAC suffix. The key is also
a cloud credential and belongs in private state. Its stability across environment
changes, reset and reprovisioning is a separate
[identity question](storage-and-configuration.md#identity-cache-and-read-errors),
not established by mDNS.

Evidence: seven paired function bodies, 39 contiguous GNU ranges per build,
1,189 byte-matched instructions and 148 matched branch destinations. Strings,
event-base names and selected initialized data agree; external call targets and
RAM globals are mapped separately. No multicast queries, DHCP changes, frame
requests, HA changes or live failure tests were performed for this pass.

## Server capacity and lifecycle

Large startup helper `0x4201a69c` copies the 88-byte configuration at
`0x3c13bd98`, then overrides stack size, handler/header capacity, timeouts and
URI matching before calling `httpd_start` (`0x4206f9d4`). Reading the actual
constant and its writes gives these effective values; they are not assumptions
based on SDK defaults. Field layout matches the
[IDF 5.4.1 configuration structure](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_server/include/esp_http_server.h).

| Field | Effective value |
| --- | --- |
| HTTP port | 80 |
| Internal control port | 32768 |
| Task priority / stack | 5 / 20,480 bytes |
| Core affinity | `0x7fffffff`, no affinity |
| Task memory capabilities | `0x804`, internal and 8-bit accessible |
| Client socket slots / listen backlog | 7 / 5 |
| URI handler slots / response-header slots | 43 / 16 |
| Socket receive / send timeout | 60 seconds each |
| LRU session purging | Disabled |
| TCP keepalive / socket linger | Disabled |
| Custom open/close callbacks and global contexts | Null |
| URI matcher | Wildcard helper `0x4207135c` |

TCP keepalive here means TCP-level probes, not whether HTTP connections can be
reused. The socket timeout is not a whole-request deadline. A body-reading loop
can make several calls, and cloud requests have their own limits. The 16-header
setting is response capacity, not an incoming-header length limit.

The configured seven clients share one server task, `0x4206f944`, which runs the
select/session loop at `0x4206f7d0`. The recovered upload, scan and album-proxy
handlers perform their blocking work inline; they do not hand those operations
to the SDK's asynchronous-request API. Consequently, a slow request can delay
unrelated status/control requests on other sockets. This follows the binary
and the [matching SDK loop](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_server/src/httpd_main.c),
but no concurrency or socket-exhaustion fault was induced. HA should serialize
device operations and avoid overlapping diagnostic polls with large uploads.
Background voice/display tasks remain separate and can still contend for the
shared image buffer.

### Unread bodies are drained after some error responses

An HTTP error status does not itself tell ESP-IDF to close the connection.
Both builds propagate the URI handler's **return value** through request/session
processing. If it is zero, the server runs unread-body cleanup before returning
to its socket loop. A nonzero handler return instead cleans the request and
closes that session without this drain.

The actual purge routine (`0x42070370` Large / `0x4206f968` Standard) receives at
most **32 bytes per iteration** until the remaining-length field reaches zero.
A nonpositive receive result, including timeout or EOF, ends the drain and causes
that socket to close. Positive short reads continue; there is no whole-drain
deadline in this routine. The receive wrapper subtracts only nonnegative returned
byte counts. On failure, the session-delete path closes the socket, marks its slot
free and decreases the active-client count; it does not stop the entire server.

| Response/handler outcome | After the handler |
| --- | --- |
| Raw unsupported-type error successfully sent; handler returns zero | Drain any unread body, despite HTTP 501 |
| HTTP 500 sent but handler returns zero | Same drain rule |
| Handler returns failure, regardless of HTTP status | Clean request and close socket, no purge loop |
| Purge reads all remaining bytes | Clean request and retain session for reuse |
| Purge times out or encounters EOF | Clean request and close only that session |
| Multipart accepted an incomplete body and returned zero | Purge the declared remainder after the HTML response |

Thus a rejected raw upload can still occupy the sole HTTP task after its error
response. Draining an entirely unread 2,304,000-byte body requires at least
72,000 successful reads with this 32-byte cap; 960,000 bytes requires 30,000.
These are arithmetic bounds on call count, not measured transfer time. If the
sender stops instead, a receive failure ends the drain. An early response does
not guarantee that unrelated controls can be serviced immediately.

This refines the upload comment in [`api.py`](../../custom_components/fraimic/api.py):
the raw **handler** rejects without reading, but SDK cleanup can drain afterward.
It provides a bounded mechanism for temporary blocking, not proof of the cause
of the historical persistent upload failure or a reason to restart automatically.

Nine complete function pairs, **389 instructions per build**, match normalized
operations and internal branches. They cover parser-to-URI return propagation,
request/session lifecycle, receive/purge and dispatch-to-close. The structure
also agrees with [SDK request cleanup](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_http_server/src/httpd_parse.c)
and [session processing](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_http_server/src/httpd_sess.c).
Twenty-four [instruction cases](http-purge-cases.json), twelve per build, exercise
seven of those bodies and 221 distinct instructions each. Parser/handler returns,
HTTP status, initializers, lower socket I/O, events, context destruction and close
are modeled. No wall-clock timing, live socket failure or persistent stall was
measured. Registered ordinary handlers still run synchronously; the checked
asynchronous-session skip branch does not mean these uploads use that API.

### Registration failures

Registration comprises 25 portal routes, six account/configuration routes, one
battery route and ten integration API routes: 42 entries in 43 available slots.
There is no common transactional registration check:

| Registration group | Failure handling in this build |
| --- | --- |
| Portal, inside `0x4201a69c` | Individual registration results are ignored |
| Account/configuration, `0x4201978c` | Each error calls fatal `ESP_ERROR_CHECK` path `0x40381d68` |
| Battery, `0x42029e64` | Return error; caller logs it and continues |
| Integration API, `0x420310b0` | Stop at first failure; earlier routes remain; caller logs and continues |

The fatal account-registration path prints the failed expression and enters a
nonreturning abort routine, matching
[the SDK error-check implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_system/esp_err.c).
It must not be described as another recoverable registration error. In the
nonfatal cases, the final server-started message does not establish that all
routes exist. Calling the startup helper again while handle `0x3fca7470` is
nonzero returns success immediately, without retrying missing registrations.

Teardown `0x4201eae0` saves Wi-Fi statistics and calls `httpd_stop`
(`0x4206fa88`) before the later network shutdown. That stop sends a control
message and waits for the HTTP task to stop; its wait has no separate overall
deadline. An active blocking handler can delay it. If the control-message send
fails, stop returns an error, but the application still clears its saved handle.
This is a static failure-path finding, not an observed leaked server or sleep
hang. The physical sleep and shutdown cases remain open.

## Onboarding page reads and local verification

These GET handlers have distinct meanings despite their setup-oriented names:

| Route | Recovered handler behavior |
| --- | --- |
| `/` | HTTP 302 to `/get-started` when the cached email is empty, otherwise `/portal`; does not require verified=true or a usable voice user ID |
| `/get-started` | Serve embedded HTML; the handler does not invoke the e-ink instruction downloader |
| `/complete` | Serve completion HTML/links; no pairing save, verification promotion or device-side network request in the handler |
| `/sign-in`, `/create-account` | Serve form HTML with the cached email prefilled; no upstream account request until form submission |
| `/api/verification-status` | `{"verified":true}` or `{"verified":false}` from cached byte `+0x106`, with `Cache-Control: no-store, no-cache, must-revalidate` |
| `/wifi`, `/hotspot-detect.html`, `/generate_204`, `/connecttest.txt` | Same embedded HTML handler; no HTTP 204, special OS probe body or HTTP redirect is selected based on the route name |

Verification-status performs no fresh vendor check and does not report the
verification task's running flag, retries, errors or response state. Its cache
header controls browser/proxy caching, not the firmware's identity cache. Backend
UI should distinguish local verified state, usable identity and active enrollment.

The form handlers insert the saved email directly into a single-quoted HTML
attribute, without an HTML-escaping call in those handlers. A future firmware UI
should escape that text; no crafted email was stored or browser behavior tested.
The selected embedded scripts are traced below; this is not a complete browser
audit of every page.

The identity accessor used here, `0x4201912c`, is lazy: once its initialized byte
is set it returns the RAM configuration directly. Only its first-use branch
copies defaults, marks initialized, and loads NVS. If opening that namespace
fails, it attempts to save defaults and ignores that save result. This is a
conditional initialization side effect, **not a write on every GET**. Startup
normally initializes the cache before serving these pages. Per-field read errors
are separately defaulted by the loader; see
[identity error handling](storage-and-configuration.md#identity-cache-and-read-errors).

### Account form limits apply before decoding

Both local account POST handlers call `httpd_req_recv` (`0x420711fc`) once for
at most **511 bytes**, append NUL to the returned prefix, then parse it. They do
not loop to the declared content length. The matching
[SDK receive implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_server/src/httpd_txrx.c)
can return a positive partial read. A field split across that boundary can be
absent or shortened while still looking like a complete local string; even a
short form is not guaranteed to arrive in one read.

Field lookup `0x420703b0` receives a 128-byte temporary buffer. Its limit is
**127 encoded bytes per value**, before application decoder `0x420175dc` runs.
On overflow the lookup copies a truncated value and returns `0xb004`; these
callers skip decoding on any nonzero result, leaving their zeroed destination
empty. There is no dedicated overlong-field response at that branch. This matches
the [SDK query helper](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_server/src/httpd_parse.c).

| Synthetic input | Host result through recovered field rules |
| --- | --- |
| 127 plain ASCII value bytes / 128 bytes | Accepted / destination left empty |
| 42 literal plus signs encoded as `%2B` / 43 signs | Accepted / destination left empty |
| 21 `é` characters encoded as `%C3%A9` / 22 characters | Accepted / destination left empty |
| Duplicate names with different case | First case-insensitive matching field wins |
| Percent-encoded field name | Name is not decoded before lookup |
| Receive prefix ending inside a value | Shortened value can return success |
| Decoded `%00` in a value | Decoder writes NUL; downstream C-string consumers see the prefix |

Email, password and confirmation use the decoder, which translates plus to space
and accepted percent pairs to bytes. The create-account timezone instead goes
through the bounded string-copy helper, without URL decoding. The 19 stock
dropdown values contain no characters that `URLSearchParams` needs to escape,
but a custom POSIX rule with commas/slashes would need correct decoding; do not
assume an encoded custom timezone reaches storage unchanged in meaning.

The thirteen host cases combine the unchanged SDK lookup function with a
reconstruction of the application decoder and receive-prefix handling. They
passed with address/undefined-behavior sanitizers. They do not execute the frame's
socket receiver, registration or NVS and do not establish the cause of any earlier
owner setup failure. A firmware fix should read a complete bounded form, decode
before validating decoded limits, and report field errors explicitly.

### Embedded setup scripts use local routes

Eight selected pages/fragments were extracted from the pinned Large application:
Get Started, Wi-Fi, sign-in, create-account, completion, verification-wait,
sign-in success and portal. Their recovered browser behavior is:

| Page | Automatic requests and transitions |
| --- | --- |
| Get Started / completion / sign-in success | No embedded script in the selected assets; links are user navigation |
| Sign-in / create-account forms | On submit, encode `FormData` with `URLSearchParams`, POST to the corresponding local route, then replace the document with the returned text |
| Create-account verification-wait | First check after five seconds, then `GET /api/verification-status` every five seconds; truthy `verified` redirects to `/portal` |
| Portal | Immediate `GET /battery/status`, then every three seconds; update voltage, percentage and optional status text |
| Wi-Fi | `GET /scan.json` on load; any query string containing `delay` defers it five seconds; retry is user-triggered and also delayed five seconds; submission POSTs the encoded form to `/connect` |

The verification and battery intervals do not wait for an earlier fetch to finish
and set no explicit abort deadline/backoff. Network rejection logs an error but
does not stop the interval. The verification script reports cached local state,
not the firmware verification worker's progress. An open portal causes recurring
requests; these script checks did not establish their effect on device sleep.

Form scripts call `response.text()` and `document.write()` without testing
`response.ok`. The verification script similarly parses JSON without testing HTTP
status. A useful local account response therefore needs meaningful HTML feedback;
HTTP status alone will not select a special error UI. The create-account password
confirmation script disables its button for empty/mismatched confirmation, but
native browser constraints and server validation remain separate.

No direct Supabase fetch or external script/font download appears in these
selected assets. Vendor policy/contact links and the dynamically inserted
dashboard link are navigation, not automatic API traffic. Inline SVG namespace
URLs are not download requests. The completion handler builds its links around
the hardcoded `http://fraimic.local` base; changing the cloud API selector does
not rewrite every local UI link. This selected-page inventory does not cover the
external dashboard or prove completely offline provisioning.

Seven host checks executed the unmodified extracted JavaScript with stubbed DOM,
fetch and timer APIs. They confirm request timing/overlap, local destinations,
redirects, encoded submissions, error-body insertion and confirmation logic.
No browser visited the frame, no form was submitted to a device, and no real
credentials were used. Browser parsing, navigation and rendering remain untested.

## Diagnostics have side effects

**Bare `GET /action` defaults to `mode=reset`.** Handler `0x4201c740` initializes
the mode to `reset` before attempting to read the query. Missing/unreadable query
data can therefore enter the environment-specific factory-reset path. Never use
this route as a liveness probe or crawl it without an explicitly reviewed action.
`mode=restart`, `sleep`, `reset` and `ota` are actions, despite using GET.

Opening `/test` **without an action** enters factory-test mode at `0x4201ed28`,
starts a roughly ten-minute timeout and changes normal background behavior. It
is unsuitable as a passive liveness check. The page contains controls that can
reset pairing/settings; the POST handler is `0x4201ba9c`.

The GET handler uses a 64-byte query buffer and a 32-byte action buffer. If query
retrieval fails, including because the complete query does not fit, the action
stays empty and enters the same landing-page branch. The factory flag and timer
are set before HTML allocation, so an allocation error can follow entry into
that mode. This branch also invokes emergency LED-off helper `0x42023210`,
which bypasses ordinary workflow protection.

`GET /test?action=battery` follows a separate read branch and returns voltage,
percentage, charging and available gauge diagnostics. Other GET branches include
touch, microphone statistics and accelerometer diagnostics; some initialize
hardware or alter diagnostic counters. Do not crawl all actions to discover them.
The OTA test is `GET /action?mode=ota`, using the older manifest path and
registration checks; it is not a distinct updater in `POST /test`. Inspection of
that POST handler, including GNU decoding beyond Ghidra's truncated upload branch,
found microphone, touch, accelerometer and image-upload actions.

### Factory diagnostic contract

These are statically recovered operations, not endpoints exercised in this pass.
The `action` selector is in the query for both GET and POST. An unrecognized
action returns `400` with `{"error":"unknown_action"}`. The POST handler does
not require that the factory landing page was opened first.

| GET action | Response and side effects |
| --- | --- |
| `touch` | `{"count":<integer>}`; first call configures GPIO 2, then a sampled high-to-low edge increments the counter and triggers an LED indication |
| `mic_stats` | `{"amplitude":<integer>,"max":<integer>,"min":<integer>,"active":<boolean>}`; inactive reports zero values; every tenth active read writes a diagnostic log |
| `accel` | `{"x":<number>,"y":<number>,"z":<number>}` formatted to three decimals after scaling signed raw samples by 1/16,384, or `{"error":"accel_not_available"}` |

The microphone flag is factory-test state `0x3fca7590`, read by `0x42020474`.
It is distinct from the ordinary voice-recording getter `0x42020150` and the
voice-enabled preference. Statistics getter `0x42020488` reads three separate
volatile values without acquiring a snapshot mutex; a response is not an atomic
sample or a WAV/audio stream.

Worker `0x4201fca4` repeatedly reads into a 4,096-byte stack buffer and computes
minimum and maximum signed 16-bit samples. `amplitude` is their difference,
not RMS, decibels or a calibrated sound level. It replaces the three statistics
only when a nonempty sample block arrives, then reuses the buffer. This worker
does not create a WAV or invoke the cloud voice-upload path.

| POST action | Effect |
| --- | --- |
| `led` | Start a separate LED-test task; task-creation result is ignored before `{"status":"ok"}` |
| `mic_start` | Start factory microphone worker; already active returns `ok` / `Already running`; an initialization/start failure returns `status:error` / `Microphone init failed` |
| `mic_stop` | Clear factory microphone active flag, wait up to 20 times for 50 ms for its task handle, then emergency LED-off; the handler ignores the stop result |
| `touch_reset` | Zero count and set previous sampled level to high; return `{"status":"ok","count":0}` |
| `accel_start` | Initialize or resume accelerometer diagnostics; failure is reported in the JSON body |
| `accel_stop` | Stop accelerometer diagnostics and return `{"status":"ok"}` |
| `upload` | Receive a multipart panel image into the shared buffer and start the display path; not a firmware update |

The ordinary failure bodies above are sent without changing the default HTTP
status. Clients must inspect JSON, not treat every HTTP 200 as successful. The
factory microphone starter refuses when normal voice recording is active, but
that getter is not an ownership reservation. Its stop helper returns success
after its bounded wait even if the task handle has not cleared. Neither the
`ok` response nor `active:false` alone proves the worker has finished.

For normal voice control, these factory actions are not reusable start/finish
endpoints. The [voice hook map](voice-local-control-hooks.md) traces normal
admission and verifies why capture stop alone does not submit a recording.

Large's embedded page also contains commented-out “Display Test” markup and
JavaScript mentioning `display_test` and `display_status`. These are inactive
assets: the complete GET/POST handler comparison finds no corresponding action
branch on either pinned build. Do not treat the page's dormant code as another
local control. [Comparison evidence](local-handler-comparison.json).

`/dev` selects the vendor development environment, not a root shell or configurable
URL. See [the complete mode-switch sequence](storage-and-configuration.md#vendor-environment-switch).

### Factory and normal microphone capture can both be admitted

The factory starter checks the normal recording-state getter, but normal
recording start does not check factory activity. Both use the same I2S channel
handle and accept `ESP_ERR_INVALID_STATE` (`0x103`) from channel-enable as well
as success. The recovered SDK enable helper returns that error when the channel
is already running; it does not grant a second owner or reserve samples.

Eight complete function pairs match across **818 instructions per build**:
normal/factory workers, both starters, both stop helpers, normal-state getter and
SDK channel-enable. The actual Standard worker entries were resolved from their
task-pointer literals, not inferred by a constant address offset.

Eighteen instruction cases, nine per build, establish these bounded outcomes:

| Sequence / injected condition | Result |
| --- | --- |
| Factory start, then normal start | Both succeed; two task handles and active flags coexist on the same channel. |
| Normal start, then factory start | Factory start returns `0x103` when normal-state query succeeds. |
| Normal running, query mutex times out | The getter reports false and factory start proceeds; the normal task remains admitted. |
| Factory stop, old worker has not exited | Twenty five-tick waits, then success with the old handle still present. A second stop returns inactive without waiting. |
| Restart after that stop, before old exit | Starter accepts the cleared flag, creates another task and replaces the shared handle. The fixture does not schedule the older task. |
| Factory task creation fails | Active flag clears, but the already-enabled channel is not disabled by this failure branch. |
| Normal stop helper while both are admitted | Normal active/task state clears; factory active/task state remains. This is the helper boundary, not the outer voice cleanup sequence. |
| Factory worker receives partial bytes with timeout | It computes statistics from those bytes; normal capture instead discards timeout-returned bytes. |
| Factory worker receives immediate errors | It retries/logs without an application delay. Its eventual exit clears the task handle but does not disable the channel. |

The [SDK reader evidence](voice.md#capture-reads-can-lose-audio-without-invalidating-wav-structure)
shows that reads advance the channel's shared DMA position. Two admitted
workers are therefore not independent copies of microphone audio. Which worker
actually consumes samples depends on scheduling and SDK locking; no physical
audio loss, CPU load or battery effect was measured here.

The fixture executes application lifecycle/query/factory-worker and SDK-enable
instructions, with task, mutex, read/status, lower enable callback and timing
outcomes modeled. It covers 421 distinct instructions per build; the normal
capture worker is compared statically, not executed again. External callees are
mapped separately. [Cases and hashes](factory-mic-cases.json).

Do not reuse `mic_start`/`mic_stop` as normal voice controls or run diagnostics
alongside voice. A firmware implementation needs one microphone owner spanning
admission, capture, stop and confirmed worker exit. A cleared factory flag or
successful stop response is insufficient to establish that boundary.

### Developer page and authentication

Large GET handler `0x4201ebbc` renders the form for the current environment and
updates last activity. Query values `auth=fail` and `auth=locked` control error
messages; they are not authentication sessions. Viewing it does not invoke the
mode-switch routine, but repeated viewing can affect idle timing.

POST handler `0x4201b6a0` consumes a form body, with these recovered branches:

| Form | Behavior |
| --- | --- |
| `action=enter_dev&password=<owner-known-password>` | Decode password, compare against embedded seven-byte value, then select development and restart on a match |
| `action=exit_dev` | Select production and restart; no password/session check in this branch |
| Missing/unknown `action` | HTTP error, without invoking the mode switch |
| Incorrect/missing password for `enter_dev` | Redirect to `/dev?auth=fail` |
| Active rate limit | Redirect to `/dev?auth=locked` before processing either action |

The exact case-sensitive password was recovered and given privately to the
owner. The same literal and comparison structure were verified in Standard
0.2.28 at POST handler `0x4201b674`. This is **static confirmation**, not a
successful login or a live environment-switch test. Credential values are not
included in these repository docs.

The handler reads at most 255 body bytes once. Password input and decoded output
each have 64-byte capacity. Decoder `0x4201b628` handles percent escapes and
converts `+` to space; it does not reverse, hash or change letter case. The
comparison checks length and all bytes. Wrong comparisons increment a shared
failure counter; from the third failure, the initial lockout is 30 seconds,
doubling on subsequent failures with an ordinary-path cap of 300 seconds.
Successful password comparison clears the counter and deadline. This is not a
live lockout test or a claim about extreme counter/shift overflow behavior.

The exit branch has no current-mode guard either. It is therefore a mutating
operation even when invoked while already in production. Both branches call the
switch helper, send an HTML response, wait 50 ticks (about 0.5 seconds) and enter
restart helper `0x42017208`. They do not inspect the helper's result before
showing the response and restarting. Neither a response page nor the success log
proves every NVS/Wi-Fi operation succeeded. Do not use either POST as a probe.

Logs and `/info` are valuable for build, partition and hardware evidence but may
contain identifying information. Sanitize captures before sharing. The absence
of a local key in a masked JSON field does not mean that the complete credential
is safe to publish elsewhere.

The log handlers add another timing caveat: GET `/logs` and POST `/logs` call
the last-activity helper. Repeated log viewing can affect idle timing. GET formats
the current log buffer and, when present, previous logs from
`/imagedata/debug_log.bin`; authentication controls the formatter's detail level.
POST accepts a password form and responds with a redirect/session cookie.
The separate POST `/logs/action` recognizes `action=clear` and clears the buffer;
its recovered handler does not call the GET handler's session check. No clear
request was made. Preserve logs before diagnostic mutations and keep the endpoint
inside the intended LAN boundary.

The [diagnostic-storage trace](diagnostics-and-logs.md) now maps that fixed cookie
marker, the 64 KiB history's whole-store reset, truncation/contention losses and
the unchecked single-file flush. Neither an empty page nor a “Flushed” message
establishes a complete or durable execution record.

## Interpreting the JSON status snapshot

### Remaining status and HTML contracts

The two battery endpoints have different wire shapes:

| Route | Fields in this Large build |
| --- | --- |
| `/api/battery` | `percent`, `voltage_mv`, `charging`, `cable_connected`, `source` (`fuel_gauge` or `adc_estimation`) |
| `/battery/status` | `charging`, `voltage_v`, `percentage`, `status`, `fuel_gauge`, `data_source` (`Fuel Gauge` or `ADC Estimation`); the gauge branch adds `current_ma`, `temperature_c`, `cycle_count`, `soh` |

The first uses JSON builder `0x42030bf8`; the second formats into a 512-byte stack
buffer at `0x4202a154`, sets `Access-Control-Allow-Origin: *` and no-cache headers.
Voltage units and field names are not interchangeable. The gauge branch initializes
extra diagnostic values, calls their getters and does not check those getter
results before formatting, so a default value is not necessarily a successful
measurement. These handlers contain no request-field setter or direct
last-activity call. That does not prove their repeated use has no power cost.

`GET /connect` (`0x4201b3f8`) renders the current connection flag and cached
disconnect reason. Its wrong-password and network-failure text is a mapping from
that reason, not a new credential test. The GET does not apply Wi-Fi configuration.
`GET /upload` (`0x4201b3ac`) updates activity and returns embedded upload HTML;
viewing it does not submit an image.

`GET /portal` (`0x4201e81c`) updates activity, renders connection/setup, battery
and firmware summaries, and includes the already traced three-second battery
poll script. `GET /info` (`0x4201f0f8`) updates activity and assembles HTML sections
for device/account, battery, Wi-Fi, maintenance schedule, preferences and time.
Its preferences are display values, not hidden form setters in this handler.
Sequential getter reads do not form a locked snapshot. Cached identity access can
retain its previously documented first-use side effects. Displayed maintenance
history and gauge labels retain their limitations elsewhere in these notes.

### JSON snapshot semantics

Large `/api/info` handler `0x42030c98` assembles a snapshot rather than reporting
a workflow or image-job state. Its fields have these narrower meanings:

| Field | Recovered source / limitation |
| --- | --- |
| `firmware_version` | Cached firmware information from `0x4202b954`, or `unknown` if that structure is not initialized |
| `build` | Compiled build literal `f1555ee5` |
| `wifi.connected` | Station connection flag through `0x4201e050`; not the public reachability gate or a backend request result |
| `wifi.mac`, `wifi.bssid` | Masked strings containing only the final three bytes; not complete hardware identifiers |
| `device.time_synced` | Application time-valid flag through `0x4201581c` |
| `device.local_time` | Local calendar string when that flag is true, otherwise null |
| `device.uptime_s` | Boot-relative timer divided by 1,000,000 |
| `settings.voice_recording` | Voice-enabled preference through `0x4201589c`; not recording activity |
| `settings.keep_awake`, `auto_update`, `charging_led` | Stored preferences, not proof that every subsystem honors them |
| `display.last_refresh` | Most recent maintenance-history entry, not the last successful image render |
| `display.next_refresh` | Stored maintenance schedule, not the cloud's next-image deadline |

Local time and both display timestamps use `%Y-%m-%dT%H:%M:%S` without a UTC
offset. Do not append `Z` or interpret them as UTC; timezone and DST context
matter, and a repeated autumn hour is ambiguous. The refresh interval/hour
fields are null when no positive maintenance timestamp is available.

The handler conditionally omits child objects when their allocation fails and
ignores individual field-add failures. A serializable partial object can
therefore still be returned successfully. Root allocation and final serialization
have explicit errors, but clients should distinguish missing fields from false,
zero and null instead of assuming every successful response is complete. No
allocation failure was induced.

There is no recording task state, buffer owner, render-in-progress flag,
content hash or job ID in this handler. Polling it faster cannot supply those
missing events. Its getters run sequentially without a whole-snapshot lock, and
the shared HTTP task can delay the response during another operation.

### Standard-only render counters

Standard `/api/info` at `0x4202f384` adds `display.render_attempts` and
`display.render_failures`. The extra block at `0x4202f791` calls getter
`0x4202fcc4`, converts two unsigned 32-bit values to JSON numbers and inserts
them into the display child object. The complete ten-instruction getter only
copies RAM values to non-null output pointers. Reading this endpoint does not
increment or persist them. Large's complete handler omits both fields.

These are the [per-build aggregate display-health counters](storage-and-configuration.md#standard-also-stores-per-build-display-health-counters),
not a job ID or guaranteed durable completion record. Child/field allocation
failures can still omit them. The integration already consumes them as optional
fields; clients should preserve the distinction between absent and zero.
[Full handler/counter evidence](local-handler-comparison.json).
The [caller and driver follow-up](rendering-and-concurrency.md#standard-counters-cover-the-final-ready-pin-waits)
shows that these count final refresh returns, bypass early worker rejection and
conditioning, and cannot attribute success to a particular backend job.

Two read-only Standard `/api/info` requests on 22 October returned the same
`render_attempts: 3`, `render_failures: 0` and `last_refresh: null`, on the pinned
0.2.28 / 4654a1d8 build. The later read completed at 21:28:54 UTC. This confirms
the live field shape and unchanged values across those reads; no image, recording
or failure was induced. Large timed out, so its current response shape was not
rechecked in this pass.

## Restart, sleep and refresh acknowledgments

The separate portal reset action performs
[whole-NVS erase and conditional opposite-environment restore](storage-and-configuration.md#reset-erases-nvs-before-restoring-the-other-environment).
Its error page still queues the later reset/sleep handoff. It must not be treated
as equivalent to the non-erasing restart handler below.

These Large 0.2.29 handlers do not parse a request body or a job identifier. Their
small responses describe different points in the operation:

| Request | Recovered response | Ordering and limit |
| --- | --- | --- |
| POST `/api/restart` | `{"status":"restarting"}` | Allocate/send JSON, wait ten ticks (100 ms), then call restart; no recording/rendering guard in this handler |
| POST `/api/sleep` | `{"status":"sleeping"}` | First request sleep, then allocate/send JSON; actual sleep is handled later by the main loop |
| POST `/api/refresh` | `{"status":"refresh_started"}` | Check recording/LED protection, allocate/send JSON, wait ten ticks, then invoke manual refresh |

Restart and refresh do not check the JSON send result before acting. A lost
response therefore does not mean nothing happened. Initial JSON-object allocation failure produces
`500` / `out_of_memory` before either operation. Sleep differs: helper
`0x42017218` has already set pending flag `0x3fca6b18` before JSON allocation,
so the same error can follow a successfully queued sleep request. These are
static error-path findings; no allocation or connection failure was induced.

Sleep checks charging detection through `0x42029ed0`; a positive result returns
`409` / `charging_cable_connected` without setting the flag. When the main loop
reaches the pending request, it checks charging again. It either clears the flag
and declines sleep, or allows approximately two seconds for HTTP completion
before pre-sleep work at `0x42012338`. The button-wait loop also exits when the
flag is set. The response is not proof the frame has already slept, and these
waits are not a complete wall-clock bound while other work is running.

Refresh's `409` / `device_busy` guard is specifically the recording getter
`0x42020150` or LED workflow-protection getter `0x420231d0`. The first waits at
most ten ticks for its mutex, the second one tick. Both report false when their
mutex is unavailable; the recording getter also needs both the active flag and
recording-task handle. This is not a shared-buffer ownership lock or an atomic
reservation. See [LED state and protection](led-and-workflow-state.md).

The accepted refresh calls `0x4201724c` → `0x420115d8` → `0x4200fc7c`, the saved
image/maintenance refresh path. The result is logged after the HTTP response;
it is not returned as a later render acknowledgment. GNU decoding confirmed the
result preserved in the return register despite Ghidra initially inferring a
`void` function. A raw image upload already starts its own render and should not
be followed by this separate refresh.

### Standard refresh lacks the early busy guard

Standard 0.2.28's `/api/refresh` handler at `0x4202f1cc` contains **31 reachable
instructions**, versus Large's 54 at `0x42030aa0`. It has no calls to either the
recording-state getter or LED-protection getter and no `409 device_busy` branch.
After response-object allocation it sends `refresh_started`, delays ten ticks
and enters manual refresh. Its two immediate manual-refresh wrappers do not add
those checks. This establishes entry into the lower maintenance path; it does
not prove a simultaneous physical render or failure of every downstream guard.

The restart and sleep handlers, JSON success/error senders, pending-sleep helper
and two manual-refresh wrappers match across **seven complete function pairs /
187 instructions per build**, after relocation and internal branch normalization.
The three API handlers consume no job ID and do not parse a body. These scoped
comparisons do not establish equivalence of all 42 routes or the model-specific
maintenance/display implementation.

### A JSON serialization error can follow an accepted command

The shared JSON sender prints and deletes the response object before sending it.
If printing fails, it attempts a `500` response containing
`{"error":"json_serialization_failed"}` and returns failure. **Restart and
refresh ignore that return and still perform their operation.** Sleep has already
set its pending byte. This differs from failure to allocate the initial response
object, which prevents restart/refresh but still follows the pending-sleep write.

Fourteen instruction cases on each pinned build check those orders:

| Scripted condition | Large | Standard |
| --- | --- | --- |
| Refresh while recording getter would be true | `409 device_busy`, no manual-refresh entry | No recording getter call; response and manual-refresh entry |
| Refresh while LED-protection getter would be true | `409 device_busy`, no manual-refresh entry | No protection getter call; response and manual-refresh entry |
| Initial response-object allocation fails | Restart/refresh skipped; allowed sleep already pending | Same |
| JSON serialization fails | Error response attempted; restart/refresh still entered; allowed sleep remains pending | Same |
| Success-response send fails | Restart/refresh still entered | Same |
| Lower manual refresh returns an error | Earlier success response unchanged; handler returns zero | Same |
| Charging getter returns true | Sleep conflict, no pending flag | Same |

The cases execute the actual handler/sender/request/wrapper instructions, covering
233 distinct instructions on Large and 210 on Standard. cJSON, HTTP, hardware
state getters, RTOS delays, restart and the maintenance result are stubbed; no
device request, concurrent recording, reset, sleep or panel refresh occurs.
[Results and CFG hashes](local-control-cases.json) retain that boundary.

For HA, distinguish transport/response failure from command outcome. A `500`
alone does not make retrying restart, refresh or sleep safe. Standard's successful
refresh acknowledgment also does not establish that recording was idle. A future
firmware command path needs shared admission and job-aware outcomes, rather than
depending on these per-route responses.

## Wi-Fi form submission

POST `/connect` (`0x4201d07c`) reads at most 511 bytes **once**, then looks for
`ssid=` and `password=` and URL-decodes them. It does not loop until the declared
body is complete. The SSID is first bounded to 32 decoded bytes, then copied
with a 31-byte bound into a zeroed driver configuration. A 32-byte SSID therefore
loses its final byte in this recovered path. Password copying is bounded to
63 bytes. These are byte limits, not Unicode character counts; boundary cases
were not submitted to a device.

The handler sends its HTML response before applying the driver configuration.
Driver failure is logged rather than sent back as a revised error page. On
success it calls `0x4201850c` to clear `force_ftu`, without checking that helper's
result. It does not itself call restart after this save. A successful-looking
page alone does not establish correct credentials, persistent first-time-setup
state or a successful association. No Wi-Fi configuration was changed in this
static pass.

### Wi-Fi field matching and byte limits

Unlike account forms, `/connect` uses case-sensitive `strstr` for the literal
fragments `ssid=` and `password=`. It finds both pointers before inserting NUL
at each value's next ampersand. It does not require a field-name boundary,
reject duplicates, validate the request Content-Type or reject missing fields
before attempting the driver configuration.

Selected outcomes from a reconstructed host fixture:

| Submitted form fragment | Result before the driver call |
| --- | --- |
| `notssid=Wrong&ssid=Lab` | SSID becomes `Wrong` |
| `SSID=Lab` | SSID remains empty |
| `ssid=First&ssid=Second` | First value wins |
| `ssid=A%26B%2BC` | SSID becomes `A&B+C` |
| `ssid=One%00Two` | Subsequent string copies retain only `One` |
| 32 ASCII SSID bytes | Final driver field contains 31 |
| Sixteen UTF-8 `é` characters | 32 decoded bytes become 31, ending in an incomplete UTF-8 sequence |
| 64 password bytes | Final driver field contains 63 |

Decoder `0x4201b628` bounds decoded output, converts plus to space, and accepts
a two-character percent conversion only when `strtol` consumes both characters.
Malformed escapes are copied literally. It does not validate UTF-8 or prevent
embedded NUL. These findings describe parsed bytes and do not establish that the
driver accepts or associates with an invalid/empty configuration.

The zeroed station configuration is then given authentication threshold value
3 at offset `0x78`, corresponding to `WIFI_AUTH_WPA2_PSK` in the
[matching SDK types](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_wifi/include/esp_wifi_types_generic.h).
Thus the scan list is not evidence that every listed network is accepted by this
setup path. Actual driver/AP compatibility and complete connection failures were
not exercised.

There is also a pre-parse side effect: if background retry is active, the handler
calls `0x4201a650` **before** its first body read. That helper clears the run flag,
signals the saved task when present and clears its attempt counter, without
joining the task. A later body-read error therefore does not mean no state was
changed. This is distinct from the connectivity monitor's own state machine.

The confirmation-page SSID passes through HTML escaper `0x42019924`, which
escapes ampersand, angle brackets and both quote types into a 128-byte buffer.
Expansion can truncate the displayed name; that is separate from the 31-byte
driver copy. This escaper is not the unescaped email insertion in account pages.

## Wi-Fi diagnostic and AP-control routes

These handlers were inspected statically; no scans, AP changes or counter clears
were submitted during this follow-up.

| Route | Recovered behavior |
| --- | --- |
| GET `/check-internet` | Update last activity; make a separate TCP connection to `8.8.8.8:53`; return `{"reachable":true}` for connection success or `ECONNREFUSED` (111), otherwise false |
| GET `/scan.json` | Start a fresh blocking active scan, then format nonempty SSIDs as JSON; failure stops the scan, waits ten ticks and retries once |
| GET `/wifi-stats` | Update last activity and render HTML from current association and diagnostic history |
| POST `/clear-stats` | Clear RAM statistics, attempt to erase their NVS record, then redirect with 303 to `/wifi-stats` |
| POST `/switch-ap` | Parse BSSID/channel, apply them to the current Wi-Fi configuration, send HTML, save Wi-Fi statistics and restart |

The connectivity diagnostic (`0x4201c404`) sets a three-second socket timeout
option before its blocking connection. Its handler does not call the monitor's
success/failure transitions or write the cached reachability flag. It therefore
does not establish that voice's separate connectivity gate is open. The
[background monitor](boot-and-scheduling.md#public-reachability-gate) uses a
different nonblocking/select implementation; these paths must remain distinct.

The scan configuration requests active dwell of 80–100 ms per channel and
includes hidden networks, but the response loop omits records whose SSID is
empty. The blocking-call semantics and structure layout match the
[IDF scan API](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_wifi/include/esp_wifi.h)
and [types](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_wifi/include/esp_wifi_types_generic.h).
This is radio work, not a cached list or a cheap liveness probe. The JSON array
contains `ssid` (string), `rssi` (signed number), `band` (string), `channel`
(number) and `bssid` (colon-separated string); there is no authentication-mode
field in this formatter. The band label is selected solely by channel below 15
versus 15 or above; the `5GHz` string is not evidence of fitted 5 GHz hardware.

### AP selection can change before an error response

`POST /switch-ap` (`0x4201c4cc`) receives at most **63 bytes once**, decodes the
whole prefix into a 64-byte buffer, then searches for `bssid=` and `channel=`.
It requires six parsed hexadecimal BSSID bytes and rejects all-zero bytes.
The optional channel uses integer conversion, then an eight-bit value; the
handler supplies zero when absent and performs no separate range check.
These are parsing rules, not proof that the Wi-Fi driver accepts every value.

After reading the current configuration, it disconnects and applies the new
BSSID/channel **before** allocating the 1,589-byte confirmation page. Failure
of that allocation therefore follows a possible configuration change. That
branch sends a server error without reaching the later stats-save/restart path.
Successful page construction sends HTML without checking delivery, waits 50 ticks,
saves statistics and restarts. There is no rollback in the handler on either
configuration or response failure. An error response must not be interpreted as
proof the radio/settings remained unchanged. No AP-switch request was sent.

### Scan-result escaping is incomplete

The SSID formatter `0x420e2a04` escapes quote, backslash, backspace, tab, newline,
form feed and carriage return. Other nonzero control bytes are copied unchanged.
A synthetic SSID containing byte `0x01` therefore produces invalid JSON, while
quote/backslash and the listed whitespace cases round-trip through a JSON parser.
It also copies non-ASCII bytes without UTF-8 validation. Embedded NUL ends the
string, and a record starting with NUL is omitted by the response loop.

The handler gives this helper 66 bytes; 32 quote characters expand to 64 bytes
and fit. It allocates 92 bytes per AP record and a separate JSON buffer of
`150 * count + 100` bytes. Return values from retrieving the AP count and records
are ignored, so an empty result does not independently prove that the scan found
no networks. These are static/error-boundary findings, not a live unusual-SSID
or driver-failure experiment. Future setup UI should distinguish scan failure,
invalid response and a valid empty list.

AP switching (`0x4201c4cc`) reads at most 63 form bytes once, URL-decodes the whole
body, requires six parsed BSSID bytes and rejects an all-zero BSSID. Missing
`channel` selects zero; supplied input is converted to an integer and stored in
a byte without a handler-level channel-range check. The existing SSID/password
are retained. Driver validation may still reject a configuration. After a
successful driver save, HTML allocation can fail: the configuration has changed,
but that branch sends an error and skips the intended restart. No fault was
injected; callers must not infer unchanged configuration from that error alone.

Stats clearing (`0x4202ed00`) zeros the 906-byte RAM record, restores schema byte
2 and clears two bookkeeping flags before opening NVS. Erase/commit results are
ignored and the helper returns no failure status. Its redirect therefore does
not prove that persistent history was erased. Preserve diagnostic evidence
before deliberate clearing and avoid these activity-updating pages during an
idle-sleep measurement.

## Image delivery

The preferred verified raw upload on this build is:

```http
POST /api/image
Content-Type: application/octet-stream
Content-Length: 2304000

<exact packed Large-panel bytes>
```

`0x420307f8` receives the body into the shared PSRAM image buffer and calls
`0x4201727c`. The wrapper attempts to save `last_image.bin`, logs any save failure,
and starts rendering. The handler can respond:

```json
{ "status": "rendering", "bytes_received": 2304000 }
```

This confirms the request reached the render-start path, **not** durable storage
or completed physical display. The upper body limit is 2,304,000 bytes. The
downstream size comparison has a ±1,024-byte tolerance, but the earlier cap
rejects the upper half; clients should always produce the exact expected size.
Do not add an extra refresh after a successful image upload.

### Raw image acceptance and failure boundaries on both models

The complete raw-upload handlers and save/start wrappers match across both builds:
245 plus 80 reachable instructions each, with model-specific size literals.
Standard's entries are `0x4202ef24` and `0x42017250`; Large's are
`0x420307f8` and `0x4201727c`. This comparison covers their operations and internal
branches, not recursive equivalence of all external callees.

The Content-Type value must be 1–63 bytes and contain the **case-sensitive
substring** `application/octet-stream`. This is not an exact media-type parser:
parameters and even a prefixed/suffixed token pass; `Application/Octet-Stream`
and a 64-byte value fail with `501 unsupported_content_type`. The ROM call is
`strstr`, confirmed by the [ESP32-S3 SDK bindings](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_rom/esp32s3/ld/esp32s3.rom.newlib.ld).
Use the plain canonical value. The handler updates last activity before these
checks; a rejected request is not necessarily neutral to the idle timer.

| Boundary | Standard | Large |
| --- | --- | --- |
| Required complete panel payload | 960,000 bytes | 2,304,000 bytes |
| Handler upper cap | 960,000 bytes | 2,304,000 bytes |
| Lengths admitted by handler plus immediate wrapper | 958,976–960,000 | 2,302,976–2,304,000 |
| Largest individual receive request | 4,096 bytes | 4,096 bytes |
| Consecutive timeout results before rejection | 5 | 5 |

The admitted lower range is tolerance, not a usable alternative format. In the
instruction cases, a payload 1,024 bytes short reaches render-start with the tail
unchanged. One byte shorter is rejected only **after** its bytes were received
into the image allocation. Neither handler has the Large refresh endpoint's
early recording/protection check. Standard's separate audio allocation remains
a model difference; this pass does not infer physical concurrency failures.

The receive loop resets its timeout count after every positive read. Five
consecutive `-3` results produce `408 upload_timeout`; zero or another negative
result produces `400 receive_failed`. Four timeouts, progress, then four more
timeouts can still complete. There is no whole-upload deadline in this handler.
On receive failure, already received bytes remain in the image buffer; the
save/start wrapper has not run. No restore or clearing step appears on that exit.

After reception, the wrapper checks size, attempts cache save, clears the system-
image marker and calls render-start with WAIT policy. Cache-save failure is logged
but does not prevent render-start. A render-start failure therefore follows a
cache-save attempt and marker-clear call. Only after successful render-start does
the handler allocate/serialize/send its success response: `500 out_of_memory`,
`500 json_serialization_failed`, or a failed response send can all occur after
render-start has succeeded. None proves that the panel remained unchanged.

Twenty-one cases per build check these boundaries, including buffer readiness,
capacity, length limits, partial reception, timeout reset and response failures.
They execute **373 distinct instructions per build** with HTTP/cJSON, ROM helpers,
buffer accessors, activity/LED, save/marker and render outcomes modeled. The
unsigned-to-double result used for `bytes_received` follows the
[SDK ROM binding](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_rom/esp32s3/ld/esp32s3.rom.libgcc.ld).
[Results and hashes](image-api-cases.json) are host evidence, not physical render,
socket timing, real allocation failure or durable-cache validation. For HA, send
the exact model payload, serialize producers and treat a failed request after
transfer as an uncertain outcome rather than automatically retrying or refreshing.

### Older multipart transport

The older `/upload` endpoint accepts multipart field `image`, filename `image.bin`.
That is different from the cloud voice multipart field `file`, filename
`recording.wav`. Existing [`api.py`](../../custom_components/fraimic/api.py)
already handles version selection and recovery from interrupted local uploads;
reuse it rather than replacing the integration's transport blindly.

The [complete legacy multipart follow-up](multipart-uploads.md) adds important
limits: receive chunk boundaries and NUL image bytes affect footer recognition;
interrupted bodies can still reach render-start; and a render-start error can be
reported in an HTTP 200 HTML page. Thirty instruction cases cover both builds.
Those findings support the existing raw-endpoint preference on the pinned
versions, but do not establish the cause of the historical persistent upload
failure or justify automatically retrying an uncertain post-transfer failure.

The [shared buffer](hardware-and-layout.md#one-psram-buffer-serves-audio-and-images)
and [cache behavior](storage-and-configuration.md#last-artwork) matter when adding
concurrent voice or cloud delivery.

The render WAIT policy runs **after** reception and cache replacement; it does
not prevent an upload from overwriting another user's buffer. Also,
`display.last_refresh` is maintenance history rather than a per-image completion
acknowledgment. See the [rendering trace](rendering-and-concurrency.md).

## Album proxy contract

Static registrations and handlers in this image include create and delete,
in addition to the previously tested GET/PUT pair. For example, `0x42030790`
reads the create body and calls proxy `0x42030064` with `/api/v1/albums` and POST.
Create/delete were not live-tested in the checklist passes. Earlier wake
troubleshooting did update an existing empty wake-test album to inactive; that
single operation does not validate the complete mutation contract.

The common proxy `0x42030064` checks Wi-Fi station connectivity, uses a ten-second
HTTP timeout and sends `User-Agent: ESP32-Fraimic/1.0` plus
`Accept: application/json`. It adds JSON Content-Type for a body. No Bearer header
is forwarded or synthesized in the recovered code; authorization uses the device
key in the request path/body. GNU disassembly covered the branch Ghidra truncated.

| Local request | Upstream request |
| --- | --- |
| GET `/api/albums` | GET `/api/v1/albums/<device_key>` |
| POST `/api/albums` | POST `/api/v1/albums`, JSON with device key |
| PUT `/api/albums/<album_id>` | PUT `/api/v1/albums/<album_id>`, JSON with device key |
| DELETE `/api/albums/<album_id>` | DELETE `/api/v1/albums/<album_id>/<device_key>` |

Body helper `0x4203051c` accepts 1–4,096 incoming bytes, parses JSON, and adds or
replaces `device_key` with the frame's own value. Five consecutive receive
timeouts abort the read; progress resets that count. It does not validate album
names, schedules or assignments itself. The proxy passes upstream status/body
through in chunks rather than parsing an album schema, with the empty-body and
failure qualifications below.

### Body transformation is not schema validation

The body helper uses ordinary `cJSON_Parse`, not a strict object-only parser.
It checks for `device_key` case-insensitively, replaces the first matching member
or adds one, then serializes with `cJSON_PrintUnformatted`. It does not check the
return value from the add/replace operation. Nineteen host cases against the
[pinned cJSON source](https://github.com/DaveGamble/cJSON/blob/acc76239bee01d8e9c858ae2cab296704e52d916/cJSON.c)
and this recovered call sequence passed:

| Input shape | Host result using a fake device key |
| --- | --- |
| Ordinary object, with missing/string/null/case-varied key | One normal key is added or replaced; other fields are retained |
| Two matching key members | Only the first is replaced; the second survives serialization |
| Array | The key value is appended as an array element; the result remains an array |
| Scalar or null | Serialized value remains scalar/null, without a usable object key |
| Valid JSON followed by text, another value or an embedded NUL | The first parsed value is used; the trailing input is not rejected |
| Malformed or empty JSON | Parsing fails |
| 4,096-byte object at the incoming limit | Injected output can exceed 4,096 bytes; there is no second output-length cap here |

These cases model the library calls, not a device mutation or vendor authorization
bypass. In particular, duplicate-field interpretation depends on the receiving
backend. A local emulator should require an object, reject duplicate identity
fields and bind validated credentials to server-owned device/account state.
Do not use successful passage through this proxy as evidence of validation.

All body-helper failures, including oversize, receive timeout and allocation
failure, become the same local HTTP 400 `invalid_json_body`. The fifth consecutive
receive timeout aborts the read; progress resets the counter. With the
server's 60-second receive wait, this is not a five-second end-to-end bound.

### Album IDs and query strings

Extractor `0x4202ff14` copies at most 255 URI bytes, discards the query at `?`,
removes one trailing slash and requires prefix `/api/albums/`. It then copies
at most **127 bytes** of the remaining suffix to the handler's ID buffer. It
does not URL-decode, enforce a UUID, reject an embedded slash or report suffix
truncation. Distinct long IDs can therefore produce the same forwarded suffix;
use short opaque IDs and validate their complete shape in the backend.

GET listing constructs its upstream path from the device key and ignores local
query parameters. PUT/DELETE similarly discard local query parameters when
extracting their ID. Local `?page=...`, filters or cache-busting parameters do not
become upstream album options through these handlers.

### Response and failure translation

The common proxy is synchronous on the shared HTTP-server task. It manually opens
the upstream request, writes a body if present, fetches headers and streams reads
in 4,096-byte chunks. It has no redirect/retry loop, whole-operation deadline or
firmware-level response-body size cap. Keep responses small and fast so album
work does not hold up unrelated local API requests.

| Upstream condition | Local handling |
| --- | --- |
| No station connection, client initialization/open/header failure | HTTP 502 JSON error |
| Body write returns negative | HTTP 502 JSON error; the caller does not compare nonnegative write count with requested length |
| Headers available | Copy the numeric status, label the response `application/json`, add `Access-Control-Allow-Origin: *` |
| Normal EOF with zero forwarded bytes | Attempt to supply `{"status":"ok"}` under the upstream status |
| Read failure after headers, including EAGAIN | Log, close upstream and attempt the final local chunk without replacing the upstream status |
| Local chunk-send failure | Log, close upstream and still attempt the terminating chunk |

It does not copy upstream Location, Retry-After, Content-Type or Content-Encoding
headers. Thus a 3xx response does not carry a usable redirect, and an HTML error
body can be labelled JSON. A read error after some data can yield an apparently
finished chunked response containing only a prefix of the upstream body. The
proxy does not compare the final byte count with Content-Length or call a
response-completeness predicate. No such network fault was induced on a frame.

Use complete JSON responses for emulator album operations, including deletion,
and validate bodies in HA. After a lost mutation response, reconcile the resulting
state or use backend idempotency; this proxy provides no transaction identifier.

The proxy's log format masks a separate key suffix but also prints the complete
upstream path. Listing and deletion paths already contain the full device key.
Treat raw frame/proxy logs as credential-bearing; that masked suffix is not full
redaction. No private key values are included in these notes.

Owner-scoped upstream reads confirmed both account-token and device-key listing
paths, including assignment and schedule fields. That does not validate mutations
or every backend permission. No album was created, edited or deleted in the
account-read/checklist validation pass. This is not an on-device album store.

The later [local-backend experiment](backend-emulation.md) exercised the physical
frame's GET proxy against an owner-hosted HTTPS server: it returned HTTP 200 and
the identical captured album object through `/api/albums`. The server had no
vendor forwarding. This validates the read path; it adds no mutation evidence.

## Changes worth exposing in a firmware fork

These are proposals, not additional stock routes:

- Owner-configurable backend URL, trust and local time source, with readable status.
- Recording/rendering/buffer-owner state for scheduler arbitration.
- Content/job identity and separate accepted, cached, rendering and rendered events.
- Read-only partition/security/capability information with credentials excluded.
- A documented recovery/configuration path independent of the selected cloud host.
