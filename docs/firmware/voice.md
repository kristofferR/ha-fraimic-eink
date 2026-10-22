# Voice capture and generation

[Research index](README.md)

## Stock sequence

```mermaid
sequenceDiagram
    participant User
    participant Frame
    participant API as Cloud API / proposed adapter
    participant Store as Upload endpoint
    User->>Frame: Tap, record, tap to stop
    Frame->>API: POST audio/presign (device_key, user_id)
    API-->>Frame: url, key, fields
    Frame->>Store: Multipart POST recording.wav
    Store-->>Frame: HTTP 2xx, empty body
    Frame->>API: POST audio/finalize (key, orientation, identity)
    Note over API: Transcription, generation and panel conversion
    API-->>Frame: HTTP 200 + presigned_url
    Frame->>Store: GET packed panel image
    Frame->>Frame: Render image
```

The HA adapter is proposed. Standalone fixtures have received physical-frame
recordings through local presign and plain HTTP multipart upload. A later test
returned successful finalize JSON and a fixed panel image: the stock client
downloaded it, completed its driver refresh, saved it and returned to ready.
No transcription or image generation was invoked. Because the same test card
was already displayed, the owner could not independently distinguish the second
refresh. See the [combined device result](backend-emulation.md#combined-voiceimage-device-result-c09).

Successful local captures were 4.608, 5.888 and 4.992 seconds, all matching the
format below. The earlier capture-only fixture intentionally returned HTTP 409
at finalize; the final test returned HTTP 200. Both observed valid finalize
requests specified `landscape` orientation.

The separate [Standard 0.2.28 capture](standard-model-comparison.md#poll-and-voice-observations)
completed a real vendor-generated image, confirmed by its owner. Its direct
storage upload returned HTTP 204; finalize omitted `status` and still completed.
This is additional model-scoped evidence for the shared contract, not a local
generation test or proof of every upload status on Large.

## Capture and timing

| Property | Recovered behavior |
| --- | --- |
| Container | RIFF/WAV, 44-byte header |
| Audio | PCM, signed 16-bit, mono, 16,000 Hz |
| Throughput | 32,000 audio bytes/second |
| Buffer capacity exposed to recorder | 2,120,000 bytes, including reserved header |
| Outer recording wait | 6,000 ticks at 10 ms, approximately 60 seconds; subsequent stop is not deadline-bounded |
| Initial button suppression | 200 ticks, approximately two seconds |
| Completion | Single tap after suppression |
| Cancellation | More than two taps in the detected group |
| Deadline without completion | Stop recording and fail; do not upload |

Capture starts at `0x4201fed0`. `0x42010994` checks `voiceRecordingEnabled`,
starts the recording task and waits for completion. `0x42011314` handles the
button/stop/cancel outcomes. `0x420201d4` writes the WAV header in place and returns
the existing buffer. Approximately 1.92 MB of audio fits within 60 seconds; this
is a sizing estimate, not a guarantee of a successfully submitted exact-duration
recording. Silence is not the stock completion signal.

On Large, the microphone/image buffer is [shared](hardware-and-layout.md#one-psram-buffer-serves-audio-and-images).
Do not introduce image downloads during recording or reuse that memory before
audio transmission finishes. A separate WAV allocation is not implicit in the
header-generation function.

Standard 0.2.28 instead has [separate audio and image allocations](standard-model-comparison.md#separate-recording-and-image-allocations).
Its selected presign/upload/finalize branches match the transport contract below,
but Large's audio/image alias must not be generalized to it.

### Capture reads can lose audio without invalidating WAV structure

The recovered Large capture-task entry is `0x4201fa24`. Its task pointer comes
from recording start `0x4201fed0`; an independently checked GNU entry allowed
recovery of this previously unnamed function. Ten application/SDK functions
were checked across 1,326 instructions in 31 decoded ranges for this pass.

The worker requests **4,096 bytes** per `i2s_channel_read` call, passing a
**50 ms timeout**. It appends bytes only when the return status is `ESP_OK` and
the byte count is positive. Capacity is checked for the whole returned block;
if it does not fit, recording is stopped without copying a smaller remainder.
An exact fit is accepted. Successful bytes are copied unchanged before the
worker accumulates min/max, absolute-amplitude and sample-count statistics.
Its `abs(sample) > 100` count is diagnostic: it does not remove silence or stop
recording. There is no sample gain/normalization or software speech detector in
this application worker; this says nothing about the microphone's physical DSP.

The compiled SDK reader at `0x4204fbec` can copy bytes, advance its DMA position,
then return `ESP_ERR_TIMEOUT` when a later queue receive fails. The app discards
that entire partial result. Later reads continue from the advanced position,
so the omitted samples are not replayed. The resulting WAV can describe its
stored bytes correctly while lacking an interval of captured audio.

Nine isolated host groups use the unchanged `i2s_channel_read` function from
the pinned [IDF 5.4.1 implementation](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_driver_i2s/i2s_common.c),
scripted queue/semaphore/state behavior and a reconstruction of the app's
admission/copy branch. Synthetic DMA buffers contain recognizable byte patterns:

| Host case | Result |
| --- | --- |
| Complete 4,096-byte read across nine scripted 480-byte buffers | All bytes admitted; nine 40 ms waits total 360 ms despite a 50 ms timeout argument |
| Timeout before any bytes | Zero bytes; recording admission leaves stored data unchanged |
| Two 480-byte buffers followed by timeout | SDK reports 960 consumed bytes and timeout; app admits zero |
| Successful read after that partial timeout | Starts with the third buffer; the discarded 960 bytes are not recovered |
| Read semaphore unavailable | Invalid-state result, zero bytes, no queue read |
| Channel already stopped | Successful status with zero bytes |
| Scripted channel-state change during a read | Short successful result of 480 bytes, admitted by the app branch |
| Capacity one byte short of a complete block | No partial copy; active flag cleared |
| Exact capacity | Complete block admitted |

All nine passed with address/undefined-behavior sanitizers and warnings treated
as errors. Queue timing is virtual; the 480-byte buffers and state changes are
fixture inputs, not a measurement of physical DMA activity. No recording,
dropout, microphone fault or hardware timing was tested. The SDK source SHA-256
is `b39ebba9ea228bba21f9629ce54e4c6ffba628c0b7ec3b477a6960e094dc232c`.

The SDK timeout applies separately to acquiring the read semaphore and each
needed DMA-buffer wait. It is not an overall 50 ms deadline for a 4,096-byte
read. The worker also does not abandon recording merely after 50 timeouts:
unsuccessful/empty reads increment its local failure total, successful reads
preserve that total, and the `> 50` abort check is reached only for a result other
than `ESP_ERR_TIMEOUT`. Thus timeout-only sequences continue until another stop
condition; a later non-timeout failure can trigger the accumulated threshold.
These threshold branches are static findings, separate from the nine host groups.

For a local voice job, retain the original WAV and derive **stored-audio
duration** from its PCM byte count. Do not label that duration as time spent
recording, or insert guessed silence for missing intervals. Presign/finalize
carry no capture-gap count or recording timestamps. A firmware extension could
report captured/stored/dropped bytes and stop reason alongside the job ID.

### Recording stop and completion are separate signals

Normal stop `0x42020090` clears the active byte under the recording mutex, then
waits in **ten-tick / 100 ms intervals** until the capture-task handle becomes
zero. There is no timeout in that loop. The worker can finish an already-started
read and append its accepted result before it checks the flag again; it clears
the handle after its final statistics update, immediately before self-deletion.
Consequently stopping at a tap is not an exact audio-sample boundary.

The outer 6,000-tick wait in `0x42010994` is followed by this same stop call and
I2S disable. It therefore does not establish a hard 60-second operation limit.
If stop sees the active byte already false, it returns invalid-state without
performing the handle wait. A blocked mutex/task or an already-stopping worker
was not reproduced on the frame.

The button-control task `0x42011314` gives the outer completion semaphore after
explicit stop/cancel/interruption paths. When its recording-state getter
`0x42020150` instead returns false, it disables I2S and exits **without giving
that semaphore**. The getter can return false because recording ended, the task
handle is zero, or its ten-tick mutex acquisition failed. The outer wait can then
reach its generic “user never stopped recording” timeout path even though the
proximate cause was internal. That log is not proof of user inaction.

The [Standard capture comparison](standard-model-comparison.md#capture-loss-and-stop-behavior-also-match)
confirms these selected read/error/stop paths in nine function pairs. It adds no
second host-fixture run or physical cancellation test. A missing presign request
cannot identify whether the user cancelled, capture failed, or the recording
was never started.

## Presign

`0x420266d8` sends:

```http
POST /api/v1/upload/audio/presign
Content-Type: application/json
```

```json
{ "device_key": "<device_key>", "user_id": "<user_id>" }
```

Illustrative response:

```json
{
  "url": "https://frame.example/audio/job-123",
  "key": "job-123/recording.wav",
  "fields": { "ticket": "<job-scoped-upload-ticket>" }
}
```

The upload routine `0x42026b9c` builds an ordinary multipart form, copying
string-valued members of `fields` and adding the file field `file`, filename
`recording.wav`. It is not an S3 SDK and does not inherently require S3 storage.
The status check accepts 200–299, but it runs **after a faulty response-length
check**. Return an empty upload response; a successful status alone is insufficient.

Supply a real JSON object for `fields`. An absent field becomes an empty serialized
string and fails the later parse. A real `{}` object was accepted by the physical
frame, which uploaded a valid WAV to an ordinary local HTTP service. No S3 server
or S3-specific form fields were needed. A scoped upload ticket gives the adapter
a useful authorization boundary.

### Presign copying and field reserialization

The Large presign result is a 5,888-byte record with three independently bounded
strings. These are byte limits, not character counts:

| Member | Offset | Storage | Maximum copied content |
| --- | --- | --- | --- |
| Upload URL | `0x000` | 1,536 bytes | 1,535 bytes plus NUL |
| Finalize object key | `0x600` | 256 bytes | 255 bytes plus NUL |
| Serialized form fields | `0x700` | 4,096 bytes | 4,095 bytes plus NUL |

The fields limit applies **after reserialization**, independently of the
4,095-byte HTTP read cap. Presign calls `0x42039644`, the formatted `cJSON_Print`
wrapper, then silently truncates its result. Object printer `0x42038f90` inserts
newlines and tabs. A compact response that fits the HTTP buffer can therefore
produce fields JSON that no longer fits. Presign still returns success; the
upload routine subsequently reparses the truncated string and fails before
opening its HTTP client.

Twenty-five isolated host groups use the pinned
[pinned cJSON implementation](https://github.com/DaveGamble/cJSON/blob/acc76239bee01d8e9c858ae2cab296704e52d916/cJSON.c)
with reconstructed positive-read HTTP-200 field handling and string-part
projection. Concrete boundary cases use synthetic short field names and values:

| Complete incoming response | Formatted fields | Copied fields | Result |
| --- | --- | --- | --- |
| 3,249 bytes | 4,095 bytes | 4,095 bytes | All 292 string fields reparse/project |
| 3,250 bytes | 4,096 bytes | 4,095 bytes | Presign succeeds; upload fields fail to parse |
| 3,255 bytes | 4,104 bytes | 4,095 bytes | Same delayed failure with 293 fields |

The same fixture verifies that exact URL/key limits fit, whereas distinct values
differing only beyond those limits copy to identical strings. Key truncation can
split UTF-8. Decoded `\u0000` shortens URL, key, field names and values at their
first NUL. None of those results establishes that the resulting URL is usable.

Required-member lookup is ASCII case-insensitive and selects the first duplicate.
An invalid first `url` blocks a later valid one; a first non-object `fields`
produces the empty fields string even if a later duplicate is an object.
Missing/non-object fields and an injected `cJSON_Print` allocation failure all
leave that empty string while presign reports success. The upload's later parse
rejects it. Within a valid fields object, duplicate string members retain their
order, non-string members are skipped, and a supplied `file` name is not filtered.
Quotes and CRLF survive into the projected form bytes without escaping.

All groups passed address/undefined-behavior sanitizers with warnings treated as
errors. The fixture omits transport, WAV streaming, PSRAM allocation and physical
storage; it deliberately does not execute the uninitialized empty-response path
discussed below. For the local adapter, issue one short ASCII upload-ticket field
with a unique name, keep the job key within 255 bytes, and validate issued fields
before returning them. Wire JSON size alone is not a sufficient fields bound.

The [Standard comparison](standard-model-comparison.md#presign-copying-and-member-lookup-also-match)
confirms the same copying, formatted-print and first-member lookup branches in
ten function pairs. That static comparison adds no second host-fixture run or
physical malformed-response test.

### Multipart construction and streaming

Presign accepts string-valued `url` and `key`, copies them with the limits below,
and serializes `fields` only when it is an object. It does not require nonempty
URL/key strings or consult a `success` flag before returning its successful parse
result. Missing/non-object fields leave an empty string that fails the upload
stage's subsequent JSON parse. A later transport failure is different from
rejecting an unusable presign response early.

Upload `0x42026b9c` walks the object's children in order. String-valued members
become form parts; numbers, booleans, null and nested containers are skipped.
Duplicate string members become duplicate multipart parts. Names and values are
inserted with `%s` directly, with no quote/CRLF escaping or reserved-name check.
For a local ticket, emit one uniquely named string field with a simple name and
value. Avoid a supplied `file` field, which would coexist with the real WAV part.
The top-level key used by finalize and a `fields.key` value used by storage are
not compared by this upload routine; keep issued keys consistent and short.

The framing allocation is **calculated total body bytes minus WAV bytes plus
one**, requested from `MALLOC_CAP_SPIRAM` (`0x400`). It holds the form prefix and
closing boundary, while audio remains in the original shared buffer. This does
not eliminate the separate JSON, HTTP and TLS allocations. Each formatted append
checks its `snprintf` result against remaining capacity and fails before network
transmission on a detected framing overflow.

The sender opens one fixed-length POST, then writes:

1. The constructed form fields and file headers.
2. The existing WAV in chunks of at most **4,096 bytes**.
3. The closing multipart boundary.

The file part is named `file`, has filename `recording.wav`, and uses
`Content-Type: audio/wav`. Every application write requires the full requested
count; a short/negative result closes and cleans up rather than resuming at a new
offset. SDK write `0x4206d930` can internally combine several positive transport
writes, so application chunks are not TCP packet boundaries.

If a later transport write returns zero or a negative value, the SDK returns
**that last result**, discarding earlier positive progress from its return value.
Thus a zero/error does not establish that no bytes left the client. The application
increments its WAV offset only after a complete 4,096-byte-or-smaller chunk;
its failure log can omit a transmitted prefix of the failing chunk. It does not
resume that prefix or proceed to the footer/response path after the failure.

The configuration sets **120,000 ms** network timeout and an **8,192-byte transmit
buffer**; its receive buffer defaults to 512 bytes, as traced in the
[client configuration audit](cloud-protocol.md#http-buffers-trust-precedence-and-url-scheme).
The transmit field is identified against the
[SDK configuration layout](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/include/esp_http_client.h),
not the application's 4 KiB audio chunk. The transport timeout is passed again on
each underlying write; it is not a two-minute deadline for the entire upload.
The multipart routine has no local elapsed-time check in its audio loop.

Only **after the footer is written** does it register the client with the abort
manager at `0x420271f3`, immediately before fetching response headers. The audio
write loop does not query the processing-cancel flag. Cancellation during body
transmission therefore does not have this client's abort registration available,
and already transmitted audio cannot be recalled. The physical cancellation test
remains deferred; other network failures and outer-task lifetime are separate.

### Host-checked write failures and framing length

Eight host groups use the unchanged `esp_http_client_write` function from
[ESP-IDF 5.4.1](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_http_client/esp_http_client.c),
with scripted transport returns, a synthetic byte sink and virtual elapsed time.
The application prefix/audio/footer sequence is reconstructed from Large's
instructions, not executed Xtensa firmware. Nineteen bounded GNU ranges cover
691 instructions, with bytes checked against the pinned app and complete range
coverage, including the SDK writer and application checks/cleanup branches.

| Host case | Result |
| --- | --- |
| Transport writes 1,024 + 1,024 + 2,048 bytes for one 4,096-byte call | SDK returns 4,096, advances offsets without duplication and reapplies 120,000 ms on every transport call; three simulated 90-second waits total 270 seconds |
| Transport accepts 1,024 bytes, then returns zero | SDK returns zero, despite 1,024 bytes in the synthetic sink |
| Transport accepts 1,024 bytes, then returns −1 | SDK returns −1 with the same earlier progress |
| Client state below request-headers-complete | Returns −1 without calling transport |
| Empty fields or one ticket, at shortest/longest generated boundary lengths | Calculated framing allocation and full body length equal the constructed bytes |
| Successful 9,000-byte synthetic audio body | WAV writes are 4,096 + 4,096 + 808 bytes; footer follows; only then are abort registration and response-header fetching reached |
| Second WAV chunk accepts 1,024 bytes, then fails | Application offset remains 4,096 while sink contains 5,120 audio bytes; no footer or response-header fetch |
| Footer accepts three bytes, then returns zero | All 9,000 audio bytes are already in the sink, but the multipart body is incomplete and the application fails before response handling |

For boundary length `B`, audio length `W` and emitted string fields with name/value
byte lengths `Nᵢ` / `Vᵢ`, the recovered body calculation is:

```text
field_bytes = Σ(B + Nᵢ + Vᵢ + 49)
body_bytes = field_bytes + W + 2B + 110
framing_allocation = body_bytes − W + 1
```

The allocation's extra byte is for termination and is not sent. Generated
boundaries are `----FormBoundary` plus a decimal unsigned 32-bit value; multipart
encoding is byte-counted, not character-counted. This calculation does not make
names/values escaped or validate an incoming presign response.

All eight groups passed with compiler warnings treated as errors and
address/undefined-behavior sanitizers. Source SHA-256 is
`7aabd415f3a39675e59f591919b9e88e31213e548b010cb0809a888d2b0ceef2`;
the extracted writer body is
`a2eb7832c2bff78b0a8e09cf9ae300d5d58d8574a58fede8eee448306c721453`.
The sink proves only scripted transport acceptance, not delivery to a real peer.
No socket/TLS traffic, recordings, real delay, allocation fault or physical
upload failure was induced. The reconstructed sender was Large-derived. A later
[complete multipart and SDK-writer comparison](standard-model-comparison.md#complete-multipart-upload-paths-also-match)
confirms matching application branches and writer behavior in Standard; it does
not add physical fault tests or prove every external helper equivalent.

For the emulator, validate and retain a complete upload under its issued job key,
start generation on finalize, and expire uploads that never finalize. Receipt of
the WAV alone does not prove that the user completed the whole workflow or that
the frame will accept a result. These static and host checks complement the
earlier successful local uploads, which remain the physical positive controls.

### Upload acknowledgment must have an empty body

The live fixture first returned HTTP 200 with a 15-byte JSON acknowledgment after
successfully storing the WAV. The frame logged `Failed to fetch headers after
streaming upload: ERROR` and did not call finalize.

GNU disassembly identifies the cause: `0x420271f8` calls the header reader at
`0x4206d890`, `0x420271fb` saves the low return word, and `0x42027200` proceeds only
when it is zero. Nonzero results go through `esp_err_to_name` at `0x42027248`.
However, the SDK's
[`esp_http_client_fetch_headers`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/include/esp_http_client.h)
returns a body length or a negative error, not an `esp_err_t` success code.
The HTTP status getter at `0x42027276` and 200–299 comparison at `0x420272b0`
come afterward. Thus an ordinary positive response length is misclassified as
failure. The low-word-only comparison has an oversized-length exception covered
by the host cases below; it is not a sound response-length validator.

For the local upload sink use HTTP 200 with `Content-Length: 0` and no body.
The follow-up physical recording accepted exactly that response and reached
finalize, confirming the remedy on this build.
This is specific to the multipart upload acknowledgment: presign/finalize JSON
still needs a **positive** explicit length. Missing/chunked length can also yield
zero in the SDK, but those variants have not been validated on this frame and
are unnecessary for the simple empty acknowledgment.

This corrects the earlier claim that any 2xx response suffices. The first Ghidra
export truncated the upload function before this check; live validation exposed
the missing condition.

### Upload acknowledgment parser and early-success boundaries

Twenty-four isolated cases now exercise the original SDK header reader and HTTP
parser, selected unchanged callbacks, and the recovered uploader's immediate
return/status branch. Five complete SDK bodies also match across both apps:
header fetching, headers-complete, body caching, message-begin and message-end.
The complete multipart application comparison already covers the caller.

| Response supplied by the host fixture | Immediate upload result |
| --- | --- |
| Explicit zero length, status 200, 201, 202, 204 or 299 | Success |
| Explicit zero length, status 199, 300, 403 or 500 | Failure, with no redirect/retry in this branch |
| Status 200 and the complete 15-byte JSON acknowledgment | Return 15 as an error before checking HTTP status |
| Status 200, chunked headers, body in a later scripted read | Success after headers; body remains unread |
| Status 200, a chunk already cached, no terminating chunk | Success while HTTP completion is false; cached body is discarded during cleanup |
| Status 200, close-delimited body | Success without waiting for the remaining body or FIN |
| Status 200, invalid chunk-size text in the same read as complete headers | Success despite the parser's recorded chunk error |
| Separate `100 Continue`, then final `200` in a later read | Treat the interim 100 as the response and fail without reading the 200 |
| `100 Continue` and final `200` together in one read | Parse through to the 200 and succeed |

These results distinguish **the application's acceptance branch** from a valid,
fully consumed HTTP response. Header fetching stops when the client state says
headers are complete; it does not check the parser's returned byte count or
error before returning the stored length. The uploader does not read or validate
an acknowledgment body afterward. Test-read boundaries represent possible
transport delivery, not a prediction of actual TCP segmentation or TLS records.

The application keeps only the low 32 bits of the SDK's 64-bit length. An isolated
header declaring 4,294,967,296 bytes therefore passes the zero-word check; the
same header plus one byte returns error one. Neither fixture sends that body.
This is an additional acceptance defect, not a usable upload-response design.

There is also a narrow cancellation distinction: this return branch reads the
abort flag only when the narrowed header result is nonzero. A supplied abort
flag plus zero-length 2xx still returns success here; a nonzero result plus the
flag becomes INVALID_STATE and clears it. The fixture does not execute the
shared-client registration/unregistration helpers, concurrent cancellation or
the outer worker's later checks, so it does not establish that a complete
cancelled voice job will continue.

For a local sink, finish validating/storing the complete multipart WAV before
returning one final **200 with `Content-Length: 0`**. Avoid an acknowledgment body,
chunked/close-delimited framing and unsolicited informational responses on this
route. A 202 is accepted as an upload status, but it adds no stock job-polling
semantics. Generation remains a separate finalize operation. The earlier Large
200/empty and Standard 204 observations are the physical positive controls;
the new variants are host-only. See [validation scope](validation-2026-10-22.md#upload-acknowledgment-framing-and-early-success-c05c08).

### HTTP response-cache growth can lose an allocation

An additional SDK audit finds a specific low-memory failure in body bytes cached
while fetching headers. `http_on_body` assigns `realloc` directly to
`orig_raw_data`. If growth fails after an earlier chunk was cached, the old
allocation remains valid through `raw_data`, but the owning `orig_raw_data`
becomes null. The callback returns an error without advancing its byte counters.
The cache cleanup helper frees only a non-null `orig_raw_data`, so it neither
frees that block nor clears the remaining cache fields on this path.

The complete cache cleanup and client cleanup bodies match on both builds:
`0x4206ce3c` → `0x4206c434` and `0x4206dbd8` → `0x4206d1d0`.
The latter calls cache cleanup, then frees the response buffer structure; it has
no alternate free of `raw_data`. The body callback and header-fetch comparison
above establish the other consequential branches. External allocator/transport
bodies are not recursively compared by this pass.

Twelve isolated cases use the pinned SDK functions and HTTP parser with a tracked
allocator and scripted response bytes. Failed second/third allocations in one
three-chunk response leave **3/6 bytes allocated after cache cleanup**, respectively.
Those small sizes make ownership observable; they do not estimate a device leak's
size or frequency. Reading the surviving cached prefix does not restore ownership.
Normal partial/full reads and repeated cleanup free the original once.

For chunked responses, header fetch still returns zero despite `HPE_CB_body`,
and the reconstructed upload acceptance branch reports success. An initial
allocation failure also produces that mismatch, but has no prior block to leak.
An empty explicit-length acknowledgment allocates no body cache and avoids this
path. Direct body reads into a caller's output buffer also bypass this allocation;
that does not remove other memory failures in the HTTP/TLS pipeline.

This is a static/host finding, **not a reproduced frame leak or an explanation
of the earlier live TLS allocation failure**. The fixture measures retained
allocations, then explicitly reclaims them outside SDK cleanup so sanitizer
runs can finish cleanly. It does not execute the full client teardown or the
firmware allocator. See [validation](validation-2026-10-22.md#response-cache-allocation-and-cleanup-e01e02).

### JSON request allocation failures can lose ownership or fields

Presign creates an object and two string children (`device_key`, `user_id`);
finalize creates an object and four (`device_key`, `user_id`, `key`,
`orientation`). Both call every string constructor before checking whether any
creation failed. At this point none of the children belongs to the object.
The error branch deletes only the root and returns the no-memory error. Any
successfully created unattached children therefore remain allocated.

If creation succeeds, both callers invoke `cJSON_AddItemToObject` for each field
without checking its return. The compiled helper (`0x42039690` → `0x420387c8`)
duplicates the field name before attaching the child. A failed name allocation
returns false without taking ownership or freeing the child. The caller still
serializes the object, so a transient failure can produce a request missing an
intended field while also leaving its child/value allocated. A later print failure
returns no-memory, but does not recover a child that was never attached.

These ownership rules agree with the
[pinned cJSON implementation](https://github.com/DaveGamble/cJSON/blob/acc76239bee01d8e9c858ae2cab296704e52d916/cJSON.c).
Seven compiled Large helpers were checked over ten GNU ranges and 145
byte-matched instructions; their Standard counterparts match normalized operations
and 26 branches. The allocator hooks, constructors, string duplication, ordinary
object attachment and recursive deletion were distinguished from application
cleanup. The two complete application callers were compared separately.

A host fixture used the real pinned cJSON source, synthetic request values,
tracked allocator hooks and reconstructed caller order. It swept each allocation
position on the successful path, first failing only that allocation and then
failing every allocation from that point onward:

| Request | Host cases including successful baseline | Result of transient field-name allocation failures |
| --- | --- | --- |
| Two-field presign | 19 | Either intended field can be omitted; its child/value remain allocated |
| Four-field finalize | 31 | Any one of the four intended fields can be omitted with the same ownership loss |

All **50 cases** passed their expected-outcome checks with compiler warnings
treated as errors and address/undefined-behavior sanitizers. The two successful
baselines released everything. Creation failures demonstrated unattached children;
six transient attachment failures serialized incomplete objects. Failures confined
to printing after successful attachment released the object and its children.
The fixture measured orphaned allocations before freeing them in test teardown;
that teardown is not present in the firmware error path.

These are conditional fault paths, not a leak demonstrated during ordinary voice
use. Host pointer sizes and custom hooks do not measure ESP32 heap consumption,
fragmentation or failure frequency. This does not establish the cause of the
earlier physical TLS allocation errors. A firmware fix should free untransferred
children on every error and check attachment results. The backend should validate
its required request fields before side effects, rather than assuming the stock
client always emits every intended member.

### JSON request writes can proceed after zero

Presign and finalize check only whether `esp_http_client_write` returned a
negative value. Large call/branch pairs are `0x4202688f` / `0x42026892` and
`0x420275b7` / `0x420275ba`; Standard equivalents are `0x420252df` /
`0x420252e2` and `0x4202600b` / `0x4202600e`. A zero result goes on to abort
registration and response-header fetching. These JSON paths do not compare
written bytes with their declared request-body length or retry an unsent suffix.

The [SDK writer behavior](#host-checked-write-failures-and-framing-length)
makes this consequential: after accepting a prefix, a later transport zero is
returned as zero, without the earlier byte count. The client can therefore reach
header fetching with an empty or incomplete request body. This is not evidence
that a server parsed the request, started generation or received any particular
number of bytes. A server waiting for the remaining body and a client waiting for
response headers can instead end in a timeout.

Four isolated SDK/reconstructed-caller cases were run at both configured timeouts
(30,000 and 600,000 ms), for **eight checks**:

| Scripted transport result for a 14-byte synthetic JSON body | Caller result |
| --- | --- |
| Zero immediately | Zero bytes accepted; proceeds to header-fetch branch |
| Five bytes, then zero | Five bytes accepted; proceeds to header-fetch branch |
| Five bytes, then −1 | Five bytes accepted; closes without header fetch |
| Five bytes, then nine | Full body accepted; proceeds normally |

All passed with compiler warnings treated as errors and address/undefined-behavior
sanitizers. The fixture uses the unchanged, previously pinned SDK writer and
reconstructs only the caller's write-result branch. It performs no HTTP-header
exchange, socket/TLS operation, real wait or device test. A backend must validate
the complete JSON request before starting work; custom firmware should require
the full request count and use an explicit operation deadline.

## Finalize

`0x42027380` sends:

```http
POST /api/v1/upload/audio/finalize
Content-Type: application/json
```

```json
{
  "device_key": "<device_key>",
  "user_id": "<user_id>",
  "key": "job-123/recording.wav",
  "orientation": "landscape"
}
```

This example matches the observed frame request. Portrait orientation was not
exercised in the physical tests above.

The upload worker takes this [orientation sample](hardware-and-layout.md#accelerometer-target-and-orientation-semantics)
after the WAV upload, immediately before finalize. It is not fixed at recording
start. The two-way classifier defaults to portrait on a sensor error and cannot
distinguish upside-down mounting. Persist the received value with the voice job
and use it in the model-specific render/cache identity.

A stock-compatible result is HTTP 200 with a ready image URL:

```json
{
  "status": "completed",
  "presigned_url": "https://frame.example/panel/job-123.bin"
}
```

The parser copies `status` if supplied, otherwise defaults to `completed`. It
does not implement a job-status polling protocol. The image URL is required for
this successful path; `202` and a job ID do not queue work on the frame.
Other server fields such as `upload_public_id` do not establish firmware-level
job identity or display confirmation.

More precisely, successful parsing requires a **string-valued** `presigned_url`,
not a nonempty or syntactically valid URL. The parser ignores `success` and
`message`. An empty URL or `success:false` can still reach its success return;
that does not make the subsequent download usable. The response fixture below
separates these parser rules from actual delivery.

The upload worker at `0x42010108` does not inspect the copied status string.
After successful finalize and a cancellation check, it copies only the URL into
the shared result and signals success. GNU instructions at `0x42010428`–
`0x4201044d` confirm that copy/result assignment. A response containing a valid
URL and `status: "processing"` therefore does not implement a waiting state in
this recovered path. This is static evidence; that response variant has not been
sent to the frame. Return a URL only when its complete panel asset is ready.

The Standard live response demonstrated that omission: it contained `success`,
`message`, null `upload_public_id` and `presigned_url`, with no `status`, and the
frame downloaded/rendered the result. Neither its presign nor finalize response
included a transcript or final generation prompt.

The shown two-field response was accepted on the physical frame with an explicit
110-byte body and an ordinary local HTTPS asset URL. No AWS query parameters or
S3 service were needed. Firmware log phrases such as “AI processing” and “raw AWS
presigned URL” describe its fixed workflow labels, not services used by this test.

| Stage | Limit / requirement |
| --- | --- |
| Presign HTTP timeout | 30,000 ms |
| Multipart-upload HTTP timeout | 120,000 ms; not a whole-upload deadline |
| Finalize HTTP timeout | 600,000 ms |
| Outer upload task wait | Approximately 15 minutes |
| Presign/finalize JSON body read | At most 4,095 bytes |
| Copied URL | At most 1,535 bytes plus NUL |
| Copied object key | At most 255 bytes plus NUL |
| Copied form fields | At most 4,095 bytes plus NUL **after formatted reserialization** |
| Body framing | Explicit positive `Content-Length`; avoid chunked JSON |

Hold finalize until the panel asset is ready. Align reverse-proxy timeouts with
the long request. Persist the job and deduplicate finalize calls so a retry does
not pay for another generation or create duplicate library entries.

### Finalize response fields and host parser checks

The output record has a 1,536-byte URL at offset `0x000`, a 64-byte status string
at `0x600`, and a 32-bit header-time measurement at `0x640`, totaling 1,604 bytes.
Copies take at most 1,535 and 63 bytes, then terminate. Missing or non-string
status becomes `completed`; string status is copied without checking its meaning.

Eight host groups use the pinned cJSON 1.7.18 source and reconstructed successful
HTTP-200 parsing/copying instructions:

| Input group | Result |
| --- | --- |
| Missing/non-string URL, non-object root or malformed JSON | Rejects; the result record remains unchanged |
| Empty URL with `success:false` | Parser succeeds with empty URL and default status |
| Missing, null or numeric status | Defaults to `completed` |
| `status:"processing"` with a URL; processing/job ID without a URL | First parses successfully, second rejects; neither creates a queued-job protocol |
| Case-varied duplicate fields | First case-insensitive match wins; invalid first URL prevents using a later valid duplicate |
| Escaped NUL within URL/status | C-string copies retain only the prefix before the decoded NUL |
| Overlong URL/status | Silently truncates to 1,535/63 bytes |
| Complete JSON followed by extra text | Accepts the complete prefix |

All groups passed with compiler warnings treated as errors and
address/undefined-behavior sanitizers. cJSON source/header SHA-256 values are
`75c51de8fa40ac9d7a99319c6330719bd692eb81c0a869265f3d4c682533f9b9` and
`0578cc29132912edbc88f83207a8fc76e5db3db0605497e909a9384ef3cc474b`.
These are host checks of a reconstruction, not execution of Xtensa firmware,
HTTP-status handling, allocation faults or physical malformed responses.
The [complete two-build application comparison](standard-model-comparison.md#presign-and-finalize-application-paths-also-match)
supports the same field/copy branches on Standard; it does not count these groups
again as a second fixture run.

### Body completeness and timeout scope

The 4,095-byte limit is a **single read capacity**, not a check that the declared
response fits or was completely received. Large presign `0x420266d8` and finalize
`0x42027380` call `0x4206d6a4` once when the fetched length is positive, then parse
the returned prefix. Finalize's positivity test uses the **signed low 32 bits**
of the SDK's 64-bit return; oversized-length examples are covered below.
Neither compares received bytes with the declared length
or calls the SDK's completeness predicate before parsing. There is no application
loop to finish an oversized JSON response.

The reader itself can perform several transport reads within that call. Its
GNU-checked timeout/error branches return already received bytes when available,
including bytes cached while fetching headers. A timeout with no bytes returns
`-0x7007`. Thus the final outcome depends on whether the returned prefix happens
to contain a complete JSON value, not simply on whether the HTTP body finished.
The permissive cJSON parser also accepts a complete value followed by other input.

Twelve host cases used unmodified selected ESP-IDF 5.4.1 reader/header functions,
its real HTTP parser and the pinned cJSON source, with a scripted transport:

| Host case | Result |
| --- | --- |
| Exact or split complete response | JSON accepted; HTTP body complete |
| Timeout before any body bytes | Negative EAGAIN result; no JSON accepted |
| Complete JSON prefix, then timeout/FIN/error before declared length | Positive prefix returned; JSON accepted despite incomplete HTTP body |
| Incomplete JSON prefix, then timeout | Positive prefix returned; JSON rejected |
| 5,000-byte response with complete JSON at the start | Only 4,095 bytes returned; JSON accepted while HTTP body remains incomplete |
| 5,000-byte object whose required field/end lies past the read cap | Prefix rejected |
| Several successful reads, each below the configured timeout | Aggregate simulated time exceeded that timeout |
| Empty finalize response | Empty string rejected |

The 600,000 ms setting is passed anew to individual transport reads; it is not
an absolute finalize deadline. Header reception and body reception both use it.
The host case simulated 599 seconds for headers and for each of two body reads,
totalling 1,797 seconds without a real wait. This demonstrates the SDK boundary,
**not** a physical frame surviving that delay: the separate 15-minute outer wait,
task lifetime and watchdog behavior are outside the fixture. The processing-time
value copied into the finalize result is sampled after headers and before the
body read, so it excludes a slow response body.

Presign has an additional static edge: it terminates its local response buffer
only after a positive read. A skipped/zero read followed by HTTP 200 reaches
`cJSON_Parse` without that initialization; the earlier `memset` clears only the
HTTP configuration immediately before the response buffer. Finalize explicitly
terminates even its zero-length result. The presign path is an untested
uninitialized-buffer hazard, not a reproduced crash or reliable empty-response
fallback; the host fixture deliberately does not execute it.

For an emulator, construct the small complete JSON first, set its exact positive
length, and send headers/body together when ready. Do not drip a JSON response
as a progress mechanism. Keep transcripts and generation metadata in the backend
job instead of expanding this response. Body reception occurs after unregistering
the active HTTP client, so a long body also extends the existing socket-cancel
gap. A future firmware fix needs bounded accumulation, explicit completion checks,
an absolute operation deadline and cancellation covering the entire request.

The [validation record](validation-2026-10-22.md#voice-response-completeness-and-timeouts-c05c07c08)
records source hashes and fixture limits. No response fault was sent to a frame.

The [panel-download trace](image-downloads.md) maps the separate image stage:
up to three attempts reuse the same URL and restart at byte zero. There is no
ticket renewal through another finalize call in that retry loop. The downloader
also accepts some bodies without a positive fetched length, unlike voice JSON.

### Finalize HTTP status, framing and failure ordering

Thirty-one additional host cases combine the matching SDK HTTP parser, header
fetch/body reader and cJSON with a bounded reconstruction of the finalize
response branch. They extend the separate JSON-field and body-reader fixtures
above. No variant was sent to a frame.

| Response / condition | Host result |
| --- | --- |
| Ready URL JSON with HTTP 200 | Accepted |
| Same ready URL with 201, 202, 400, 401, 403, 404, 429, 500 or 503 | Body read, then rejected without parsing the URL |
| Empty HTTP 200 or 204 | Rejected; neither supplies a usable finalize result |
| HTTP 200 with URL plus `status:"failed"`, `success:false`, or `status:"processing"` | Accepted; those fields do not prevent the existing worker's URL handoff |
| HTTP 202 with processing/job ID | Rejected; no queued-job behavior |
| Chunked JSON, including a complete body cached in the header read | Rejected; fetched length zero skips the body reader, so cached JSON is discarded |
| Close-delimited JSON already cached | Rejected through the same skipped-read path; later FIN is not read |
| 100 Continue or 103 Early Hints in a separate transport read | Rejected at that status; final 200 is never read |
| The same informational response and final 200 together in one read | Final status/body accepted |
| HTTP 503 with a slow positive-length body | Body reception delays rejection; `Retry-After: 1` does not produce a retry |

The status is sampled at `0x4202767d`–`0x4202768a`, but the body-read call at
`0x420276bb` precedes the HTTP-200 decision at `0x420276dc`–`0x420276eb`.
The slow-503 case used two virtual 599-second body reads: 1,198 seconds elapsed
before failure, with no real wait. This establishes ordering and the SDK's
per-read timeout, not a physical worker surviving beyond its separate 15-minute
outer wait. Error responses should have a small, promptly completed body.
There is no presign/upload/finalize retry loop in the recovered upload worker;
`Retry-After` does not schedule another finalize. Keep generation retries and job
retention in the backend. Image retries are a separate later stage.

The return-width boundary also matters. `0x420275fb` retains only the low word
of the SDK's 64-bit fetched length. Declared lengths of 2^31 and 2^32 skip the
read even with a complete JSON prefix cached; 2^32+1 narrows to one, takes the
reader and accepts a complete prefix followed by a timeout despite an incomplete
HTTP body. These cases send only short headers and JSON in the host fixture,
not gigabytes. Use the exact small JSON length; this is not streaming support.

Only a negative narrowed header result checks the shared HTTP abort flag in
this branch. With that flag set, header timeout returns `0x103` and clears it;
a valid response still parses, while a later body timeout returns generic `-1`
without another abort read. The upload worker's separate processing-cancel
check still follows successful finalize. These are sequential branch fixtures,
not a physical cancellation or race test.

For the emulator, return **one final HTTP 200, a small complete JSON object and
its exact positive Content-Length** when the panel asset is ready. Disable
informational responses on this route and avoid chunked/close-delimited JSON.
Do not use a URL alongside `failed` or `processing` as a state signal. The
[validation record](validation-2026-10-22.md#finalize-http-status-and-framing-c07c08)
lists the reconstruction boundaries and hashes.

## Cancellation and scheduled-content races

The following is a deeper **static** trace of Large 0.2.29, not a completed
physical cancellation test. Two task entries absent from the earlier Ghidra
function list were verified against GNU disassembly and the task-create literals:
`0x42010108` is the presign/upload/finalize worker; `0x420104a8` is the separate
image-download worker. `0x42011adc` orchestrates them and the renderer.

### Gesture and cancellation flag

The button monitor `0x4200f770` runs in recording mode `1` or processing mode `2`.
It ignores additional press edges less than 100 ms apart and groups edges within
800 ms of the first. The third qualifying edge immediately triggers cancellation;
single/double taps do not take that processing-mode branch. These are recovered
thresholds, not measured physical gesture tolerances.

In processing mode it sets the byte at `0x3fca6b19` and calls `0x42025ea8`, the
HTTP-abort manager. The main loop switches to that mode after the recording's
completion indication. For a controlled test, wait until the fixture has received
finalize before cueing the three taps; tapping during the preceding transition
would test a different boundary.

### Which stages can abort their socket

| Stage | Recovered cancellation behavior |
| --- | --- |
| Presign | Registers its client after writing the request, around the response-header wait; unregisters before reading JSON |
| Multipart WAV upload | Registers around acknowledgment-header reading after sending the body; the worker also checks the processing flag when the routine returns, before invoking finalize |
| Finalize | Same registration window as presign: header wait covered; connection setup, request write and subsequent JSON read are outside that window |
| Panel download | Registers after connection opening and remains registered through headers/body; abort flag can produce invalid-state (`0x103`) and end download retries |
| Before rendering | The main flow checks the processing flag after a successful download and skips rendering when set |
| Rendering already started | No processing-flag check was found in the recovered render worker; the orchestration waits for its completion semaphore |

For finalize, the GNU-verified sequence at `0x420275f3` / `0x420275f8` /
`0x420275fd` is register → fetch headers → unregister. Only a negative header
result plus the abort-manager flag takes its explicit aborted return. The upload
worker independently checks the processing flag after each successful stage, so
a cancel arriving as a successful response completes can still prevent the next
stage. It has no retry loop around presign, upload or finalize; the download
worker separately allows up to three attempts for ordinary failures.

The earlier decompiler export omitted the upload routine's acknowledgment tail.
A raw direct-call scan, cross-checked with GNU instructions, found the additional
register/fetch/unregister sequence at `0x420271f3` / `0x420271f8` / `0x420271fd`.
Its nonzero header-result branch checks the abort flag before classifying the
result as an ordinary error. The gap is during WAV transmission, not the entire
upload operation. This is also why the documented response-length bug must be
interpreted alongside cancellation state.

The HTTP manager has **one global client slot**, at `0x3fcabcd0`. Registering
another client logs that it is overwriting an active one; unregistering clears
the slot without comparing an owner/job ID. Its mutex protects slot access, not
an entire workflow. This establishes an ownership limitation, not a reproduced
collision. An emulator should avoid introducing concurrent content producers.

`0x42025ea8` calls the SDK cancellation primitive at `0x4206db7c`, which matches
[ESP-IDF 5.4.1's `esp_http_client_cancel_request`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c).
It acts on the transport; it sends no application-level cancellation message.
The wrapper marks its abort flag even when the SDK call fails, and can return
success when no client is registered. Neither that return nor an LED pattern
proves that the backend stopped work.

A server-observed disconnect also cannot distinguish intentional cancellation
from lost Wi-Fi or a client timeout. Keep durable job state and a bounded lifetime;
make finalize idempotent and retain a completed original even if delivery loses
its connection. Explicit cancel/result messages require a firmware extension.
Receiving the WAV alone is not proof the device will call finalize.

### Active-client ownership and failed unregistration

The cancellation manager is a 24-byte record at `0x3fcabcd0`: client pointer at
`+0`, mutex at `+4`, HTTP-aborted byte at `+8`, borrowed operation-label pointer
at `+0xc`, and 64-bit start time at `+0x10`. The label and timestamp are diagnostics;
they are not an ownership token. The processing-gesture byte at `0x3fca6b19` is
separate.

| Helper | Successful locked operation | Missing mutex / ten-tick lock timeout |
| --- | --- | --- |
| Register `0x420233b0` | Replace current client/label/time and clear HTTP-aborted byte | Return `-1` / `0x107`; preserve record |
| Unregister `0x42023464` | Clear client/label/time, preserve HTTP-aborted byte | Return `-1` / `0x107`; preserve record |
| Read aborted `0x42025fc4` | Return HTTP-aborted byte | Return false in either case |
| Reset aborted `0x42026014` | Clear HTTP-aborted byte | Return `-1` / `0x107`; preserve record |

Ten ticks is approximately 100 ms in this build. Initializer `0x42025e34` creates
the mutex if absent; calling it again with an existing mutex does not reset a
stale client or abort byte.

A raw direct-call scan and GNU checks identify **four register sites, seven
unregister sites, five aborted reads and five resets**. They belong to the common
image downloader, voice presign, multipart acknowledgment and finalize. All
register/unregister/reset results are discarded. Thus registration failure does
not stop the request, and failed unregister does not prevent later client cleanup.
No exact function-pointer words for those four helpers were found in the image;
this bounds the reference search rather than excluding computed indirect calls.

The common downloader has two additional details:

- After body reception it unregisters at `0x4202648f`, then later unregisters
  again in the common cleanup epilogue at `0x420266b9`. Header-error branches also
  unregister before reaching that epilogue. There is no expected-client argument.
- A failed HTTP open at `0x420261ac` reaches the same unregister/close/cleanup
  epilogue even though this invocation never reached registration at `0x420261df`.

These establish several **conditional interleavings**, not reproduced failures:

| Ordering | Consequence permitted by the recovered code |
| --- | --- |
| A registers, B replaces it, A unregisters | A clears B's cancellation target |
| A unregisters after receiving its image; B registers before A's final epilogue | A's second unregister clears B |
| A cannot open its connection while B is registered | A's common epilogue can clear B despite never registering A |
| A's unregister times out, then A reaches client cleanup | The slot can retain a pointer to freed HTTP-client storage |
| Another registration/reset occurs between an aborted read and subsequent handling | Shared cancellation classification can change across requests |

In the fourth case, a later abort can pass that stale pointer into the SDK. Also,
the abort wrapper holds the slot mutex while calling SDK cancellation, whereas a
worker can proceed with freeing its client after its unregister wait fails. The
mutex therefore does not itself establish safe HTTP-client lifetime. Actual
scheduler ordering, held-lock duration, allocator reuse and resulting memory or
socket effects remain untested. These paths do not explain the earlier TLS-memory
failure without additional evidence.

Unregister deliberately preserves the HTTP-aborted byte so the caller can inspect
it afterward; a successful new registration clears it. The getter's false-on-lock-
failure behavior can instead classify a cancellation-related read error as an
ordinary error. For image download that classification affects retry handling;
the separate processing flag can still stop the outer worker. A log label or
`0x103` result should not be treated as a reliable per-job cancellation receipt.

For a firmware fork, registration and cleanup need an expected client/job identity
and a lifetime handshake: do not free a client while cancellation may use it, and
do not clear a different client's slot. Keep abort/result state with its job.
For stock-backend operation, serialize content producers where possible and keep
job retention/idempotency independent of connection or LED state. This backend
discipline does not repair the firmware's internal ownership paths.
The [Standard follow-up](standard-model-comparison.md#cancellation-ownership-and-download-timeouts-also-match)
confirms the same slot helper behavior and 21 direct caller sites in 0.2.28.

### SDK cancellation state and response bookkeeping

Large's SDK primitive `0x4206db7c` rejects a null client or state below
`CONNECTED` (numeric 2). It calls transport close through `0x420e6b44`, then
connection helper `0x4206da20`. That sequence has a narrower meaning than the
SDK header's description of closing and opening a socket:

- Cancellation calls the transport directly. It does not first call ordinary
  HTTP close `0x4206d9d8`, which sets the client state back to `INIT` and emits
  disconnect events.
- The connection helper first invokes prepare `0x4206d4e8`: it clears replay and
  first-line flags, zeros processed-body count, frees cached `Location` and
  `WWW-Authenticate` response strings, and reinitializes the HTTP parser.
- Prepare does not lower the connection state. If that state remains at least 2,
  the helper returns without opening a new socket. If another operation has
  lowered it to `INIT`, the connect branch can run. Neither branch here sends
  the HTTP request headers/body again.
- On accepted completion, cancellation copies the stored 64-bit content length
  into the processed-body count. That is bookkeeping, not newly received data.
  The length-delimited reader's loop can consequently consider its target count
  reached. Chunked completion has its separate flag.

Ten isolated cases using the unmodified pinned SDK functions confirm the
unchanged-state path, close failure and synthetic state-change/reconnect paths.
A state change injected by the fixture is **not a reproduced thread race**.
The fixture also demonstrates that a count-based SDK completeness predicate can
return true after cancellation without another body read, including when both
stored counters are `-1`; incomplete chunked state remains false. These are SDK
state results, not successful finalize parsing or a backend/image acknowledgment.

The frame's abort wrapper `0x42025ea8` holds its global-slot mutex across the SDK
call and sets its abort byte only afterward when a client is present. It logs an
SDK error but still returns zero after a successfully acquired mutex. With no
registered client it also returns zero, without setting that abort byte. The
processing-gesture flag is separate. Its return therefore cannot prove socket
closure, a new connection, worker exit or backend cancellation.

Registration/unregistration use the same slot mutex, but it does not serialize
the HTTP worker's parser/reader accesses against cancellation. Parser-reset and
cached-string changes therefore need a concurrent transport test before claiming
thread-safe cleanup or a particular corruption. No such test ran here. For the
local backend, keep job completion independent of connection lifetime, do not
infer a retry from the SDK cancellation call alone, and retain explicit job
identity/idempotency. The separate
[download-timeout trace](image-downloads.md#voice-download-timeout-and-forced-task-deletion)
now identifies its retained handle, completion ordering and skipped HTTP epilogue;
actual concurrent cleanup still needs validation.

### Timeout and error boundaries still needing validation

The upload and download task-creation results are discarded before waiting on
their completion semaphores. GNU checks at `0x42011d49`–`0x42011d55` and
`0x42011fb2`–`0x42011fbd` show the result register being overwritten with the
semaphore handle. If task creation fails, the normal path still enters the
15-minute upload or five-minute download wait. A timeout log is therefore not
proof that a network request was ever started. Allocation failure was not induced.

The 15-minute outer upload wait does not retain an upload-task handle or perform
the explicit abort/join sequence used for download timeout. Its task context and
status-result pointer refer to the caller's stack. The later
[lifetime trace](#late-upload-workers-retain-caller-stack-pointers) identifies
the worker's reads and writes after that wait can expire; it remains a conditional
static path rather than a reproduced physical crash. Do not use a 15-minute stall
on the physical frame as the first experiment.

The apparent WAV cleanup call (`0x42020294`) does not free or zero the shared
audio allocation, cancel a worker, or wait for it. It is a no-op for the expected
pointer and only logs an unexpected pointer. Getter `0x420201d4` constructs the
44-byte WAV header in the existing recording buffer and returns that buffer.
Thus the outstanding risks are the borrowed task context/result and future
reuse of shared bytes, not a demonstrated heap free of the WAV at this call.

The download timeout requests HTTP abort, waits another 500 ticks (about five
seconds), then can force-delete its retained task. The
[caller/worker lifetime map](image-downloads.md#voice-download-timeout-and-forced-task-deletion)
shows that even success during that grace period returns failure without rendering,
and identifies conditional stale-handle and skipped-cleanup paths. A cancelled download that
returns an error follows the main flow's generic download-failure branch;
the explicit before-render cancellation branch follows successful download.
Consequently an error indication alone is insufficient to classify cancellation.
Physical timing, cleanup, socket closure, stale-result behavior and every retry
boundary remain open under C07/C08/D05.

### Late upload workers retain caller-stack pointers

Large orchestration `0x42011adc` places a **220-byte context** at its stack pointer
plus `0x6f8`; the separate status word is at stack pointer plus `0x7dc`. It gives
that context pointer directly to upload worker `0x42010108`:

| Context offset | Contents and owner |
| --- | --- |
| `0x00` | Device-key text, 65-byte field in caller stack |
| `0x41` | User-ID text, 128-byte field in caller stack |
| `0xc4` / `0xc8` | Existing WAV pointer and byte count |
| `0xcc` / `0xd0` | URL destination `0x3fca64dc`, capacity 1,536; destination is global |
| `0xd4` | Address of global upload-completion semaphore handle at `0x3fca6b2c` |
| `0xd8` | Pointer to the caller's local status word |

The task-creation call passes a null output-handle pointer. GNU tracing follows
the unchanged parameter through creation `0x403858d8`, initialization
`0x40383af4` and stack setup `0x4038298c`; the last stores the parameter pointer
in the new task's initial register frame. It does **not copy the context**.
This matches the parameter handling in the
[IDF 5.4.1 Xtensa port](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/freertos/FreeRTOS-Kernel/portable/xtensa/port.c).

After one nonblocking semaphore drain, the caller waits 90,000 ticks. A timeout
takes `0x42011e5c` through the no-op WAV cleanup to a failure return. There is no
upload join, task deletion or abort request on that path. The main-loop caller
then stops the button monitor and resumes its ordinary loop without inspecting
the returned status. Its “Workflow complete” log also runs after this failure;
that message is not an upload/render acknowledgment.

The worker retains the original context pointer across all three network stages.
Every recovered terminal branch reads the status pointer from context `+0xd8`,
writes success/error/cancel status, reads the semaphore-handle address from
`+0xd4`, gives that semaphore, then deletes itself. The success branch additionally
reads `+0xcc/+0xd0` to copy the image URL. Setting the processing-cancel flag does
not remove these terminal context accesses.

**Static consequence:** if the worker remains alive after the caller returns and
later finishes a stage, it dereferences expired caller-stack storage. A successful
late result can also replace the shared URL and give the unscoped semaphore;
draining it before the next launch cannot reject a completion that arrives after
that drain. Reuse of the same stack region by a later invocation can redirect
these accesses into the later context. No physical stale completion, memory
corruption or particular two-job interleaving has been observed.

This path is consistent with the earlier SDK host result where repeated transport
reads outlasted the outer wait; a per-read timeout does not prove the worker has
ended. A firmware change needs owned context/result storage, an absolute deadline,
and cancellation followed by worker exit before releasing or reusing state.
The stock emulator can bound its own work and leave timeout headroom, but it
cannot repair the caller's lifetime contract with a response field.

### Candidate stale cancellation across two jobs

The button monitor and the workflow have distinct state. Stopping the monitor
at `0x42011218` clears its local event flag at `0x3fca6b01`; it does **not** clear
the processing-cancel byte at `0x3fca6b19`. Starting another monitor also leaves
that byte alone. Recording initialization clears the separate recording-cancel
byte at `0x3fca6b1a`.

The recovered workflow clears processing cancellation in three explicit branches:
an upload invalid-state result with the flag set, a successful upload followed
by cancellation, and a successful download cancelled before rendering. The
generic download-error branch and normal render-completion branch have no such
clear. The processing button monitor remains active until the outer workflow
returns, including during rendering and cache save.

**Inferred candidate:** a cancel that makes download return an error, or arrives
after the last pre-render check, can leave the flag set within the same wake
session. A subsequent recording can then obtain a presign response and immediately
abort before sending its WAV because upload worker `0x42010108` checks that flag
after presign. Its explicit cancellation cleanup would then clear it. This is a
static path hypothesis, not an observed two-job failure; reboot/sleep boundaries
and remaining indirect stores must be accounted for in validation.

For a future firmware change, make cancellation belong to a job and join old
workers before discarding their context or accepting a new owner of the buffer.
Blindly clearing a global flag at the next job's start can let an old worker
continue. For the stock adapter, a presign request without a WAV or finalize is
not proof of user intent to generate; let unused tickets expire.

### Prepared bounded finalize experiment

The later [two-job host model](#bounded-two-job-ownership-and-completion-model)
exercises the recovered ownership consequences without requiring a recording.
It does not replace this deferred physical experiment.

A private fixture accepts one local recording and holds finalize for at most
45 seconds. It observes peer disconnect and otherwise returns intentional
HTTP 409. It never returns an image URL, invokes transcription/generation or
offers firmware. Device access requires explicit arming; the host-only run was
unarmed and changed no frame/network configuration.

Five real TLS host checks using a 3,244-byte synthetic silent WAV passed: bounded
delay, terminal result replay after delay, concurrent-finalize rejection, early
peer disconnect, and terminal replay after disconnect. These validate the test
instrument, not stock-frame cancellation. The listener was stopped afterward;
the owner deferred the recording/three-tap test and requested static research.

Fixture SHA-256:
`4df7e41a2c3d3f2ea61ac62e80d7ca79ae46fee48f683f504010d0c7df55c8c7`.

### Bounded two-job ownership and completion model

A deterministic host model now enumerates **70 client-slot event orders** and
explicit late-completion/cancellation traces. It reconstructs the documented
register, unregister and abort transitions; it does not execute Xtensa, FreeRTOS,
the SDK cancel function, sockets or an allocator. Model object labels represent
client lifetimes, so no freed memory is actually dereferenced.

The enumeration preserves A's register → unregister → free order and B's
register → cancel → unregister → free order. Their 35 possible merges are run
once with successful A unregistration and once with an injected lock timeout.
It assumes overlapping requests are possible, as allowed by the previously
traced unjoined-worker/shared-slot paths. It does not prove those orderings occur
under the frame's scheduler.

| Result when B requests cancellation | All unregistrations succeed | A unregister is forced to time out |
| --- | ---: | ---: |
| Target B | 21 | 25 |
| Target A, still alive | 6 | 9 |
| No registered target | 8 | 0 |
| Target freed A storage | 0 | 1 |

These are counts of a deliberately bounded state space, **not probabilities or
device failure rates**. Example counterexamples are:

- A registers → B registers → A unregisters → B cancels: the target is gone.
- B registers → A registers → A unregister times out → A is freed → B cancels:
  the slot still names A's released client storage.
- A unregisters after download → B registers → A's common cleanup unregisters
  again: B loses its target. A failed-open epilogue can do the same without ever
  registering A.

A separate trace holds cancellation's lock while A's cleanup times out and
continues to free A. It records a possible lifetime conflict, without pretending
to execute the concurrent SDK access or establish its resulting memory effects.

The completion model admits an outer upload timeout, then B's launch and initial
semaphore drain, followed by A's late success. Without stack reuse, A's borrowed
context is simply expired; no result can safely be inferred from dereferencing
it. **If reuse of the same caller-stack region is additionally assumed**, A can
write B's status, replace the shared URL and give the unscoped semaphore after
B's drain. The model then allows B to consume A's result while B's own worker
has not completed. Stack reuse and the required network/task timing remain
explicit assumptions, not measured behavior.

A final trace follows cancellation after A's pre-render check: normal render
completion and monitor stop preserve the processing flag; B then completes
presign but exits before WAV upload, after which the explicit cancelled-upload
branch clears it. This exercises the earlier same-wake stale-flag hypothesis.
It neither tests sleep/reboot nor proves the absence of all indirect flag writes.

The useful backend rule remains: retain job identity across disconnects, bound
work below outer waits, and do not treat presign, socket closure or a shared
completion indication as a per-job delivery acknowledgment. Firmware ownership
needs a job-scoped result/cancel record, expected-owner cleanup and worker exit
before releasing context. A backend response field cannot supply that ownership.
See [validation](validation-2026-10-22.md#two-job-and-recording-interleavings-c08d05).

### Scheduled content can interrupt recording

The [poll field-selection trace](cloud-protocol.md#field-selection-and-permissive-json-parsing)
also shows that a true pending flag is retained when its image URL is missing
or invalid. The worker can request interruption before a usable asset exists;
an emulator must prepare the asset before publishing the flag.

The background poll worker `0x42025aec` can interrupt an active recording when
server work is pending. The backend only learns about the voice job at presign,
after recording ends. Furthermore every poll reports `is_periodic_poll=false`.
A server-side lock beginning at presign cannot protect the earlier recording.

A bounded host model enumerated the 15 merges of recording start → stop →
presign → job finish with poll decision → device consumption. With a hold that
starts at presign, two orders interrupt recording. With a proposed immediate
recording-start event, one remains: **poll response decided → recording starts →
pending response consumed**. Once the model interrupts recording, its later
nominal presign event is skipped, matching the no-upload path. These counts are
coverage of this small model, not event frequencies.

A hypothetical device arbiter that defers pending content while recording
eliminates interruption in those same orders by construction. That is a proposed
policy, not a tested firmware patch. Recording events help the backend withhold
new offers but cannot recall an already-issued response; rejecting its later
asset GET is too late to prevent the interruption before download. The existing
HA scheduling hold similarly blocks new dispatch, not work already dispatched.
Use both backend coordination and device-side ownership for the full guarantee.
The [host record](validation-2026-10-22.md#two-job-and-recording-interleavings-c08d05)
retains state assumptions and remaining physical criteria.

**Proposed firmware additions:** `recording_started`, `recording_stopped`,
`busy`, `cancel_requested`, and `render_complete` events with job/content IDs.
Use one scheduler to arbitrate routine content and voice; protect the shared
buffer at every entry point, including local HTTP uploads.

## Local speech and HA integration

The audio matches the common HA STT input format. A backend can parse the WAV,
invoke configured STT, then route the transcript to existing artwork, dashboard
rendering or image generation. An external Assist client uses WebSocket pipeline
messages and raw PCM, so the Fraimic HTTP upload still needs an adapter. See the
[Assist pipeline protocol](https://contributors.home-assistant.io/core/internals/assist-pipelines/)
and [STT entity formats](https://contributors.home-assistant.io/core/entities/stt/).

### Installed-provider check and WAV boundary

Read-only inspection of the owner's HA 2026.10.2 found Home Assistant Cloud and
Google AI STT. Both advertise 16 kHz, 16-bit mono PCM/WAV and Norwegian Bokmål;
no Wyoming/local STT integration was configured. No recording or transcription
request was sent during this check.

The authenticated HA `/api/stt/<provider>` view validates `X-Speech-Content`
metadata and passes body chunks to the provider. It does not strip a WAV header.
In this exact version, [Google AI STT](https://raw.githubusercontent.com/home-assistant/core/2026.10.2/homeassistant/components/google_generative_ai_conversation/stt.py)
collects the stream and wraps WAV-labeled input as raw PCM. Its
[conversion helper](https://raw.githubusercontent.com/home-assistant/core/2026.10.2/homeassistant/components/google_generative_ai_conversation/helpers.py)
does not detect an existing RIFF header.

A host fixture using that actual helper confirmed that passing a complete WAV
adds another header and treats the original 44 bytes as 22 extra audio samples.
Parse the Fraimic WAV, validate its PCM format and pass PCM to this provider;
do not blindly remove 44 bytes from arbitrary uploaded WAV files. This is a
container-boundary test, not a transcription quality test or proof every STT
provider has the same stream contract. See the [validation record](validation-2026-10-21.md).

Keep generated originals, transcripts, provider/job identity and edit lineage in
the HA library. A local transport can still call hosted AI; fully offline creation
also needs local STT and generation engines. Heavy inference belongs on a capable
server, not the ESP32.

A pure control command currently still needs an image result to follow the stock
success path. Async generation that sleeps while working, no-redraw success,
streaming speech recognition and automatic end-of-speech capture are proposed
protocol/firmware extensions, not existing stock features.
