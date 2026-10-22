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
| `app_data` | `force_ftu` | Development first-time-setup override; stale production value is cleared |
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
| `app_data` | `deep_sleep`, `storage_mode`, `last_sleep_ts` | Sleep flags and timestamp also advanced after conditioning |
| `app_data` | `wakeup_img` | First-time wake-up image state |
| `app_data` | `img_version` | Version associated with installed instruction artwork |
| `app_data` | `sys_img` | Persisted compressed system-screen marker |
| `app_data` | `wifi_stats` | Wi-Fi diagnostic state |
| `ota_data` | `cur_ver`, `last_ver` | Reported/stored OTA versions |
| `ota_data` | `ota_url`, `ota_sha256`, `ota_size`, `ota_ver` | Legacy manifest reads/cleanup; not the current poll queue's RAM URL |
| `ota_data` | `ota_fail` | Failed version, count, timestamp and reason |
| `ota_data` | `pend_force`, `force_ver` | Pending/confirmed forced-version bookkeeping |
| `ota_data` | `upd_cnt`, `rb_cnt`, `boot_cnt`, `last_ts` | OTA statistics |

Additional tracing identified legacy manifest string capacities (URL 2,048 bytes,
SHA-256 text 65 bytes), a 32-bit size and 64-bit OTA/sleep timestamp accessors.
The four switch accessors use signed 32-bit storage despite their boolean meaning;
do not infer NVS types from JSON types. The following pass narrows the type/default
map; SDK-owned state, other releases and migration fault cases remain incomplete
(N02/N03).

Initialization at `0x420153b0` can erase and reinitialize NVS on the SDK's
no-free-pages/new-version errors. A recovery plan must cover provisioning and
calibration, not assume that booting an app preserves all configuration under
every storage error. No live NVS erase or migration was attempted.

### Recovered NVS types and record sizes

These are application storage types, separate from in-memory C fields and JSON
types. SDK wrappers and their internal item IDs were checked in GNU disassembly:
U8 `0x01`, I32 `0x14`, U32 `0x04`, I64 `0x18`, U64 `0x08`, string `0x21`, and
the blob-reader item type `0x41`. The mappings agree with the
[matching NVS implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/src/nvs_api.cpp)
and [item definitions](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/include/nvs_handle.hpp).
Capacities below are observed application read/write sizes, not global NVS limits.

| Namespace / keys | Storage type / size | Evidence and fallback behavior |
| --- | --- | --- |
| `app_data/server_mode` | U8 | `0x42017670` / `0x42017974`; only 1 selects development, failed read selects production |
| `app_data/force_ftu` | U8 | Read in `0x420153b0`, written by mode/reset helpers; initialization starts its byte at zero |
| `app_data/wakeup_img` | U8 | `0x42015974` / `0x420159b4`; missing/error or value other than 1 reads false |
| `app_data/wake_reason` | U8 | `0x42015dac`; missing/read error returns zero |
| `app_data/voice_rec`, `keep_awake`, `auto_update`, `chg_led` | I32 | `0x42014780` / `0x42014968`; successful reads convert nonzero to true; failed reads leave existing RAM flags |
| `app_data/email_vp`, `email_vd`, `email_verified` | I32 | `0x420189c0`, `0x42018af0`, `0x42017350`; in-memory verification is one byte, but persistent values are four bytes |
| Per-mode/legacy email, device key and user ID | String | Identity-loader capacities 100, 65 and 65 bytes including NUL; see offsets below |
| `app_data/timezone` | String, 32-byte read capacity | Shared; read failure defaults to `EST5EDT`, successfully read empty string is distinct |
| `app_data/wifi_ssid_p`, `wifi_ssid_d` | Blob, 32-byte ordinary backup | `0x420185ac`; fixed driver field, not a NUL-terminated NVS string |
| `app_data/wifi_pass_p`, `wifi_pass_d` | Blob, 64-byte ordinary backup | Same switch helper; other reset paths can preserve the returned blob length |
| `app_data/deep_sleep`, `storage_mode` | **One-byte blobs**, not U8 | `0x42010674` and pre-sleep paths use `nvs_set_blob`; deep-sleep startup reader uses `nvs_get_blob` |
| `app_data/refresh_sched` | Blob, 32-byte write/read capacity | `0x42014ad4` / `0x42014d48`; I64 epoch at 0, double correction at 8, interval/hour/minute at 16/20/24; loader zero-initializes its destination |
| `app_data/refresh_hist` | Blob, 48-byte write/read capacity | `0x42014b48` / `0x42014d14`; zero-initialized five-timestamp ring with index/count |
| `app_data/sched_img_time` | **I64** | `0x42015d30` / `0x42015d60`; epoch value with a zero-valued RAM cache sentinel |
| `app_data/last_sleep_ts` | **U64** | `0x4202d860` / `0x4202d90c`; written during sleep preparation and after conditioning returns success; set checked, commit unchecked |
| `app_data/img_version` | String, 16-byte read capacity | `0x4202a968` / `0x4202aa48`; missing/read error differs from a readable different version |
| `app_data/sys_img` | String, 32-byte read capacity | `0x4202f970`; recognizes `low_battery`, removes an unrecognized successfully read marker |
| `app_data/wifi_stats` | Blob, 906-byte write/read capacity | `0x4202e8bc` / `0x4202e9b0`; reset path zeroes it and sets byte zero to 2 |
| `ota_data/ota_fail` | Blob, 56-byte write/read capacity | `0x4202b550` / `0x4202b588`; version[16], U8 count at 16, U32 epoch at 20, reason[32] at 24; no returned-length check |
| `ota_data/upd_cnt`, `rb_cnt`, `boot_cnt` | U32 | `0x4202d3a4` / `0x4202b62c` |
| `ota_data/last_ts` | **U64** | Same statistics helpers; distinct from signed album deadlines |
| `ota_data/ota_size` | U32 | Legacy manifest loader `0x4202d780` |
| `ota_data/cur_ver`, `last_ver`, `ota_url`, `ota_sha256`, `force_ver`, `pend_force` | String | Direct string readers/writers; `pend_force` is a version string, not a boolean |

The four switch loader's local fallback integers do not themselves overwrite
the global flags on a failed read. Voice and charging-LED defaults are initialized
to 1 in the app data segment (`0x3fca0c11` / `0x3fca0c10`); the ordinary cold-start
defaults remain voice on, keep-awake off, auto-update off and charging LED on.
A repeated settings load after a read error should not be described as resetting
every flag to those defaults.

The schedule/history loaders pass their capacity to `nvs_get_blob` but do not
check the returned size against 32/48 after success. A smaller stored blob can
therefore leave a zero-filled tail; these functions do not enforce a complete
record schema. The Wi-Fi-statistics loader similarly does not check its returned
length or reject another stored version after a successful read. No malformed
NVS records were injected. A future migration should validate version and exact
record size rather than depend on these permissive readers.

### Failed settings saves are not retried by an identical snapshot

Large setter `0x420158cc` compares the four incoming switches with their RAM
bytes. An exact match returns success without opening NVS. Otherwise it replaces
all four RAM bytes **before** calling saver `0x42014968`. There is no dirty flag
or rollback in this path.

The saver opens `app_data` read/write, then calls the I32 setter separately for
`voice_rec`, `keep_awake`, `auto_update` and `chg_led`, in that order. It stops at
the first failed write, closes the handle and returns that error. Only after all
four writes succeed does it call `nvs_commit`, close and return the commit result.
An open failure returns immediately without writes. Ghidra incorrectly labels
the saver `void`; GNU instructions preserve the selected error in return register
`a2`, and the settings setter returns it to the poll caller.

**Inferred persistence failure:** if saving a changed snapshot fails, RAM still
contains every requested switch. The next identical snapshot returns success
without another save attempt, even if the storage fault has cleared. A snapshot
that differs from RAM enters the save path again. Repeating the same desired
settings is therefore insufficient evidence that they reached persistent storage.

The poll call at `0x4202513a` logs a nonzero setter result, then rejoins normal
response processing at `0x420251f6`, beginning with the `firmware` member. It does
not turn this settings error into a failed poll or request a persistence retry.
A successful poll result and the current RAM switches do not acknowledge a
durable settings update.

Startup has a separate boundary. Loader `0x42014780` returns its **namespace-open
result**, not the individual key-read results. After a successful open, each
successful I32 read sets its RAM flag to `value != 0`; each failed read leaves
that flag unchanged. Missing keys (`0x1102`) suppress the per-key warning; other
read failures log one. Even if all four key reads fail, the loader returns zero.
Startup `0x420167b4` calls the default saver only when the loader returns nonzero,
and does not check that save's result. Individual missing or unreadable keys thus
do not trigger this default-persistence attempt.

These findings were checked against the pinned app with nine bounded function
bodies and two caller regions: 29 GNU ranges and 522 byte-matched instructions,
with contiguous coverage enforced for each range. They are static paths and
inferred failure consequences, not induced NVS faults or reboot observations.
The [Standard comparison](standard-model-comparison.md#settings-persistence-also-matches)
now confirms the selected application paths on that build; the following section
resolves the Large build's lower-level transaction boundary.
For custom firmware, track pending persistence independently of RAM equality,
retry failed saves, and distinguish applied settings from durable settings.

### NVS commit does not make the four switches atomic

The Large application's open path `0x42049e60` → `0x42049de8` → `0x4204b840`
constructs a handle with vtable `0x3c3c3cc4`. Resolving that table in the pinned
image establishes the actual indirect targets, rather than assuming SDK source
alone describes this binary:

| Operation | Compiled path / behavior |
| --- | --- |
| I32 set | `0x42049f68` → `0x42049f3c` → `0x420e34a4`; virtual slot `+0x30` is `0x4204b29c`, with type `0x14` and four data bytes |
| Typed setter | Rejects invalid/read-only handles; otherwise calls storage writer `0x4204af28` immediately |
| Commit | Wrapper `0x42049974` invokes slot `+0x28`, `0x4204b258`; returns success when the handle's valid byte is nonzero, otherwise `0x1107`. No storage flush occurs in this method |
| Close | Removes the API handle entry, destroys its object and frees it; the object destructor removes it from the manager's handle list. There is no settings rollback |

For non-blob items such as these switches, the storage writer checks an existing
same-type value and can return success without writing if it matches. Otherwise
it calls the page writer (`0x4204bee0`), handles page-full/new-page retries, and
then removes any previous item. This is per-key work, not a four-key commit.
The compiled call sequence agrees with the matching
[handle methods](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/src/nvs_handle_simple.cpp),
[storage writer](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/src/nvs_storage.cpp)
and [handle manager](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/src/nvs_partition_manager.cpp).

**Consequences:** a failure on the third switch does not undo successful first
and second setters. A later wake can therefore load a mixture of old and new
switches, while the current wake retains the full requested RAM snapshot. Skipping
the final commit after a set error does not restore the earlier snapshot.
Conversely, a setter error is not proof that it changed nothing: the storage
writer can successfully write a replacement and then fail while removing the
old item, translating flash-operation failure `0x6001` to remove-failed `0x1108`.
The post-reboot resolution of such duplicate/error states was not exercised.

The follow-up checked eleven additional functions over 26 GNU ranges and 416
byte-matched instructions. This resolves the selected Large SDK dispatch and
transaction semantics, not every page/flash fault, power-loss recovery, encryption
or Standard SDK implementation. An emulator should keep its desired settings as
authoritative state and avoid interpreting successful polls as durable receipts.
A firmware change needs explicit persistence status and recovery, rather than
relying on the final `nvs_commit` call to make these four writes atomic.

### A failed schedule clear can reload the old deadline

`0x42015d30` updates the two-word RAM deadline first, then attempts the I64 NVS
write and commit. It does not propagate those errors. Getter `0x42015d60` returns
a nonzero cached deadline without rereading NVS, but **zero means load from NVS**.

**Inferred failure case:** after clearing the RAM deadline to zero, a failed
persistent write can leave an old NVS deadline. The next getter can reload it
during the same wake session, not only after reboot. Conversely, a newly set
nonzero RAM deadline can mask a failed save until restart. This does not mean
ordinary successful poll clears fail; it identifies a persistence-fault boundary
for C02/S03. The firmware needs a separate cache-loaded flag and explicit save
results if this state is extended for local playlists.

### The application also consults SDK-owned Wi-Fi state

Wi-Fi-present helper `0x4201ea80` first asks the driver for its current station
configuration. Only if that API fails does it open **`nvs.net80211`** and query
the blob length of **`sta.ssid`**. A nonzero length passes its fallback check;
it does not inspect the SSID contents there. This is additional recovery-sensitive
state outside `app_data`, not a complete map of the SDK Wi-Fi namespace or proof
that manually restoring one blob is sufficient.

The recovered PHY calibration helpers also open namespace **`phy`**
(`0x420afa00` / `0x420afa4c`). They store `cal_version` as U32, `cal_mac` as a
six-byte blob and `cal_data` as a 1,904-byte blob. Loader `0x420af6e4` checks the
version against the current PHY library, the returned MAC length, the MAC against
the chip's default station MAC, and the exact calibration length. These are
radio calibration records, not microphone or battery calibration, and their
presence in code does not recover this device's installed values. A future
backup/migration scope must include SDK namespaces as well as application keys.

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

The saver returns the selected-key write or commit error; Ghidra's initial `void`
prototype was misleading. GNU disassembly retains that result in the return
register through NVS close. Legacy-alias write results are not checked separately.
The create-account caller ignores the result and updates RAM anyway; sign-in
checks it before reloading. No storage failure was injected.

Sign-in at `0x420192c8` clears byte `0x64` of its identity copy before saving,
so it persists an empty timezone instead of preserving the previous value.
Create-account copies the submitted timezone into the 32-byte field. The loader
only substitutes `EST5EDT` on a failed NVS read, but time initialization and
maintenance calculation also use that fallback for an empty string. This is a
static path to losing a configured timezone, not proof of why the observed Large
was using `EST5EDT`. UTC album deadlines remain a different time domain.
The [timezone parser follow-up](boot-and-scheduling.md#timezone-format-and-default-rules)
also establishes that this field needs a compact POSIX rule, not an IANA name;
an invalid nonempty value can produce UTC instead of the empty-value fallback.

The saved key comes from the local request, not the setup response's key. Email
nonempty and verified=true are insufficient to prove a nonempty user ID for
voice. See the [enrollment parser and callers](cloud-protocol.md#enrollment-boundary).

### Device-key selection and regeneration

Large `0x420176a8` and Standard `0x4201767c` load or generate the key used by
initialization and both local account forms. The three recovered Large callers supply
a 65-byte key buffer and an 18-byte formatted-MAC buffer. This is separate from
the [short discovery suffix](local-api.md#local-discovery-and-hostname-lifetime).

After opening `app_data` read/write, the helper obtains the station MAC and
formats all six bytes as lowercase, colon-separated hex. The MAC-read return
value is ignored. It then reads the environment selector and follows this order:

| Condition | Result |
| --- | --- |
| Selected `device_key_p` or `device_key_d` reads successfully and is nonempty | Return it unchanged; no hex, length-equals-64 or MAC-consistency validation |
| Selected key is empty or any read error occurs; selected `user_id_p` / `user_id_d` is readable and nonempty; legacy `device_key` is readable and nonempty | Return the legacy key and attempt to copy it into the selected environment key |
| Those reuse/migration conditions fail | Derive and save a new key |
| Namespace open fails | Return that error without obtaining a MAC or attempting reuse/generation |

The legacy source is the same unsuffixed `device_key` in both environments.
Development migration is gated by a nonempty **development** user ID, but its
fallback credential can therefore come from the production-era legacy alias.
This is narrower than saying every mode switch copies an account; the switch
itself does not do that, and this branch requires the conditions above.

Fresh generation uses HMAC-SHA256 over the formatted MAC with 32 bytes of
embedded key material, then formats the 32-byte digest as 64 lowercase hex
characters. It uses no mode, account, time or random input. The selected digest
descriptor in the image has type 9, output size 32 and block size 64, matching
the [Mbed TLS digest definitions](https://raw.githubusercontent.com/Mbed-TLS/mbedtls/v3.6.2/include/mbedtls/md.h)
and recovered HMAC setup/start/update/finish wrapper. This establishes the
algorithm; it does not identify the exact Mbed TLS dependency revision.
The embedded material was compared privately and matches in the two pinned
images. Neither that material nor derived device credentials is published.

**Inferred identity consequence:** with the same valid MAC and these same
generation inputs, removing a stored key and regenerating it produces the same
value. Separate production/development NVS slots do not by themselves guarantee
different credentials. Conversely, readable pre-existing keys can differ and
take precedence over generation. Do not treat reset, environment switching or
a firmware version change as a guaranteed credential-rotation mechanism.
No reset, MAC change or account migration was performed to validate this live.

Error handling also differs between the branches. Legacy migration ignores both
the selected-key write and commit result, closes NVS and returns success. Fresh
generation returns the key-write error, or the commit result after a successful
write; the formatted key already exists in the caller's output buffer when either
save fails. A crypto failure closes the handle and returns generic `-1`.
Missing keys and other read errors are not distinguished before the fallback,
so a transient read error can enter migration/generation and a replacement write.
The MAC local is not initialized before the unchecked read; valid generation
input is not established if that read fails. No such failures were induced.

The account-form callers check this helper's result before submitting setup.
Initialization `0x42019670` instead logs a key-initialization error and continues;
on success it copies the key into the configuration and calls the ordinary
configuration saver without checking that save result. A successful helper or
startup log is therefore not a complete persistent-identity acknowledgment.

Five paired bodies cover the selector, key helper, embedded-material helper,
digest lookup and HMAC wrapper: 356 byte-matched GNU instructions, 40 matched
branch destinations and 13 contiguous ranges per build. Nineteen direct-call
pairs and 26 literal pairs are mapped; digest descriptors and embedded material
were checked separately. This is static comparison, not execution of the
firmware's crypto/NVS code or proof of arbitrary reset/flash-fault recovery.

For the local backend, accept the provisioned/request key as an opaque private
credential and bind it to a separate owner-controlled device record. Retain a
non-secret ID for public discovery and job references. Reproducing the vendor's
derivation is unnecessary for the already-demonstrated stock protocol.

### Identity cache and read errors

Accessor `0x4201912c` returns the global configuration at `0x3fca6b50`. Its
initialized byte at `0x3fca6b4d` is set by default-copy helper `0x42017544`
**before** the lazy NVS load. Repeated accessor calls then use RAM, rather than
retrying that load. Explicit refresh `0x42019294` and startup initialization are
separate paths. The accessor is used by status, registration/verification getters,
voice identity lookup, album routes and calendar code as well as the setup pages.

The loader returns the NVS-open result; a successful open remains success even
when individual reads fail. It substitutes empty email/device-key/user-ID strings,
`EST5EDT` for a timezone read error, and false for verification read failure.
Missing keys, wrong types, excessive stored string lengths and other field errors
are not distinguished by the application fallback branches. A partially defaulted
configuration can therefore be treated as loaded successfully.

If the lazy loader instead fails to open the namespace, the accessor attempts to
persist its default configuration and ignores the saver result. Missing namespace
on a new unit and a transient open failure share that branch. It is not a
transactional repair or a guarantee that identity was erased. Normal initialized
GET requests take neither that load nor the default-save path. No NVS fault,
first-use race, identity loss or cache-reload experiment was induced.

For a fork, distinguish missing/unprovisioned data from read errors, preserve
usable cached identity on transient failures, and expose load health separately
from the account's verified flag. Do not turn a failed identity read into a
blanket default save during a status request.

## Vendor environment switch

The password-gated `/dev` entry selects vendor staging, not an arbitrary local
backend or a shell. The [form and authentication branches](local-api.md#developer-page-and-authentication)
were traced without submitting either mode-switch action. A custom backend
setting should be separate from this vendor-environment switch.

`0x420185ac` performs the following sequence:

1. Read the existing `server_mode` and station Wi-Fi configuration. If its SSID
   is nonempty, back up SSID/password under that environment's `_p` or `_d` keys.
2. Persist the requested `server_mode` through `0x42017974`. A write or commit
   error stops the remaining work inside the switch helper.
3. Look for the target environment's Wi-Fi backup. Both reads must succeed and
   the SSID must be nonempty. The destination driver configuration is zeroed
   before restoring these two fields; this is not a backup of all Wi-Fi options.
4. With a readable backup, attempt to apply it and clear `force_ftu`. Without one,
   set `force_ftu=1` and erase the shared `wakeup_img` marker.
5. Store `ota_data/cur_ver` as `0.0.0`, then request removal of the cached
   `create_account.bin` and `get_started.bin` system images.

The identity loader selects separate account keys after the mode changes. The
switch routine itself does not copy the production account into development or
erase the production identity. The shared timezone, settings, schedule and image
state must not be mistaken for fully isolated environment profiles. This is a
static map of the normal paths, not proof of recovery after interrupted writes.

### Storage types and partial failures

The Wi-Fi backups are **blobs of 32 SSID bytes and 64 password bytes**, not NVS
strings. The recovered read wrapper uses internal item type `0x41`, which agrees
with the SDK's [`ItemType::BLOB`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/include/nvs_handle.hpp)
and [`nvs_get_blob`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/src/nvs_api.cpp).
The mode accessor reads a byte initialized to zero and treats only value `1` as
development; failed/missing reads select production. Its writer normalizes the
requested mode to zero or one. Mode is not a free-form server URL.

Wi-Fi backup writes and their commit are not checked before the success log or
the mode change. Restoring Wi-Fi logs an apply error but still calls the helper
that clears `force_ftu`. That helper checks key erasure, but ignores the following
commit result. Thus a log that says credentials were backed up/restored is not
sufficient validation. A new firmware setting should preserve existing state and
propagate errors rather than reuse this sequence unchanged.

`0x42017974` returns the NVS open/write/commit result, despite Ghidra's inferred
`void` prototype; GNU instructions preserve it in the return register. The switch
helper checks that result, but the HTTP caller does not inspect the switch
helper's result before announcing a transition and restarting. No NVS fault,
mode switch or backup restore was induced on either frame.

### Update solicitation and cached artwork

The `0.0.0` value is a one-poll override, not a replacement for the compiled
firmware version. In `0x4202475c`, finding it selects `current_version=0.0.0` for
this request, while attempting to restore the normal version in NVS **before**
the HTTP transaction. On the ordinary successful-save path, a failed request can
therefore consume the override. The restore write/commit results are ignored, so
persistence failure can instead leave it active. This behavior is separate from
the forced-version/failure bookkeeping described in [OTA research](ota-and-recovery.md).

The cleanup wrapper `0x4202b060` calls `0x4202a8d4`, which attempts to unlink
`/imagedata/system_images/create_account.bin` and `get_started.bin`. Those two
names are global, not suffixed by environment. No deletion of `last_image.bin`
was found in this helper. Subsequent system-screen fetches still depend on the
selected backend; the deletion alone is not an assurance that fresh assets exist.

Restart helper `0x42017208` mounts image storage, saves diagnostic state and calls
the SDK restart path. The recovered shutdown-handler loop matches
[`esp_restart`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_system/esp_system.c).
Ghidra incorrectly included instructions from the adjacent sleep routine after
the nonreturning call; that neighboring charging guard does not gate this restart.

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
The filesystem also holds a [diagnostic snapshot](diagnostics-and-logs.md#previous-is-one-saved-snapshot)
of up to 65,544 bytes. Include this and system artwork when estimating future
playlist capacity; the actual free-space/partition measurement remains open.

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
Neither cache routine enforces the exact panel length. The
[short-asset trace](image-downloads.md#a-short-asset-can-reach-rendering-and-replace-the-cache)
shows how poll/voice workflows can attempt cache replacement even when the render
worker rejects the length. Its termination signal is not a success result.

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

The version decision is more specific than a generic “changed firmware” check.
`0x4202a968` compares the stored string with a compiled `0.2.29` literal:

| Result | Condition | Installer behavior |
| --- | --- | --- |
| `0` | Stored string equals the compiled value | Keep a readable exact-size wake image; replace it if validation fails |
| `1` | Key absent, NVS open/read failure, or other read error | Delete old server-screen cache files; adopt a valid wake image or install the embedded one, then attempt to stamp the version |
| `2` | Successfully read a different version string | Delete old server-screen cache files and overwrite the wake image from the embedded asset without first accepting its current contents |

The comparison is against this image-version string, not the app hash or the
one-poll `ota_data/cur_ver` override. A modified app that retains the string does
not automatically replace an otherwise valid wake file through this check.
Conversely, a version-string change forces replacement even when the existing
file is intact. No custom file was installed to test persistence.

Validation allocates an **8,192-byte temporary buffer** and counts bytes read;
it performs no palette or content check. Allocation failure returns `0x101`,
which the installer treats like other validation failures and follows with a
rewrite attempt. After writing, `0x42028bc8` validates again and unlinks the file
if that validation fails. Thus resource/read failures and actual corrupt content
are not distinguished in this repair policy. This is static behavior, not proof
that memory pressure deleted artwork on either inspected frame.

The writer opens the destination directly rather than writing a replacement file
and renaming it. A short write or failed post-write validation triggers unlink;
an `fsync` error is logged but does not by itself fail an otherwise readable,
full-length result. Version stamper `0x4202aa48` checks the string write but
ignores its commit result, and the installer does not propagate stamping errors.
Successful installation logging therefore does not prove the version marker
will survive reboot. These branches extend N04–N06; no filesystem fault was induced.

### Account/setup screens: fetched from the backend

Instruction IDs 1 and 2 are `create_account` and `get_started`. Their dispatcher
branch downloads them instead of falling back to local files. On applicable
image-version/migration paths, `0x4202a8d4` also deletes old
`system_images/create_account.bin` and `get_started.bin` files.

This is why a generic claim that all system screens are cached would be wrong.
The optional save flag in the instruction-render path saves to `last_image.bin`,
not a persistent cache of every server-keyed system screen.

**Local-backend opportunity:** serve model-specific raw panel assets for these
two keys, for example a local onboarding URL or HA-specific setup instructions.
This uses the recovered metadata/download contract and needs no new screen
format. It has not been exercised as independent enrollment. Supplying those
assets does not replace the embedded/local wake-up screen or the RLE low-battery
screen, and there is no discovered stock endpoint for installing a custom wake
file.

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
The follow-up below establishes that the decoder does **not** validate the palette
or require all supplied pairs to be consumed.

A host-side decoder reconstructed from these rules consumed all **216,382 input
bytes** and produced exactly **2,304,000 bytes**, with no invalid runs or leftover
input. The asset uses only palette values `0, 1, 2, 3, 5, 6`. Output SHA-256:
`a1db1ecf37389628588baf3c2d44912318087759eb55558dfaa4b834236721be`.
This validates the recovered format against the embedded asset, not a new panel
render. Neither the embedded nor decoded vendor artwork is included here.

### Status decoder validation and partial writes

GNU instruction checks and a reconstructed C fixture refine the contract:

| Input condition | Recovered result |
| --- | --- |
| Null input, output or length pointer; output capacity below 2,304,000 | `0x102`, before decoding |
| Input shorter than two bytes or odd byte count | `0x104`, before decoding |
| Input ends before all rows are full | `0x10c`; earlier output bytes remain written |
| A consumed run has length zero or crosses its 800-pixel row | `0x108`; earlier output bytes remain written |
| Extra even-length data after all eight controller blocks | Success; trailing pairs are not inspected, even a zero run |
| Colour outside `0, 1, 2, 3, 5, 6` | No rejection or palette normalization |

Packing at `0x4202fb92`–`0x4202fba0` loads two unsigned colour bytes, shifts the
first by four, ORs the full second byte, and stores the low byte. Neither input
is masked to a valid panel colour. Repeated colour `4` therefore produces `0x44`;
the pair `0x00, 0x10` produces `0x10`, changing the high nibble as well. Odd-length
runs can legitimately pair across run boundaries within a row. Every completed
row has an even 800 pixels, so no pixel remains pending across rows.

The output-length pointer is written only on success. An error does not zero it
or roll back partially decoded bytes. The current wrapper initializes its local
length to zero and skips render-start on decode failure, but decoding has already
modified the shared image allocation. The 16 host cases reproduce these rules
under AddressSanitizer/UndefinedBehaviorSanitizer and reproduce the preserved
vendor asset's earlier output hash. They execute a reconstruction, not the ESP32
application. No malformed asset was supplied to a physical frame.

Generated firmware assets should be checked for exact completion, row bounds and
palette before publication. If decoding can overlap another consumer, ownership
must cover decoding itself; a render-start guard comes too late.

### Status markers and restoration are not display acknowledgments

`0x4202fc34` expands the status image into the ordinary shared image buffer
**before** calling render-start with DROP policy. It converts `0x103` (busy/drop)
to success without updating the status marker. The earlier decoded bytes are
not restored on that branch. This is another statically identified writer-before-
arbitration path, not an observed collision.

On accepted render-start, it updates the in-memory marker at `0x3fcaca94` and
calls `0x4202f904` to persist `app_data/sys_img`. It does not wait for render
completion. The marker and “displayed” log thus indicate acceptance, even if the
worker subsequently fails. The helper does not replace `last_image.bin`.

Restore helper `0x4202fde0` loads the saved artwork into the same allocation
before its own DROP call. A drop again returns success while retaining the
status marker. Accepted render-start clears the marker before completion;
failed cache load also clears it, despite not restoring any artwork. An actual
render-start error leaves it set. These branches must not be interpreted as
proof that either the status image or restored artwork reached the glass.

Marker persistence is best effort: `0x4202f904` logs an NVS-open failure, checks
set/erase only to decide whether to attempt commit, discards commit failure and
returns no result to its caller. In-memory and persisted markers can therefore
diverge on storage failure. `0x4202fdac` likewise clears memory before requesting
NVS deletion. Physical overlap, storage faults and next-boot restoration remain
open; no battery-state or reset experiment was performed.

### Standard status assets use different row geometry

The pinned Standard 0.2.28 build resolves `low_battery` at `0x4202dfe8` to
DROM `[0x3c22aee8, 0x3c231836)`, a **26,958-byte** embedded asset. Its decoder
`0x4202e138` uses two halves, each with **1,600 strips of 600 pixels**, and packs
each strip into 300 consecutive bytes. The second half starts at byte 480,000;
the total output is exactly **960,000 bytes**. The log calls each strip a “row”;
this is controller-stream geometry, not a claim that the result is an ordinary
row-major 1600 × 1200 bitmap. Keep the model-specific panel packer.

The same error classes, partial writes, unmasked colour packing and ignored
trailing pairs apply. A destination below 960,000 bytes fails before decoding;
a larger destination does not increase the decoded length. Eighteen reconstructed
C host cases passed with AddressSanitizer and UndefinedBehaviorSanitizer, including
distinct strip/half contents and preservation of the unused tail of Standard's
1,048,576-byte image allocation. An independent decoder consumed every asset pair
and produced identical bytes. This asset uses only colours `0, 1, 3`.

| Artifact | SHA-256 |
| --- | --- |
| Standard embedded RLE | `bf009f5933a467900f245db06695f7ad13e82f6b6f1a892f6529768e5e4d12d7` |
| Decoded 960,000-byte panel payload | `0d5ea5c820540c57ff5c8f2aad188a0d7d454f2c7f1293cfd06b6d3a9a6d7703` |

Standard show `0x4202e360` and restore `0x4202e50c` have the same ordering as the
Large paths above: decode/cache-load first, DROP render-start second, marker
changes on acceptance without waiting. A dropped operation returns success and
retains its marker despite the earlier buffer write. A cache-load failure clears
the marker without restoring artwork. The Standard marker is at `0x3fcacaec`;
save/reload/clear are `0x4202e030`, `0x4202e09c` and `0x4202e4d8`.

These helpers preserve `last_image.bin`; they do not expose an RLE upload route.
Standard's separate recording allocation avoids Large's audio/image alias, but
its image producers still share the image allocation. Neither this comparison nor
the host checks demonstrate actual overlap, NVS-failure recovery or a new physical
render. The vendor artwork remains private.
