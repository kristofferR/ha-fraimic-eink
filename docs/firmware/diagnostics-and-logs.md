# Diagnostics, log retention and capture limits

[Research index](README.md)

These are static findings for the pinned Large 0.2.29 application. No log-clear,
authentication-bypass, filesystem-fault or logging stress test was performed.
The purpose is to interpret existing evidence and design better local-backend
diagnostics, not to treat a log page as a complete execution trace.

## The password changes detail visibility

GET `/logs` serves the page without requiring a successful password submission.
The cookie checker `0x4201ba58` returns a boolean that becomes a maximum record
visibility class: unauthenticated requests select class 0; the accepted marker
also permits class 1. The normal SDK capture hook classifies a line beginning
with `I` after an optional ANSI prefix as class 1 and other lines as class 0.
The explicit application logging wrapper `0x4202e308` records class 1 regardless
of the severity letter it formats. Therefore this is not a uniform severity or
authorization model across every logging path.

POST `/logs` reads at most 127 bytes in one receive call, extracts a password
into a 64-byte buffer and compares against its embedded value. Success redirects
with a **fixed cookie marker**, Path `/logs`, HttpOnly and SameSite=Strict. The
GET checker uses a substring search in a Cookie header of 1–256 bytes. There is
no random session token, server-side session lookup or expiry check in that
checker. The developer-mode throttle is not used by this handler. Do not use
this mechanism as the local emulator's admin authentication design.

POST `/logs/action` reads at most 63 bytes in one call and accepts `action=clear`
without invoking that cookie check. It calls `0x4202e200`, which tries the log
mutex for ten ticks, about 100 ms. If the mutex is unavailable, the void helper
does nothing; the HTTP handler still sends its ordinary success response. It
clears only the in-memory store and counters, not `debug_log.bin`. A new “cleared”
log can be added immediately afterward. No clear was submitted during this pass.

GET and password POST call the last-activity helper. Repeated polling can postpone
idle behavior, so log capture is not a neutral battery/sleep baseline.

## In-memory retention is bounded and lossy

Initializer `0x4202dff0` allocates **65,536 bytes of PSRAM** and a mutex, then
installs capture hook `0x4202ded8`. PSRAM allocation failure leaves serial-only
logging rather than an equivalent heap-backed history.

The hook formats into a 256-byte buffer, applies the redactor, writes to the
serial output and tries the history mutex with **zero wait**. A failed mutex
attempt skips history insertion. The additional filtering callback
`0x420e2b70` simply returns zero in this binary; it supplies no further filter.

Append helper `0x4202ddc0` caps each stored text at **255 bytes**. Its binary
record is:

| Offset | Field |
| --- | --- |
| 0–3 | Little-endian U32 uptime in seconds |
| 4 | One-byte visibility class |
| 5–6 | Little-endian U16 text length including NUL, 1–256 |
| 7 onward | Text and trailing NUL |

The optional wall-clock prefix consumes some of the same 255-byte text limit.
Long messages can lose their tail or newline. This is not a store of complete
HTTP bodies, structured events or unlimited serial output.

When the next complete record would exceed capacity, the app sets write position,
used bytes and record count to zero before adding it. It **discards the entire
current history**, rather than evicting only the oldest record. The low-level
byte writer is circular, but the higher-level append policy resets the window.
That reset does not first persist the discarded history.

Formatter `0x4202e0cc` waits at most ten ticks for the mutex. It returns zero on
contention, which the page can display as no captured entries even if the store
is populated. It also stops on an invalid/incomplete record or output capacity.
Combined with truncation, filtering and whole-store reset, absence from `/logs`
cannot prove that an operation did not occur.

## “Previous” is one saved snapshot

Flush `0x4202e484` obtains the log mutex with a 50-tick wait, about 500 ms, and
holds it across writing `/imagedata/debug_log.bin` with mode `wb`. It writes:

1. U32 magic `0x464c4f47` in little-endian byte order.
2. U32 number of saved record bytes.
3. The current binary records, oldest retained first.

The maximum represented file is 65,544 bytes, including its eight-byte header.
It contains neither an explicit format version nor a checksum. The reader
`0x4202e644` validates magic, a nonzero count no greater than 65,536, and complete
payload reading, then walks the same bounded records and visibility filter.
An invalid record stops conversion; it does not establish the remaining file
was inspected successfully.

The writer ignores both header/body `fwrite` results and the close result. It
does not perform a separate checked `fsync`, readback verification or atomic
rename. A “Flushed” success log is therefore not evidence of durable complete
storage. A failed overwrite can destroy the previous snapshot. An empty current
store skips writing and leaves any older file in place.

The common flush wrapper `0x4202e7a0` has recovered calls in the pre-sleep flow
and a main-loop restart path; restart helper `0x42017208` calls the flush directly.
This is not automatic crash/panic persistence or
a multi-boot archive. The flush can initialize/mount image storage if needed,
including its existing recovery policy; it is not an independent read-only
diagnostic operation. No new flush was invoked here.

During a slow flush, capture's zero-wait mutex attempts can lose new history
records. GET `/logs` can also allocate two 64 KiB text buffers plus a temporary
buffer of up to 64 KiB for the saved binary payload. Its current-log allocation
has a 2 KiB ordinary-heap fallback; the previous-log output allocation does not.
These are bounded code-path costs, not measured peak usage during a particular
voice request.

## Redaction is heuristic

`0x4202dae8` recognizes MAC-like text, email local parts and seven keyword
patterns: `password`, `pwd`, `token`, `secret`, `api_key`, `apikey` and `ssid`.
It masks portions of addresses and replaces selected values. It is not a JSON,
URL or HTTP parser; its bounded in-place replacement helper can decline a
replacement that would not fit the formatted buffer.

In particular, this keyword list does not cover arbitrary device-key path
segments or every signed-URL parameter. The album logger separately masks a
suffix but prints credential-bearing paths. Keep raw diagnostics private and
apply explicit field/path redaction before exporting captures. A visible mask
elsewhere in a line does not make the whole line safe to publish.

For a local backend, retain structured job events with stable job/device IDs,
stage, monotonic timing, result and safe error codes. Keep recordings, transcripts
and final prompts behind owner access and a retention policy. Frame logs can
supplement that record, but do not replace render acknowledgments or a durable
job history.
