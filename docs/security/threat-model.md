# Initial threat model

Scope: local, synthetic, read-only vertical slice. This is a design review, not a completed penetration test or formal compliance assessment. Verify implemented controls with executable tests before claiming them effective.

## Assets and trust boundaries

Protect operator tokens, authenticated identity, tenant-scoped reports, capability grants, reviewed connector definitions, evidence provenance, local state and audit history. HTTP clients, telemetry, connector responses and MCP descriptions are untrusted. The backend supplies identity and policy; connectors cannot self-authorize. The host administrator remains trusted for this demo.

## Threats and required controls

| Threat | Initial control | Residual risk / required follow-up |
|---|---|---|
| Unauthenticated execution | Require configured bearer token, reject missing/invalid credentials | Enterprise OIDC, expiry, rotation, revocation and TLS remain pending |
| Demo credentials used in production | Fail startup outside explicit supported demo mode | Production identity implementation must precede deployment |
| Cross-tenant report access | Assign tenant in trusted context and scope storage reads | Multi-tenant identity mapping, database policies and adversarial tests needed |
| Unauthorized connector substitution | Reapply connector allowlist, trust, health and capability policy on every selection | Administrative workflow and remote attestation are future work |
| Manifest/tool poisoning | Preserve reviewed discovery and reject definition changes | Full supply-chain signing and distributed registry governance pending |
| Prompt injection in event text | Deterministic investigator treats text as data; no response executor exists | LLM introduction requires structured plans and adversarial evaluations |
| SSRF / credential forwarding | Fixed loopback reference service, no redirects, no arbitrary executable configuration | General remote connector egress, DNS rebinding, OAuth and network isolation pending |
| Malformed or oversized output | Schema validation, bounded result size and deadlines | Process CPU/memory limits and streaming backpressure require further hardening |
| Fabricated evidence or conclusions | Preserve raw event, source connector, hashes and evidence references | Hashes detect accidental changes; they do not prove a remote source is truthful |
| Database tampering or token disclosure | Avoid credential logging; separate runtime secrets from stored reports | SQLite administrator can rewrite records; secure remote audit and encryption absent |
| Unsafe response action | Read-only gateway rejects privileged classes | Full approval lifecycle, single-use binding and isolated executor unimplemented |
| Service failure loses work | Persist investigation state and explicit errors | Restart/resume, idempotency and recovery testing are not established |
| Demo/live data mixing | Synthetic event schema and fixed demo tenant | No live connector is enabled; validate future ingestion paths independently |

## Review requirements before production

Use current authoritative OWASP, NIST and protocol guidance when network access is restored. Complete dependency/advisory checks, security scanning, OIDC/TLS review, connector isolation, approval lifecycle tests, recovery drills, tenant-isolation testing and AI evaluation. Do not infer those checks from a successful demo.
