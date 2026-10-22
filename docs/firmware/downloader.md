# Download firmware for offline analysis

[Research index](README.md) · [Downloader script](../../scripts/download_firmware.py)

Run the downloader on an internet-connected computer while the frames remain
blocked from the web. It checks the vendor's normal device endpoint, downloads
the offered application binary, and saves its size and SHA-256 beside it.
It never contacts the physical frame, flashes firmware, changes settings or
reports an OTA success/failure. It needs Python 3.11 or later and no packages;
`uv` handles running it.

## Save the full device key once

Keep a separate private key file for each frame, outside this repository, for
example `~/.config/fraimic/large.key`. Put only that frame's **full provisioned
device key** in the file and restrict access with `chmod 600`. Do not put the key
in command arguments, screenshots or version control. Alternatively, supply it
through the `FRAIMIC_DEVICE_KEY` environment variable.

The masked value from `/api/info` and the account-facing `device_id` are not
usable credentials. Existing owner-held captures or private device logs may
contain the full key; see the [cloud API notes](../fraimic-cloud-api/routes.md).
The downloader does not enroll a device or retrieve credentials for you.

## Check or download

From the repository root, check the Large frame's offer without downloading:

```bash
uv run scripts/download_firmware.py \
  --device-key-file "$HOME/.config/fraimic/large.key" \
  --model large --current-version 0.2.29 --check-only
```

Remove `--check-only` to download. For a Standard frame:

```bash
uv run scripts/download_firmware.py \
  --device-key-file "$HOME/.config/fraimic/standard.key" \
  --model standard --current-version 0.2.28 \
  --output-dir "$HOME/Downloads/fraimic-firmware"
```

Use the version you want the checker to report as installed. The examples are
the researched builds, not an assertion about the latest release. To request an
offer even when you already have the currently offered version, report an older
version such as `--current-version 0.0.1`. The server still decides what that
device is eligible for. There is no known version-listing or arbitrary historical
download endpoint, and a release announcement does not guarantee an offer for
every device/model. Use each frame's own key and matching model.

An absent/null `firmware` field prints “No firmware offered” and exits successfully.
That means no offer for this request, not proof that no newer firmware exists.
An offered version is downloaded even if its version string equals the one sent;
the script does not attempt to order vendor version strings.

The default output directory is the git-ignored `scratch/firmware`. Each successful
download creates `fraimic-<model>-<offered-version>-<hash-prefix>/` containing:

- `firmware.bin`: unchanged response bytes.
- `metadata.json`: UTC download time, API origin, model/display type, reported
  version, offered version, byte count and full SHA-256.

Device keys, signed URLs, account data and optional telemetry are excluded from
the metadata. A completed directory is never overwritten. If it already exists,
the script exits with an error; choose another output directory for a new copy.
Ordinary failures and interruptions clean up temporary downloads before publishing
an archive. Exit codes are `0` for a successful check/download (including no offer),
`1` for an operational failure, `2` for invalid CLI arguments and `130` for Ctrl-C.

If you have a trusted expected digest, add `--sha256 <64-hex-digits>` to reject a
mismatch. Otherwise the saved digest is an artifact fingerprint, not independent
proof of authenticity. The script checks the ESP32-S3 image header and declared
HTTP length, but does not validate segment checksums, appended hashes, signatures
or bootability. This is an OTA application image, not a full flash/NVS backup.

## Protocol and deliberate differences

The [recovered poll](cloud-protocol.md#poll) and the vendor's live
[`openapi.json`](https://origin.fraimic.com/openapi.json), checked on 22 October
2026, identify the current offer shape:

```text
GET https://origin.fraimic.com/api/v1/upload/check/<device_key>
    ?display_type=133|315
    &orientation=portrait|landscape
    &is_periodic_poll=false
    &current_version=<reported-version>

{"firmware": {"version": "<offered-version>", "presigned_url": "<temporary URL>"}}
```

The downloader uses `133` for Standard and `315` for Large. It follows the nested
**firmware** URL only; the top-level `presigned_url` is artwork and is ignored.
No account login/Bearer header is needed. It fetches the firmware URL immediately
because it expires. A failed download is not retried; rerun to obtain a fresh offer.

This reproduces the offer/download flow, not every microcontroller behavior:

- A poll can update the vendor's last-seen/version bookkeeping or affect pending
  artwork bookkeeping. Even `--check-only` is a real cloud device poll. Only the
  computer needs internet, but the vendor may see the blocked frame as active.
- Optional `--battery-pct`, `--wifi-ssid` and `--ip` reproduce telemetry fields.
  They are omitted by default to avoid inventing device readings. Orientation
  defaults to portrait. The script identifies itself with its own User-Agent.
- Checks use a 10-second socket timeout; downloads use 30 seconds and 4 KiB reads,
  matching the recovered transport values. These are not total-operation deadlines.
- Like the [direct updater](ota-and-recovery.md#direct-download-framing-and-failure-boundaries),
  downloads require HTTP 200 and a positive Content-Length, with no redirect,
  resume or automatic retry. There is a 32 MiB download cap instead of a physical
  OTA-partition limit. The script does not use the unused legacy manifest URL.
- HTTPS certificate verification remains enabled. Poll redirects are also
  refused to avoid forwarding a credential-bearing path; stock polls can follow
  redirects. `--api-base-url` supports another HTTPS API origin. Plain HTTP is
  accepted only for loopback fixtures (`localhost`, `127.0.0.1`, `::1`).

The tests use a local HTTP fixture for both models, offers/no offers, private
metadata, HTTP failures, redirects, incomplete downloads, header/hash rejection
and archive preservation. They do not depend on vendor availability:

```bash
uv run --with pytest pytest tests/test_download_firmware.py -q
```
