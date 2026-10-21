# Storage and configuration

[Research index](README.md)

## NVS is not the image filesystem

Observed boot logs report encrypted NVS. That does not establish whole-flash
encryption, secure boot, or the ability to restore NVS from an app download.
The image cache uses a separate FAT partition labeled `imagedata`.

These are recovered key names, not key values or instructions to edit live NVS.
The table is useful for a future migration/backup tool; it is not an exhaustive
schema or a guarantee of compatibility between releases.

| Namespace | Keys | Purpose / evidence |
| --- | --- | --- |
| `app_data` | `server_mode` | Production/development selector, `0x42017670` |
| `app_data` | `device_key_p`, `user_id_p`, `email_p`, `email_vp` | Production identity/verification |
| `app_data` | `device_key_d`, `user_id_d`, `email_d`, `email_vd` | Development identity/verification |
| `app_data` | `device_key`, `user_id`, `email_addr`, `email_verified` | Legacy production aliases/migration |
| `app_data` | `wifi_ssid_p`, `wifi_pass_p`, `wifi_ssid_d`, `wifi_pass_d` | Per-environment Wi-Fi backup keys |
| `app_data` | `timezone` | Shared POSIX timezone string |
| `app_data` | `voice_rec`, `keep_awake`, `auto_update`, `chg_led` | Four device switches |
| `app_data` | `refresh_sched` | Maintenance scheduling record |
| `app_data` | `refresh_hist` | Five-entry maintenance timestamp ring; [not an image-delivery ledger](rendering-and-concurrency.md#displaylast_refresh-is-maintenance-history) |
| `app_data` | `sched_img_time` | 64-bit next album-image epoch |
| `app_data` | `wake_reason` | Maintenance versus album timer reason |
| `app_data` | `deep_sleep`, `storage_mode`, `last_sleep_ts` | Sleep state and timestamp |
| `app_data` | `wakeup_img` | First-time wake-up image state |
| `app_data` | `img_version` | Version associated with installed instruction artwork |
| `app_data` | `sys_img` | Persisted compressed system-screen marker |
| `app_data` | `wifi_stats` | Wi-Fi diagnostic state |
| `ota_data` | `cur_ver`, `last_ver` | Reported/stored OTA versions |
| `ota_data` | `ota_fail` | Failed version, count, timestamp and reason |
| `ota_data` | `pend_force`, `force_ver` | Pending/confirmed forced-version bookkeeping |
| `ota_data` | `upd_cnt`, `rb_cnt`, `boot_cnt`, `last_ts` | OTA statistics |

## Identity layout and migration

`0x420189c0` loads an in-memory configuration with these capacities:

| Offset | Field | Capacity including terminator |
| --- | --- | --- |
| `0x00` | Account email | 100 bytes |
| `0x64` | POSIX timezone | 32 bytes |
| `0x84` | Device key | 65 bytes |
| `0xc5` | User ID | 65 bytes |
| `0x106` | Email verified | One byte |

It selects production or development identity keys from `server_mode`; timezone
is shared and falls back to `EST5EDT` if its read fails.

`0x42018af0` saves those fields. In production it also writes legacy aliases
`device_key`, `user_id`, `email_addr` and `email_verified`. `0x42017350` migrates
legacy user/email/verification fields into production-suffixed keys when the new
keys are absent. Partial knowledge of one key is insufficient for a safe identity
migration, reset or restore.

The password-gated `/dev` flow selects vendor staging, not an arbitrary local
backend or a shell. Mode switching preserves/restores separate identity and
Wi-Fi state, resets OTA version reporting to `0.0.0`, and can require enrollment.
It was not activated during this research. A custom backend setting should be
separate from this vendor-environment switch.

## Mounting the image partition

`0x42028368` finds the `imagedata` data partition and mounts `/imagedata` through
the FAT/wear-leveling path, allowing four open files and a 4,096-byte allocation
unit. Its initial format permission depends on `0x420282f8`:

- If the legacy `device_key` cannot be read/found, it considers the unit
  unprovisioned for this check and enables format-on-mount-failure immediately.
- Otherwise it attempts mounting three times, then tries again with formatting
  enabled if those attempts fail.

This couples cache recovery to a legacy provisioning key. A temporary NVS read
error or changed provisioning scheme can affect this decision. It does not mean
the partition is always formatted at startup, but it must not be the only copy
of artwork the user expects to retain.

Actual partition capacity, free space and endurance have not been established
from a full partition table. Two full Large panel images already total 4,608,000
bytes; do not promise an offline multi-image playlist just from the 16 MB header.

## Last artwork

`/imagedata/last_image.bin` is the recovered single-image persistence mechanism.

`0x42028524` writes directly with `fopen(..., "wb")`, `fwrite`, flush, `fsync`
and close. It accepts at most 2,566,144 bytes. It does not perform a temporary-file
rename transaction. The `fsync` error is logged but success is determined by the
write byte count. Interrupted overwrites can leave a partial file.

`0x42028698` verifies nonzero file size, destination capacity and a complete read.
It does not perform a content hash check. The local API's render-start wrapper
logs save failure and continues rendering, so HTTP acceptance does not guarantee
the image can later be restored. See [local upload](local-api.md#image-delivery).

**Proposed:** atomic replacement, content hash metadata, distinct cache/display
results, and backend restoration from canonical HA assets. Flash wear policy and
filesystem support for the chosen atomicity strategy need validation.

## Three different kinds of system artwork

### Wake-up screen: embedded raw image installed to FAT

The `wake_up` asset occupies DROM `[0x3c140614, 0x3c372e14)`, exactly 2,304,000
bytes. `0x4202aae0` checks `img_version`, existence and readable length, and
installs `/imagedata/system_images/wake_up.bin` when needed.

The validator `0x42028ae8` checks the expected length and reads through the file.
It does not compare content with the embedded bytes or calculate a checksum.
A same-size altered/corrupted image can pass that validation. A missing/truncated
file or a firmware-version change can cause reinstallation. This makes custom
boot artwork plausible, but a filesystem patch alone is not guaranteed to survive
upgrades or cache recovery.

### Account/setup screens: fetched from the backend

Instruction IDs 1 and 2 are `create_account` and `get_started`. Their dispatcher
branch downloads them instead of falling back to local files. On applicable
image-version/migration paths, `0x4202a8d4` also deletes old
`system_images/create_account.bin` and `get_started.bin` files.

This is why a generic claim that all system screens are cached would be wrong.
The optional save flag in the instruction-render path saves to `last_image.bin`,
not a persistent cache of every server-keyed system screen.

### Low-battery status: embedded RLE, preserves last artwork

`0x4202f8bc` resolves the `low_battery` asset from DROM
`[0x3c372e18, 0x3c3a7b56)`. `0x4202fc34` expands it into the image buffer and
requests rendering without overwriting `last_image.bin`. It records `sys_img`;
`0x4202f970` recognizes `low_battery` on reload and clears unknown marker values.

The decoder at `0x4202fa0c` expects:

1. An even-length stream of two-byte `(color, run_length)` pairs.
2. Eight controller blocks, each containing 720 rows of 800 padded pixels.
3. Nonzero one-byte run lengths that stay within each row; a run cannot cross
   its row boundary.
4. Adjacent expanded pixels packed high nibble first into the output byte.
5. A destination of at least 2,304,000 bytes.

It rejects exhausted input, zero runs and row overruns. This is the embedded
status-asset format, not an additional network format accepted by `/api/image`.
Use valid Spectra 6 color indices in any generated asset; decoder mechanics alone
do not establish a complete palette-validation contract.

A host-side decoder reconstructed from these rules consumed all **216,382 input
bytes** and produced exactly **2,304,000 bytes**, with no invalid runs or leftover
input. The asset uses only palette values `0, 1, 2, 3, 5, 6`. Output SHA-256:
`a1db1ecf37389628588baf3c2d44912318087759eb55558dfaa4b834236721be`.
This validates the recovered format against the embedded asset, not a new panel
render. Neither the embedded nor decoded vendor artwork is included here.
