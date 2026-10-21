# Static and host validation: 22 October 2026

[Research index](README.md) · [Checklist](research-todo.md)

This continuation uses the same hash-pinned Large 0.2.29 application. It does not
change the running frame, its network routing, accounts or artwork. The deferred
physical cancellation test remains deferred.

## HTTP server and factory diagnostics: H05/S06/E01

The 88-byte server configuration was read directly from the application at
`0x3c13bd98`, then combined with startup writes at `0x4201a69c`. Ghidra exports,
GNU instruction decoding and IDF 5.4.1 source comparison distinguish configured
client capacity from actual handler concurrency. The constant, exports and
bounded decoder are retained in the private research set.

Confirmed statically:

- Seven client slots share a single server task. Its blocking upload, scan and
  proxy handlers can delay other requests; 60-second socket timeouts are not a
  whole-request deadline.
- The 42 registrations occupy a configured 43 slots. Portal errors are ignored,
  account-registration errors abort, and battery/API registration errors can
  leave a partially available server. The already-running path does not retry.
- Server stop waits for the task; application teardown clears the handle even
  if stop fails to send its shutdown message. Neither failure was induced.
- A failed or oversized factory GET query can fall through to entering factory
  mode. This happens before HTML allocation and bypasses LED protection.
- Factory microphone statistics are a separate diagnostic state, not ordinary
  voice-recording activity or a streaming-audio interface. POST success/error
  bodies and stop/task-creation limitations are mapped separately.
- `/api/info` exposes preferences and maintenance dates rather than job state.
  Local timestamps lack an offset, and field/object allocation failures can
  leave a partial JSON snapshot. Factory amplitude is block peak-to-peak.

The [local API contract](local-api.md#server-capacity-and-lifecycle) contains
addresses, field values, response shapes and linked upstream corroboration.
No socket-exhaustion, blocked-handler, allocation-failure, factory-mode or
microphone experiment was performed. H05/S06 remain open for their remaining
schemas, boot states and physical behavior; E01 remains open for the rest of the
incomplete analysis corpus.

Two previously undefined Ghidra entries, Wi-Fi/IP event handler `0x4201ab08`
and factory microphone task `0x4201fca4`, were recovered after independently
checking their entry instructions and bounds. Only the analysis database was
changed; the original firmware bytes remain unchanged.

## Poll parser and error semantics: C02/S03/C08

The IDF v5.4.1 submodule reference pins cJSON to
[`acc76239bee01d8e9c858ae2cab296704e52d916`](https://github.com/DaveGamble/cJSON/tree/acc76239bee01d8e9c858ae2cab296704e52d916),
version 1.7.18. The host fixture compiles that source with a small model of the
recovered Large field-selection branches. It uses actual cJSON parsing, lookup,
type predicates and serialization; it does not execute the Xtensa application.

Compiled on Omarchy with `cc -std=c11 -Wall -Wextra -Werror` and address/undefined
behavior sanitizers. **All 25 cases passed**, with no sanitizer report. Coverage
includes boolean/legacy precedence, missing URLs, case-insensitive and duplicate
keys, non-object roots, trailing text, empty/truncated JSON, numeric versus string
epochs, fractional seconds, settings object/type behavior, verification booleans,
scalar/null `user_settings` and bounded URL copying.

| Private artifact | SHA-256 |
| --- | --- |
| Pinned `cJSON.c` | `75c51de8fa40ac9d7a99319c6330719bd692eb81c0a869265f3d4c682533f9b9` |
| Pinned `cJSON.h` | `0578cc29132912edbc88f83207a8fc76e5db3db0605497e909a9384ef3cc474b` |
| Poll JSON fixture | `470a69bba30bc00e9113071ce24b9c9adcbce548d4e91872a65dea9554276f10` |

Firmware helpers `0x4203962c`, `0x4203953c`, `0x4203966c`, `0x42039100` and the
type predicates were inspected alongside caller branches. GNU checks cover
pending-flag selection, URL copying, signed 64-bit deadline comparison and error
returns. This supports the particular behaviors in the
[poll contract](cloud-protocol.md#field-selection-and-permissive-json-parsing),
not whole-library equivalence or proof of the vendor's unmodified source revision.

Separately, static error-path checks show connection-open error `0x7002`, HTTP
404 and statuses 500 or above returning empty internal success while skipping
settings/deadline updates. HTTP 401/403 return an error, and the worker retries
only EAGAIN once after a one-second delay. No HTTP fault was sent to the frame.

The model omits HTTP accumulation/framing, allocation faults, NVS, the ROM
conversion implementation, callback concurrency, recording interruption and
scheduler execution. Numeric inputs are finite and within signed 64-bit range.
C02/S03/C08 remain open for device behavior and persistence/lifetime cases.

Source inspection also found that HA's current timestamp sensor parser assigns
its default timezone to naive frame timestamps. A frame configured with different
rules therefore needs explicit timezone handling; no integration code was changed.
