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
| Unsafe response action | Read-only gateway rejects privileged classes | Full approval lifecycle, single-use binding and isolated executor unimplemented |
| Service failure loses work | Persist reports, state and errors in migrated SQLite/PostgreSQL; restart persistence tested | Automatic resume, idempotency and recovery drills are not established |
| Demo/live data mixing | Synthetic event schema and fixed demo tenant | No live connector is enabled; validate future ingestion paths independently |

## Review requirements before production

Review current authoritative OWASP, NIST and protocol guidance using supported network-permitted tools. Complete dependency/advisory checks, security scanning, OIDC/TLS review, connector isolation, approval lifecycle tests, recovery drills, tenant-isolation testing and AI evaluation. Do not infer those checks from a successful demo.
