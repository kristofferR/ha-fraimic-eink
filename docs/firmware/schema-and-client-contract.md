# API schemas versus the stock client

[Research index](README.md) · [Cloud protocol](cloud-protocol.md) · [Checklist](research-todo.md)

An emulator needs the stock client's contract, not just generated models from
the vendor's OpenAPI document. This comparison uses two preserved schemas and
the existing 21 October Standard capture. It makes no new network requests and
does not establish the vendor's current deployment or mutation permissions.

## Snapshot changes

The repository's [OpenAPI snapshot](../fraimic-cloud-api/openapi.json) is described
by its [route reference](../fraimic-cloud-api/routes.md) as captured on 7 July
2026. It entered the repository in
[7eed22e](https://github.com/kristofferR/ha-fraimic-eink/commit/7eed22e58c0d5666728c2ef5362bb412ef3ad017).
The private research copy was retrieved from the vendor's public
`/openapi.json` over verified HTTPS on 21 October. Their hashes, sizes and
comparison results are retained in [sanitized metadata](schema-comparison.json).

Both snapshots advertise **25 method/path operations across 23 paths**. No
operation was added or removed. The schema count increases from 33 to 34:

| Change in the October copy | Meaning / limit |
| --- | --- |
| Add `AccountInfo`, requiring boolean `email_verified` | Describes the account-verification object consumed by the poll parser |
| Add optional nullable `CheckUploadResponse.account` | Existing capture returned null; the firmware's promotion branch is separately traced |
| Replace documented poll query `is_periodic_poll` with `include_account` | Stock still sends `is_periodic_poll=false`; removal from the document does not establish removal from the service |
| Add optional nullable `RefreshImageRequest.device_id` | Image refresh can advertise device targeting; no mutation was tested here |
| Revise the image-refresh description to mention optional device locking | Documentation change, not permission or persistence evidence |

Those are the complete structural differences between these two saved JSON
documents. They are not a release history or proof that server behavior changed
only in those ways. `display_type` was absent from the poll parameter list in
both copies, although the frame sends it.

## Reconciliation with the captured exchanges

An offline field-name/type audit checked all **24 decoded origin API exchanges**
against the October copy. It found no missing declared required fields or
incompatible declared field types in the recorded shapes. The following request
members were present without being declared:

| Captured exchange | Count | Undeclared fields |
| --- | --- | --- |
| `GET /api/v1/upload/check/{device_key}` | 18 | Query `display_type`, `is_periodic_poll` |
| `POST /api/v1/upload/audio/presign` | 1 | JSON `user_id` |
| `POST /api/v1/upload/audio/finalize` | 1 | JSON `user_id` |
| Account setup and global setup assets | 4 | None identified |

All these captured responses were HTTP 200. The request schemas do not explicitly
forbid additional properties, so “undeclared” is not itself a schema violation.
Acceptance does not show whether the service used, ignored or validated an extra
field. A stock-compatible adapter should accept the known stock shape while
binding identity to its validated device credential, rather than treating a
submitted `user_id` alone as authorization.

The audit used redacted type shapes, not raw values. It cannot verify enum values,
numeric/string constraints, runtime coercion, complete payload validity or
permission checks. Unconstrained dictionaries such as `device_settings` and
`device_info` also hide details from schema-only validation. The API capture
excludes the direct S3 upload/download bodies; those have separate evidence.

## Differences that affect implementation

| Area | Advertised schema | Stock-client / observed boundary |
| --- | --- | --- |
| Audio presign input | Only `device_key` is declared and required | Both pinned clients send `user_id` too; do not reject that known extra field |
| Audio presign output | Requires `success`, `url`, `fields`, `key`, `message`; `upload_id` is optional/nullable | The recovered client consumes URL/key/fields, with fixed copy limits and permissive parsing; return a coherent success object rather than relying on that permissiveness |
| Audio finalize output | Requires `success` and `message`; URL and public ID may be null; no declared `status` | A usable image URL is needed for the stock voice workflow to succeed. The captured successful response omitted `status` and had a null public ID |
| Setup output | Requires `success`, `message` and dictionary `device_info` | Static/host parsing accepts less, but usable pairing/voice still needs a stable identity. Parser acceptance is not independent provisioning |
| Poll settings | `device_settings` is an unconstrained dictionary | The client applies a complete four-switch snapshot with defaults for missing members; this behavior cannot be generated from the schema |
| Poll compatibility fields | No `user_settings`, `has_new_tasks` or `next_scheduled_image_time` properties | Firmware has separately traced copy/fallback branches; they are not evidence of current vendor emission |
| Authentication | Neither snapshot declares OpenAPI security schemes; some account-facing routes model `authorization` as an optional header parameter | Actual gallery reads require an account session; missing auth and a device key as Bearer returned 401 in earlier tests. Do not infer anonymous access from the schema |
| Transcript and prompt | Gallery items advertise nullable transcript/style/metadata; finalize does not | The correlated voice item exposed a transcript through owner-authenticated gallery reads. The vendor's final generation prompt was not recovered |

The [presign and finalize traces](voice.md),
[settings/enrollment parsing](cloud-protocol.md) and
[observed gallery authorization](cloud-protocol.md#albums-and-gallery) supply the
behavior behind this table. Neither snapshot advertises a device job-status or
cancellation endpoint. That agrees with the recovered synchronous finalize flow;
it does not prove the vendor has no private endpoints.

For the local backend, maintain a small explicit adapter contract: known stock
request fields, complete settings snapshots, bounded response sizes, synchronous
finalize and model-specific assets. Keep the HA job/transcript/prompt/library
model separate from the stock wire format. A server-schema change alone cannot
add async jobs, command-only success or display acknowledgements to these builds.
Account mutations, authorization across other routes and complete independent
enrollment remain open; no new endpoint permission was exercised in this pass.
