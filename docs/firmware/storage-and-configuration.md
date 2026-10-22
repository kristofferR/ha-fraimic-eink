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
checks it before reloading. The later [identity persistence model](#identity-saves-and-reset-restoration-host-cases)
injects selected API failures; no physical storage failure was induced.

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

## Reset erases NVS before restoring the other environment

The reset helpers are not namespace-only account erasers. Development reset
`0x42017aac` and production reset `0x4201800c` first read a small backup into
stack buffers, erase the default `nvs` partition, initialize it again, then
attempt to restore the **opposite** environment's selected fields.

| Helper / selected mode | Backup and attempted restore | Additional writes after erase |
| --- | --- | --- |
| Development reset | Production `device_key_p` (legacy `device_key` fallback on read error), `user_id_p`, `email_p`, `email_vp`, `wifi_ssid_p`, `wifi_pass_p` | `server_mode=1`, `force_ftu=1` |
| Production reset | Development `device_key_d`, `user_id_d`, `email_d`, `email_vd`, `wifi_ssid_d`, `wifi_pass_d` | No explicit mode/first-time override; the mode getter defaults to production after erase |

Key/user/email read capacities are 128/65/100 bytes; verification is I32;
SSID/password blob capacities are 32/64 bytes. Backup eligibility is each read's
success, not a nonempty-string or exact-blob-length check. Successful empty values
can be restored. A successfully read empty production key does not trigger the
legacy fallback; a read error does. Blob restores use their returned lengths.

The erase wrapper `0x42049d8c` supplies the literal `nvs` to `0x42049d40`.
That helper finds a data/NVS partition by this label and erases from offset zero
through its reported size, matching
[`nvs_flash_erase_partition`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/nvs_flash/src/nvs_api.cpp).
This removes other namespaces in that partition as well as `app_data` on a
successful erase. The backup list contains no timezone, four-switch settings,
maintenance/album schedule, OTA history, Wi-Fi statistics or SDK Wi-Fi/PHY state.
Those records are not preserved by these helpers, although later startup and
shutdown code can recreate some of them. The separate `imagedata` FAT partition
is not the target of this erase; that distinction alone does not establish which
artwork survives the entire reset workflow or subsequent filesystem recovery.

### Backup and restore errors do not form a transaction

A failed backup namespace open, or any failed individual backup read, does not
abort the erase. That field simply loses its restore flag. Production reset
skips reopening `app_data` if no development fields were read successfully;
development reset still opens it to write its mode and first-time flags.

After erase/reinitialization, every individual restore write is unchecked,
including the development mode/first-time flags. The helpers check the final
commit and return the erase, initialization, restore-open or commit result.
GNU instructions preserve that result in `a2`; Ghidra's `void` labels are wrong.
Thus a helper can return zero after failed field writes when commit succeeds.
Large's [resolved commit implementation](#nvs-commit-does-not-make-the-four-switches-atomic)
does not turn these separate writes into an atomic restore. No power-loss,
flash-write, backup or restore failure was injected.

The HTTP reset branch adds an earlier hazard. Before selecting a mode or calling
either backup helper, it initializes NVS; `0x110d` (no free pages) or `0x1110`
(new version found) triggers an immediate whole-`nvs` erase and reinitialization.
Any opposite-environment backup is attempted **after** this recovery erase.
Consequently the later preservation logic cannot recover data already erased,
and the original mode may also be lost. This conditional path was not exercised.

### The HTTP result and later reset handoff are separate

Large handler `0x4201c740` selects a success/error HTML page from the helper result,
but sets the reset-pending RAM byte `0x3fca6b17` and logs completion in both cases.
It does not suppress the later reset work merely because the helper returned an
error. A failed response send is also ignored.

When the main loop reaches that flag, it clears it, delays 200 ticks (two seconds),
enters the reset LED state and calls the HTTP/network teardown path. It then
attempts a local wake-up instruction render when available, reevaluates user
state, and enters storage sleep through `0x42010674`. These are later operations,
not part of an atomic NVS transaction or an immediate reboot. The existing
[teardown](local-api.md#server-capacity-and-lifecycle),
[render-completion](rendering-and-concurrency.md) and sleep limits still apply.
The later cache checks and writes are traced below. Final persisted identity,
artwork and failure recovery remain unverified; no reset request was sent.

The two reset-helper bodies match Standard `0x42017a80` / `0x42017fe0` across
969 byte-matched GNU instructions, 60 branch destinations and 17 contiguous
ranges per build, with 13 direct-call and 79 literal pairs reviewed. A separate
Large pass checks three SDK bodies and the HTTP/main-loop reset regions across
12 ranges and 396 instructions. That second pass is not a Standard SDK/caller
comparison. These findings argue for a dedicated backend migration setting that
preserves identity and storage, rather than repurposing factory reset.

### Cached identity and later writes after reset

Large's initialized identity accessor `0x4201912c` returns the RAM configuration
without reloading NVS. The reset helpers do not explicitly invalidate that cache.
The “complete” predicate `0x42015240` combines a nonempty cached email with its
cached verification byte; it does not validate a device key, user ID or successful
post-reset read. A status reported in this interval is therefore not evidence
that the corresponding account records survived the erase.

User reevaluation `0x42015264` also requires Wi-Fi credentials. Its credential
predicate `0x4201ea80` first asks the initialized driver for STA configuration
and checks the first SSID byte. If that request fails, it opens `nvs.net80211`
and asks for the `sta.ssid` blob's length: a successful nonzero length passes,
without examining its contents. It does not consult the environment-specific
`app_data/wifi_ssid_p` or `wifi_ssid_d` backups here.

Successful SDK deinitialization changes the internal initialized state from 3
to 1. The STA-config getter then returns `0x3001` instead of serving old driver
configuration, causing the NVS fallback above. If the SDK SSID record is absent,
reevaluation selects setup even when the cached account remains complete.
Conversely, a teardown failure that leaves usable old STA configuration, together
with the old complete account cache, can select the configured branch. That
branch attempts to erase `force_ftu`, ignores the helper's result and requests
the ready LED. This is a conditional static path, not an observed reset outcome.
The erase helper treats a missing flag as success and ignores commit failure.

The pending-reset sequence also performs later storage writes:

| Later operation | Persistence attempted and error handling |
| --- | --- |
| First network teardown | `0x4202e9b0` saves the 906-byte RAM `wifi_stats` blob only when dirty. Open/write/commit failure leaves its dirty flag set; the caller ignores the result. |
| Storage-sleep entry | Attempts one-byte blobs `deep_sleep=1` and `storage_mode=1`; individual writes and commit are unchecked after a successful namespace open. |
| Second network teardown inside storage sleep | Calls the same statistics flush again, so an earlier failed flush can be retried. Wi-Fi stop/deinit errors are logged without preventing the remaining sleep sequence. |
| Immediately before deep sleep | `0x4202d860` attempts I64 `last_sleep_ts` from the current clock; it checks the write but ignores commit failure. |

Neither reset helper clears the statistics dirty flag. Consequently a successful
erase can be followed by saving pre-reset statistics and new sleep markers;
the HTTP reset response is not a snapshot of final NVS contents. The recovered
storage-sleep branch does not call the whole-identity saver, so these writes do
not establish that the erased account is restored.

This follow-up checks 15 complete Large helper bodies across 661 byte-matched
GNU instructions, 68 branches and 31 contiguous ranges, alongside the recovered
storage-sleep caller. It does not compare these SDK/cache paths on Standard or
execute them on either device. Internal SDK cleanup, concurrent writers,
interrupted shutdown, subsequent boot and actual final storage remain open.

### Identity saves and reset restoration: host cases

An API-boundary reconstruction now exercises **34 interruption points and 28
setter failures across nineteen scenario groups**, using synthetic identity and
an in-memory namespace/key store. Successful mutations take effect wholly and
immediately; injected setter/erase errors happen before mutation. Cuts stop before
the next operation or final commit. This tests application sequencing and return
handling, not NVS page recovery, partial erase, physical power loss or reboot
durability. In particular, a real setter error can have effects excluded by this
model, as the [storage-writer trace](#nvs-commit-does-not-make-the-four-switches-atomic)
already shows.

The saver writes selected email, shared timezone, selected device key, selected
user ID and selected verification, in that order. Production then writes four
legacy aliases before commit; development does not. The ten production and six
development cut points include the window immediately after the third successful
setter: **new device key with old user ID**. Earlier successful setters remain
in the model when a later checked setter fails. A completed production save's
selected identity can also disagree with a legacy alias whose unchecked write
failed, while the saver returns success. A development save changes shared
timezone while preserving the production account keys.

The ten development-reset and eight production-reset cut points include the
empty-partition window after erase and the partial opposite-environment restore.
All successful erase paths discard shared timezone/schedule and other namespaces
unless later code explicitly recreates them. The tests assume readable backup
fields; separate cases exercise missing reads, failed backup open and short or
empty successful values.

| Fault/condition in the reconstruction | Consequence |
| --- | --- |
| Any of five checked save writes fails, in either environment | Saver returns that error without undoing earlier mutations |
| Any of four production alias writes fails | Selected fields can be current while that alias stays old; successful commit still yields success |
| Any of eight development-reset or six production-reset restore writes fails | Other writes continue; successful commit can hide the missing field, including mode/first-time flags |
| Backup open fails | Erase still occurs; development restores only mode/first-time flags, production skips the empty restore |
| Primary production key read fails during development reset | Readable legacy key is used; a successfully read empty primary key instead suppresses fallback |
| Post-erase initialization or restore-open fails | Helper returns an error after the model's partition is already empty |
| HTTP recovery erase occurs before selecting mode/backing up | Mode falls back to production and the later helper has no opposite-environment backup source |
| Create-account ignores a save error | Its requested RAM identity can differ from storage; sign-in's error branch does not perform the success-only explicit reload |
| Later statistics/sleep writes succeed | New records can appear after reset without reconstituting the erased account |

Commit-error controls retain earlier successful model mutations. The readable
short Wi-Fi example preserves returned lengths; it does not execute the blob
reader's type/capacity checks. Later-write controls model only selected successful
write calls, not full network teardown, blob layout or sleep. Cached account
status and reset HTML therefore remain unsuitable as persistence acknowledgments.

For a backend migration, keep identity changes separate from reset/environment
switching and verify the complete identity record after saving. A future firmware
format should publish one validated generation of related identity fields, with
explicit recovery selection. These observations do not establish a new format,
prove atomic flash support or require reproducing the vendor key derivation.

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

### Formatting permission is not proof that formatting happened

The provisioning helper queries the legacy `device_key` string's required length
without reading its contents. A successful nonzero length disables initial
formatting; it is not a nonempty credential check. Namespace/query errors or
zero length enable formatting. Environment-specific keys are not consulted.
An already-ready filesystem-manager state bypasses these checks entirely, while
an earlier failed state allows another initialization attempt.

Each initialization allows three mount calls using that initial permission,
with 100 ms delays after the first two failures. If all fail, a fourth call
enables formatting. The matching SDK helper `0x420352a4` first attempts an ordinary
FAT mount regardless of permission. It calls the formatter only for
`FR_NO_FILESYSTEM` (13) or `FR_INT_ERR` (2) with permission enabled. Other FAT
errors, and failures before reaching this helper, do not take that format branch.
This agrees with the pinned
[`s_f_mount_rw` source](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/fatfs/vfs/vfs_fat_spiflash.c).

Formatting allocates a 4,096-byte work buffer. A successful format sets an SDK
flag before remounting, so a subsequent remount error can return failure after
the destructive step already succeeded. The application does not inspect that
flag: its fourth-attempt success log says the partition was formatted even if
that attempt simply mounted an intact filesystem. Conversely, repeated eligible
failures can enter formatting on all four calls when permission starts enabled.
This does not establish that formatting occurred on either owned frame.

Twenty-four host case groups exercise the unchanged SDK helper plus reconstructed
application retry/permission branches. They cover both eligible errors, rejected
error classes, work-buffer/format/remount failures, retry counts, permission
changes and misleading fourth-attempt logging. FAT calls are controlled stubs;
no filesystem image, wear-leveling driver, flash, interruption or actual wait is
simulated. N04 remains open for those layers and physical recovery.

### Failed mounts can retain wear-leveling handles

The SDK wrapper acquires a wear-leveling handle before reserving a FAT drive,
registering VFS or mounting FAT. Its later error exits do not release that
handle. No available FAT drive returns `0x101` directly; disk/VFS registration,
FAT mount/format and final context-allocation failures follow cleanup that
unregisters VFS and disk I/O without calling wear-leveling unmount. Those two
cleanup helpers free their own registrations, not the wear-leveling instance.
The structure matches the pinned
[SDK mount wrapper](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/fatfs/vfs/vfs_fat_spiflash.c).

Large `0x42036c74` and Standard `0x42035738` allocate from an eight-slot table.
They select the first empty slot without deduplicating the partition. A successful
call publishes the instance; a later mount call overwrites the application's
single output handle. Therefore a retry can succeed with a new handle while an
earlier failed attempt's slot remains allocated. Failures *inside* wear-leveling
mount have a separate local cleanup path and do not publish that slot.

With an initially empty table, eight attempts that each acquire a handle and
then fail can fill all slots. A ninth returns `0x101` before reaching FAT.
Two complete four-attempt application initialization failures can reach that
condition if every attempt follows the required late-failure path. Other mounts,
earlier allocation errors and separate cleanup can alter the count. This is a
conditional resource-retention mechanism, not evidence that either frame has
experienced it or an explanation of the captured TLS allocation failure.

Twelve host groups exercise the unchanged SDK wrapper with controlled dependencies,
including registration, FAT and allocation failures, successful
retry with an earlier retained slot, eight-slot exhaustion and an already-registered
VFS status supplied together with a valid pointer by the stub. That last case
checks wrapper status handling, not the real registration helper's output on
error; the distinction is traced below. Wear-leveling is an eight-slot accounting stub based on the verified
allocator, not real flash or a measurement of leaked heap bytes. Host cleanup
deliberately frees fixture contexts after assertions. Three additional paired
GNU bodies verify the allocator and both cleanup helpers across 232 instructions,
24 branches and six ranges per model. No storage failure was induced on a frame.

### Existing VFS registration does not supply a filesystem pointer

The real registration helper `0x42036ab8` returns `0x103` immediately when the
base path already has a VFS context. It does not populate its filesystem output
pointer on this path. Only the successful final branch stores that pointer.
The mount wrapper nevertheless accepts `0x103` as well as zero and continues
with its local pointer slot at stack offset 20. The complete wrapper has not
initialized that slot before the registration call; it later loads it as the
FAT mount argument. The two recovered functions therefore do not provide safe
reuse of an existing registration. This agrees with the corresponding
[SDK registration code](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/fatfs/vfs/vfs_fat.c).

This is a conditional uninitialized-value path, not a reproduced crash or proof
that ordinary startup reaches duplicate registration. The host fixture's injected
`0x103` case deliberately supplied a valid filesystem pointer; it establishes
only that the wrapper accepts the status. Its label and evidence hashes now make
that scope explicit. No uninitialized-pointer execution was attempted.

The helper also establishes the allocation requests for the app's four-file
configuration: an 8,832-byte base context plus four 4,136-byte file structures
(25,376 bytes), then a separate 16-byte flags allocation. The combined 25,392
bytes exclude allocator overhead, VFS registration, wear-leveling objects and
other buffers; they are not a measurement of actual free heap or internal-RAM
placement. Registration on Standard `0x4203557c` matches across 83 instructions,
13 branches and four ranges. Actual initialization races, resource pressure and
safe cache replacement remain untested.

The allocation-region preference is now resolved separately. FatFs allocation
helper `0x420351f4` supplies two capability masks to the SDK preference allocator:
`0x1400` (`DEFAULT | SPIRAM`) first, then `0x1800` (`DEFAULT | INTERNAL`). The
allocator stops on the first successful allocation. This matches
[ESP-IDF's external-memory-preferred FatFs port](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/fatfs/port/freertos/ffsystem.c).
Thus the context and flags prefer PSRAM and independently fall back to internal
memory; the 25,392-byte total is not an unconditional internal-memory charge.
The same helper serves the recovered 4,096-byte format workspace and 512-byte
long-filename workspace. PSRAM allocation failure can shift those requests to
internal memory, but no runtime placement, fragmentation or TLS impact was
measured. Three paired allocation/free/preference bodies match across 68 GNU
instructions, seven branches and four ranges per model; no new host or device
allocation fault was injected.

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

**Proposed:** recoverable replacement, content hash metadata, distinct cache/display
results, and backend restoration from canonical HA assets. The rename and sync
boundaries below constrain that design; space, wear and interruption behavior
still need validation.

### Cache success and failure leave different state behind

The complete writer confirms that `fflush` and `fclose` results are discarded;
the `fileno` result is passed to `fsync` without a separate validity check.
Even after a logged `fsync` error, an exact `fwrite` byte count yields success.
A short write returns failure after closing, without unlinking the partial file
or restoring the previous one. The direct `wb` open can already have truncated
the old artwork. These are application return-value rules, not a claim that
every reported-success write failed to reach flash.

The loader makes separate existence and size `stat` calls, then opens the path
and performs one `fread` for the sampled size. It does not verify file type,
recheck size, test a content hash or check the close result. A short read returns
failure with the destination's already-read prefix still modified and the output
length untouched. If a file grows between size sampling and reading, a complete
read of the earlier length can succeed without consuming the added bytes.
Concurrent replacement, truncation and read failures were not induced.

The “saved image exists” predicate checks initialized storage and successful
`stat`, not a nonzero exact-size valid image. Thus a bad cache can pass that
presence check and fail at load or rendering later. Preserve the backend's
canonical artwork and track delivery separately from durable cache and display
completion; stock cache/status success is not an integrity acknowledgment.

Nine paired application/SDK bodies match across 796 GNU instructions, 84 branches
and 29 contiguous ranges per image. Their model-specific save caps are
2,566,144 bytes for Large and 1,048,576 bytes for Standard, both larger than their
exact panel assets. The underlying stdio, FAT and wear-leveling implementations
are not recursively validated by this comparison. No file fault or concurrent
cache access was performed on a frame.

### Rename does not replace an existing cache file

The registered FAT rename wrapper `0x420366b8` calls `f_rename` at `0x420346b0`
under its VFS lock. It does not unlink an existing destination first. If the
destination names a different existing object, the FAT routine returns
`FR_EXIST` (8), which the wrapper maps to `-1` with `EEXIST` (17). The recovered
branch matches the pinned
[FatFs implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/fatfs/src/ff.c).

On a disposable RAM FAT12 filesystem, renaming `pending_image.bin` over an
existing `last_image.bin` failed and preserved both files. Renaming to an absent
destination succeeded across remount. Explicitly unlinking the old destination
first left a remountable state with no canonical `last_image.bin`, even though
the pending file remained valid. A successful rename to an absent path is not
proof of power-loss atomicity during its internal directory updates.

A fork therefore cannot assume that writing a temporary file and renaming it
over the old name implements atomic replacement on this filesystem. Retaining
two validated versions with explicit recovery is a candidate only if measured
capacity permits it. Preserve canonical artwork in the backend regardless;
the replacement protocol and interrupted-write recovery still need design and
validation before changing firmware.

### A second sync can conceal an earlier metadata-sync failure

The registered `fsync` wrapper `0x42036a80` calls `f_sync` at `0x42033f4c` and
propagates a FAT error as `-1`/errno. Inside `f_sync`, an early file-buffer write
error returns before clearing the file's dirty/modified state. That path can be
retried. Later, after updating directory metadata in the filesystem window, it
calls `sync_fs` and clears the file's `FA_MODIFIED` bit **regardless of that
call's result**. A following `f_sync` can then return success without attempting
the pending metadata work again. `f_close` first calls this same sync function.

The isolated RAM-disk fixture distinguishes these paths:

| Injected condition | Observed host result |
| --- | --- |
| Directory-sector write fails while saving a full sector to an existing empty file | First sync fails; second sync and close succeed without another write. After discarding the filesystem cache and remounting, the file still has its old zero length. |
| File-data-buffer write fails for a 1,000-byte payload | First sync fails; the next sync retries and the complete payload survives remount. |
| Disk `CTRL_SYNC` reports failure after writes | First sync fails; second file sync does not call `CTRL_SYNC` again. The RAM disk already contains the writes, so this case does not establish actual media loss. |

This compounds the application's ignored `fflush`/`fclose` results and its logged
but nonfatal `fsync` error. A later successful close cannot erase an earlier
durability failure. The VFS close wrapper also releases its file-slot allocation
after `f_close` returns, including an error return; that is separate from the
application's success decision.

Seven paired rename/sync/close/error-mapping bodies match across 384 GNU
instructions, 93 branches and 16 ranges per model. Six host groups use unchanged
SDK FatFs source on an 8 MiB RAM FAT12 volume with 4,096-byte sectors, heap long
filenames, per-file buffers and single-thread mutex stubs. The configuration
matches the relevant recovered branches, not every device build setting or
32-bit ABI. Whole-sector I/O and selected errors are simulated; actual partition
geometry, torn writes, wear leveling, concurrency and physical power loss are
not. No frame cache or artwork was modified.

### Recoverable cache replacement proposal and interrupted-write checks

For a future firmware change, use two independently validated cache records and
recover by scanning them, rather than unlinking the current file before rename.
This avoids assuming POSIX replacement semantics on the inspected FAT code.
It is **recoverable under the tested failure model, not proven flash-atomic**.
Stock firmware does not implement this format or slot selection; adding a header
to its existing raw `last_image.bin` is not a compatible backend-only change.

The proposed record is one file containing a 64-byte header and the exact packed
panel payload. Header fields include format magic/version, model, generation,
payload length and SHA-256 covering both the first 32 metadata bytes and payload.
Before selection, require exact model/length, a complete read, supported format,
valid six-colour nibbles and a matching digest. Hashing only the payload would
leave generation metadata unprotected. This checks integrity, not publisher
authentication or physical display.

Scan both slots and select the highest valid generation. Treat equal valid
generations as ambiguous and request explicit recovery; do not wrap an exhausted
generation counter. If neither validates, preserve evidence and restore from the
canonical HA original rather than formatting storage automatically. Rewrite only
the inactive slot, retain every write/sync/close failure, and re-open/validate
before making an in-session success claim. A later successful close must not
clear an earlier error. Cache recovery, accepted delivery and panel completion
remain separate states.

The proposed format was exercised with unchanged pinned FatFs on the existing
8 MiB RAM FAT12 fixture. Each baseline contained two records and one synthetic
system asset of the model's panel size. The model-specific sizes here are real;
the volume geometry and existing free space are **fixture choices**, not observed
Fraimic partition capacity.

| Payload | One record | Two records + one same-size system asset, before FAT/cluster overhead | Interrupted-write boundaries |
| --- | --- | --- | --- |
| Standard, 960,000 bytes | 960,064 bytes | 2,880,128 bytes | 242 |
| Large, 2,304,000 bytes | 2,304,064 bytes | 6,912,128 bytes | 570 |

For all **812 cut points**, the previous active slot remained valid after dropping
the filesystem cache and remounting. Cuts are before whole `disk_write` calls,
whose multi-sector writes are all-or-nothing in this model; subsequent writes and
syncs fail. They are not arbitrary byte/sector tears or physical power cuts. For
241 Standard / 569 Large cuts, recovery selected the old generation. At the last
cut per model, all file writes had reached RAM but final sync failed: the save
still reported failure, while remount selected the complete new generation. This
is an uncertain save outcome, not grounds to erase the earlier error.

Sixteen additional checks cover same-size valid-palette corruption, hashed
generation metadata, invalid palette despite a matching hash, wrong model,
equal-generation ambiguity, truncation, low space, no valid slot and generation
exhaustion. Low-space admission uses measured fixture free clusters plus the
inactive file's reclaimable cluster-rounded size, and reserves two extra clusters.
That reserve is a test policy, not a proven bound on all device metadata/wear costs.
The active slot is left untouched when the preflight fails.

These results do not establish recovery from torn/shared FAT directory sectors,
wear-level metadata corruption, interrupted erase, reordered writes, cache lies,
concurrent saves or damage to the previously valid slot. Nor do they prove space
for two images on either real frame. Measure the installed layout/free space and
validate recovery before adopting this firmware design. Canonical HA originals
remain necessary even with hashed local records. N05's design/host milestone is
complete; physical durability remains blocked on layout and recovery access.
See [validation](validation-2026-10-22.md#recoverable-cache-slot-design-n05).

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
will survive reboot. These branches extend N04–N06; no filesystem fault was
induced on a frame.

#### Wake-asset validation and recovery host cases

Twenty-two Large-only cases now reconstruct the five validator/writer/version/
stamper/installer routines over disposable host files. The complete GNU bodies
cover 481 instructions and twenty ranges, checked against pinned image bytes.
Synthetic fill patterns replace vendor artwork; read/allocation/NVS/sync/close
fault returns are modeled. The host filesystem is POSIX, not the device FAT or
wear-level layer.

| Case | Reconstructed result |
| --- | --- |
| Current version, readable exact-size custom file | Keep it without stamping or rewriting |
| Current version, exact-size bytes containing invalid palette nibble 4 | Still keep it; no palette/hash check |
| Missing, short or oversized file | Replace with the synthetic embedded counterpart |
| Different stored version | Remove legacy setup-screen caches and overwrite a valid custom file |
| Missing version/read error, valid custom file | Remove legacy setup caches, adopt custom file and attempt a version stamp |
| First validation read/allocation fails, second succeeds | Rewrite an otherwise valid custom file |
| Allocation also fails after rewrite, or post-write read is short | Unlink the replacement and return failure |
| Short write | Unlink partial replacement; previous wake contents already lost |
| Opening replacement fails | Return failure while retaining the existing file |
| Sync/close reports failure but complete bytes remain readable | Installer can return success through the unchecked return paths |
| Version string write fails | Installation still reports success; a differing old version causes another rewrite next modeled boot |
| Missing version stamp repeatedly fails, custom file remains valid | Re-adopt without rewriting on the next modeled pass |
| Storage not ready | Return invalid-state; do not replace the file |
| All relevant files were lost | Restore wake artwork only; no reconstruction of the last user image |

The model's legacy-cache deletion preserves `last_image.bin`. Simulated missing
version/file states describe inputs to the installer, not proof that a real reset
or formatter produces exactly those inputs. No reset, NVS write, installed custom
artwork, firmware upgrade, palette fault or format operation was performed.
The same-size invalid-palette case is accepted by validation; it is **not** a
claim that the panel will render those bytes correctly or safely.

For a future fork, make an explicit distinction between absent/corrupt content
and temporary read/resource failure. Validate model, exact length, palette and
integrity before adoption, preserve a prior good copy during repair, and retain
canonical custom artwork in HA for recovery. No stock endpoint for installing
that wake file has been established. N06's host criterion is checked, with custom
artwork/upgrade persistence still deferred behind recovery prerequisites.
See [validation](validation-2026-10-22.md#wake-asset-validation-and-recovery-n06).

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
