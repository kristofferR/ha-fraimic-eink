# Where the local backend should run

[Research index](README.md) · [HA reuse](home-assistant-roadmap.md) · [Protocol experiments](backend-emulation.md)

**Recommendation: a small companion listener for the stock frame protocol,
with ha-fraimic-eink owning artwork, rendering and voice-job history.** This is
an architecture recommendation backed by source inspection and isolated host
checks, not an installed service. It closes the bounded comparison in A05;
durable jobs, production authentication and integration remain A02–A04.

## Observed deployment

Read-only checks on 22 October 2026 found HA **2026.10.2**, a working Supervisor
app inventory, and the active `http/config` slot set to `stable`. That slot uses
port **8123**, has no server certificate/key or trusted-proxy settings, and has
no pending trial configuration. There is no `http` fragment in the main YAML.
The UI-managed HTTP configuration is therefore the useful evidence here;
absence from YAML alone would not establish the running configuration. This
does not inventory external reverse proxies or reserve port 443 on the host.

The integration source remains release
[`e5450665`](https://github.com/kristofferR/ha-fraimic-eink/commit/e5450665ddbb57c2542c883375ba68c0aefbb1b1).
Its management views use HA's normal bearer authentication. Its sidebar panel
also requires an administrator; that panel flag should not be confused with a
per-handler role check. No existing route's authentication was changed.

## Comparison

| Boundary | Protocol views inside HA | Companion listener |
| --- | --- | --- |
| Stock HTTPS origin | Needs a TLS front end or changes to HA's shared listener; a view cannot choose its own certificate | Owns the frame-facing TLS listener and stock paths |
| Certificate loading | HA creates the SSL context when binding its server; certificate replacement needs a deliberate reload/restart strategy | Can rotate its listener independently of HA; active requests still need draining or persisted recovery |
| Access to artwork | Direct calls into the integration | Narrow authenticated bridge to the integration |
| Startup/reload | Shares Core startup, shutdown and integration availability | Can retain accepted audio and serve already-frozen assets while HA is unavailable |
| Long finalize | HA cancels a handler on client disconnect; Core shutdown allows ten seconds for handler shutdown | Can own the frame's wait separately from generation, with an explicit job deadline and capacity |
| Logging | HA's debug wrapper logs `request.path`, which would include a stock poll's device key | Route-category logging can exclude credentials before any generic access logger sees them |
| Packaging | One integration, plus a TLS front end if preserving the present HA listener | One additional service/app and a small integration bridge |

HA-hosted views remain feasible. A tightly scoped reverse proxy can supply
stock-host TLS and route rewriting, but it adds another component and still
shares HA request lifetimes. A companion is preferred here because it can also
own upload tickets, private audio and immutable image delivery. It should not
grow a second artwork library, renderer or generation configuration UI.

The relevant pinned sources are HA's
[HTTP server](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/http/server.py)
and [view wrapper](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/helpers/http.py).
The latter defaults to authenticated views and can log the path at debug level.
Its general JSON helper may enable compression above 1,024 bytes; use explicit,
uncompressed stock-protocol responses instead of relying on that helper's
negotiation. A request handler is not durable job ownership.

### TLS and certificate maintenance

Both recovered frame builds require TLS 1.2. HA's version-pinned
[`server_context_modern`](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/util/ssl.py)
also sets a TLS 1.2 minimum. An isolated handshake using that exact builder,
a temporary synthetic certificate and a TLS-1.2-only host client succeeded.
Do not infer an HA TLS-version incompatibility from the name “modern”. This
does not establish acceptance of HA's certificate by either frame.

Stock API-origin trust remains a separate constraint: the earlier frame tests
accepted the private research chain for the stock hostname. An ordinary
certificate for an owner-controlled hostname does not by itself change the
firmware's hardcoded origin or installed trust. The experiment is not a durable
certificate provisioning/renewal solution. A supported custom origin/trust
configuration remains a later firmware direction.

The proposed listener should load its certificate privately, monitor expiration,
and make rotation independent of HA's own listener. Preserve accepted jobs and
artifacts before restarting it; a restart can still break a stock request, whose
retry behavior varies by stage. Certificate rotation, network cutover and a
renewed chain have not been tested on a frame. No key material belongs in the
repository or application logs.

## Minimum boundary to implement

1. **Frame listener:** only the recovered methods and paths, with explicit
   hostname/routing scope. Bind each device key to its enrolled device/user/model;
   do not accept a client-supplied user ID as independent authority. Retain the
   small JSON limit, complete settings-snapshot rules and default absence of OTA
   offers. Do not proxy arbitrary paths to HA or the vendor.
2. **Private upload/asset storage:** short-lived, unpredictable, purpose-bound
   tickets tied to job identity. A valid ticket is bearer access; the stock
   storage request need not carry another device credential. Validate WAV and
   multipart limits before acknowledging with exactly zero response bytes.
   Serve immutable, model-validated panel bytes with an exact length. Permit the
   firmware's bounded image retries; do not copy the experiment's one-shot guard
   into production as if it were a display acknowledgment.
3. **HA bridge:** a separate narrow credential for configured frames and job
   operations, never the owner's HA token or Supervisor token. If implemented
   as a HA view with `requires_auth = False`, that exemption applies only to the
   bridge view and must be replaced there by its own authentication and scope
   checks. Preserve the existing management views and panel authentication.
   Fixed route names keep credentials out of HA's path logger; never log bridge
   headers or job payloads. Do not expose generic service execution or URL fetches.
4. **One authoritative job identity:** persist the relationship between uploaded
   audio, transcript, final prompt, generated original, library ID and frozen
   panel artifact. The listener can spool transport data, while HA owns creation
   history. A disconnected finalize waiter must not silently delete that job or
   start a second paid generation. Reconcile after either process restarts.
5. **Bounded waits:** stock finalize waits synchronously for a ready URL. Put a
   backend end-to-end deadline below its 600-second transport wait, with budget
   for bridging and delivery; do not mistake repeated socket timeouts for one
   absolute firmware deadline. Return one final 200 with a short, exact-length
   JSON body only when ready. On failure use a short final error with no asset
   URL, never heartbeat chunks, a `202` job response or a failed-status URL.

Use a bounded queue and limits per frame plus a global concurrency/storage cap.
Expire abandoned tickets and recordings deliberately, separately from retention
of accepted artwork and history. Library insertion must deduplicate by job ID;
an asset read is delivery evidence, not proof of panel completion.

For this installation, a Supervisor app is a plausible deployment unit, using
its private `/data` storage and an explicitly published device port. Keep host
networking, broad host mounts and Supervisor/Core API access disabled unless a
concrete need is established. Ingress is useful for an owner UI, not the stock
device's hardcoded API origin. An external container is also possible; host and
port ownership, restart behavior and backups must be chosen during implementation.
These packaging boundaries follow the
[app configuration reference](https://contributors.home-assistant.io/apps/reference/configuration/).
No app was installed or configured by this pass.

## Isolated host evidence

**24 checks passed** with Python 3.14.8 and HA's pinned aiohttp 3.14.5 on Omarchy.
Only loopback listeners were used. The fixture executed the unmodified extracted
HA request wrapper and TLS-context builder; HA token recognition, bridge logic,
ticket handling, job limits and availability were synthetic substitutes.

- Missing/device/bridge credentials did not enter the normally authenticated
  management view; the synthetic HA token did. The narrow bridge accepted only
  its own credential, rejecting both frame and owner credentials.
- The actual wrapper's debug output contained the synthetic poll-path key.
  Closing a waiting TLS request cancelled its handler with HA's runner options.
- A synthetic standalone boundary enforced 4,096-byte JSON and 2,128,192-byte
  total upload limits, one-job capacity, ticket-purpose separation and expiration.
  Its successful upload acknowledgment was empty with explicit length zero.
- Simulated HA unavailability produced a finite 503 without an image URL while
  a previously prepared synthetic asset remained readable. All checked edge
  responses had exact Content-Length and no chunked transfer encoding; its
  structured events omitted synthetic credentials and tickets.

The synthetic sink tests transport bounds, not WAV decoding; the earlier
[voice fixture](backend-emulation.md#voice-capture-fixture-c05c06c07) covers that
contract. This pass does not exercise installed HA middleware/role permissions,
integration reload, durable recovery, a real bridge, certificate renewal, port
publication, concurrent generation or either physical frame. Those remain
implementation/device acceptance criteria, not reasons to repeat this comparison.

See [validation and artifact hashes](validation-2026-10-22.md#backend-deployment-boundaries-a05).
