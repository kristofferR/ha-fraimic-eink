# Backend emulation on the closed frame

[Research index](README.md) · [Protocol](cloud-protocol.md) · [Checklist](research-todo.md)

On 21 October 2026, the owned Large 0.2.29 frame accepted **five locally generated
idle-poll responses and one album-list response** from a standalone HTTPS server.
The server did not forward requests upstream. This extends the earlier successful
certificate/pass-through experiment to actual response emulation.

The enclosure remains closed. No firmware, trust store, pairing, image or device
settings were changed by the idle experiment. It is evidence for the transport
and already-paired read protocol, not a complete deployed cloud replacement.

Later bounded experiments captured microphone audio locally and displayed one
owner-approved six-colour test card. The owner confirmed the card and its upright
orientation. A subsequent recording completed the combined local voice-to-image
protocol and driver sequence using that same card. Its unchanged pixels made
the second refresh visually ambiguous; the completion evidence is in frame logs.

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

This capture-only pass validated **microphone → local presign → local multipart
upload → local finalize request**. The successful finalize path was tested later
below. Other upload status variants, malformed presign handling, long recordings,
cancellation and retries remain open. Host duplicate handling is not evidence of
actual frame retry.

A later [24-case host acknowledgment pass](voice.md#upload-acknowledgment-parser-and-early-success-boundaries)
keeps the emulator contract narrow: store the complete multipart WAV, then send
one final 200 with explicit zero length. Separate informational responses can
fail before the final status, while chunked/close-delimited acknowledgments can
return success without body completion. These are isolated parser results,
not additional physical recordings or a change to the deployed fixture.

## One-shot panel delivery: C03/C09/D06

The owner approved replacing the current artwork once with a prepared six-colour
test card. A separate local HTTPS fixture offered the asset through the normal
poll response, using `has_new_upload: true` and a short `presigned_url` on the
same API hostname. The asset was an ordinary local file behind an unpredictable
ticket; no S3 service, AWS query parameters or AI provider was involved.

The fixture preserved the future album deadline, omitted settings/account data
and offered no firmware. It retired the image offer **before transmitting the
asset**, returned idle responses afterwards and rejected a repeated asset request
with HTTP 410. This is an in-memory, one-run guard, not durable job tracking or a
display acknowledgment. The frame-capable process required explicit arming.

### Asset and host checks

The existing integration's `image_convert.convert_image` produced the payload
from a 2560 × 1440 landscape card using its calibrated `SPECTRA6_RGB` palette.
Conversion used native dimensions 1440 × 2560, rotation 90, preview rotation 270,
fit `contain`, mode `none`, saturation/contrast 1 and sharpen/tone 0. The result
was exactly **2,304,000 bytes**, containing only panel indices `{0,1,2,3,5,6}`;
the landscape preview was 720 × 405. These rotations match this test and mount,
not every installation.

Asset SHA-256:
`3350da5b6662864964b2ec29a6768a43118deda4ff78267b4549c5a2d7e47526`.
Fixture source SHA-256:
`3e960da7a009390bc85ab1b059120f7f348d5c7e7c2fc747d5c4ddf6f320fd89`.
Both remain private research artifacts outside the repository.

Five host checks passed before arming a fresh process: image offer; hostname/root
verified TLS download with matching size and hash; subsequent idle poll;
repeated-asset HTTP 410; and unknown-ticket HTTP 404. No local push API or refresh
command was used, avoiding a second delivery route for the same test.

### Physical result

All times below are UTC on 21 October 2026. The frame's log clock was UTC−04:00;
server events and firmware timestamps were correlated with that offset.

| Time | Evidence |
| --- | --- |
| 19:49:48 | Frame accepted the local poll: `upload=Y`, future deadline set, no firmware, settings absent |
| 19:49:52 | Downloader reported HTTP 200 and `Content-Length: 2304000` |
| 19:49:55 | Exactly 2,304,000 bytes downloaded; firmware measured 4,525 ms, about 497 KiB/s |
| 19:50:03 | Rendering sent 288,000 bytes to each of eight controllers; conditioning was skipped for the logged recent-wake state |
| 19:50:05 | All eight driver ICs reported ready; display refresh started |
| 19:50:14 | Firmware reported the complete image saved to flash while refresh continued |
| 19:50:42 | Driver reported display refresh complete |
| 19:50:44–19:50:57 | Vendor discharge sequence ran for 13 seconds; all power switches disabled, then server task reported successful rendering |
| 19:50:58 onward | Local polls returned to idle; no second asset was offered or downloaded |
| 19:52:29 | Successful vendor poll resumed with the normal settings snapshot |

The owner confirmed that the **LOCAL IMAGE TEST** card was visible, with all six
labelled colour blocks and upright text. This adds physical observation to the
download, cache-save and driver-completion logs. It does not turn an HTTP success
or the renderer's semaphore into a general-purpose display acknowledgment.

The 150-second frame-scoped routing window removed its DNS rules on both replicas
and its exact TCP translation, with cleanup verified. The local listener was
stopped. The approved card remains the current artwork until another delivery.
No firmware, trust-store, pairing or settings change was made.

This verifies local **poll → HTTPS panel asset → flash save → physical display**
on the stock Large build. Reboot/cache persistence, failed transfers, negative
certificates, cancellation and repeat offers remain untested. This poll-only
experiment did not exercise voice finalize or close C03/C09 by itself.

## Combined voice/image host fixture: C09

A follow-on fixture joined the two transports on the host: synthetic one-second
WAV → empty upload acknowledgment → synchronous finalize HTTP 200 with
`status: completed` and `presigned_url` → the same verified panel asset. Fifteen
host checks passed, covering identity/ticket validation, upload ordering and
replays, conflicting audio, orientation validation, repeated finalize, verified
TLS asset/hash, one-shot consumption, rejection of a second job, and an unchanged
idle poll with its future deadline. The synthetic WAV was deleted afterwards.

During these host checks the service was unarmed for the physical frame, no
routing window was opened, and it was stopped afterwards. No STT or generator
was invoked. The subsequent owner-directed device experiment used a fresh process.

## Combined voice/image device result: C09

The owner approved another short recording and one refresh of the same card.
The armed fixture accepted only one voice job. Poll responses remained idle, so
the image could be delivered only through voice finalize. The result URL was
retired before its first transmission, preventing an automatic second download.

The frame supplied a **159,788-byte WAV**, comprising a 44-byte header and 79,872
mono 16-bit samples at 16 kHz: **4.992 seconds**. The stored file was parsed and
verified locally, with mode `0600`. It was not listened to, transcribed or sent
to a provider. The fixed panel asset has the same hash as the earlier card.

| UTC, 21 October 2026 | Observation |
| --- | --- |
| 20:02:46 | Local presign HTTP 200, 131-byte JSON; complete multipart WAV upload accepted with HTTP 200 and zero response bytes |
| 20:02:47 | Finalize requested `landscape`; HTTP 200 with 110-byte JSON containing `status: completed` and `presigned_url` was accepted |
| 20:02:49–20:02:52 | HTTP 200 with exactly 2,304,000 panel bytes; firmware measured 4,665 ms for download |
| 20:03:00–20:03:02 | Eight controller blocks sent, all ICs ready, display refresh started |
| 20:03:39 | Driver reported display refresh complete |
| 20:03:41–20:03:54 | Discharge sequence completed; all power switches disabled; processing/rendering reported success |
| 20:03:54–20:04:12 | Voice result saved to flash; frame reported success and returned to ready |
| 20:04:14 | Vendor polling resumed with the normal settings snapshot |

The owner still saw the correct test card but did not independently confirm the
refresh, suggesting the coloured LED might mean work was ongoing. Because this
test intentionally reused identical pixels, that observation cannot distinguish
the previous image from the new delivery. The logs establish a completed stock
client and driver sequence; they are not optical proof that new pixels appeared.
No second image was queued. The driver had finished before the cache save and
ready-state transition, which explains why display completion and workflow
completion must be tracked separately.

Unlike the poll-delivered image, which was saved while refreshing, the voice
result was saved **after rendering and panel discharge**. The reported 69.434-second
processing timer ended before the further approximately 18.55-second cache save.
Do not use that timer alone as time-to-ready. The final `/api/info` comparison
showed unchanged settings and display/maintenance fields; only battery voltage,
local time and uptime changed. In particular, `display.last_refresh` did not
acknowledge this completed voice workflow.

The 300-second routing window was cleaned up early after download: both DNS
replicas and the exact TCP translation were checked, normal vendor DNS and
polling resumed, and the fixture stopped. The window's later timed cleanup also
succeeded. Fixture source SHA-256:
`9c7641d91bf3b6cbf488fc6859a6299a966c160f275ae9199260b3bb882577cd`.

This closes C09's host and physical **transport/driver** round trip with a fixed
asset. It does not establish actual STT/generation, HA library insertion, durable
job recovery, retry/cancellation correctness, distinct-image optical confirmation
or a reliable machine-readable display acknowledgment.

## Negative TLS controls: C03

An idle-only experiment on Large 0.2.29 tested certificate trust and hostname
validation separately. It offered no image or firmware and changed no settings.
Short-lived test certificates used the existing leaf key: one self-signed for
the correct API hostname, and one issued through the accepted chain but with
only `wrong-host.invalid` in its subject/SAN. A matching control used the same
generated certificate profile with the correct API hostname.

Five host TLS checks passed: accepted matching control; rejected self-signed
certificate under the normal test-root trust; accepted that certificate when
explicitly trusted; rejected the wrong hostname under the accepted chain; and
accepted that chain when the client expected its test hostname. OpenSSL verified
the generated matching control too. This separated name/trust failures from
certificate construction errors before interpreting the device result.

| UTC, 21 October 2026 | Large-frame result |
| --- | --- |
| 20:15:13, correct name but untrusted self-signed certificate | Bundle verification failed, handshake `-0x3000`, HTTP 0 / `ESP_ERR_HTTP_CONNECT`; server received a TLS access-denied alert, no HTTP request |
| 20:15:44, accepted issuer chain but wrong hostname | Peer verification failed, handshake `-0x2700`, HTTP 0 / `ESP_ERR_HTTP_CONNECT`; server received a bad-certificate alert, no HTTP request |
| 20:16:15, original accepted control | Successful TLS handshake and 89-byte idle response |
| 20:16:45, newly generated matching-profile control | Successful TLS handshake and 89-byte idle response |
| 20:17:15, routing restored | Successful vendor poll with its normal settings snapshot |

The generated name-matching control matters: its successful device handshake
checks that the wrong-name certificate was otherwise usable by this client.
These results support trust-chain and hostname enforcement for this build's poll
path. They do not test every HTTP consumer, expired/revoked chains, every malformed
certificate or the Standard frame's negative cases.

Both failures also produced a generic log suggesting the task endpoint might not
be implemented. That message followed a failed TLS handshake; it was not an HTTP
404/501 or evidence that the route was missing. Diagnose the earlier TLS error
and observed server traffic rather than that generic explanation.

The 180-second routing window was cleaned up early; both DNS replicas and the
exact NAT rule were checked, and the timed cleanup later succeeded again. All
TLS test listeners were stopped. Settings and exposed maintenance/display fields
were unchanged. A matching local control restored the intended future album
deadline before normal vendor polling resumed; this does not independently test
deadline persistence throughout the failed handshakes.

Final fixture SHA-256:
`9db16cf1a503420a525172db0fb4c0581113c78c3df3cde17eda795095d0fbd6`.
Certificates, private keys and raw captures remain outside the repository.

## What remains before a usable local backend

- Expand the validated short-recording path to controlled response faults,
  cancellation and duration boundaries.
- Add STT and generation through a separately chosen provider to the validated
  fixed-image workflow. Keep original artwork and job/transcript metadata in HA's
  library; neither provider execution nor library insertion was part of these tests.
- Replace snapshot responses with durable device/job/album state; implement replay,
  expiry, ownership and reload recovery. The host fixture's duplicate handling
  does not establish production durability or stock-firmware retry behavior.
- Coordinate polling and scheduled content with voice so shared frame memory is
  not overwritten. Serving a download is not proof of a completed panel refresh.
- Retain canonical artwork independently of the frame's single-file cache.
  Its [save/load checks](storage-and-configuration.md#cache-success-and-failure-leave-different-state-behind)
  do not establish integrity or durability, and mount recovery can format the
  artwork partition. A successful cache or mount log is not a durable image receipt.
- Test WAN loss, local time and cold boot separately. This experiment left public
  reachability probes and SNTP available and preserved existing pairing.
  The later [NTP receive trace](boot-and-scheduling.md#ntp-response-contract-and-clock-application)
  calls for accurate time in plain 48-byte server responses; a zero timestamp
  becomes 2036 and is not a safe placeholder. Local-NTP compatibility is untested.
- Establish a sustainable URL/trust configuration. The short-lived test chain for
  the vendor hostname proves compatibility; it is not an owner-controlled hostname
  or a durable deployment mechanism. No arbitrary self-signed acceptance was shown.
  Both builds contain an [outbound `.local` resolver](boot-and-scheduling.md#outbound-local-names-and-blocking-resolution),
  so a consistently lowercase local name is a candidate for returned asset URLs
  and a future configurable API origin. Fresh resolution differs from cached or
  coalesced requests. Multicast reachability, certificate identity and the separate
  public connectivity/time dependencies still need validation; no such hostname
  was tested on a frame in this static pass.
  Its [DNS reply parser](boot-and-scheduling.md#dns-replies-for-a-local-backend)
  expects a matching active transaction with an echoed question and exact IN
  classes. An unsolicited mDNS announcement or cache-flush-class answer alone
  does not establish compatibility. Twenty-six isolated packet cases support
  the parser contract; real multicast delivery remains untested.
  The [connection path](cloud-protocol.md#address-selection-does-not-recover-from-a-bad-ipv4-destination)
  also prefers IPv4 at DNS lookup and does not switch to another family after a
  TCP/TLS failure. A reachable AAAA record is not a substitute for a reachable A
  record in that case; test backend addressing from the frame's network.

Hardware inspection and custom-firmware boot/recovery tests remain deferred under
the owner's closed-enclosure preference. They are not prerequisites for further
bounded backend protocol experiments using the already-proven transport.
