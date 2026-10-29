# Human review and synthetic response approvals

This increment adds a durable report-review gate and a single-use approval consumer for synthetic dry runs. It does not execute endpoint isolation or any external response action. The read-only integration gateway continues to reject writes.

## Identities and permissions

The API assigns permissions from trusted configuration. Models, request bodies and OIDC role claims cannot assign reviewers or approval authority.

- The demo analyst can investigate, request review, propose a synthetic response and consume its approval through simulation.
- The separate demo admin can review reports and approve responses. The requester cannot approve their own report or response, even when holding admin permissions.
- OIDC supports the server-mapped role `reviewer` in `WORK4CE_OIDC_SUBJECT_ROLES`. It can read/review and approve, but cannot run investigations, propose responses, simulate them or administer connectors. Existing `analyst` and `admin` mappings remain supported.

Review and approval are separate decisions. Accepting a report does not approve an action. Every simulation requires current permissions, the original requester, an unexpired matching action approval and current source authorization.

## Report checkpoint

Set trusted `WORK4CE_REQUIRE_HUMAN_REVIEW=true` to require review after collection/report generation. The default is `false` for compatibility. Only exact `true` or `false` values are accepted; request bodies cannot disable this policy. The requirement is bound to the workflow and idempotency key.

The execution state becomes `completed` when collection is finished. A separate review record makes the public report status `awaiting_review` until a different authorized subject decides. The state endpoint exposes `execution_status` to distinguish collection completion from acceptance. Evidence, report hashes and model usage do not change during review, and resume cannot bypass it.

For a report created without the mandatory gate, its owner may explicitly request review. This also changes the public status to `awaiting_review` without repeating collection.

| Request | Purpose |
|---|---|
| `POST /investigations/{id}/review` | Owner requests or refreshes an expired pending review |
| `GET /investigations/{id}/review` | Owner or authorized reviewer reads the review record |
| `GET /reviews` | Reviewer reads a bounded tenant-scoped review queue |
| `POST /investigations/{id}/review/decision` | Reviewer supplies `review_id`, `decision` (`approved`/`rejected`) and optional `comment` |

Pending reviews expire after 300 seconds. An owner refresh rotates the review identifier, so a stale decision cannot approve the new request. Approved and rejected decisions are terminal for the immutable report; approved review remains valid after its original decision deadline. Rejection exposes `review_rejected`; use a new investigation to collect corrected evidence. There is no edit/retraction workflow for approved reports yet.

Tenant-wide `investigations:read` still permits reading report content and business status. Private review metadata and comments are returned only to its requester or a subject with review permission. The dedicated review endpoint denies unrelated analysts. Do not put credentials in comments.

## Synthetic response lifecycle

Only action `endpoint.isolate`, fixture targets `demo-host-1`/`demo-host-2`, and parameters `{"duration_minutes":1..60}` are accepted. The target must appear in the bound synthetic report evidence. This fixture target check is not a production asset-authorization system. The report must have an approved, current, unchanged review before a proposal is created or used.

| Request | Purpose |
|---|---|
| `POST /responses` | Owner supplies `investigation_id`, action, target, parameters and optional `lifetime_seconds` (default 300; 1–900) |
| `GET /responses` | Owner sees their proposals; authorized approvers see tenant-scoped proposals |
| `GET /responses/{id}` | Owner or authorized approver reads its bound request/result |
| `POST /responses/{id}/decision` | A different approver supplies `decision` and optional comment |
| `POST /responses/{id}/revoke` | Requester or authorized approver revokes a pending/approved request |
| `POST /responses/{id}/simulate` | Original requester supplies the minted `approval_id` |

Approval cannot extend the initial proposal expiry. The approval identifier is not a bearer credential and never substitutes for current API authentication and authorization. It is bound to tenant, requester, investigation/report hash, action, target, parameters and proposal. Missing, mismatched, expired, revoked or already-consumed approvals cannot authorize simulation.

Consumption rechecks persisted bindings, approved review, report integrity and enabled source connectors inside a locked transaction. It atomically marks the approval consumed and records a result with `dry_run:true` and `performed:false`. No connector invoke, command or live response adapter is called. Two competing consumers cannot both consume an approval. A lost client acknowledgement can be resolved with GET; retrying simulation is denied rather than authorizing another execution.

There are at most 100 pending/approved response proposals per tenant/requester. Expired proposals still occupy capacity until explicitly revoked. Queues return bounded lists; report-review backlog, completed-record retention and request-rate control remain incomplete.

## Persistence and limits

Migration head is `0004_reviews`. Back up useful databases. SQLite auto-upgrades known schemas; PostgreSQL requires `python -m work4ce_assistant database migrate` before startup. Review decisions, approval identifiers, revocation and simulation results survive restarts. Hashes and supported persistence APIs protect bindings, but are not a tamper-resistant boundary against a privileged database writer.

The approval lifecycle portion of acceptance H is exercised only against a synthetic dry run. A separately isolated privileged executor, live response connectors, production approval integration, high-impact action policies and operational recovery tests remain unimplemented. Production remains disabled.
