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
status, download completeness and partition capacity, and rejects obvious text
error pages. None of that by itself proves that a modified app will pass every
bootloader/eFuse check.

Espressif documents the inactive-slot and app-confirmation mechanism in the
[ESP-IDF v5.4.1 OTA guide](https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/system/ota.html).
The stock image has a valid checksum/appended hash but no standard appended
Secure Boot v2 signature sector. Secure boot configuration, flash encryption,
anti-rollback and the complete partition map remain unverified on this device.

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

## Failure tracking and reporting

`0x4202b8a8` records failed offered version, count, timestamp and reason in NVS.
`0x4202ba20` blocks the same version after three failures for up to 24 hours based
on wall-clock time. Missing/unusable time bypasses that timed block and clears
tracking in the corresponding branch. This is not an immutable recovery lock.

The pending version buffer holds 15 characters plus NUL; the URL holds 2,047 plus
NUL. Avoid truncation-driven version collisions in any update naming scheme.

`0x4202d1d0` consumes result state while the poll URL is being assembled, before
the HTTP transaction succeeds. A failed request can lose the report. It reports
the compiled version string, not a durable image hash. Backend rollout tracking
must not assume every result is delivered exactly once or accurately identifies a
URL-only modified artifact.

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
