# Backend emulation on the closed frame

[Research index](README.md) · [Protocol](cloud-protocol.md) · [Checklist](research-todo.md)

On 21 October 2026, the owned Large 0.2.29 frame accepted **five locally generated
idle-poll responses and one album-list response** from a standalone HTTPS server.
The server did not forward requests upstream. This extends the earlier successful
certificate/pass-through experiment to actual response emulation.

The enclosure remains closed. No firmware, trust store, pairing, image or device
settings were changed by the idle experiment. It is evidence for the transport
and already-paired read protocol, not a complete deployed cloud replacement.

## Idle experiment: C02/C03/C12

The fixture used Python's HTTP/TLS server on the development host, the previously
accepted test chain for the stock API hostname, a privately loaded device key,
and an unchanged album snapshot. It allowed only the owned frame and host test
client. The two supported routes were:

```text
GET /api/v1/upload/check/<device_key>
GET /api/v1/albums/<device_key>
```

Poll JSON contained `has_new_upload: false`, `presigned_url: null`,
`firmware: null`, and the **same future numeric `next_image_utc`** returned by a
fresh vendor poll. It omitted `device_settings`, `user_settings` and `account`.
Do not substitute `/api/info`'s maintenance `display.next_refresh` for this album
deadline. The fixture refused to start with a pending upload/firmware offer or
an imminent deadline, and returned failure rather than an expired success.

Every response had an explicit byte `Content-Length`, JSON Content-Type,
`Cache-Control: no-store` and connection close. Unknown routes, wrong keys,
wrong hosts/model/version and mutations were rejected. Raw request URLs were
excluded from event logs because they contain the device key and Wi-Fi details.

Six host checks passed before routing the frame: accepted idle response, identical
albums, wrong key, wrong hostname, wrong model/version and forbidden PUT. The
host TLS client verified the hostname and test root. That positive check does
not establish rejection of every invalid certificate by the frame.

### Device result

| Observation | Result |
| --- | --- |
| Local idle polls | Five HTTP 200 responses, each 89 bytes |
| Poll timing | 19:25:56–19:27:57 UTC, approximately 30 seconds apart |
| First corresponding frame log | `Poll OK: upload=N, next_img=set, fw=N, settings=absent` |
| Later poll logs | `Poll OK` with no changes |
| Local album request through the frame | `/api/albums` returned HTTP 200, object equal to the captured snapshot |
| Local album response body | 2,992 bytes; no vendor forwarding |
| Before/after `/api/info` | Settings and maintenance schedule unchanged |
| Return to vendor | Successful poll at 19:28:27 UTC with the normal settings snapshot |

The matching server events identify the frame's source address, route category,
status and length; they omit credentials and album contents. The fixture source
SHA-256 is `4029d580792ad3e4d832d1b92c8ee5d34e9afcb4ba0c8fdfdb18b39ce3f64521`.
Private scripts, credentials and captures remain outside the repository.

This verifies that omitting the settings object preserves the observed live
switches in this scenario. It does not test incomplete objects, failed NVS writes,
reboot persistence, new-image delivery, schedule clearing or unattended wakeups.
The album result tests proxy transport; a fixed snapshot is not an album database.

### Routing and cleanup

The 150-second window used a DNS rule scoped to this frame and the API hostname,
plus a source/destination-specific TCP translation to the fixture listener.
Both DNS replicas were updated and checked. The rule applied only to the target
client; observed rewritten answers had a ten-second TTL.

Cleanup removed only this experiment's rules, verified both DNS replicas and the
routing rule, and preserved unrelated configuration. Subsequent frame DNS queries
resolved the vendor again, the frame logged a successful vendor poll, and the
local server was stopped. Immediate DNS `check_host` results lagged rule loading;
the actual per-client query log and frame requests established activation.

## Voice capture fixture: C05/C06/C07

A second fixture implements HTTPS presign, plain HTTP multipart upload and a
deliberate stop at finalize. It uses short-lived, unpredictable upload tickets,
a device-key check, a small job cap, explicit response lengths, bounded request
bodies and private WAV storage. Presign returns a real empty `fields: {}` object.
The multipart file field is `file`, filename `recording.wav`.

Eleven host checks passed with a synthetic one-second, 32,044-byte mono 16 kHz
16-bit WAV. They covered wrong device key, presign shape, finalize-before-upload,
invalid ticket, malformed recording, oversized body, upload round trip, identical
re-upload, conflicting re-upload, deliberate finalize failure and identical
repeated finalize. The saved WAV matched the input byte-for-byte and the synthetic
recording was deleted. No STT, generator or renderer was called.

The deliberate final response is HTTP 409 with a research-capture-complete error.
This stops stock firmware before image download/rendering and is expected to look
like generation failure to the owner.

### Physical microphone results

The owner completed three short recordings. The fixture never forwarded audio
or finalize requests to a vendor or AI provider.

| Attempt | Observed result |
| --- | --- |
| Separate upload port | Local HTTPS presign accepted; upload connection failed because the host firewall did not admit that port. No audio reached the server. |
| Shared reachable port; HTTP 200 + 15-byte JSON upload acknowledgment | Valid 147,500-byte WAV stored locally: 73,728 samples, 4.608 seconds. Frame rejected the positive response length before finalize. |
| Shared reachable port; HTTP 200 + `Content-Length: 0` | Valid 188,460-byte WAV: 94,208 samples, 5.888 seconds. Frame logged successful upload and called local finalize, then handled the intended HTTP 409 and returned to ready. |

Both captured files have a 44-byte RIFF/WAV header followed by mono, signed
16-bit PCM at 16,000 Hz. Their lengths match header plus two bytes per sample.
The owner completed them with a single stop tap; no timeout or cancellation test
was attempted. Raw audio remains private and was not transcribed or listened to.

The last sequence was observed at 19:41:29–19:41:31 UTC: presign HTTP 200 with
131 response bytes; multipart upload HTTP 200 with zero response bytes; finalize
with matching job/identity and **`orientation: landscape`**; deliberate HTTP 409
with 103 response bytes. Do not infer portrait workflow orientation solely from
the panel's native 1440 × 2560 layout. The firmware logs still label the upload
“S3” even though this was an ordinary owner-hosted HTTP sink.

The response comparison and [instruction trace](voice.md#upload-acknowledgment-must-have-an-empty-body)
establish the empty-acknowledgment requirement on this build. The final fixture
source SHA-256 is `5ebf6527c31b96d61993df8db7811ad26d5c1cd3438297009b787071a9647ac5`.
Its one-port HTTP/TLS dispatch was a temporary host deployment choice, not a
firmware requirement. The host firewall was not changed.

Both voice routing windows were rolled back, both DNS replicas checked, and the
listener stopped. A vendor poll with its normal settings snapshot resumed at
19:42:18 UTC. Firmware, registration, four switches and exposed maintenance
schedule matched the before state. No packed image was served or redraw requested.

This validates a **microphone → local presign → local multipart upload → local
finalize request** path. Successful finalize/image download/display, all upload
status variants, malformed presign handling, long recordings, cancellation and
retries remain open. Host duplicate handling is not evidence of actual frame retry.

## What remains before a usable local backend

- Expand the validated short-recording path to controlled response faults,
  cancellation and duration boundaries.
- Serve a known packed panel asset and verify a physical redraw, then add STT and
  generation through a separately chosen provider. Keep original artwork and
  job/transcript metadata in HA's library.
- Replace snapshot responses with durable device/job/album state; implement replay,
  expiry, ownership and reload recovery. The host fixture's duplicate handling
  does not establish production durability or stock-firmware retry behavior.
- Coordinate polling and scheduled content with voice so shared frame memory is
  not overwritten. Serving a download is not proof of a completed panel refresh.
- Test WAN loss, local time and cold boot separately. This experiment left public
  reachability probes and SNTP available and preserved existing pairing.
- Establish a sustainable URL/trust configuration. The short-lived test chain for
  the vendor hostname proves compatibility; it is not an owner-controlled hostname
  or a durable deployment mechanism. No arbitrary self-signed acceptance was shown.

Hardware inspection and custom-firmware boot/recovery tests remain deferred under
the owner's closed-enclosure preference. They are not prerequisites for further
bounded backend protocol experiments using the already-proven transport.
