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
| Outer recording deadline | 6,000 ticks at 10 ms, approximately 60 seconds |
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

For the emulator, validate and retain a complete upload under its issued job key,
start generation on finalize, and expire uploads that never finalize. Receipt of
the WAV alone does not prove that the user completed the whole workflow or that
the frame will accept a result. These streaming/fault details are static findings;
the earlier successful local uploads remain the physical positive controls.

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
come afterward. Thus a valid positive response length is misclassified as failure.

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
| Body framing | Explicit positive `Content-Length`; avoid chunked JSON |

Hold finalize until the panel asset is ready. Align reverse-proxy timeouts with
the long request. Persist the job and deduplicate finalize calls so a retry does
not pay for another generation or create duplicate library entries.

### Body completeness and timeout scope

The 4,095-byte limit is a **single read capacity**, not a check that the declared
response fits or was completely received. Large presign `0x420266d8` and finalize
`0x42027380` call `0x4206d6a4` once when the fetched length is positive, then parse
the returned prefix. Neither compares received bytes with the declared length
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

### Scheduled content can interrupt recording

The [poll field-selection trace](cloud-protocol.md#field-selection-and-permissive-json-parsing)
also shows that a true pending flag is retained when its image URL is missing
or invalid. The worker can request interruption before a usable asset exists;
an emulator must prepare the asset before publishing the flag.

The background poll worker `0x42025aec` can interrupt an active recording when
server work is pending. The backend only learns about the voice job at presign,
after recording ends. Furthermore every poll reports `is_periodic_poll=false`.
A server-side lock beginning at presign cannot protect the earlier recording.

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
