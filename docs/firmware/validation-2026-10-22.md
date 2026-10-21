# Static validation: 22 October 2026

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
