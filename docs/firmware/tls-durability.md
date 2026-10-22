# TLS durability on the two saved firmware builds

[Research index](README.md) · [TLS contract](cloud-protocol.md#http-and-tls-requirements) · [Machine-readable evidence](tls-durability.json)

Investigated on 22 October 2026 for Large **0.2.29 / f1555ee5** and Standard
**0.2.28 / 4654a1d8**, addressing the certificate-lifecycle question in
[issue 99](https://github.com/kristofferR/ha-fraimic-eink/issues/99).

**The recovered firmware does not enforce certificate validity dates, and its
API TLS configuration supplies no revocation list.** Both models contain the
same trusted root material. Consequently, the saved certificate dates and the
CA's existing revocation do not establish a cutoff for these unchanged builds.
Hostname and signature-chain checks still apply. Future firmware can change
these policies; its behavior cannot be established before obtaining that image.

This pass used saved applications/certificates, a public signed CRL and isolated
host verification. No frame, network rule, installed certificate, HA deployment
or firmware was changed. Newly generated fixture keys remain private.

## What is established

| Question | Result | Evidence boundary |
| --- | --- | --- |
| Can the leaf be replaced? | A newly signed leaf with a fresh P-256 key passes the matching host verification path. The earlier Large test accepted a different leaf with the original key. | Fresh-key physical rotation remains untested; no recovered leaf/key pin was identified. |
| Does the saved leaf stop working on 23 October? | No date-based rejection exists in the recovered verifier. Host verification accepts the original leaf after its expiry, before its start date, and with the clock set to 2044. | Static plus host evidence, not a physical expired-leaf handshake. |
| Does intermediate expiry stop it in 2039? | Not under this date-disabled policy. It would stop a date-checking verifier using the saved native chain. | Date-checking control rejects the first second after the upper intermediate expires. |
| Has the signing intermediate been revoked? | Yes, on 18 October 2026 at 09:38:46 UTC, for CA Compromise. Both successful frame tests happened after that. | CA CRL signature and serial verified independently; the earlier tests were not a before/after revocation experiment. |
| Does the frame enforce that revocation? | The stock API path supplies a null CRL. Its compiled CRL checker therefore has no entries to check. | Adding the real CRL to the host fixture rejects the same chain. No OCSP-fetch or browser-blocklist integration was found in this path. |
| Can browser distrust silently replace this bundle? | No such update mechanism was found. The identified initialization path reads the bundle embedded in the application. | Exact pointer/caller census; not proof against arbitrary computed aliases or future code. |
| Can a firmware update break local TLS? | Yes. Removing the root, adding revocation enforcement, enabling dates, pinning a key or changing the expected origin can invalidate this arrangement. | Root removal and date/revocation changes are demonstrated in host controls; future vendor behavior remains unknown. |

## The certificate dates are metadata, not current firmware deadlines

These are the actual saved certificates, not generic lifetimes inferred from CA
documentation. All times below are UTC. Full fingerprints and public-key hashes
are in [the evidence file](tls-durability.json).

| Certificate | Valid from | Valid until | Role |
| --- | --- | --- | --- |
| Original `origin.fraimic.com` leaf | 21 Oct 2026 15:21:59 | 23 Oct 2026 16:21:59 | Original private research listener |
| Matching-name control leaf | 21 Oct 2026 19:12:37 | 21 Oct 2026 22:12:37 | Different certificate, same leaf public key; physically accepted by Large |
| EM OV TLS CA - G3C | 30 Apr 2025 15:37:41 | 28 Apr 2040 18:30:00 | Compromised signing intermediate |
| emSign Root TLS CA - G3 | 11 Jul 2024 15:43:36 | 9 Jul 2039 18:30:00 | Upper intermediate in the native chain |
| emSign ECC Root CA - G3 | 18 Feb 2018 18:30:00 | 18 Feb 2043 18:30:00 | Root represented by subject/public key in the firmware bundle |
| Alternative EM OV TLS CA - G3C, signed by AAA Certificate Services | 14 May 2025 00:00:00 | 31 Dec 2028 23:59:59 | Saved cross-sign alternative; this pass tests it only on the host |

If date enforcement were enabled, **9 July 2039 18:30:00 UTC** would be the
native chain's earliest intermediate ceiling, regardless of a longer-lived
leaf. The known lower intermediate key cannot renew its upper parent's
certificate. The alternative cross-sign reaches its date ceiling in 2028.
Neither ceiling is enforced by the two recovered date-disabled verification
paths. This does not promise indefinite hardware operation or compatibility
with other TLS clients.

The root bundle itself contains **152 records / 69,876 bytes**, identical in both
applications. Its SHA-256 is
`85a40d3a53f7c25ab90168b03eb00c1316ee1be23fb088daa0631bfeb2416c3f`.
Each record holds a DER subject and public key, with no certificate validity,
serial or revocation URL. The trusted emSign ECC root matches record 107 using
zero-based indexing; neither native intermediate is independently trusted there.
Thus the root's 2043 date is also absent from the bundle verification path.

## Why expiry and revocation do not stop this path

Eight complete reachable GNU instruction bodies match across the pinned models,
covering **589 instructions per image**. Instruction bytes were checked against
the recorded application hashes. These are analytical function identifications,
not recovered vendor symbols:

| Role | Large entry | Standard entry |
| --- | --- | --- |
| Bundle validation | `0x42044bbc` | `0x42040f80` |
| Bundle verification callback | `0x42044df4` | `0x420411b8` |
| Attach built-in bundle | `0x42044ec8` | `0x4204128c` |
| X.509 chain verification | `0x420897a8` | `0x42088e54` |
| Parent selection within a candidate chain | `0x4208958c` | `0x42088c38` |
| CRL verification | `0x420896bc` | `0x42088d68` |
| Top-level X.509 verification | `0x42089a10` | `0x420890bc` |
| TLS peer-certificate verification | `0x420732cc` | `0x420728c4` |

The chain body initializes each certificate's flags and proceeds directly to
trust/signature processing. It has no current-time acquisition or certificate
`valid_from`/`valid_to` comparisons. Parent selection likewise omits date-based
selection, and the CRL body omits CRL-date comparisons. This matches the
`MBEDTLS_HAVE_TIME_DATE`-disabled branches of the pinned
[Mbed TLS implementation](https://github.com/espressif/mbedtls/blob/98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8/library/x509_crt.c).
ESP-IDF 5.4.1 defaults this certificate-expiry option off, but the finding comes
from the binaries, not from assuming that default. See the
[configuration definition](https://github.com/espressif/esp-idf/blob/v5.4.1/components/mbedtls/Kconfig#L593).

The bundle callback filters only the `BAD_MD` flag before deciding whether it can
resolve `NOT_TRUSTED`. It does **not** generally erase expiry, revocation or
hostname errors. The date flags are never produced by the recovered chain path;
revocation is ineffective because attachment supplies a null CRL. The
[matching bundle source](https://github.com/espressif/esp-idf/blob/v5.4.1/components/mbedtls/esp_crt_bundle/esp_crt_bundle.c)
explains that distinction. Supplying an actual CRL produces `REVOKED`, which the
callback leaves intact.

An exact-reference census of the bundle pointer on each image finds the
initializer, lookup, verifier and attachment functions. The initializer's only
identified caller is attachment of the built-in blob. No independently fetched
trust-store update was identified. Browser/Android trust updates operate outside
this firmware: Google's announced distrust rollout does not update this embedded
bundle. See [Google's incident response](https://blog.google/security/protecting-chrome-and-android-users-from-compromised-emudhra-intermediate-ca-certificates/).

The downloaded [issuer CRL](https://crl.emsign.com/?roottlscag3.crl) has a valid
signature under the saved upper intermediate and lists serial
`296926C227A3A1526392B19482A504`, matching the signing intermediate. Its last update
and revocation timestamp are 18 October 2026 09:38:46 UTC; next update is
16 April 2027 09:38:46 UTC. The public
[CA incident record](https://bugzilla.mozilla.org/show_bug.cgi?id=2083449)
independently identifies the same certificate and revocation.

## Isolated verification and its limits

The host fixture builds the exact Mbed TLS submodule revision used by ESP-IDF
5.4.1 and uses the original SDK bundle source, with logging/error-platform stubs
and the extracted firmware bundle. A process-local clock override affects only
the fixture. **Fifteen cases pass under each of two configurations, 30 total:**
the recovered date-disabled policy and a date-enabled control.

Both configurations accept a replacement leaf with a fresh key and reject the
wrong hostname, an untrusted self-signed leaf, the chain with the actual CRL
supplied, and the chain after removing its root. They differ at the leaf's
start/end dates and the two intermediate expiry boundaries. The date-disabled
fixture also accepts the original chain at 1 January 2044; the control rejects it.
The date-enabled tests show that the clock override and expiry-sensitive cases
are effective, rather than silently exercising a fixed clock.

This executes native X.509 validation, not an entire TLS handshake or ESP32
application. Other library options use host defaults. The function comparison
checks operations and internal branches; external helper bodies are not all
recursively compared. Physical fresh-key rotation and an explicitly expired
certificate handshake remain untested. The earlier positive/negative
[Large controls](backend-emulation.md#negative-tls-controls-c03) and
[Standard capture](standard-model-comparison.md#poll-and-voice-observations)
provide the existing physical evidence.

## Consequences for the local backend

On these unchanged builds, certificate expiry and the already-published
revocation are not demonstrated time bombs for the local listener. Fresh leaf
issuance can be performed locally with the existing private signing material;
it does not require vendor renewal or ACME issuance. Normal certificate rotation
is still sensible for other clients and future date-enforcing builds. A running
listener's reload behavior and in-flight request preservation are separate
implementation concerns.

Treat compatibility as a property of an **exact firmware image**. Before offering
an update, compare its embedded root bundle, name/pinning behavior, date/revocation
policy and API origin. The emulator should continue returning `firmware: null`
unless an update is deliberately requested. The recovered OTA path does not
consult the auto-update preference getter, so that UI switch alone is not an
update barrier. No update-control settings were changed in this investigation.

A configurable owner-controlled origin and trust anchor remains the preferable
firmware direction. It removes reliance on a compromised third-party CA and the
vendor hostname. That is an implementation goal, not a prerequisite for the
already-demonstrated stock local backend.

## Replacement wording for issue 99

> TLS works on the pinned Large 0.2.29 and Standard 0.2.28 builds. They enforce
> hostname and signature-chain trust, but their recovered verifier omits
> certificate-date checks and the API TLS configuration supplies no CRL. The
> signing intermediate was already revoked before both successful device tests.
> Both applications contain the same embedded root bundle; no independent trust
> updater was found. Host verification accepts a fresh-key replacement leaf and
> the existing chain beyond its encoded expiry dates. Physical fresh-key rotation
> and expired-leaf testing remain open. Future firmware can change trust,
> revocation, date checks or pinning, so audit each image before offering it.

This is proposed wording; this research pass did not edit the GitHub issue.
