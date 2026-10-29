# Durable synthetic investigations

Use the normal configured bearer authentication. All examples describe API requests; do not place credentials in scripts or logs. The backend assigns tenant, subject and connector grants.

## Queue, inspect, resume and cancel

Send `POST /investigations` with a body such as:

```json
{"query":"PowerShell","limit":20,"defer":true}
```

Add an `Idempotency-Key` header containing a stable identifier of 1–128 characters drawn from letters, digits, `.`, `_`, `:`, and `-`. The response is `202` with the workflow identifier and current state. Deferred work is persisted; it does not start an automatic worker. Without `defer`, the request executes immediately through the same durable workflow.

| Request | Behavior |
|---|---|
| `GET /investigations/{id}/state` | Return owner-scoped status, checkpoint presence, tool-call counts and deadline; no lease owner or idempotency-key internals |
| `POST /investigations/{id}/resume` | Explicitly claim and continue the workflow using current authorization |
| `POST /investigations/{id}/cancel` | Persist cancellation and invalidate the active worker's completion authority |
| `GET /investigations/{id}` | Read the stored report with tenant-scoped `investigations:read` authorization |

Resume/cancel/state are scoped to both tenant and subject. Cross-owner access returns 404. Active concurrent resume returns 409. Failed/cancelled workflows are terminal; create a new investigation when appropriate. Repeating an idempotency key with different query, event limit or configured budgets returns 409.

## Checkpoints and recovery

The default deadline is 120 seconds from enqueue, including queue time. Resume never resets the deadline or tool budget. Each workflow permits two actual connector invocations by default; reservations are persisted before invocation, including a failed connector followed by authorized fallback.

Workers use a 30-second lease. An interrupted worker releases its lease when possible; after an abrupt process exit, a new worker must wait for lease expiry before claiming. No automatic resumer or background scheduler is provided.

If the validated read result was checkpointed, resume reuses its original attributed evidence and stable identifiers without another external query. If interruption occurred before checkpoint commit, the read may be retried within the remaining persisted budget. This is bounded at-least-once read behavior, not exactly-once execution. Writes and response actions remain denied.

A completed POST/idempotent replay rechecks current permissions, the original source connector's enabled state, allowlist and reviewed manifest hash. It cannot use saved evidence to restore revoked execution grants. Reading an already saved report remains a separate tenant-scoped `investigations:read` operation.

Explicit cancel does not guarantee that an already running remote request stops. It fences later checkpoint/report commits, so the stale worker cannot overwrite cancellation. Cancellation of an application task instead leaves recoverable state. If cleanup fails, the lease may remain until expiry; error details are redacted.

## Trusted backend limits

| Environment variable | Default | Valid range |
|---|---|---|
| `WORK4CE_MAX_TOOL_CALLS` | `2` | Integer 1–8 |
| `WORK4CE_INVESTIGATION_TIMEOUT_SECONDS` | `120` | 0.01–600 seconds |

Configure these through trusted environment settings. Request bodies cannot override them; injection attempts are rejected. Persisted workflows retain their original budget/deadline binding, and changing arguments or configured budgets under the same idempotency key conflicts.

## Capacity and limitations

Four API execution slots guard immediate execution, resume and deferred admission. At most 100 nonterminal workflows may exist per tenant/subject; admission is atomic across store instances. Terminal workflow and audit retention are unbounded, and request-rate controls remain future work.

Migration head is `0004_reviews`. SQLite auto-upgrades and preserves known legacy data; PostgreSQL needs `python -m work4ce_assistant database migrate` before startup. Back up useful data before upgrading.

The default read/report workflow is deterministic; optional structured model assistance and persistent usage accounting are described in the model guide. Human review, multi-step reconciliation, general AI reasoning, tokenizer/billing assurance, distributed scheduling and response approvals remain incomplete. Synchronous storage may block the event loop. See `docs/prompt-status.md` and the release-readiness report for scope and verified evidence.


## Executed recovery evidence

The full PostgreSQL/SQLite suite passed 225 tests in 82.533 seconds with zero skips. Four actual API/worker end-to-end tests terminate a worker using `os._exit` after checkpoint commit, restart the API and manually resume after lease expiry. Both databases retained stable evidence and issued no second REST search. This tests recovery at the implemented read boundary, not automatic scheduling or every possible failure point.
