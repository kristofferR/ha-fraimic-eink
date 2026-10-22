# Image downloads, retries and incomplete assets

[Research index](README.md)

These findings are **static and host-validated** for Large 0.2.29 / f1555ee5, pinned by the
[identity manifest](firmware-identity.json). Ghidra call/data flow was checked
against GNU ESP32-S3 instructions. The successful local card and Standard vendor
transfer are separate positive observations; no malformed image was sent to either
frame during this pass. Do not transfer the Large renderer's limits to Standard.

## The downloader checks declared length, not exact panel size

Common downloader `0x4202606c` is used by voice worker `0x420104a8`, poll-image
workflow `0x42010c4c` and setup-screen fetcher `0x4202abe8`. It opens a new HTTP
client, fetches headers, requires status **200**, then receives into the caller's
buffer. It has no PNG/JPEG decoder, palette validation or image-content hash.
The expected Large packed image is 2,304,000 bytes, which is the ordinary caller
capacity. The downloader does not require that many bytes merely to return success.

| Response or read condition | Recovered behavior |
| --- | --- |
| Header fetch returns a negative error | Fail, or return cancellation `0x103` when the HTTP-abort flag is set |
| Status other than 200, including 206 or redirects | Fail; optionally read up to 1,023 error-body bytes for a length diagnostic |
| Declared length exceeds destination capacity | Reject with `0x101` before the receive loop |
| Positive declared length, but fewer bytes received | Fail when reception ends without that declared count |
| Nonempty body matches its positive declared length | Download success, even when that length is smaller than a panel image |
| Fetched length is zero | Enter the receive loop; a nonempty body can succeed without a declared-count comparison |
| Zero bytes received | Fail |
| Body read returns `-0x7007` | Retry that read; three consecutive occurrences end the download |
| Positive body read between those errors | Reset the consecutive-error counter |
| Other negative body-read result | Fail, or cancellation `0x103` if the abort flag is set |

The manual `open` / `fetch_headers` path does not run the automatic redirect loop
used by polling/setup JSON. It does not refresh an expired signed URL, interpret
`Retry-After`, or request an HTTP byte range. Error-body text is not used as a
recovery protocol.

### Zero fetched length is different from voice JSON

The matched SDK reader (`0x4206d6a4`) and header fetcher (`0x4206d890`) explain why
the positive-length voice-JSON rule cannot be applied to panel downloads. Header
fetch can return zero for unknown/chunked length. The panel caller still reads;
the voice JSON callers skip their body-reading branch for non-positive length.
The [matching SDK source](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c)
supports these function identifications and the read semantics below.

The panel caller passes **all remaining destination capacity**, not a fixed
application chunk size, to each SDK read. The SDK can consume many 4,096-byte
transport reads before returning to application code. A transport timeout after
some bytes can return those bytes as positive progress; only a timeout with no
progress returns `-0x7007`. Thus three consecutive error results do not mean
three timeouts anywhere in a transfer, and the 30,000 ms client timeout is not
a total download deadline. The voice workflow has its separate five-minute wait.

When the destination fills, the next application read requests zero bytes. The
SDK returns zero without proving that the response stream is complete, and the
application has no separate final complete-data check. A host reconstruction
using the matching SDK reader reproduced an unknown-length response filling the
panel buffer and being accepted while more body bytes and chunk termination
remain unread. The full 2,304,000-byte-capacity case also passed with the parser
reporting **incomplete**. This is not a verified device result or a supported
emulator baseline. Serve a direct 200 with the exact explicit model-specific length.

The output count is reset only after successful headers/status/capacity checks.
Early failures can leave a caller's previous count untouched. The recovered
normal callers gate rendering on the returned error as well; that count alone
is not a success signal. The downloader also does not clear or roll back bytes
already written into shared PSRAM when a transfer fails.

### Host results with the matching SDK reader

Nineteen cases passed under address/undefined-behavior sanitizers using the same
seven unchanged IDF 5.4.1 HTTP functions and actual parser as the earlier voice
harness. The surrounding Large download loop is reconstructed; transport is
scripted and elapsed time virtual. Most boundary cases use a 16-byte capacity,
with two additional cases at the actual Large capacity. No socket, TLS session,
frame, display driver or flash cache participates.

| Host response | Observed reconstructed-download result |
| --- | --- |
| Exact positive Content-Length | Success; full Large case receives 2,304,000 bytes |
| Complete declared short body | Success with the shorter count; untouched destination tail remains unchanged |
| Declared length truncated by FIN | Failure; already copied prefix remains in the destination |
| Length above capacity, redirect, or header timeout | Reject before resetting the supplied output-count sentinel |
| Full-capacity chunked body, terminator missing or still unread | Success with parser incomplete |
| Large-capacity chunk followed by extra data | Success after the first 2,304,000 bytes; extra chunk and terminator remain unread |
| Short chunked body with terminator | Success; the same short body missing its terminator fails |
| Close-delimited body | Short body succeeds after FIN; full-capacity body succeeds before FIN |
| Three consecutive zero-progress transport timeouts | Failure after 90,000 virtual ms, with three EAGAIN returns |
| Progress interleaved with six transport timeouts | Success after 269,997 virtual ms; only four calls return EAGAIN, in two nonfatal streaks |

The progress case distinguishes transport timeouts from application-visible
errors: a timeout after bytes were accumulated returns those bytes as progress,
resetting the application's consecutive-error counter. It does not establish a
hard overall deadline or model the voice caller's separate five-minute wait.

One additional reduced-capacity control coalesces a complete 32-byte chunked body
with headers: the SDK caches all of it, but the reconstructed caller accepts only
16 bytes while 16 decoded bytes remain cached. Its parser reports complete.
This checks SDK cached-data behavior with a destination smaller than the header
receive buffer; it is **not** evidence that a whole oversized Large image fits
that 4 KiB header read. The full-size case above independently demonstrates the
unread-extra-data boundary at the real panel capacity.

All destination guards stayed intact. The harness omits the non-200 diagnostic
body read, allocation failures, cancellation races, reconnect retries and the
physical renderer. It tests no palette acceptance or image correctness.

## Whole-download retries reuse the same URL

Voice and poll-image workflows allow **up to three total download attempts**.
Success and cancellation `0x103` stop the retry loop. Other failures take the
retry branch only while attempts remain. Voice additionally checks its processing
cancellation flag after a failed attempt.

Before a retry, each workflow samples the connection getter `0x4201e050` up to
50 times with ten-tick gaps, about five seconds at this build's 10 ms tick.
If it still reports disconnected, the workflow gives up. Otherwise it waits
another 300 ticks, about three seconds, before the next attempt. These are
static delay values, not measured end-to-end timings.

Each retry creates a fresh client with the **same URL** and restarts body writes
at byte zero after successful headers. No Range, ETag or resume state is installed
by these paths. A 403 from an expired ticket can therefore be retried against
the same expired ticket; the worker does not redo voice finalize or presign to
obtain a replacement. The setup-screen fetcher makes one downloader call per
invocation and has no equivalent three-attempt loop inside that function.

For an emulator, keep a panel URL stable and reusable throughout its delivery
window. Do not consume a ticket on its first GET, regenerate artwork per GET,
or mark the image displayed merely because a server completed one response.
Use the model/content/job identity to serve identical bytes across retries.

## Voice download timeout and forced task deletion

Large orchestrator `0x42011adc` gives worker `0x420104a8` a **1,556-byte context**
on its own stack at `SP + 0xe4`. The URL is copied into that context; the pixel
buffer and result destinations remain borrowed pointers:

| Context offset | Contents |
| --- | --- |
| `+0x000` | 1,536-byte URL field, zeroed before copying at most 1,535 bytes |
| `+0x600` | Shared image-buffer pointer |
| `+0x604` | Destination capacity, 2,304,000 bytes |
| `+0x608` | Output-count pointer to caller `SP + 0x10` |
| `+0x60c` | Pointer to completion-semaphore handle storage `0x3fca6b28` |
| `+0x610` | Status pointer to caller `SP + 0x7d8` |

The caller initializes its task-handle slot at `SP + 0x7d4` to zero, drains the
semaphore once, and creates an 8,192-byte-stack task at priority 5 on core 0.
It discards the creation result, then waits 30,000 ticks, about 300 seconds.
Task-creation failure therefore still enters the wait.

On timeout it invokes the shared HTTP abort wrapper, ignores its result, and
waits another 500 ticks, about five seconds. If that second wait also fails and
the retained handle is nonzero, it calls task deletion at `0x40384c14`. Both
timeout outcomes then select download-error LED state 38 and return failure.
**Even a successful download completing during the grace period does not reach
rendering or the voice cache-save branch.** These are wait budgets, not a measured
305-second total: the abort call, logging and scheduling also take time.

### Completion is signalled before the worker deletes itself

The worker writes its status, performs terminal logging, gives the completion
semaphore at `0x4201063d`, then deletes itself at `0x42010645`. No context access
is recovered after that give. Normal completion therefore publishes the result
after the worker's last borrowed-context use; it does not wait for reclamation
of the worker's stack and task control block.

The worker does not clear the caller's retained task handle. After a failed second
wait, the caller neither rechecks the semaphore nor establishes exclusive ownership
of that handle before deletion at `0x420120d2`. **Conditional inference:** the
worker could signal and self-delete between those operations, leaving the caller
to delete an already-terminated task. The kernel entry treats a supplied nonzero
handle as a task-control-block pointer and immediately removes its state-list
item through `0x40383510`; it has no generation or liveness check at that point.
This is a possible stale-handle ordering, not an observed crash or a measured
race window. Merely adding a second liveness query would still need synchronization.

### Task deletion does not run the downloader's normal epilogue

When the common downloader returns normally after client creation, its epilogue
at `0x420266b9` calls unregister `0x42023464`, HTTP close `0x4206d9d8`, then client
cleanup `0x4206dbd8`. The latter releases HTTP request/response allocations,
parser/configuration storage and the client itself. Force-deleting the task
before this epilogue prevents those instructions from running in that task.
The timeout caller does not execute equivalent client cleanup afterward.

The recovered kernel path removes scheduler/event-list membership, defers
reclamation for a task running on either core, or directly calls task reclamation
`0x403838e8` otherwise. Reclamation invokes port cleanup, per-task C-runtime
cleanup and the allocation-policy-specific stack/control-block frees. Port
cleanup includes one registered thread-local deletion-callback slot and
coprocessor-state cleanup. It does not unwind the interrupted HTTP call stack.
These identities match the [IDF 5.4.1 kernel](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/freertos/FreeRTOS-Kernel/tasks.c)
and [Xtensa port](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/freertos/FreeRTOS-Kernel/portable/xtensa/port.c);
the application instructions, including the callback-address checks omitted by
Ghidra's decompiler, were checked separately with GNU.

**Conditional inference:** deletion during HTTP work can retain client allocations
or leave the shared active-client slot referring to an abandoned client. Deletion
during retry delay can instead occur after that attempt's normal cleanup.
Exact timing matters: this pass does not establish all runtime thread-local
callbacks, leaked bytes, socket lifetime, lock ownership, or a cause for the
previously observed TLS allocation failure. An HTTP abort return and a task-deleted
log are insufficient evidence of resource cleanup.

For the backend, retain completed artwork and reusable tickets when delivery
fails; a late successful GET is not proof the frame displayed it. A firmware fork
should give each job owned context/buffers, use cooperative cancellation with a
completion handshake, and release HTTP resources in the worker before releasing
job ownership. Uncoordinated deletion of a worker that also self-deletes is not
a cleanup protocol. Physical timeout/cancellation and Standard equivalence remain
open under C08/D01/D07.

## A short asset can reach rendering and replace the cache

The render-start entry `0x420208d4` checks nonzero pointer/length, waits or drops
according to its busy policy, then starts a task. The actual size check occurs
later inside worker `0x420204b8`:

```text
accept length when uint32(length - 2,302,976) <= 2,048
```

That is **2,304,000 ± 1,024 bytes**, inclusive. The downloader's ordinary capacity
prevents the upper half. A complete HTTP response declaring 2,302,976 through
2,303,999 bytes can therefore pass download and the worker's size check.
The worker copies only the supplied bytes, does not clear the missing tail,
and subsequently transfers the full eight 288,000-byte controller blocks.
For the usual shared-buffer input, the copy is another alias of the same allocation.

**Inferred consequence:** the missing tail can contain bytes left by an earlier
image, recording or failed download. This is a data-flow result, not a reproduced
optical corruption. An interrupted response that declared the full panel size
still fails the downloader's count comparison; it is not the same case as an
honestly declared short asset.

An even shorter nonempty response can pass HTTP download and task creation,
then fail the worker's size check. Early worker cleanup gives the same termination
semaphore used for successful work. Poll-image processing starts its cache save
after task creation; voice processing saves after this semaphore without a
separate worker success result. Either recovered flow can consequently attempt
to replace `last_image.bin` despite that later size rejection.

The cache writer `0x42028524` accepts nonzero lengths up to 2,566,144 bytes, and
loader `0x42028698` checks nonzero size, capacity and complete file reading, not
the exact model length. This leaves persistence/reload implications to validate.
See [cache ordering and completion](rendering-and-concurrency.md#observed-poll-and-voice-cache-ordering)
and [last-artwork storage](storage-and-configuration.md#last-artwork).

## Implementation requirements and remaining checks

- Validate model, packing, exact length and an application-side content hash
  **before** making an asset URL available to a frame.
- Serve immutable complete bytes with HTTP 200 and explicit length. Keep error
  documents on non-200 responses; a 200 error body is not a valid panel result.
- Retain download tickets across repeated full GETs. A response finishing is a
  transfer observation, not a render acknowledgment.
- In a firmware fork, require the exact panel length before task creation/cache
  replacement, verify stream completion, and propagate the worker's result.
  Buffer ownership still needs to cover download, render and storage.

Device fault injection remains open under C03/C07/C08/D06/D07/N04: chunked/missing-
length responses, short declared assets, partial transport and stalls now have
bounded host coverage; retry expiry, network failover and cache recovery remain
separate. The physical cancellation test remains
deferred. No frame routing, setting, artwork or firmware changed in this pass.
