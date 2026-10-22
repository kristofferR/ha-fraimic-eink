# OTA updates and recovery

[Research index](README.md)

Custom-image boot acceptance and physical recovery are **unknown**. No custom
app, rollback, eFuse change or flash write was attempted during this research.
The downloaded stock app is not a full-device backup.

## Two update paths

| Entry | Input | Verification behavior |
| --- | --- | --- |
| `0x4202bb88` | Older manifest: URL, size, SHA-256 | Separate manifest hash verification |
| `0x4202c514` | Direct presigned URL, used by current pending-update workflow | Explicitly skips the separate manifest SHA-256; still uses ESP image validation |

The current poll parser accepts `firmware: {version, presigned_url}` and passes
it to `0x4202ba20`. The direct update downloads into the inactive OTA partition
through `esp_ota_begin`/write/end and selects the next boot slot. It checks HTTP
status, declared-length completion and partition capacity. Its apparent response
MIME check actually reads request headers; invalid image bytes are rejected later
by the OTA/image routines. These checks do not prove that a modified app will pass
every bootloader/eFuse check.

Espressif documents the inactive-slot and app-confirmation mechanism in the
[ESP-IDF v5.4.1 OTA guide](https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/system/ota.html).
The stock image has a valid checksum/appended hash but no standard appended
Secure Boot v2 signature sector. Secure boot configuration, flash encryption,
anti-rollback and the complete partition map remain unverified on this device.

### Direct-download framing and failure boundaries

The direct path configures a 30,000 ms HTTP transport timeout and 4,096-byte
receive/transmit buffers, manually opens the connection and fetches headers,
then requires status 200. There is no redirect loop, Range/resume request or
in-function retry. A logged suggestion to retry a server error is not an actual
retry in this function; later offers and the failure cooldown are separate.

The content-type call at this boundary is `0x4206d664`, the request-header getter.
It reads the same client `+0x20` header table as setter `0x4206d4a4`, matching
[`esp_http_client_get_header` in IDF 5.4.1](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c).
The direct updater does not set a request Content-Type. Its `text/html` /
`text/plain` string checks therefore do **not** establish a response-MIME filter.
This corrects the earlier claim that this guard rejects text error pages.

| Condition | Recovered behavior |
| --- | --- |
| Negative header-fetch result | Reject before OTA begin |
| Declared length exceeds selected partition size | Reject before OTA begin |
| Header-fetch result is zero, including unknown/chunked length | Begin sequential OTA, skip the read loop, then fail finalization because zero bytes were written |
| Positive read | Pass the returned bytes directly to `esp_ota_write` |
| Negative read, including EAGAIN | Abort this attempt; no read retry in this updater |
| Zero read before declared length | Fail as premature close |
| Completed byte count differs from declared length | Abort rather than select the new boot slot |
| Declared bytes received | Close HTTP, finalize/validate the image, then validate/select the boot partition |

The zero-length path can log “Download complete” before finalization fails. It
does not install an empty image. Unlike the panel-image downloader, this loop
cannot consume a chunked/unknown-length firmware body: its loop bound is the
header-fetch length. Serve firmware with a positive exact Content-Length if an
update is ever deliberately enabled.

The additional download timer begins after OTA initialization and is checked
only after successful chunk writes. GNU disassembly confirms a threshold of
600,000,999 microseconds, corresponding to elapsed whole milliseconds exceeding
600,000. It is not an independent watchdog or a hard ten-minute deadline covering
DNS, TLS, headers, a blocking read or final image verification.

### Rejection can still change the inactive slot

`0x42045694` receives size `-2`, the sequential-write mode. This avoids an upfront
partition erase, but `0x420450bc` erases newly needed sectors **before** checking
the first data byte for ESP image magic `0xe9`. The ordering is present in GNU
instructions at `0x4204511d` / `0x42045133` before the comparison at `0x4204514a`.
A successful erase followed by a bad first byte can therefore damage the previous
contents of the inactive slot even though the new image is rejected. This is a
static inference about the failure path, not an induced flash failure.

Abort `0x42045238` frees the OTA context; it does not restore erased or written
bytes. Finalization `0x42045264` rejects zero written bytes, otherwise calls image
verification; only successful finalization proceeds to boot selection
`0x420453bc`. These boundaries agree with the matching
[IDF OTA implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/app_update/esp_ota_ops.c).
Thus “the update failed” is not evidence that both application slots retain their
old contents. No error-page, truncated-image or rollback experiment was run on
either frame.

The SDK includes a runtime flash-encryption branch in the write routine and a
pending-validation check in begin. Their compiled presence does not establish
this device's eFuse state or actual bootloader rollback policy.

## Update policy

The recovered path does **not** consult `autoUpdateEnabled` before queuing or
installing a server offer:

- The setting resides at `0x3fca6b41`; load/save/update routines reference it.
- Its getter `0x420158b4` has recovered calls only from `/info` and `/api/info`.
- `0x4202ba20` checks initialization, nonempty version/URL and failure cooldown,
  then queues the update. It does not compare offered versus current version.
- `0x4202b984` simply returns the pending flag.
- Main-loop and pre-sleep installation consult pending plus `0x42016400`.

The vendor may enforce the preference server-side by withholding offers. A local
emulator must do the same intentionally; sending `autoUpdateEnabled=false` is not
sufficient. Repeatedly offering the same version/artifact can cause repeated
installation attempts. This is a strong static finding, not a live update test.

A URL-only modified app retains the compiled stock version unless it is separately
changed. Track an explicit artifact identity and rollout decision outside a simple
version-string equality check.

The vendor `/dev` switch deliberately asks for an update by storing `cur_ver`
as `0.0.0`. The next poll normally reports that value once and restores the normal
stored version before sending its request. A failed request can consume the
override; failed restoration can leave it active. See the
[mode-switch trace](storage-and-configuration.md#update-solicitation-and-cached-artwork).
This is another reason to implement a configurable local backend separately from
the existing environment toggle. No development-mode poll or update was attempted.

## Safety predicate

`0x42016400` checks:

- recording is inactive;
- the display and get-started render are not busy;
- battery check passes or charging status is accepted;
- Wi-Fi is connected;
- system time is synchronized;
- uptime is at least 60 seconds.

The predicate also runs before pre-sleep installation and while waiting for button
activity. These gates are internal behavior, not proof of a public update API or
a guarantee that all undesirable update timing is prevented.

### Apparent battery scale mismatch

`0x4202d6b4` maps 3,000–4,200 mV to a nominal percentage and accepts at least 30%.
Its input, `0x42029d60`, doubles the gauge reading to pack voltage. The post-OTA
health check uses the same getter and expects 5,000–9,000 mV. Consequently a normal
pack reading above 4,199 mV takes the pre-check's 100% branch.

This is an apparent one-cell/two-cell scale mismatch supported by the instructions.
It is separate from the [deferred cable-detection observation](evidence-and-open-questions.md#battery-observation).
It was not tested with an update at low charge. Do not treat the nominal 30% gate
as verified pack state-of-charge protection.

## First boot and confirmation

`0x4202ce1c` checks the OTA state. For a pending-validation image it checks access
to a PSRAM buffer and a plausible battery/I2C reading, waits about ten seconds,
then marks the app valid or asks for rollback.

It does not require successful communication with the configured cloud API before
confirmation. A bad custom URL could therefore leave a hardware-healthy app
confirmed and unable to reach its backend. Keeping the local API working is useful,
but is not yet a proven recovery mechanism for every failed modification.

Future firmware health checks should cover the changed functionality and retain
an owner-accessible way to correct backend configuration. Whether the actual
bootloader reliably returns to the previous slot still needs a controlled test.

### App-side confirmation is real, but is not a recovery guarantee

The application contains working OTA-data operations, rather than unsupported
stubs. Boot selection `0x42045328` obtains its new-state value from
`0x420e30b0`, which returns **0 / NEW**. Confirmation wrapper `0x420455e8`
calls `0x42045514(true)`; rollback wrapper `0x420455f4` calls the same function
with false. The state values are NEW=0, PENDING_VERIFY=1, VALID=2, INVALID=3 and
ABORTED=4, matching the
[SDK record definitions](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/bootloader_support/include/esp_flash_partitions.h).

The NEW-state setter and the previously traced pending-image check in OTA begin
match the SDK's rollback-enabled application branches. This establishes compiled
app-side support; it does **not** read the separately installed bootloader,
its configuration, the current OTA records or either unit's actual eFuses.

Confirmation locates the active OTA record. If already VALID it returns zero;
otherwise it rewrites that record as VALID and returns the storage result.
The application health checker propagates confirmation failure, but its background
initializer only logs that failure and continues. That initializer calls the
health checker at `0x42016bf6`, before its Wi-Fi-start call at `0x42016c44`.
The recovered ordering therefore supplies no test of the configured backend,
local time service or voice/image workflow before confirmation.

If reading the running partition's state fails, the health checker also returns
zero without running its pending-image tests. This can be a non-OTA/factory case
or another state-read failure; its zero result alone does not mean health was
checked or an app was newly confirmed.

### Rollback requires a usable alternate image

Checker `0x4204546c` reads both OTA records, chooses the active one, then examines
the other. An eligible alternate record maps to a slot with
`(sequence - 1) % app_partition_count`; that partition must exist and pass image
verification. If the alternate record is ineligible, the compiled function can
instead try a factory partition. A missing/invalid image or missing usable record
can leave no rollback candidate. The downloaded vendor app does not establish
what is currently in those on-device slots.

Record eligibility is weaker than confirmed application health. Helper
`0x420e30b8` rejects an erased sequence or INVALID/ABORTED state; `0x42045e78`
also checks the sequence CRC. It does not require state VALID. The subsequent
image-format check is not a test that the alternate app can reach the backend.
Thus the SDK's “previously worked” log should not be treated as proof of a fully
functional fallback image for the owner's intended configuration.

With no candidate, the rollback request returns `0x1505` without invalidating
the active record or restarting. With a candidate, it marks the active record
INVALID, rewrites it and calls restart **only if that write succeeds**. The
matching [SDK implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/app_update/esp_ota_ops.c)
corroborates the API meanings; the conditions and constants above were checked
in the downloaded Large binary.

The application health-failure branch increments its rollback counter, records
failure and sets visible/internal failure state **before** calling this API.
At `0x4202d193` it discards a returned rollback error and returns the earlier zero
status. The background initializer can therefore continue into network startup
after a failed rollback request. A changed `rb_cnt` or “triggering rollback” log
is evidence of an attempt, not evidence of another app booting. No failed-health
or rollback experiment was performed.

### OTA metadata and anti-rollback evidence remain separate

Reader `0x42044f64` loads two 32-byte records, one at each erase-sector boundary
of the OTA-data partition. Rewriter `0x42044ff0` updates the sequence and its CRC,
erases the selected record's sector, then writes 32 bytes. It returns an erase
or write error and has no readback in this helper. The CRC routine at
`0x42045e64` covers the four sequence bytes, not the image or all record fields.
Preserving application bytes alone therefore does not preserve boot-selection
state. Interrupted metadata writes and the bootloader's resulting choice remain
untested.

In the examined Large app, boot selection proceeds from image validation to OTA
record rewriting without the SDK's optional explicit secure-version check.
Rollback-candidate validation also lacks that optional check, and successful
confirmation returns after the record write without the optional eFuse
secure-version update. These paths match the SDK's **anti-rollback-disabled
application branches**. This does not establish the installed bootloader's policy,
actual secure-version eFuses, all image-validation checks or acceptance of a
downgrade/custom image. R02/R03/R05/R09 remain open.

## Failure tracking and reporting

The Large application's cooldown is a best-effort wall-clock mechanism, not a
durable rollout lock. `0x4202b8a8` writes `ota_data/ota_fail` as a 56-byte blob:

| Offset | Stored field |
| --- | --- |
| 0 | Version, 16-byte field; ordinary writes copy at most 15 bytes |
| 16 | Unsigned one-byte failure count |
| 17–19 | Padding |
| 20 | Low 32 bits of the failure's epoch time |
| 24 | Reason, 32-byte field; ordinary writes copy at most 31 bytes |

The writer increments the count when the loaded version matches its argument;
otherwise it starts at one. Increment is not saturated: a synthetic count of 255
wraps to zero. This does not establish that ordinary operation reaches 255, since
the cooldown usually blocks earlier. The save helper checks set/commit results,
but the writer discards its returned error and logs the attempted count anyway.

### Cooldown clock and version boundaries

Queue helper `0x4202ba20` zeroes the record, calls loader `0x4202b550` and ignores
its result. The loader supplies a 56-byte capacity but does not validate the
returned length. A failed read that leaves the destination untouched therefore
leaves zero failures; other partial-read/malformed-record behavior was not tested.

For count at least three and an exact version match, it tests positive current
time and a nonzero saved timestamp, then computes signed whole hours
`(now - saved_timestamp) / 3600`. GNU instructions confirm signed ROM division
`0x4000225c`, identified as `__divdi3` in the
[ESP32-S3 ROM map](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_rom/esp32s3/ld/esp32s3.rom.libgcc.ld).
The comparison uses the quotient's low 32 bits as unsigned, blocking values 0–23.

| Time relative to the saved failure | Queue result for a matching version with at least three failures |
| --- | --- |
| Same time through 23 h 59 m 59 s later | Reject with `0x103`; leave previous pending contents intact |
| Exactly 24 hours later | Attempt to clear failure tracking, then accept |
| Saved failure 1–3,599 seconds in the future | Signed division truncates to zero; still reject |
| Saved failure 3,600 seconds or more in the future | Negative hours become a large unsigned value; attempt clear, then accept |
| Current time zero/negative, or saved timestamp zero | Attempt clear, then accept |

Clear helper `0x4202b5f0` ignores erase and commit results. Its “cleared” log is
not storage confirmation, and a failed clear does not stop the current acceptance.
These clock cases were reproduced in a host reconstruction, without changing a
device clock or NVS record.

The poll passes the complete parsed version string into the queue helper. The
helper compares that string **before** truncating it into a 15-byte pending value.
Main-loop and pre-sleep failures pass that truncated pending value to the failure
writer. Consequently, an offer longer than 15 bytes does not match its own saved
failure version on the next poll and can evade the three-failure cooldown. Two
different long versions with the same 15-byte prefix also share the stored identity.
The pending URL is independently truncated to 2,047 bytes, without a length error.

### Pending offers are replaced, not revoked by an empty poll

An accepted offer overwrites the shared version/URL buffers and sets the pending
flag, even if another offer was already queued. An invalid or cooldown-blocked
offer returns before those writes, retaining the previous offer. A poll with an
absent, null or unusable `firmware` object simply skips queuing; it does not clear
an already pending offer. Withholding offers prevents new installations from being
queued, but is not a revocation protocol for one already accepted.

Getters `0x4202b9d8` and `0x4202b9fc` return pointers into these RAM buffers, not
copies. Clear helper `0x4202b990` resets the pending flags and zeroes both buffers;
it does not erase the failure record. Both direct-install callers record a failed
attempt before clearing this pending state. No concurrent replacement, restart
persistence or update was exercised. A future adapter should use explicit rollout
state, short unambiguous wire versions and immutable artifact identities, while
keeping offers disabled until deliberate update support exists.

### Result reporting

`0x4202d1d0` consumes result state while the poll URL is being assembled, before
the HTTP transaction succeeds. A failed request can lose the report. It reports
the compiled version string, not a durable image hash. Backend rollout tracking
must not assume every result is delivered exactly once or accurately identifies a
URL-only modified artifact.

The reporting getter reads the initialized flag at `0x3fcabd80`, state word at
`0x3fcac618` and error word at `0x3fcac614`:

| Input state | Report and immediate RAM change |
| --- | --- |
| Initialized, state 7 | Success with compiled `0.2.29`; state becomes zero, error word is left unchanged |
| Initialized, state 8 and nonzero error | Failure with compiled `0.2.29` and a fixed error-category string; state and error both become zero |
| Uninitialized, other state, or state 8 with zero error | No report; state/error remain unchanged |

Error codes 1, 2, 4, 6, 8 and 9 select network, checksum, partition-space,
download, boot-health and server-error descriptions respectively; other nonzero
codes select the generic unknown-error message. These are reporting labels, not
proof that each validation was executed by every update path. In particular, the
older checksum label does not add a payload-hash check to the direct updater.

The poll calls this getter before SSID/orientation preparation, URL-length
validation and HTTP-client creation. A rejected overlong URL or later allocation,
connection or response failure has already consumed the report. A subsequent
poll does not resend it automatically. The request's separate `current_version`
can be the one-poll `0.0.0` override while `ota_version` remains `0.2.29`.
Twenty-seven combined host cases verify selected URL/encoding and report-state
boundaries, including one-shot consumption and URL rejection. They do not perform
an update, induce a network failure or establish actual boot outcome delivery.

NVS includes `ota_fail`, `pend_force`, `force_ver`, `cur_ver`, `last_ver`,
`upd_cnt`, `rb_cnt`, `boot_cnt` and `last_ts`. Names alone do not establish that
every forced-version mechanism remains active in this newer direct-download path.

### Legacy manifest and retained bookkeeping

The recovered direct call sites separate the paths:

| Caller | Path |
| --- | --- |
| Poll `0x4202475c` | Queue version/URL through `0x4202ba20` |
| Main loop `0x42012810` and pre-sleep `0x42012338` | Direct updater `0x4202c514` |
| `/action?mode=ota`, `0x4201c740` | Read saved manifest `0x4202d780`, then older updater `0x4202bb88` |

The factory/test POST handler is not another firmware-upload entry point: its
upload branch handles a panel image. The legacy action requires registration and
the safety predicate. It does not accept a new firmware URL as an action parameter.

Manifest loading reads `ota_data/ota_url` into a 2,048-byte string,
`ota_sha256` into 65 bytes and `ota_size` as a 32-bit value, then validates them.
No writer to the URL/size manifest was recovered in the current queue path.
The cleanup helper `0x4202d750` erases `ota_ver` and `ota_sha256`, rather than
clearing every manifest key. An old saved manifest must not be confused with a
new poll offer.

Direct references to `pend_force` lead to initialization `0x4202d484` and
health confirmation `0x4202ce1c`: loading/clearing it and, when appropriate,
writing `force_ver`. No current `pend_force` writer was recovered. The offered
version queued in RAM is not evidence that this legacy key survives reboot.
This is a bounded negative result from references, not proof against all possible
indirect or differently named persistence paths.

Statistics have reset semantics: initialization increments `boot_cnt`; successful
pending-image confirmation increments `upd_cnt`, resets `rb_cnt` to zero and
`boot_cnt` to one, and writes the timestamp/compiled version. A failed health
check increments `rb_cnt`. Thus rollback and boot counters are not lifetime totals.
Actual rollback, persistence failures and custom-version reporting remain untested.

## Minimal customization and outstanding prerequisites

The central production URL literal fits at most its original 26-byte string length
without relocation. Any binary patch must preserve layout and regenerate the ESP
image integrity fields. That is a candidate approach, not a prepared update.

A lasting implementation should provide an owner-controlled API URL and trust
configuration, local NTP, backend-aware connectivity checks, and recovery access.
Avoid making normal operation depend on the compromised certificate chain used in
the initial owner-scoped experiment.

Before relying on custom firmware, establish:

1. Full partition layout and a backup strategy for bootloader, application slots,
   NVS/provisioning and calibration, rather than only the app image.
2. Actual secure-boot, flash-encryption and anti-rollback configuration.
3. A reliable recovery entry despite the reported lack of a USB serial interface.
4. Controlled update/confirmation/rollback behavior with the current hardware.
5. A reviewable minimal patch and a way to restore the stock app/configuration.

No physical test points, ROM-download entry sequence or recovery command have
been verified here. Do not infer them from generic ESP32-S3 boards.
