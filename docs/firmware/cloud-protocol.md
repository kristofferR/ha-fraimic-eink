# Cloud protocol and local emulator contract

[Research index](README.md)

The first emulator target is an **already-paired frame**. This page describes the
client contract recovered from the app; examples use reserved domains and
placeholders, not credentials or deployable services.

The [bounded backend experiment](backend-emulation.md) now validates local idle
polls, album reads, physical microphone upload, one owner-confirmed panel image,
and the combined voice-finalize/download/driver flow with that fixed image.
It also found an upload-response
length bug; follow the [empty acknowledgment requirement](voice.md#upload-acknowledgment-must-have-an-empty-body).

## Backend selection

`0x42017a4c` chooses between `https://origin.fraimic.com` and
`https://dev-api.fraimic.com`. NVS `app_data/server_mode == 1` selects development.
There is no arbitrary URL setting in this selector.

The production string is 26 bytes long at file offset `0x11590`, virtual address
`0x3c101590`. An equal-or-shorter replacement is a possible in-place patch, with
image integrity fields regenerated. This has not been prepared or boot-tested.
Longer, configurable URLs require additional code/storage, not an oversized string
overwrite. See [OTA and recovery](ota-and-recovery.md).

| Caller | Uses the central API base for |
| --- | --- |
| `0x42023bcc` | Global/system-image metadata |
| `0x42023ed4` | Account/device setup |
| `0x4202475c` | Image, settings and firmware polling |
| `0x420266d8` | Voice presign |
| `0x42027380` | Voice finalization |
| `0x42030064` | Album API proxy |

The web-app (`0x42017a64`) and Supabase authentication (`0x42017a7c`) selectors
are separate. Image, audio-upload and firmware URLs come from server responses.
A replacement API host therefore does not automatically replace every host.

The recovered web-selector consumers are the successful sign-in page
(`0x420192c8`) and portal HTML (`0x4201e81c`). They insert a dashboard link:
production `https://app.fraimic.com`, development
`https://d2fz2sijx5cx76.cloudfront.net`. The auth selector feeds the email-verification
task at `0x42023674`: production `https://sclpedxwezoiwzesfdps.supabase.co`,
development `https://mhabnmforgicbwlyudxa.supabase.co`. The development API URL
also appears as a label in `/dev` HTML; that occurrence is not another client.

For already-paired operation, the main dependencies are API requests, the asset
and upload URLs returned by that API, the public TCP probe and SNTP. Independent
enrollment additionally needs an intentional account flow and dashboard links.
The [stock sign-in branch](#enrollment-boundary) is a candidate that avoids the
separate email-verification task; independent provisioning remains untested.
These are recovered consumers, not a packet capture proving
every boot-state dependency has been removed.

The [selected embedded-page audit](local-api.md#embedded-setup-scripts-use-local-routes)
adds browser-side dependencies: local form POSTs, five-second cached-verification
polls, three-second portal battery polls and Wi-Fi scanning. These assets contain
no direct browser Supabase fetch; create-account's separate authentication worker
still runs on the frame. Dashboard and policy links are user navigation. This
distinction matters when replacing enrollment without forwarding owner passwords.

### Outbound-client and URL inventory

The follow-up [machine-readable inventory](outbound-dependencies.json) records
**eleven HTTP-client constructor call sites**: the ten current configurations
listed below plus older updater `0x4202bb88`. A raw Xtensa call-encoding scan,
reference tracing and bounded GNU checks agree on those sites. This catches
multipart construction at `0x42026fdd`, omitted from Ghidra's constructor-reference
list because its enclosing function was incompletely analyzed.

The same audit finds ten direct API-selector calls. Eight construct requests in
the six consumers already listed above; the other two only log the selected base
during background startup (`0x420169af`) or a poll connection error
(`0x42024ccf`). The two web-selector calls produce dashboard links, and the one
authentication-selector call belongs to email verification. No serialized exact
pointers to those three selectors or the client constructor were found in the
application segments. This strengthens the recovered consumer inventory without
proving that every possible computed/indirect call has been excluded.

A separate scan finds 43 printable HTTP(S) URL occurrences across eleven distinct
hosts. Their roles matter more than the raw count:

| Literal category | Role in this build |
| --- | --- |
| Production/development API and authentication origins | Frame-side requests through the selectors above |
| Production/development dashboard origins | Browser navigation links |
| `fraimic.com` links | Three navigation links, including account/policy pages; not additional frame-side clients |
| `fraimic.local` / `192.168.4.1` | Local portal addresses, links and instructions |
| 29 `www.w3.org` occurrences | SVG namespace declarations; no remote fetch follows from the namespace URI |
| `http://192.168.1.145` at `0x3c1242f0` | Legacy literal beside a manifest-path string; no recovered reference or exact pointer to either literal |

The nearby legacy path is `%s/shared_files/firmware/firmware_manifest.json` at
`0x3c124308`. Its presence does **not establish an active manifest server**. The
recovered older updater receives a URL from the saved manifest, and the current
poll queue supplies its own URL to the direct updater. Neither observed data flow
uses that LAN literal. No request to that address was made.

Returned image/upload/firmware URLs are dynamic and therefore cannot be enumerated
from literal hostnames. The URL scan also excludes non-HTTP services: the four
bare time-server names, DNS fallback and public TCP probe remain separate
dependencies. For already-paired backend work, cover the central API and returned
storage URLs, preserve deliberate OTA withholding, and validate local DNS/time
and connectivity independently. This inventory is static evidence, not an
air-gap test or an independent enrollment.

The later [Standard inventory](standard-outbound-dependencies.json) confirms the
same eleven constructor roles, ten API-selector calls, two dashboard-selector
calls and one authentication-selector call in 0.2.28. All six selected origins
and all eleven literal HTTP(S) hosts match Large. Standard's logging-only API
calls are `0x42016987` and `0x42023723`; its multipart constructor call is
`0x42025a2d`. Its unused legacy LAN/manifest literals are at `0x3c123e84` and
`0x3c123e9c`, again with no exact pointer occurrences in the vendor application.

The Standard raw scan produced 25 candidate byte matches but only 24 actual
calls. The extra candidate at `0x4200ba4e` starts inside a jump instruction and
crosses into the next instruction. Ghidra also omits the genuine multipart call
after unsupported `SALTU` instructions. Thirty bounded GNU ranges, covering 874
unique instructions with bytes checked against the pinned image, resolve both
cases. Matching consumer roles support a shared stock-protocol adapter; they do
not prove every consumer body, TLS configuration or indirect path equivalent.

## Poll

The [saved-schema comparison](schema-and-client-contract.md) distinguishes
advertised fields from these client behaviors. The October schema omits
`display_type` and `is_periodic_poll` from its poll parameters, although all
18 captured Standard polls sent both and received HTTP 200.

```http
GET /api/v1/upload/check/<device_key>?display_type=315&orientation=portrait&is_periodic_poll=false&current_version=0.2.29
```

The client additionally sends battery percentage, Wi-Fi SSID and, when available,
LAN IP. Some requests include `include_account=true` and OTA result fields.
All three URL formats in `0x4202475c` hardcode `is_periodic_poll=false`; it cannot
identify scheduled wakes versus user activity on this build.

Orientation is sampled while constructing the poll. Its
[two-way accelerometer classifier](hardware-and-layout.md#accelerometer-target-and-orientation-semantics)
ignores direction/Z and falls back to portrait on failure, without a validity
field. Do not treat the string as a four-way mounting angle or proof of a healthy
sensor. Voice samples separately immediately before finalize.

The key in the URL path is a credential. Redact it in application, reverse-proxy
and observability logs. Do not confuse an account-facing device ID or masked info
value with the full provisioned key.

### Poll request encoding and URL limits

The poll reads at most 32 SSID bytes from the station snapshot into a zeroed
33-byte array. Encoder `0x42023300` keeps ASCII letters, digits and `-_.~`, and
encodes every other byte as uppercase `%HH`. Spaces become `%20`; a literal plus
becomes `%2B`. UTF-8 is encoded byte by byte, with no Unicode validation. An
embedded NUL ends the input. The 97-byte destination fits the full worst case of
32 escaped bytes plus NUL. An unavailable station snapshot produces an empty
`wifi_ssid` value rather than omitting that field.

The final request has a **512-byte URL buffer**, including NUL. All three ordinary,
OTA-success and OTA-failure formats reject a required length above 511 with
`0x104`, before constructing the HTTP client. They do not send the truncated
prefix. This bound includes the API origin, credential path and all query fields;
a future longer configurable origin must account for the whole URL.

The SSID encoder is not applied to every field. The device key and version
strings are interpolated directly. OTA failure text comes from fixed firmware
messages, is copied to a 128-byte array, and only has spaces replaced with `+`.
For example, its fixed server-error message retains literal parentheses and a
slash. These current messages contain no `&` or `#`; this does not establish a
safe encoder for future arbitrary error text. LAN IP is formatted from the
station's four address bytes, and `include_account=true` is a fixed suffix.

Twenty-seven host cases cover selected encoding, URL and report-state rules.
They confirm that SSID `&`, `#`, `+` and `=` remain encoded inside the value,
and that 511/512-byte URL boundaries differ. The long-origin cases are synthetic
boundary tests, not observed stock-host failures. Backend parsing should decode
query values once and treat SSID/IP/version as telemetry; the
[OTA report](ota-and-recovery.md#result-reporting) is consumed before any HTTP
acknowledgment and carries no durable job or artifact identity.

### Successful response fields

| Field | Client behavior |
| --- | --- |
| `has_new_upload` | Boolean pending-image flag; compatibility fallback `has_new_tasks` |
| `presigned_url` | Image URL copied when pending content is true |
| `user_settings` | Any present JSON value is serialized into an output buffer; not proof of local application of every setting |
| `device_settings` | Applies a complete four-switch snapshot when an object |
| `firmware` | Nonempty `version` and `presigned_url` queue an update, subject to the recovered guards |
| `next_image_utc` | Future numeric UTC epoch; compatibility fallback `next_scheduled_image_time` |
| `account.email_verified` | Can reconcile an existing registration's verification state |

Illustrative idle response for a device with no active album schedule:

```json
{
  "has_new_upload": false,
  "presigned_url": null,
  "next_image_utc": null,
  "firmware": null
}
```

When content is ready, return `has_new_upload: true` and its packed panel asset
URL. When scheduling is active, return the intended future deadline on **every**
HTTP 200 response with parsed JSON, including polls without new content. If neither
time field supplies an acceptable future value, the parser clears the saved
deadline. Error paths that return internal success are different; see below and
[scheduling](boot-and-scheduling.md).

### Field selection and permissive JSON parsing

These details are static Large 0.2.29 findings, supported by a 25-case host
fixture using IDF 5.4.1's pinned cJSON 1.7.18 plus the recovered selection rules.
The fixture does not execute firmware, persistence or recording actions.

| Input | Recovered behavior |
| --- | --- |
| Boolean `has_new_upload` | Takes precedence even when false; `has_new_tasks:true` does not override it |
| Missing/non-boolean `has_new_upload` | Try a boolean `has_new_tasks`; numbers and strings are not truthy booleans |
| True pending flag with missing/non-string/empty URL | Pending remains true, while the output URL can remain empty |
| Overlong image URL | Copy at most 1,535 bytes into the worker's 1,536-byte buffer and terminate; no rejection for truncation here |
| Numeric `next_image_utc` | Takes precedence even if past, zero or otherwise not future; do not then try the legacy field |
| Missing/non-numeric `next_image_utc` | Try numeric `next_scheduled_image_time`; a numeric string is still not a number |
| Ordinary fractional timestamp | Convert double to signed 64-bit integer, then compare with current time; fractional seconds are discarded |
| Object `account` with literal `email_verified:true` | Promote an existing registered but unverified identity; false/missing/non-boolean does not revoke verification |

The integer conversion target is ROM `__fixdfdi` at `0x400022c8`, identified by
the [ESP32-S3 ROM map](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_rom/esp32s3/ld/esp32s3.rom.libgcc.ld).
Nonfinite or out-of-range numbers have not been characterized; the emulator
should emit bounded whole-second epochs. A positive future value can be stored
yet fail the separate scheduler's greater-than-30-second lead-time rule.

The parser calls `cJSON_ParseWithLength` (`0x4203962c`) without requiring complete
input consumption and does not require the root to be an object. A valid JSON
prefix followed by extra text can therefore parse. Roots such as `[]` or `null`
also parse, supply none of the expected fields and reach the schedule-clear path.
An empty or genuinely truncated JSON value fails parsing before those updates.

Object lookup at `0x4203966c` / `0x42039100` is case-insensitive and returns the
first matching child. Thus duplicate or differently cased keys can be interpreted
differently from a backend validator that keeps the last key. The helper branches
match the [pinned cJSON source](https://github.com/DaveGamble/cJSON/blob/acc76239bee01d8e9c858ae2cab296704e52d916/cJSON.c).
Emit one canonical object with unique correctly cased keys; permissive client
acceptance is not a useful extension mechanism.

The background worker `0x42025aec` acts on the pending flag after a successful
return, including stopping an active recording. It does not first require a
nonempty valid download URL. A malformed pending response can therefore request
recording interruption without supplying a usable image. This is a static
consequence, not an induced recording failure. Publish pending content only after
its exact model-specific asset and URL are ready.

### HTTP errors are not equivalent to an idle JSON response

The poll routine initializes its returned pending flag and strings to empty.
Before parsing HTTP 200 JSON, it handles failures in this order:

| Condition | Internal result and state effect |
| --- | --- |
| Transport result `0x7002` (`ESP_ERR_HTTP_CONNECT`) | Return success/empty result, regardless of the later status branches |
| HTTP 404 | Return success/empty result; optional `detail` changes diagnostic logging only |
| HTTP 401 or 403 | Return `0x7002` as an error |
| HTTP status 500 or above | Return success/empty result |
| Other unsuccessful status/transport | Preserve a nonzero transport error, or return generic failure if transport succeeded |
| HTTP 200 and transport success, but JSON parsing fails | Return `0x108` / invalid response |

The SDK identifies `0x7002` as a connection-open error, not an HTTP status or
proof that an endpoint is unimplemented; see its
[error constants](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/include/esp_http_client.h).
The firmware log suggesting an unimplemented development service is an
interpretation, not a reliable diagnosis. A 404 mentioning an unrecognized device
does not clear pairing in this routine.

All pre-parser branches above skip settings application and the next-image
setter, preserving that existing state. This differs from a parsed HTTP 200
`{}` or `null`, which reaches the deadline-clear path. An internal success
result is therefore insufficient evidence of a healthy backend or an applied
snapshot. The wrapper retries only `0x7007` / EAGAIN once after one second;
these suppressed error results do not trigger that immediate retry. This does
not prevent later scheduled polls or separate connectivity recovery.

### Settings snapshot semantics

Omitting the entire `device_settings` object preserves current switches. Including
an object invokes `0x420158cc` with defaults for absent/non-boolean members:

| Cloud key | Default within an incomplete object | `/api/info` key |
| --- | --- | --- |
| `voiceRecordingEnabled` | `true` | `settings.voice_recording` |
| `keepAwakeEnabled` | `false` | `settings.keep_awake` |
| `autoUpdateEnabled` | `false` | `settings.auto_update` |
| `chargingLedEnabled` | `true` | `settings.charging_led` |

`{ "device_settings": {} }` resets all four to those defaults. Read existing
preferences where available and send a complete intended snapshot. Unchanged
snapshots avoid the settings-save path. RAM changes precede NVS persistence;
an NVS failure can leave session state different from the next boot's state.
The [save-failure trace](storage-and-configuration.md#failed-settings-saves-are-not-retried-by-an-identical-snapshot)
also shows that repeating the identical snapshot skips persistence again: RAM
already matches, and there is no dirty flag. The poll logs the original save
error and continues, so poll success does not acknowledge durable settings.

`autoUpdateEnabled=false` does **not** locally block an otherwise accepted
firmware offer in the recovered path. Withhold `firmware` unless deliberately
offering an update. See [update policy](ota-and-recovery.md#update-policy).

### `user_settings` is copied, with no recovered local application

The poll worker serializes any present `user_settings` value, without first
requiring an object, into a 2,048-byte output buffer at
`0x3fca8c81`. Getter `0x42025da0` copies it to its caller. The recovered callers
are the button-wait path (`0x4201163c`) and main loop (`0x42012810`); neither was
found parsing or applying members of that copy. Main receives at most 511 bytes
plus NUL; the button path supplies four-byte destinations for both settings and
URL, taking at most three bytes plus NUL. It only checks result/pending state,
then returns to main without clearing a successful pending image. Main obtains
the full bounded URL itself; the short button copy is not the download URL.

This does not make backend-owned preferences meaningless. It means a setting
such as style can affect server generation without a local parser. Do not assume
that adding a member to `user_settings` creates a firmware setting. The distinct
`device_settings` branch above does apply its switches. Device fixtures and
remaining indirect-reference checks are still tracked in C02/E01.

### Poll completion is one shared result, not a delivery receipt

Worker `0x42025aec` clears a 13,744-byte global result region at `0x3fca8680`
before polling. Its pending byte is at offset 0, 1,536-byte URL at offset 1,
2,048-byte settings string at offset `0x601`, and result code at `0xe04`.
The completion byte at `0x3fca867c` is **outside** that cleared region.

After the request/retry and any recording-stop attempt, the worker sets that
completion byte and gives its semaphore. It then delays **200 ticks / two seconds**
in `0x4202358c`, frees the copied device key, clears its task handle and deletes
itself. Thus result-ready and task-running can both be true for two seconds after
the request finishes. The running getter reflects a nonzero handle, not ongoing
HTTP activity or a render job. Starter `0x42025c84` rejects a nonzero handle.

The recovered foreground consumers test the completion byte, then use getter
`0x42025da0`; that getter itself neither checks completion nor acquires a lock.
It copies current shared fields and returns the stored result. Clear helper
`0x42025e10` zeroes the region and completion byte; it does not cancel, wait for
or join the worker. The located semaphore references cover creation and giving,
not a foreground take/join. This is a bounded reference audit, not a claim that
all possible indirect accesses have been excluded.

Neither the starter nor a new worker resets an old completion byte before the
new request. If an old result has not been consumed when another poll starts,
that byte can still describe the previous request while the shared fields have
already been zeroed or are being rewritten. A late clear can likewise erase
shared state without identifying which request produced it. These are conditional
ordering hazards inferred from the code; no overlapping-poll fault was induced.

Main invokes the image helper and then clears the poll result. A completed poll,
semaphore signal, zeroed result or idle worker handle is therefore not a
per-image physical-render acknowledgement. A local adapter needs its own durable
offer/job identity and conservative retry policy; the stock poll response has
no result-generation token or render receipt to make those signals equivalent.

The [Standard lifecycle comparison](standard-model-comparison.md#poll-result-ownership-also-matches)
confirms the same result offsets/capacities, separate ready byte, two-second
post-publication lifetime and non-joining copy/clear behavior. Its compared
button/main callers likewise copy `user_settings` without applying members.
Seven function pairs and two caller regions match across 425 instructions;
this does not extend the result to every parser branch, dispatcher or loop.

## System and setup screens

```http
GET /api/v1/upload/global/315/create_account?ip=<frame_ip>
GET /api/v1/upload/global/315/get_started
```

`0x42023bcc` requires HTTP 200 and JSON containing a string `presigned_url`.
It reads at most 2,047 response bytes and rejects a URL that does not fit the
caller's 1,536-byte buffer. Use compact JSON and a short asset URL.

This metadata client uses manual open/header/read calls, a 10,000 ms transport
timeout, a 4,096-byte transmit buffer and the SDK's 512-byte default receive
buffer. It does not follow redirects, install the
shared JSON event callback, or register itself with the HTTP-abort manager. Unlike
voice presign/finalize, it still reads after a zero fetched length; only negative
header results reject that stage. It rejects zero/negative body reads before
parsing and NUL-terminates a positive result. It does not compare the read count
with the declared length or require HTTP-message completion. A complete JSON
prefix can therefore suffice even if later bytes fail or exceed the read cap.
This follows the same SDK reader/parser semantics already traced for voice;
no additional physical framing test was run. An empty URL string passes this
parser's type/length checks but is not a usable asset URL.

`0x4202a8b8` maps instruction type 1 to `create_account`, type 2 to `get_started`;
type 0 (`wake_up`) has no server key. The dispatcher `0x4202ad38` downloads the
two server-keyed screens whenever it displays them. There is no local cache
fallback in that branch. The account screen adds the current station IP if known.

**Correction to an early hypothesis:** the presence of `system_images/` does not
mean every setup screen is cached. The wake-up image is locally installed; these
two screens depend on the backend in the recovered path. An emulator supporting
onboarding needs corresponding assets or an explicit firmware fallback.
Their [background task and poll-deferral limits](rendering-and-concurrency.md#setup-screen-tasks-and-the-two-minute-poll-hold)
also matter: fetching a screen is not an atomic handoff of its image memory.

### Setup metadata comparison and host boundaries

The complete metadata client, instruction-key selector and fetch caller now
match Standard at `0x42022640`, `0x42028fc0` and `0x42029324` respectively
(Large `0x42023bcc`, `0x4202a8b8`, `0x4202abe8`). Three paired bodies contain
422 byte-matched GNU instructions, 38 branch destinations and 12 contiguous
ranges per image. The expected model path segment differs (`315` / `133`);
other compared strings, the three-entry instruction-name table and normalized
operations agree. External SDK/driver calls are mapped, not recursively proved
equivalent by this pass.

The request builder has a 512-byte URL buffer and rejects a formatted length
of 512 or more. It supplies `User-Agent: ESP32-Fraimic/1.0` and `Accept:
application/json`, with no device-key or account-authorization header in this
path. The fetch caller adds `?ip=<four decimal octets>` only for `create_account`
and only after successful station-netif/IP-info lookup. It does not separately
reject an all-zero returned IP. `get_started` receives no such query, and the
local `wake_up` type has no server-key mapping. An emulator should treat the IP
as display/setup information, not proof of device identity.

A new isolated fixture combines unchanged IDF 5.4.1 header/body reader functions
and HTTP parser with the pinned cJSON implementation and a reconstructed setup
response branch. It uses the actual 512-byte receive buffer, 2,047-byte body cap,
1,536-byte URL destination and 10-second per-transport timeout. Nineteen cases
passed with AddressSanitizer and UndefinedBehaviorSanitizer:

| Host case | Result |
| --- | --- |
| Exact HTTP 200 JSON | URL accepted |
| Header and two body reads, each progressing after 9,990 ms | Accepted after 29,970 virtual ms; no ten-second whole-request limit |
| Complete JSON prefix followed by timeout before declared body end | Accepted with HTTP completion false |
| Incomplete JSON prefix, or timeout before any body | Rejected; the latter reader returns HTTP EAGAIN |
| Explicit zero Content-Length | Body read attempted, returns zero, rejected |
| Valid chunked JSON, whose header-fetch result is zero | Read and accepted, including ordinary chunk termination |
| Same chunked JSON without its terminating chunk, then timeout | Accepted with HTTP completion false |
| HTTP 302 | Rejected before reading its body; no redirect follow |
| 2,500-byte declared body with complete JSON at the front | First 2,047 bytes accepted, HTTP completion still false |
| Empty URL with `success:false` | Parser success; neither field supplies a usable image or backend success guarantee |
| Differently cased duplicate URL keys | First matching member wins; an invalid first member rejects a later valid one |
| Decoded NUL within URL | C-string prefix accepted |
| Missing URL or non-object root | Rejected |
| Valid JSON followed by trailing text | Prefix accepted |
| URL lengths 1,535 / 1,536 bytes | First accepted; second returns `0x104` without truncating into the destination |

On these rejection paths the destination begins with NUL; successful parsing
does not validate URL syntax or fetch its asset. These host results do not include
real sockets, TLS, DNS, allocation faults, a display or execution on either frame.
The HTTP source SHA-256 remains
`7aabd415f3a39675e59f591919b9e88e31213e548b010cb0809a888d2b0ceef2`,
and the [cJSON pin](voice.md#json-request-allocation-failures-can-lose-ownership-or-fields)
is unchanged. The cases are one shared host run, not nineteen device tests per
model. Use compact, complete HTTP 200 JSON and a short, nonempty asset URL for
the emulator; parser permissiveness is not a reason to emit incomplete responses.

## Enrollment boundary

`POST /api/v1/account/setup` (`0x42023ed4`) sends JSON fields `email`, `password`,
`device_key`, `mac_address` and `display_type`. The local create-account and sign-in
handlers both call it. The following is a static contract for Large 0.2.29;
Standard's setup parser at `0x42022948` has the same result layout and field checks.
The [Standard live capture](standard-model-comparison.md#enrollment-and-setup-screens)
returned a much larger vendor response, not a test of these minimum fields.

### Parser acceptance versus usable identity

The output is zeroed before the request. HTTP 200 plus boolean `success: true`
is enough for the setup function to return success. Missing `device_info`,
`user_id` or `device_key` does not override that result. String fields are copied
with these limits:

| Response field | Maximum copied text | Result use |
| --- | --- | --- |
| `message` | 127 bytes | Optional feedback/error text |
| `device_info.user_id` | 64 bytes | Saved by both local form handlers |
| `device_info.device_key` | 64 bytes | Parsed and logged, but not used as the saved key by these handlers |

Both handlers save the **original key submitted in the request**, loaded or
generated by `0x420176a8`. Returning a different key is not a key-rotation mechanism
through these paths. The backend should bind the submitted key to its owner.
The device can generate its own key before enrollment; the emulator does not need
to reproduce its embedded key-generation secret.
The [key-selection trace](storage-and-configuration.md#device-key-selection-and-regeneration)
now establishes deterministic MAC-based generation in both pinned builds,
per-environment stored-key precedence and a conditional shared legacy fallback.
Separate account environments do not necessarily imply distinct key values.

An illustrative usable-identity candidate is:

```json
{
  "success": true,
  "device_info": {
    "user_id": "local-owner-id",
    "device_key": "<same-key-as-the-request>"
  }
}
```

This is **not a device-validated minimum response**. A nonempty stable user ID is
necessary for voice: getter `0x42023b30` returns not-found for an empty ID. In
contrast, the local registered check `0x420151dc` tests only whether the email
string is nonempty, and the verification check reads the saved flag. A device
can therefore look registered/verified without a usable voice identity.
The setup parser does not apply `device_info.settings`, `pending_settings` or
telemetry; use the separate poll contract for device settings.

### Host-checked enrollment response boundaries

Thirty host case groups now exercise the recovered HTTP-200 field handling and
shared data-event accumulator with the pinned cJSON 1.7.18 source. The fixture
does not execute the firmware, save identity, enroll a frame or emulate the
separate verification task. It confirms parser success for `{"success":true}`
and for a stable `user_id` without a returned `device_key`; neither is proof of
complete enrollment. Relevant edge cases are:

| Input | Host result |
| --- | --- |
| Numeric/string `success` | Failure; the field must be a JSON boolean |
| Case-variant field names | Accepted by case-insensitive lookup |
| Duplicate `success` or `user_id` | First matching member wins |
| Missing/null/array `device_info`, or non-string identity fields | Can still return success with empty identity strings |
| Decoded NUL within `user_id` | Copy stops there; an initial NUL produces an empty saved-ID candidate |
| Identity strings longer than 64 bytes | Truncated to 64 bytes with NUL termination; a multibyte UTF-8 character can be split |
| Complete leading object followed by text or another JSON value | Leading object controls the result; trailing content is ignored |

For an intentional local enrollment flow, validate identity before returning
success: use one ordinary JSON object, unique canonical field names, a nonempty
stable user ID within the 64-byte limit, and no embedded NUL. Short ASCII IDs
avoid byte-truncation ambiguity. Bind the request's device key; do not use the
response-key field as a rotation mechanism. Keep the entire response comfortably
below 4,095 bytes and return it directly, without redirect bodies. The
[accumulator host cases](#overflow-can-change-the-json-being-parsed) explain why
response truncation cannot safely serve as validation.

### Sign-in and create-account take different paths

The browser-to-frame form parser has a separate
[511-byte single-read / 127-byte encoded-field boundary](local-api.md#account-form-limits-apply-before-decoding).
Those limits apply before the device constructs the cloud JSON. A failure to
preserve a submitted credential is therefore possible without an upstream
authentication rejection; this has not been induced on either frame.

After successful setup, sign-in (`0x420192c8`) saves the entered email, original
device key, returned user ID and verified=true. It checks the save result,
reloads configuration, re-evaluates setup state and requests the `get_started`
screen. The examined handler does not start the separate Supabase verification
task. It returns a local HTML success page containing the selected dashboard
link, rather than issuing a device-side request to that dashboard.

This makes stock sign-in a plausible independent-enrollment entry point with
an owner-controlled local account flow, a stable identity and setup assets.
It does not establish working cold provisioning, removal of the public network
probe/NTP dependencies, or permission to overwrite an existing pairing.

Create-account (`0x42018cc8`) saves verified=false and starts verification.
Its call to the identity saver is followed by a RAM configuration copy without
checking the returned error. A successful registration message alone therefore
does not prove persistence. Sign-in checks that error instead. GNU instruction
checks cover the identity copies and save handling at `0x4201903b`–`0x42019070`
and `0x4201951a`–`0x4201954a`; no NVS fault was induced.

Sign-in also writes an empty timezone string. The calendar/time consumers fall
back to `EST5EDT` when it is empty; see [identity persistence](storage-and-configuration.md#identity-layout-and-migration).
If setup fails without a response message, its sign-in page uses generic invalid
email/password text even for a transport failure. That text alone is not an
authentication verdict.

Create-account starts `0x4202463c` / `0x42023674` to check verification. That task posts
`email`/`password` to the selected auth host's
`/auth/v1/token?grant_type=password`, using the embedded public anonymous-client
key in `apikey` and Bearer headers. The identity NVS record has no password field.
The task temporarily retains credentials in RAM; this is not a password-free flow.

Verification checks for HTTP 200 and a parsed string `access_token`, then saves
verified state and requests the get-started screen. It makes at most 180 attempts,
with five-second delays and a 15-second HTTP timeout. This is not a fixed
15-minute wall-clock deadline: request time adds to the delays. Poll responses
can separately reconcile `account.email_verified`.

The verification task has two additional parser constraints:

- Its 512-byte request body is formatted directly as
  `{"email":"%s","password":"%s"}` from two NUL-terminated, at-most-127-byte
  credential copies. It does not JSON-escape them. Quotes/backslashes can change
  the request's meaning or make it invalid. The initial account-setup request
  instead uses cJSON serialization, so those two requests are not equivalent.
- Before parsing an HTTP 200 body, it searches for the literal substring
  `access_token`. Once that substring is present, the task exits after attempting
  parsing, even when JSON is malformed, the field is not a string, or saving
  verification fails. The string check does not require a nonempty token. Without
  the substring, it continues its retry loop. A token-looking error body can
  therefore end verification without completing it.

These are static findings, not a test of the owner's password or the cause of
the captured Standard setup error, which had a separate TLS allocation failure.
The local sign-in candidate above avoids this verification task; supporting
create-account requires its separate auth contract and lifecycle too.

Do not forward account passwords to a replacement server as an accidental
consequence of a URL patch. Define an explicit owner-enrollment flow before
supporting unpaired or reset frames. Preserve existing paired state for the first
local-backend experiment. [Configuration notes](storage-and-configuration.md)
describe production/development identity separation and migration.

## Albums and gallery

The frame's local album routes are cloud proxies, not an on-device playlist
database. Supporting them in an emulator is separate from using HA playlists
to answer the image poll. See [all local routes](local-api.md).

Owner-account reads on 21 October 2026 returned HTTP 200 for both gallery pages
and `/api/v1/gallery/<upload_public_id>`. A device key supplied as a Bearer token
returned 401; an earlier request without authentication also returned 401.

Observed items have `upload_id`, `upload_type`, `created_at`, `metadata`,
`transcript`, `style_name`, `original_url`, `orientation` and `crop_params`.
The account contains both `audio` and `image` uploads. Voice items can carry
transcripts; metadata/style may be null. Crop objects include `x`, `y`, `unit`,
`width`, `height`, `orientation` and `display_type`; do not discard their unit.

Pagination returns `page`, `page_size`, `total_count`, `total_pages`, `has_next`
and `items`; the advertised maximum page size is 50. IDs matched between sampled
list/detail reads. One voice original downloaded successfully as a 1200 × 1600 PNG,
separate from the packed panel asset. Its signed URL had about an hour remaining.
A later check after its 19:56:41 UTC expiry returned HTTP 403 `AccessDenied` for
that old URL. Re-fetching the same item returned a new, unexpired URL; upload ID
and observed metadata were unchanged. The new URL returned HTTP 200 and exactly
the same 4,016,864 PNG bytes, verified by SHA-256 comparison with the earlier
download. This establishes one expiry/refresh cycle, not indefinite retention.
Persist originals and deduplicate by account/upload identity, not the signed URL.
No library import was performed.

The same item was subsequently linked to the captured Standard voice workflow:
the audio key, panel URL and original share a private generation directory/job
UUID. Its gallery record contains a transcript. The public gallery upload ID is
different from that object-key UUID; do not assume a direct identity equality.
This proves transcript/original availability for that creation, not access to the
vendor's final generation prompt. See the [correlation evidence](standard-model-comparison.md#prompt-visibility-and-ha-reuse).

Both owner-authenticated `GET /api/v1/albums` and a credential-bearing
`GET /api/v1/albums/<device_key>` without a Bearer header returned 200. In this
account they returned the same album IDs, including empty wake-planning albums.
Do not assume this endpoint filters solely to the requesting frame. Observed
albums include `device_assignments` containing `device_id`, interval schedules,
image counts and images. Create/update/delete remain untested; see the
[recovered proxy contract](local-api.md#album-proxy-contract).

## HTTP and TLS requirements

- Use explicit `Content-Length`, compact JSON and short URLs. The voice JSON
  readers skip body reading when fetched length is non-positive.
- Serve final URLs directly. The recovered image downloader and voice JSON paths
  use `esp_http_client_open` / `fetch_headers`; they do not run the automatic
  redirect loop in `esp_http_client_perform`. A redirect accepted by a desktop
  HTTP client is not evidence the frame follows it. Poll/setup/auth paths using
  `perform` differ as traced below. This distinction follows the matching
  [IDF client implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c);
  controlled device redirect/error tests remain open.
- Serve panel assets as HTTP 200, `application/octet-stream`, exactly 2,304,000
  bytes for this Large build. A PNG/JPEG is not the raw panel buffer.
  [Download and retry analysis](image-downloads.md) distinguishes HTTP body
  completeness from panel size: a shorter declared asset can pass the downloader,
  and render-worker failure does not reliably prevent cache replacement.
- The image downloader logs AWS query-field presence but does not require an
  S3-specific URL. A local HTTPS file on the accepted API hostname, without AWS
  query parameters, was downloaded, cached and physically displayed in the
  [one-shot test](backend-emulation.md#one-shot-panel-delivery-c03c09d06).
- The current clients in the configuration table below attach the ESP-IDF CA
  bundle. Most also set config byte `0x71` (`use_global_ca_store`), but the
  initializer takes the bundle branch first; the stores are not combined by
  setting both. Byte `0x72` (`skip_cert_common_name_check`) remains zero. The
  [SDK header](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/include/esp_http_client.h)
  names the fields; the actual binary's selection is described below.
- DNS redirection alone does not make an unrelated certificate valid for the
  vendor hostname. Use deliberately configured hostname/trust for a durable
  custom backend. Large's [controlled negative tests](backend-emulation.md#negative-tls-controls-c03)
  rejected a self-signed certificate for the correct name and an accepted-chain
  certificate for the wrong name; a matching-profile correct-name control worked.
  This verifies the poll path's tested trust/name boundaries, not every consumer
  or all certificate failure modes.

### HTTP buffers, trust precedence and URL scheme

The configuration block is 148 bytes in this binary. Its receive-buffer field is
at `+0x64`, transmit-buffer field at `+0x68`, timeout at `+0x4c`, and certificate
bundle callback at `+0x78`. Mapper `0x4206d20c` substitutes **512 bytes** for
either zero buffer field. The following values come from the actual config stores
and that mapper, not from similarly sized application JSON arrays:

| Consumer | Timeout (ms) | HTTP RX bytes | HTTP TX bytes | Request driver |
| --- | ---: | ---: | ---: | --- |
| System-image metadata `0x42023bcc` | 10,000 | 512 default | 4,096 | Manual |
| Account setup `0x42023ed4` | 30,000 | 512 default | 4,096 | `perform` |
| Email verification `0x42023674` | 15,000 | 4,096 | 2,048 | `perform` |
| Poll `0x4202475c` | 10,000 | 512 default | 4,096 | `perform` |
| Image download `0x4202606c` | 30,000 | 4,096 | 4,096 | Manual |
| Audio presign `0x420266d8` | 30,000 | 512 default | 4,096 | Manual |
| Audio multipart `0x42026b9c` | 120,000 | 512 default | 8,192 | Manual |
| Audio finalize `0x42027380` | 600,000 | 512 default | 4,096 | Manual |
| Direct OTA `0x4202c514` | 30,000 | 4,096 | 4,096 | Manual |
| Album proxy `0x42030064` | 10,000 | 512 default | 4,096 | Manual |

“Manual” means explicit open/header/read/write calls, without the automatic
redirect loop. `perform` consumers leave automatic redirects enabled with the
SDK's default limit of ten. These timeouts apply to transport operations, not an
absolute end-to-end deadline. The earlier voice reader fixture demonstrates why
several successful reads can outlast one configured timeout.

RX size is neither the accepted response-body limit nor a TLS record-size limit.
For example, the 512-byte HTTP receive buffer can feed a separate 4,096-byte JSON
accumulator or a 4,095-byte application read. The album proxy's 4 KiB application
read similarly need not be one underlying transport read. Constructor
`0x4206df98` allocates the HTTP TX and RX arrays separately; headers, parser state,
JSON and TLS need other memory. These figures do not isolate the cause of the
observed Standard SSL allocation failure.

All ten rows supply bundle callback `0x42044ec8`. Verification leaves the
global-CA flag zero; the other nine set it. Constructor branches at
`0x4206e128` select the bundle callback when present, otherwise the global store,
otherwise an explicit certificate. This matches the
[SDK initializer](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c).
Therefore adding a certificate only to a global CA store would not select that
store for these unchanged configurations. A future owner-trust implementation
must intentionally choose its trust path.

The SSL transport enum in a configuration is also not an HTTPS-only policy.
After applying config defaults, the constructor parses the supplied URL through
`0x4206dca4`, which replaces its scheme and port; an explicit `http://` URL selects
HTTP. The earlier local microphone uploads are the physical positive control
for plain HTTP storage. Plain-HTTP compatibility for every endpoint remains
untested.

The older manifest updater `0x4202bb88` differs: 30,000 ms timeout, 4,096-byte RX,
default 512-byte TX, and zero bundle/global-CA/explicit-certificate fields in its
configuration. It is separate from the direct OTA row and is not evidence that
the currently used updater accepts untrusted HTTPS. No update was attempted.

### TLS setup needs internal RAM before authentication

The pinned Large and Standard builds configure **TLS 1.2 only**. Defaults helper
`0x42072760` sets minimum and maximum to `0x0303`; version check `0x4207174c`
rejects another range. Handle constructor `0x420c44c8` warns and retains defaults
when asked for TLS 1.3. The local HTTPS endpoint must therefore support TLS 1.2;
a TLS-1.3-only listener is incompatible with this recovered configuration.
This is static evidence, not a new negotiated-version test.

Setup `0x42072598` and handshake initializer `0x420724f4` request these five
allocations for a freshly initialized context, in order:

| Allocation | Requested bytes |
| --- | ---: |
| Incoming TLS record buffer | 16,717 |
| Outgoing TLS record buffer | 4,429 |
| Negotiating transform | 220 |
| Negotiating session | 144 |
| Handshake parameters | 584 |
| **Subtotal** | **22,094** |

These sizes come from the binary's literal values and call arguments. They
include record-buffer overhead and are not HTTP RX/TX sizes. Checksum setup
`0x42071ebc` also requests 116- and 224-byte digest contexts through
`0x4207da28`. Neither subtotal is the complete connection or peak heap cost:
the outer TLS object, hostname, RNG, certificates, socket, HTTP client and later
handshake allocations are additional.

The calloc/free dispatch slots initially select `0x42081dbc` / `0x42081dd0`.
Allocation passes capability mask **`0x804`, INTERNAL | 8BIT**, to the heap
allocator, without a PSRAM fallback. The slot-reference audit found the dispatch
reads and no direct setter reference in either image; arbitrary computed writes
are outside that negative result. This matches the internal-memory branch of
the [pinned allocator port](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/mbedtls/port/esp_mem.c)
and the [capability definitions](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/heap/include/esp_heap_caps.h).
Free PSRAM does not satisfy these allocations. Internal free bytes alone also
do not establish that a contiguous allocation of the required size is available.

Failure of either record allocation or any of the three negotiating allocations
returns `-0x7f00`. The three small allocations are attempted before their combined
failure check, so failure of the first does not skip the other two. Their failure
branch releases all three; setup then releases and clears the record buffers and
derived pointers. A later checksum failure follows a different return code and
leaves negotiating subcontexts for outer cleanup. Constructor failure invokes
`0x420c40e8`, including SSL cleanup `0x420726c0`, before returning `0x8017`
for a setup failure. External cleanup routines were not exhaustively audited.

Eight [isolated source case groups](validation-2026-10-22.md#tls-setup-allocation-and-version-boundaries-c03e01e02)
verify these selected allocation/cleanup boundaries. The observed Standard
`mbedtls_ssl_setup -0x7F00` precedes the network handshake and HTTP credentials
for that connection. It does not establish a rejected password, bad server
certificate, which allocation failed, or why memory was unavailable. Reducing
JSON size or shortening a certificate chain cannot reduce these initial fixed
allocations. Serializing client work and measuring internal largest-free-block
are candidates for a future firmware change; neither is implemented here.

### Compiled cipher suites and hostname configuration

Both images contain the same **58 cipher definitions**, each restricted to
TLS 1.2, and the same 185-entry preference array. Getter `0x42075f58` filters
that array through lookup `0x42075f3c`; the removal predicate `0x420e47a0`
always returns zero. All 58 definitions survive that filter, in the order
preserved in [the cipher inventory](tls-capabilities.json). Names and scalar
fields were decoded and compared across both images; relocated string pointers
were not mistaken for different cipher definitions.

Useful AES-GCM candidates for a local server are present:

| Certificate authentication | Cipher suite | ID |
| --- | --- | --- |
| RSA | `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | `0xc02f` |
| RSA | `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384` | `0xc030` |
| ECDSA | `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` | `0xc02b` |
| ECDSA | `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384` | `0xc02c` |

There is no ChaCha20 definition. A server restricted to ChaCha20 therefore has
no match in this compiled list. The inventory is not a captured ClientHello or
proof that every listed suite is usable with current credentials, key exchange,
curve and signature settings. Later handshake filtering and actual negotiation
remain distinct checks; certificate name/trust validation still applies.

Client configuration `0x420c4174` sets the certificate hostname before SSL setup.
With name checking enabled, it duplicates an explicit `common_name` override
when supplied, otherwise the supplied URL hostname. Hostname setter `0x420722b0`
accepts up to **255 bytes**, not Unicode characters. An overlong value returns
`-0x7100` before replacing the previous name. An accepted-length replacement
first frees the old name; failure to allocate the new copy leaves no stored name
and returns `-0x7f00`, which the caller propagates as hostname-setup failure.
Empty and null inputs have different storage behavior: empty allocates a
one-byte string, while null clears the pointer. These are helper semantics, not
evidence that malformed URL hosts reach a completed connection or bypass checks.

The ALPN setter `0x42072320` is compiled and is called when a protocol list is
provided. It requires each name to contain 1–255 bytes and the sum of name bytes
to be at most 65,535, then stores the caller's list pointer without copying it.
This does not establish that current application requests configure ALPN or
that HTTP/2 is supported. SNI serialization and actual ClientHello contents are
separate from storing a hostname and remain to be traced.

### Address selection does not recover from a bad IPv4 destination

The recovered HTTP transports start with an unspecified address family. Transport
allocator `0x420c2bd8` zero-allocates 108 bytes; the TLS configuration begins at
offset 4, with its family field at configuration offset `0x50`. SSL/TCP initializers
`0x420c2e04` / `0x420c2e74` select encrypted/plain operation without changing that
field. Large's HTTP constructor `0x4206df98` and common-options helper
`0x4206d16c` configure trust, buffers, keep-alive and an optional interface name;
the recovered path has no HTTP address-family setting. This describes those
constructors, not an exhaustive search for arbitrary runtime memory writes.

Transport helper `0x420c314c` converts the default to `AF_UNSPEC`. As already
[traced in both builds](boot-and-scheduling.md#outbound-local-names-and-blocking-resolution),
`getaddrinfo` selects the resolver's IPv4-then-IPv6 mode. This is DNS-stage fallback,
not parallel connection attempts or recovery after a connection failure:

| Situation | Recovered behavior |
| --- | --- |
| Uncached ordinary hostname | Starts with an A query |
| Matching cached IPv6 answer, with no matching cached IPv4 answer | Can return cached IPv6 before starting a fresh A query |
| NOERROR reply with no usable A address | Dual-family request changes to an AAAA query |
| DNS timeout or terminal nonzero response code | Error path; these branches do not switch to AAAA merely because A resolution failed |
| A address resolved, but TCP connect fails or times out | Connection attempt fails; no alternate family/address attempt in this path |
| A connection works but TLS setup/handshake fails | Error returned; no alternate-family restart in the recovered TLS state machine |

The pinned resolver retains at most one address per query. The hostname-to-socket
helper uses the first `addrinfo` result and frees the list; it contains no loop
over `ai_next`. Common connect helper `0x420c34cc` configures that socket, connects,
waits with `select` if needed and checks `SO_ERROR`. Its failure exits close the
socket and return an error. Plain HTTP connector `0x420c2dac` and SSL connector
`0x420c2afc` propagate that failure. Any later application retry is a separate
attempt, and may reuse the same DNS cache entry.

**Backend implication:** publishing a reachable AAAA record alongside an
unreachable A record does not establish a working fallback. For the stock adapter,
make the chosen A address reachable from the frame, or deliberately validate a
different family/hostname arrangement. DNS cache state and TTL matter when moving
the backend. Do not assume round-robin addresses or desktop-browser fallback
behavior will supply resilience.

The timeout boundary is also narrower than a total request deadline. Common
connect performs name resolution before applying socket/connect waits. Synchronous
TLS wrapper `0x420c3a58` measures elapsed time only after its low-level call returns
an in-progress result; a returned success exits before that elapsed-time check.
It cannot interrupt a blocking DNS or lower-level operation in the middle of that
call. Thus the timeout field alone does not prove a hard wall-clock cap. No slow
DNS, socket or TLS fault was induced here.

Nine additional [Standard transport functions match](standard-model-comparison.md#connection-address-selection-and-errors-also-match).
The findings combine complete binary paths with the previously checked DNS/cache
and reply-parser behavior. They are static conclusions, not successful IPv6
connections, a measured retry timeline or new physical/host fault tests.

### Automatic redirects preserve the request and share response state

The three recovered direct application callers of `esp_http_client_perform`
(`0x4206e804`) are polling, account setup and email verification. Their zeroed
configs leave `disable_auto_redirect` false. SDK config mapper `0x4206d20c`
supplies the default limit of ten redirects. Response checker `0x4206e748`
handles 301, 302, 303, 307 and 308 through `0x4206e470` / `0x4206dca4`.

The recovered redirect path changes URL/host/port but does not change the method
or clear the POST body/custom headers. In particular, do not assume a 303 turns
an account-setup POST into a harmless GET, or that changing hosts strips auth
headers. This is a static data-flow finding, not a live cross-host credential
test. A local account flow should terminate locally and use direct responses;
do not forward an owner's vendor password as a side effect of routing.

All three clients install callback `0x420234cc` using a shared destination
pointer (`0x3fcabc44`), received length (`0x3fcabc40`) and capacity
(`0x3fcabc3c`). Each request sets capacity 4,096 and length zero before `perform`.
The callback:

- Appends decoded data events only when the resulting length is **less than**
  capacity, leaving room for NUL: at most 4,095 bytes.
- Skips an entire event that would overflow, logs it and still returns success.
  It does not mark the response as failed; later smaller events can still fit.
- Does not reset the accumulator on finish, disconnect or redirect.
- Does not reject data merely because it came from chunked transfer framing.

Consequently, the manual voice readers' positive-`Content-Length` rule must not
be generalized to these event-driven paths. Their chunked path is reachable
statically; it has not been exercised in a physical response-variant test.
Compact explicit-length JSON remains the emulator baseline.

The callback's `Date` header branch does not parse its value or synchronize time:
it only reads and converts the already-current local clock. This holds in both
pinned models; see the [HTTP-time trace](boot-and-scheduling.md#http-date-does-not-supply-a-fallback-clock).
An accurate backend response date is not a replacement for the stock time service.

An intermediate redirect body and the final body can accumulate in the same
buffer. The JSON wrappers (`0x4203961c` / `0x4203962c`) disable the parser's
require-end-of-input option. A complete leading JSON value can therefore be
accepted while trailing bytes are ignored, or an HTML redirect body can prevent
the final JSON from parsing. Overflow behavior also depends on event boundaries,
not just total response size. Serve one direct, bounded response instead of
depending on either behavior. These consequences are now reproduced in the
bounded host fixture below, but remain untested as physical response variants.

### Redirect URL handling differs from a browser

Twenty host cases execute the unmodified IDF 5.4.1 URL setter, redirect setter and
response checker with the pinned HTTP URL parser. GNU checks of the corresponding
Large functions and URL-parser branches support these results. The fixture uses
synthetic request data and stubbed header storage, close and event hooks; it does
not make a network request or execute TLS, the full `perform` loop or a frame.

| Redirect input | Host-checked result |
| --- | --- |
| 301, 302, 303, 307 or 308 with an absolute HTTPS URL | Updates destination and requests replay; POST method/body and unrelated custom-header state remain unchanged |
| `/next?new=2` | Keeps scheme/host/port, replaces path and query |
| `next` or `?new=2` | Fails URL parsing; no browser-style relative resolution |
| `//other.invalid/next` | Keeps the original host and treats the entire value as a path |
| Absolute URL without a query, or with a fragment | Clears the old query; the fragment is not copied into path/query |
| Absolute HTTP URL or explicit port | Updates scheme/port; no HTTPS-only redirect policy in this setter |
| Missing `Location` or malformed `http://` | Response checker returns failure without scheduling replay |
| 304 | Not a redirect; no replay |

The counter permits ten successive redirects. The next redirect returns `0x7001`;
any non-2xx status also hits that limit check before status-specific handling. A
2xx status resets the counter first. This limits replay count, not elapsed time.
With automatic redirects enabled, the checker posts its redirect event to the
SDK event loop; it invokes the client's redirect callback only when automatic
redirects are disabled. These are distinct event paths.

This strengthens the earlier request-state trace without claiming an observed
cross-host credential transmission. For an emulator, use final absolute asset
URLs and return setup, verification and poll JSON directly. If the HTTP server
normally redirects a missing trailing slash or moves users to a login page,
exempt the device protocol routes. Manual voice/image/album/OTA clients still do
not execute this redirect loop. An HTTP-success redirect fixture is not evidence
that those clients will follow the same URL.

### Overflow can change the JSON being parsed

The enrollment fixture models this callback with scripted data events of at most
512 bytes, matching the setup client's default receive-buffer capacity:

- A 4,095-byte padded success response fits. A 4,096-byte version delivered in
  512-byte events drops its final event, retains only 3,584 bytes and still parses
  the complete leading success object.
- A constructed oversized, valid object initially has `success: false`. With
  one event grouping, the callback discards a middle member and appends a smaller
  final event, producing a different valid object with `success: true`. The same
  original body with a different grouping instead fails JSON parsing. No write
  exceeds the buffer: **silent content loss changes meaning**.
- An accumulated leading redirect JSON object controls the final parse; leading
  redirect HTML prevents the following JSON from parsing. Finish/redirect events
  do not reset the accumulation state.

These are reconstructed callback/parser results, not actual HTTP/TLS exchanges
or a demonstration of a physical device accepting those event boundaries.
They establish why the emulator should serialize, size-check and serve a compact
final response rather than relying on the client's overflow handling. A later
firmware fix should make overflow fail the request and reset response ownership
for each exchange. [Validation](validation-2026-10-22.md#enrollment-json-and-event-boundaries-c11c01d01)
records source hashes, scope and the thirty cases.

### Shared response ownership and verification guard

The callback does not choose a destination from the originating client or its
`user_data`, and it takes no request-wide lock. The pointer, length and capacity
describe whichever request assigned them most recently, not a response object
owned by each caller. Their actual backing memory differs:

| Client | Response allocation | Recovered cleanup behavior |
| --- | --- | --- |
| Poll `0x4202475c` | Fixed 4,096-byte global at `0x3fca767c` | Clears the shared pointer after client cleanup |
| Account setup `0x42023ed4` | 4,096-byte local stack array | Clears the pointer after parsed HTTP 200 handling; client-init, POST-body setup, transport, non-200 and JSON-parse failures can return without clearing it |
| Verification `0x42023674` | Fresh 4,096-byte heap allocation per attempt | Ordinary retry frees then clears; the token-substring exit frees without clearing |

The poll dispatcher `0x42016570` does provide a meaningful guard: it skips when
not registered, and for a registered **unverified** identity it skips while
getter `0x42024628` reports verification running. Once verified, that check is
bypassed. It also checks connectivity, OTA state and the time-limited
[Get Started hold](rendering-and-concurrency.md#setup-screen-tasks-and-the-two-minute-poll-hold);
the poll starter rejects an already-present poll task handle. Ordinary unverified-account polling is therefore
not evidence of concurrent verification. These checks do not acquire ownership
of the shared response buffer.
The compared Standard build lacks the verification-running and Get Started
exclusions in its poll dispatcher; see
[the task comparison](standard-model-comparison.md#polling-instruction-tasks-and-conditioning-differ).

The recovered account-form handlers do not wait for an existing poll or
verification task. Verification starter `0x4202463c` does not check for an existing
verification worker, stores no task handle, and sets its shared running byte
**after** task creation succeeds. Repeated successful create-account submissions
can consequently start multiple workers; any one exit clears the same byte. A
new worker's early failure can also race the starter publishing running=true.
Those are possible schedules from the code, not observed device failures.

With overlapping requests, one caller can redirect another caller's data events
or clear its destination on cleanup. Stack/heap exit paths also leave a stale
pointer until reassigned. No use-after-return/free or cross-response corruption
was induced; without an overlapping event, a stale pointer alone does not show
an access. The earlier Standard TLS allocation failure is not evidence of this
particular race.

A future fork should attach response memory and bounds to each HTTP client's
context, and make verification a single owned task with coordinated cleanup.
The backend can use direct, short responses but cannot enforce all local form
and background-worker scheduling. Manual voice/download clients do not use this
JSON accumulator and retain their separate ownership/cancellation issues.

- [Connectivity and NTP](boot-and-scheduling.md#offline-dependencies) still need
  attention for WAN-free operation.

For audio endpoint schemas, limits and status handling, see [voice](voice.md).

The [Standard live capture](standard-model-comparison.md) adds observed setup
request/response shapes, positive test-chain acceptance, a direct HTTP 204 audio
upload and successful finalize without a `status` field. Its vendor-proxy setup
success does not establish independent local enrollment. Keep the two model
assets and their firmware fingerprints separate.
