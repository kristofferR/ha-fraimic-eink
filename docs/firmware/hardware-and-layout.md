# Identity, hardware and application layout

[Research index](README.md)

## Exact image

| Property | Evidence |
| --- | --- |
| Product | Fraimic Large, 31.5-inch EL315TW1 panel |
| Reported version/build | `0.2.29` / `f1555ee5` |
| App descriptor version | `v0.2.24-33-gf1555ee` |
| Descriptor build time | 16 July 2026, 10:17:43 |
| Separate timestamp printed in boot log | `2026-07-16 10:15:17 -0400` |
| Processor / OS | ESP32-S3, Xtensa LX7; ESP-IDF v5.4.1 / FreeRTOS |
| App file length | 4,123,920 bytes |
| SHA-256 | `a75914caba6f5f35936a40e394b1d55eb88de4be4e76aa6d6bdabc061486a64f` |
| ELF hash in descriptor | `43429a72fd1aaae1845a100c8d04bc119b7aecd5286dfc7518155474f42255b1` |
| Image header | Six segments; 16 MB flash, DIO, 80 MHz |
| Integrity | ESP image checksum and appended SHA-256 validated |
| Standard appended signature | No Secure Boot v2 signature sector found |
| Running slot, observed | `app1`, flash offset `0x4a0000`, size `0x480000` |

The 16 MB header is not a recovered partition table. The running-slot observation
does not establish the other slot, image-filesystem capacity, encryption keys,
calibration locations or a working recovery procedure. App image integrity and
boot authorization are distinct; see [OTA](ota-and-recovery.md).

The descriptor timestamp has **unknown timezone**, retained as null in the
identity JSON. The matching SDK's [descriptor initializer](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_app_format/esp_app_desc.c)
uses compiler date/time macros, and its [structure](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_app_format/include/esp_app_desc.h)
contains no timezone field. No vendor build-environment provenance was recovered.
Neither the frame's configured timezone nor the research computer's timezone
can fill that gap. H07 is closed with this explicit unknown.

A later live boot log exposed a **separate** build-log timestamp with an explicit
offset: `2026-07-16 10:15:17 -0400`. The exact string is embedded at file offset
`0xfd20`, virtual address `0x3c0ffd20`. GNU Xtensa disassembly confirms its load at
`0x42016b5d` and the logging call at `0x42016b71`, alongside build hash `f1555ee5`.
It differs from the descriptor time. Its origin as a source-control timestamp or
build-system timestamp is unproven, so it does not fill the descriptor timezone.

The USB-powered read also reports encrypted `nvs`, a valid running `app1`, and a
CW2217 chip ID of `0xA0` with configured 10 mΩ sensing. Encrypted NVS does not
establish whole-flash encryption or secure-boot/eFuse state. The owner has chosen
to keep the enclosure closed; physical pad/component identification is deferred.

## Address translation

The [identity JSON](firmware-identity.json) records all six image segment headers.
For the two main flash-mapped regions used in these notes:

| Region | Virtual start | File data offset | Length |
| --- | --- | --- | --- |
| Main DROM | `0x3c0f0020` | `0x20` | 3,014,832 bytes |
| Main IROM | `0x42000020` | `0x2f0020` | 970,436 bytes |

Within those segments:

```text
DROM file offset = virtual address - 0x3c0f0000
IROM file offset = virtual address - 0x42000000 + 0x2f0000
```

These equations address bytes in the downloaded app file. Do not use them as
whole-flash write offsets. A synthetic ELF used for analysis is not flashable.

## Display and wiring

This app targets the Large panel, portrait-native **1440 × 2560**, with eight
controller blocks. Its raw wire image is **2,304,000 bytes**, which is larger than
`width * height / 2` because of controller padding. It is not ordinary row-major
4bpp. Use the tested packing in
[`image_convert.py`](../../custom_components/fraimic/image_convert.py).

Spectra 6 nibble values used by the integration are `0, 1, 2, 3, 5, 6` for black,
white, yellow, red, blue and green respectively; nibble `4` is unused. The
integration includes dithering, orientation and calibrated preview colors.
Do not transfer the 13.3-inch panel's packing or timings to this build.

Recovered display initialization at `0x42022140`:

| Signal | GPIO |
| --- | --- |
| SPI clock | 12 |
| MOSI / MISO | 45 / 48 |
| IC1–IC4 chip selects | 15, 16, 17, 18 |
| IC1–IC4 data/command | 4 |
| IC5–IC8 chip selects | 8, 3, 46, 9 |
| IC5–IC8 data/command | 5 |
| 12 V enable | 40 |
| Shared I2C SDA / SCL, observed in logs | 10 / 11, at 100 kHz |
| Microphone PDM clock / data input | 41 / 42 |

Microphone initialization at `0x4201fd90` configures **I2S0 PDM RX**, 16 kHz,
16-bit mono. The GPIO configuration stores clock 41 and first data input 42.
The call target `0x420500e0` identifies itself as `i2s_channel_init_pdm_rx_mode`;
the config layout was checked against the matching
[ESP-IDF PDM header](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_driver_i2s/include/driver/i2s_pdm.h).
The microphone's physical part number is unknown.

Modules include the panel power/conditioning driver, PMIC, TCA9534 GPIO expander,
CW2217 fuel gauge, accelerometer, touch/button handling, I2S microphone and LED
state manager. Probe code names LIS3DH, BMA255 and MSA311/MSA321; this is not proof
of which accelerometer is fitted to the investigated unit.

### Accelerometer target and orientation semantics

The primary register helpers `0x4202915c` / `0x420291b0` use fixed seven-bit I2C
address **`0x1e`**. Initialization `0x42029520` reads register `0x0f` and expects
**`0x41`**, then writes `0x20=0x57`, `0x23=0x80` and `0x26=0`, waits ten ticks
(100 ms) and requires an acceleration read to succeed. The embedded probe table
labels the corresponding target **LIS2HH12TR**; its expected identification value
matches the manufacturer's [LIS2HH12 datasheet](https://www.st.com/resource/en/datasheet/lis2hh12.pdf).
This narrows the software target, not the physically verified part marking.

The alternative probe table at `0x3c140378` contains:

| Embedded candidate label | I2C address | Identification register / expected value |
| --- | --- | --- |
| LIS2HH12TR, alternate configuration | `0x1e` | `0x0f` / `0x41` |
| LIS2HH12TR, address variant | `0x1d` | `0x0f` / `0x41` |
| LIS3DH | `0x19` | `0x0f` / `0x33` |
| LIS3DH, alternate address | `0x18` | `0x0f` / `0x33` |
| BMA255 | `0x18` | `0x00` / `0xfb` |
| BMA255, alternate address | `0x19` | `0x00` / `0xfb` |
| MSA311/MSA321 | `0x62` | `0x01` / `0x13` |

Those names do not establish working alternative drivers. GNU confirms that
`0x420293e4` returns zero both after logging a matching candidate and after
exhausting the table. Its initializer caller interprets zero as failure and
clears availability. The ordinary register helpers also retain address `0x1e`;
this probe does not install a new address/register map. A “Found compatible
accelerometer” line from that branch would therefore not prove initialization
continued successfully. This is a static defect/limitation; no alternate chip
or failed-probe experiment was performed.

Acceleration reader `0x42029264` reads status register `0x27`, then six separate
byte registers `0x28`–`0x2d`, assembling signed 16-bit X/Y/Z values. It checks
transaction return codes but does not examine the status bits for fresh data.
There is no burst/snapshot transaction in this reader. Coherent sample timing
under motion or I2C contention remains untested.

Classifier `0x42029754` and string wrapper `0x420297c4` implement:

```text
unavailable sensor or read failure -> portrait
abs(X) > abs(Y)                    -> portrait
otherwise                         -> landscape
```

Equality, including X=Y=0 after a successful read, selects landscape. Z, signs,
confidence, filtering and hysteresis are absent from this decision. Upside-down
portrait and reversed landscape have the same respective strings; there is no
four-way rotation angle in this protocol field. A near-diagonal/noisy sample can
change classification without the frame being remounted. These are consequences
of the comparison, not measured physical jitter.

Helper `0x420298d0` initializes or resumes the sensor when unavailable and can
power it down after reading. Its two recovered callers, the poll and voice-upload
worker, both pass 1, retaining sensor operation at that point. Resume writes
`0x20=0x57` and waits five ticks (50 ms); ordinary shutdown writes `0x20=0` and
clears the available flag only on success. The “initialized before” byte is
separate, so later reads can resume without repeating identification/configuration.
No energy-use conclusion follows from this call ordering alone.

The voice worker samples orientation **after successful audio upload, immediately
before finalize**. It is not a capture-start snapshot or a continuous orientation
event. The poll samples when constructing its request. Neither wire request
distinguishes a measured portrait result from the portrait error fallback.
Store the received orientation with each backend job/render and keep an explicit
owner rotation override if four-way mounting matters. The existing saved Large
log reports `landscape`, but contains no part marking or physical rotation test.

The vendor display power-down path contains discharge delays totaling about
13 seconds. Recovered [conditioning modes](rendering-and-concurrency.md#conditioning-adds-full-panel-clear-cycles)
add a black or white/black full-panel clear before the artwork. They use the
ordinary refresh path and do not establish partial-refresh/custom-waveform
support. Such support and a speech-output speaker remain unverified. Retaining
the display driver and power sequencing is a much smaller first step than
replacing the complete firmware.

## One PSRAM buffer serves audio and images

This is **Large's** allocation design. [Standard uses separate recording and
image allocations](standard-model-comparison.md#separate-recording-and-image-allocations)
in the pinned 0.2.28 build.

`0x42028d94` allocates **2,304,000 bytes** of PSRAM and stores its pointer through
the literal at `0x42003590`. Both accessors return that same pointer:

| Accessor | Role | Reported capacity |
| --- | --- | --- |
| `0x42028e68` | Recording buffer | `0x42028e74` returns 2,120,000 bytes |
| `0x42028e88` | Image buffer | `0x42028e94` returns 2,304,000 bytes |

The recording start routine reserves the first 44 bytes for the WAV header.
`0x420201d4` writes that header in place and returns the same buffer, without
creating an independent WAV copy. The normal voice sequence uploads audio before
downloading its resulting image into this memory.

The renderer's `epdImageDataBuffer` at `0x3fca75d4` is also initialized from the
image accessor. Its copy call does not create an independent image snapshot for
the ordinary shared-buffer input. See [rendering and concurrency](rendering-and-concurrency.md)
for pointer initialization, early ownership gaps and the render worker's lifetime.

**Inference:** concurrent LAN image uploads, cloud downloads or new recordings
could invalidate data still in use. The follow-up trace found that the stock raw
upload handler writes into shared memory before the render-busy wait. The alias
and ordering are confirmed; a deliberate concurrent-corruption experiment was
not performed. A firmware fork needs one explicit owner for the buffer, or a
carefully budgeted separate allocation. A backend-only scheduler cannot enforce
every local HTTP entry point's buffer ownership.
