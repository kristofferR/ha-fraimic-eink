# Image downloads, retries and incomplete assets

[Research index](README.md)

These findings are **static** for Large 0.2.29 / f1555ee5, pinned by the
[identity manifest](firmware-identity.json). Ghidra call/data flow was checked
against GNU ESP32-S3 instructions. The successful local card and Standard vendor
transfer are separate positive observations; no malformed image was sent to either
frame during this pass. Do not transfer the Large renderer's limits to Standard.

## The downloader checks HTTP completeness, not panel completeness

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
application has no separate final complete-data check. **Inferred fault case:**
an unknown-length response can fill the panel buffer and be accepted even if
more body bytes or chunk termination remain unread. This is not a verified
device result, and not evidence that chunked transfers are a supported emulator
baseline. Serve a direct 200 with the exact explicit model-specific length.

The output count is reset only after successful headers/status/capacity checks.
Early failures can leave a caller's previous count untouched. The recovered
normal callers gate rendering on the returned error as well; that count alone
is not a success signal. The downloader also does not clear or roll back bytes
already written into shared PSRAM when a transfer fails.

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

Fault injection remains open under C03/C07/C08/D06/D07/N04: chunked/missing-length
responses, short declared assets, partial transport, stalls, retry expiry,
network failover and cache recovery. The physical cancellation test remains
deferred. No frame routing, setting, artwork or firmware changed in this pass.
