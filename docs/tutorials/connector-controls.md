# Review and control registered sources

An administrator can disable or review/re-enable already registered synthetic read connectors through **Integrations**. Analysts and reviewers retain the scoped status view. Registration, credentials, network routes and capability definitions still come from trusted backend configuration; the browser cannot upload or edit them.

## Prepare and operate

Migration head is `0008_connector_controls`. Back up useful data before upgrading. SQLite auto-upgrades known schemas; PostgreSQL operators must run `.venv/bin/python -m work4ce_assistant database migrate` before starting the updated API. Migration8 adds revisions and current change/review metadata to connector state. Existing enabled/disabled values, reports, workflows, reviews, approvals, cases and incident histories are preserved. Restarting/bootstrap does not reset a disabled source or its revision.

1. Sign in with a trusted administrator identity and open **Integrations**.
2. Select **Disable source**, enter a reason and confirm. The expected revision, state change and audit reference commit atomically. New tool admission and checkpoint reuse check current source access; disablement does not retract collected evidence or undo an already completed read.
3. Select **Review and enable** on a disabled source. Inspect its capability/version, permissions, scope, read/side-effect policy and pinned definition hash. Enter a reason, confirm the review checkbox and submit.
4. The backend performs fresh capability discovery and a health check. Both must pass against the registered definition. Only then can the same expected revision be enabled, with the reviewer, timestamp, reason and exact manifest hash recorded atomically.

When every source is disabled, the status view remains accessible and `/ready` reports 503. An admin can recover a registered source through the same review flow. A stale dialog receives 409, closes and refreshes current state. Recheck current state before trying again. Reasons render as literal text and are visible only through scoped administration APIs/UI.

## Authorization and concurrency

Every operation requires `connectors:admin` from trusted server mappings plus the connector's tenant, synthetic scope, allowlist, permissions and definition-integrity admission. JWT role claims and request bodies cannot supply these grants. The reviewed hash must match the current registered manifest; discovery must return exactly the registered capability. Invalid/discovered changes, unhealthy sources, timeout or cancellation leave activation unchanged. Checks never invoke an event search or model.

Discovery and health each have at most three seconds, reduced by a shorter declared capability timeout. There is no await between the final definition check and the database state transaction. SQLite acquires its writer before reading the revision; PostgreSQL locks the row. Expected revision and opposite current state are checked again under lock. An intervening disable wins against an in-flight enable review; even a repeated legacy disable of an already disabled source advances the revision. State/review/audit roll back together on failure. Synthetic response consumption also locks current source state and checks any reviewed definition against the immutable report evidence hashes, so a disable/re-enable race cannot consume an approval under a different definition.

The effective active state also requires a stored enable-review hash to match the registered manifest. A trusted re-registration after restart cannot reuse an old review for a changed definition. Admin metadata still shows the durable enabled bit, so an admin can disable that source and review the new definition. Ordinary status/readiness/capability resolution/checkpoint admission treat the mismatch as inactive. Initial built-ins retain trusted bootstrap admission when no enable-review record exists.

## API

| Endpoint | Contract |
|---|---|
| `GET /connectors/administration` | Admin-only bounded array of safe capability fields, manifest hash, durable state/revision and current change/last enable-review metadata |
| `POST /connectors/{id}/administration/disable` | `{"expected_revision":0,"reason":"Temporarily disable this synthetic source."}` |
| `POST /connectors/{id}/administration/review-enable` | `{"expected_revision":1,"manifest_hash":"<returned 64-character hash>","reason":"Reviewed the registered read contract."}` |

Mutation responses return the committed admin DTO. Bodies are strict; reason is trimmed/nonempty and at most 1,000 characters. Unknown or out-of-scope sources return 404; missing current admin permission returns 403; malformed bodies return 422. Stale/current-state conflicts return `409 connector_revision_conflict`; hash mismatch returns `409 connector_review_mismatch`; fresh contract mismatch returns `409 connector_contract_mismatch`. Discovery failure or unhealthy source returns a redacted 503. All responses use no-store. No token, endpoint, database URL, credential or private review material is included.

Legacy `GET /connectors` retains its four-field array, now reporting effective activation. Legacy `POST /connectors/{id}/disable` retains its response and audit tuple while advancing the same revision and recording a fixed legacy-change reason. There is no unguarded enable route.

## Evidence and remaining scope

SQLite/PostgreSQL tests cover compare-and-set races, disablement fencing, restart persistence, audit rollback, malformed state and v7 preservation. API/signed-token tests cover scope, hash/definition checks, health failures/timeouts, cancellation, safe projections and changed-definition re-registration. Browser tests cover actual controls, stale edits, literal reasons, complete disablement/recovery and an investigation after reactivation. See [release readiness](../release-readiness.md) for totals.

This implements part of master specification §8.2/19.1. It does not complete connector security certification, registration/configuration, dependency/network/isolation reviews or live vendor verification. Current change and last successful enable-review reasons are retained; audit stores actor/action/revision references rather than all historical reason text. Production and live privileged response remain disabled.
