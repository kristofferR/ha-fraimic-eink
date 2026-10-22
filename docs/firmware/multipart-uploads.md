# Legacy multipart uploads

[Research index](README.md) · [Raw image API](local-api.md#image-delivery)

This static/host follow-up covers Large 0.2.29 and Standard 0.2.28's `POST /upload`.
It establishes concrete parser and response differences from `POST /api/image`.
It does **not** reproduce or identify the root cause of the historical persistent
upload failure that HA works around with a restart. No device request was made.

## The parser is not a general multipart implementation

The complete handler is `0x4201cc0c` on Large and `0x4201cbe0` on Standard.
Both have 413 reachable GNU instructions with matching normalized operations and
internal branches. Ghidra's earlier Large body stopped at a bad disassembly;
the complete GNU traversal recovers all return paths and checks their image bytes.

The handler reads a 1–255-byte Content-Type value, searches for `boundary=`,
copies up to 127 following bytes and requires a nonempty result. It does not
unquote that value or separately parse later parameters. It then allocates a
1,024-byte receive buffer. The first `\r\n\r\n` found marks the file-data start;
the field name and filename are not validated. A host case using another field
and filename still reaches the save/render path. Keep using the conventional
`image` / `image.bin` form; permissive parsing is not another supported API.

After the header separator, it builds `\r\n--<boundary>--` and searches within
each received chunk. There is no carried boundary suffix between chunks. The
search helper, Large `0x420cf7bc` / Standard `0x420cfaa0`, has 27 matching
instructions. It uses a bounded byte search, but rejects a match when a NUL byte
occurs before it. Thus it behaves as a bounded **string** search over binary
image data. The initial header search also uses `strstr`; no receive-buffer
termination is added by the handler. The host cases supply a complete header
separator in the first receive and do not claim to quantify an over-read.

## Valid image bytes can change how the footer is handled

The receive capacity differs: Large's image allocation is exactly 2,304,000 bytes;
Standard's is 1,048,576 bytes for a 960,000-byte panel. Both legacy handlers check
allocation capacity, then rely on the shared save/start wrapper's ±1,024-byte
size tolerance. The raw endpoint has an additional exact-panel-size upper cap.

These cases use identical complete image bytes except for the stated final NUL,
and a 26-byte closing trailer. Receive chunk boundaries are synthetic:

| Case | Large | Standard |
| --- | --- | --- |
| Closing trailer delivered separately | Saves exactly 2,304,000; render-start accepted | Saves exactly 960,000; render-start accepted |
| Final 64 image bytes and footer together, no NUL before footer | Same correct size | Same correct size |
| A NUL before footer in that combined chunk | Footer not recognized; capacity error, `413 File too large` | Footer not recognized; saves 960,026 bytes and reaches render-start |
| Closing boundary split across receives | Capacity error, `413 File too large` | Saves 960,026 bytes and reaches render-start |
| An additional 512 image bytes | Capacity error | Saves 960,512 bytes and reaches render-start |

The Standard cases establish extra cached/input bytes, not visible corruption:
the expected first 960,000 image bytes remain intact. The Large cases establish
rejection after buffer writes, not a permanently stuck upload service. Packet
segmentation and actual socket receive boundaries were not reproduced on a frame.

## An interrupted receive can still start rendering

Unlike the raw endpoint's consecutive-timeout handling, the first nonpositive
receive exits this loop. It then checks whether **any** file bytes were collected
and calls the normal save/start wrapper. There is no requirement that the full
declared body or closing delimiter was received before that call.

On both builds, a timeout or EOF after all but 512 image bytes still saves that
short image and reaches render-start; the wrapper's tolerance accepts it. A
timeout after only 256 image bytes instead produces the invalid-size error.
A declared body ending immediately after a complete image, with no closing
trailer, also reaches render-start. These are controlled instruction outcomes,
not recommendations for constructing requests. An interrupted transfer is not
proof that no display operation began.

## HTTP 200 can contain an upload-failed page

After save/start, only `0x104` is mapped to a `400` invalid-size response. Another
error, such as the modeled `0x107` render-start timeout, selects an HTML failure
page while retaining **HTTP 200**. The body says the image was uploaded but the
display failed to start. Response-chunk send results are ignored, including the
terminating chunk, and the handler returns zero on this page path.

The current [`api.py`](../../custom_components/fraimic/api.py) multipart transport
checks HTTP status but does not interpret a successful-status HTML body. It can
therefore treat this failure page as upload success. Its connection-error branch
also restarts/retries both transports, whereas timeout has a separate uncertain-
outcome exception. The firmware evidence does not make other connection failures
safe to retry: either transport can reach render-start before its response fails.
This is an implementation consideration, not a change made by this research.

For the pinned versions, keep the existing raw-endpoint preference. A later
integration change can recognize the legacy failure page and distinguish an
uncertain post-transfer outcome from a pre-transfer connection failure. A real
firmware fix needs exact-length, binary-safe incremental parsing and consistent
error propagation. A durable job/result acknowledgment remains an extension.

## Evidence and remaining boundary

[Thirty instruction cases](legacy-upload-cases.json), fifteen per build, pass.
They cover 440 distinct instructions on Large and 417 on Standard across the
handler, search helper and save/start wrapper. The different coverage comes from
model-capacity branches. A returned handler error and a sent HTTP error are
tracked separately, as are received and saved byte counts. The temporary receive
allocation is freed on all exercised paths.

HTTP receives/send results, allocator state, ROM/memory-search/format helpers,
buffer accessors, activity/LED, cache/marker and render results are modeled. ROM
names match the [ESP32-S3 SDK bindings](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_rom/esp32s3/ld/esp32s3.rom.newlib.ld).
The binary search wrapper itself executes; its lower bounded byte search is
modeled. No claim is made about every malformed multipart form, socket teardown,
actual heap failure, cache durability, physical display, or the cause of the
earlier persistent failure. SDK request cleanup is a separate boundary.
