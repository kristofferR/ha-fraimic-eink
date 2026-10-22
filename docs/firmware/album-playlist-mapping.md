# Local album compatibility and HA playlists

[Research index](README.md) · [Stock proxy](local-api.md#album-proxy-contract) · [Voice features](voice-feature-proposal.md)

The proposed adapter should keep **HA's library and saved playlists as content
owners**, with a small compatibility record for stock album IDs, frame assignments
and wake scheduling. An album is not an active playback queue, and a stock album
mutation is not a display acknowledgment. This is a design/host contract; no
production adapter or scheduler was implemented.

## Supported first subset

| Stock album field / operation | Proposed local interpretation |
| --- | --- |
| Short opaque album `id` | Stable compatibility ID mapped explicitly to a saved HA playlist; do not derive identity from names |
| `upload_ids` in order | Resolve each original through a stable upload/library-ID map, then use picture slides referencing library images |
| `name`, description | Saved catalog name plus adapter metadata; duplicate names require explicit ID selection |
| `playback_mode: sequential/random` | Saved playlist shuffle false/true; actual active-queue transition is separate |
| Complete positive interval in minutes/hours/days | Convert to seconds; persist schedule metadata and let one delivery owner compute stock poll deadlines |
| `active` and device assignments | Explicit per-frame schedule bindings, not an immediate queue activation or frame send |
| Empty `upload_ids` | Preserve a wake-only scheduling record; no artwork slide and no redraw |
| PUT omitting top-level fields | Preserve omitted values; replace a supplied schedule as one complete object |
| DELETE | Remove compatibility binding and its managed catalog view; retain reusable originals and do not silently erase an active queue snapshot |

Do not map arbitrary vendor uploads straight to signed URLs in slides. Import or
resolve the original into the library first; signed URLs expire and are not stable
image IDs. Per-model/mount rendering belongs at the existing render-only boundary.

Initially reject `specific_days`, incomplete/non-positive interval schedules and
unsupported null clearing explicitly. Do not silently translate a calendar rule
into an interval. The saved vendor schema permits several of these shapes; schema
acceptance alone is not an executable local schedule. Full calendar support needs
its own semantics and timezone validation.

Keep assignment metadata separate from the legacy one-playlist-per-frame map.
An owner album can have multiple assignments, and a frame may have several albums.
The local adapter needs an explicit arbitration rule before starting playback;
one active queue/delivery owner per frame is the simpler initial boundary. The
fixture stores assignments but does not compute deadlines, replace live queues or
resolve competing active albums.

## Credentials and mutation boundaries

The stock proxy uses a device key in path/body, without forwarding an owner Bearer
token. Bind that key to a server-owned frame identity. The proposed first subset
allows a device to manage only its own single-frame compatibility records; shared
or other-frame records require the separate owner management interface. This is a
deliberately narrower local policy, not a claim about vendor authorization. The
earlier account/device-key read returned the same account albums, so vendor listing
must not be assumed to be frame-isolated.

Require an object and reject duplicate identity members. The actual firmware only
replaces the first case-insensitive `device_key` occurrence and can forward arrays,
scalars or duplicate keys. Do not treat that transformation as authorization.
Return compact complete JSON, including a deletion result. Keep album work fast:
the stock proxy blocks its shared HTTP-server task while forwarding the response.

Preserve stable playlist/slide IDs with a diff or transactional replacement in a
production implementation. Record an operation/revision for replay and reconcile
after a lost response; stock mutations do not provide an idempotency token. A
playlist edit must not rebuild the active queue implicitly. Removing a binding
also needs an explicit policy for an already-issued image/deadline; no local
metadata deletion can recall a response the frame already received.

## Isolated mutation evidence

The unchanged HA release
[`e5450665`](https://github.com/kristofferR/ha-fraimic-eink/commit/e5450665ddbb57c2542c883375ba68c0aefbb1b1)
cloud client and art/wake album payload builders were pointed at a disposable
`127.0.0.1` server. A request guard rejected any other destination; login was
disabled and all credentials/IDs were synthetic. HA storage used existing test
substitutes, and the actual saved-playlist/queue APIs supplied the content mapping.

**Nineteen checks passed**, with eighteen decoded authorized loopback requests
plus rejected malformed/unauthenticated requests. They establish:

- Real art creation/update payloads map existing originals and interval seconds;
  the saved content changes while an existing queue snapshot stays unchanged.
- Partial top-level edits retain schedule/images; random maps to shuffle, while
  multi-frame assignments remain metadata without triggering playback.
- The actual wake-album builder sends an empty image list, which creates no art
  playlist in the proposed subset.
- The existing client reads complete schema-shaped list/create/update/delete
  responses and reports the fixture's 422/403 errors correctly.
- Incomplete/specific-day schedules, missing originals, unknown assignments and
  nullable active state are rejected without changing the fixture's album record.
- Synthetic device credentials can update/delete their own record and cannot
  reassign it to another frame or edit a shared album. Duplicate keys and absent
  credentials are rejected. These are fixture-policy checks, not vendor tests.
- Deletion retains original references and the preexisting queue snapshot.

The disposable mapping deliberately rebuilds a saved playlist and therefore does
**not** preserve its playlist/slide IDs, supply atomic mutation, survive process
restart or implement idempotency. It is a payload/API compatibility fixture, not
the recommended production algorithm. Scheduler activation, computed deadlines,
the physical firmware proxy, vendor mutations and real authorization remain
untested. C12's design/host milestone is complete; its account/device criterion
stays deferred. See [validation and hashes](validation-2026-10-22.md#local-album-mutation-contract-c12).
