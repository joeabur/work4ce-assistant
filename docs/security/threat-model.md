# Initial threat model

Scope: local, synthetic, read-only vertical slice. This is a design review, not a completed penetration test or formal compliance assessment. Verify implemented controls with executable tests before claiming them effective.

## Assets and trust boundaries

Protect operator tokens, authenticated identity, tenant-scoped reports, capability grants, reviewed connector definitions, evidence provenance, local state and audit history. HTTP clients, telemetry, connector responses and MCP descriptions are untrusted. The backend supplies identity and policy; connectors cannot self-authorize. The host administrator remains trusted for this demo.

## Threats and required controls

| Threat | Initial control | Residual risk / required follow-up |
|---|---|---|
| Unauthenticated execution | Require demo bearer token or verified OIDC JWT, reject missing/invalid credentials | OIDC fixtures cover signatures/time claims; live identity lifecycle, rotation, revocation and deployed TLS remain pending |
| Demo credentials used in production | Fail startup outside demo mode; OIDC mode never falls back to demo tokens | Live identity and enterprise operational validation must precede deployment |
| Cross-tenant report access | Assign tenant in trusted context and scope storage reads | Synthetic subject-role mapping is tested; production multi-tenant identity and database policies remain pending |
| Unauthorized connector substitution | Reapply connector allowlist, trust, health and capability policy on every selection | Administrative workflow and remote attestation are future work |
| Manifest/tool poisoning | Preserve reviewed discovery and reject definition changes | Full supply-chain signing and distributed registry governance pending |
| Prompt injection in event text | Deterministic investigator treats text as data; no response executor exists | LLM introduction requires structured plans and adversarial evaluations |
| SSRF / credential forwarding | Fixed loopback reference service, no redirects, no arbitrary executable configuration | General remote connector egress, DNS rebinding, OAuth and network isolation pending |
| Malformed or oversized output | Schema validation, bounded result size and deadlines | Process CPU/memory limits and streaming backpressure require further hardening |
| Fabricated evidence or conclusions | Preserve raw event, source connector, hashes and evidence references | Hashes detect accidental changes; they do not prove a remote source is truthful |
| Database tampering or token disclosure | Avoid credential logging; separate runtime secrets from stored reports | Database administrator can rewrite records; secure remote audit and encryption absent |
| Unsafe response action | Read-only gateway rejects privileged classes; cancellation fences stale commits | Full approval lifecycle, single-use binding and isolated executor unimplemented |
| Service failure loses work | Persist reports, workflow checkpoints, budgets and lease/revision fencing; explicit resume supported | No automatic scheduler or general multi-step recovery; backup/restore drills pending |
| Demo/live data mixing | Synthetic event schema and fixed demo tenant | No live connector is enabled; validate future ingestion paths independently |

Workflow idempotency and checkpoints are scoped by tenant/subject. Completed execution replay requires current source grants and reviewed manifest hash. Saved-report reading is separately tenant-authorized. Queue admission caps nonterminal work at 100 per owner, while terminal/audit retention and request-rate limits remain future work. Leases bound stale ownership; they do not guarantee cancellation of remote I/O or exactly-once reads.

## Review requirements before production

Review current authoritative OWASP, NIST and protocol guidance using supported network-permitted tools. Complete dependency/advisory checks, security scanning, OIDC/TLS review, connector isolation, approval lifecycle tests, recovery drills, tenant-isolation testing and AI evaluation. Do not infer those checks from a successful demo.


## Model assistance boundary

Treat model outputs and telemetry as untrusted. The model can return only one existing search plan and exact evidence quotations; deterministic validators enforce original query scope, valid source IDs/hashes and allowed assessment combinations. Backend identity/authorization and integration policy remain independent. Outgoing fields are allowlisted, recognizable credential patterns are blocked, and explicit provider-mode consent plus trusted HTTPS configuration are required. These controls do not constitute enterprise DLP or privacy certification.

Persistent reservations precede provider attempts. Failures, retries and unknown cancellation outcomes consume budget; result commits require a current workflow lease/deadline and reject cancelled work. Fingerprints bind route, synthetic designation, prompt/schema and operator prices/budgets without credentials. Cached outputs are owner/input/configuration-bound and revalidated. Remaining risks include provider-reported usage, incorrect configured prices, inference duplication before cache commit, process-local circuit state, limited prompt-injection evaluations and unverified live-provider behavior.


## Human-review and approval boundary

Requester/reviewer identity and grants come from trusted authentication. Report decisions and response approvals are distinct, cannot be self-issued, and bind immutable report/request hashes. Pending review refresh rotates its identifier; action approvals cannot extend the original expiry. Revoked, missing, mismatched, expired or consumed approvals fail closed. Current source grants are checked by policy, and source enablement is locked again at consumption.

Review notes are private to the requester and authorized reviewers, even where tenant report-read access is broader. A regression tests the report endpoint as well as the dedicated review route. Human comments remain untrusted text and are rendered as React text by the workbench. The current consumer only writes a synthetic dry-run record; privileged worker isolation, production asset policy, real connector verification and tamper-resistant audit remain future boundaries.

## Browser workbench boundary

The static shell is public and contains no credentials or case data. Same-origin authenticated requests fetch data with cache disabled and cookies omitted; the server attaches no-store to HTTP responses. Identity/permissions from `/me` control visible actions but never grant backend authorization. Case summaries are owner-scoped except for trusted reviewers and exclude raw reports, comments and approval nonces.

Tokens live only in memory, clear on reload/sign-out, and are never placed in URLs, browser storage or cookies. Pending fetches are aborted and fenced by session generation; report selections are similarly fenced. This reduces persistence/exposure but does not protect a token from a compromised browser or authorized same-origin script. Sign-out does not revoke an already-issued token; OIDC login/revocation lifecycle and deployed TLS remain future work.

Telemetry and comments are text nodes, with no raw HTML rendering. The CSP permits only local assets and hashes of trusted compiled inline scripts; it excludes unsafe-inline/unsafe-eval, frames and external connections. No external fonts/assets or service worker are used. Browser checks confirmed literal hostile-markup display and no CSP violations for the tested workflows. These checks do not constitute a full XSS, accessibility or browser-security assessment.

History cursors are bounded, versioned position markers tied to the trusted tenant/owner read scope. They are unsigned and may be constructed by a client; no cursor field controls authorization or query scope. Each request uses current backend grants, with tenant/owner filters applied independently of the marker. SQL ordering uses creation time and ID rather than mutable report status. Private notes and approval nonces remain excluded from summaries. The workbench fences older-page responses on refresh and logout to prevent stale history from repopulating a newer view. Large-history performance, rate limits and snapshot semantics remain separate concerns.
