# Case assignment and escalation

Case coordination adds operational responsibility to an investigation. It supports assignment/unassignment, an escalation reason, and manager acknowledgment. All cases and evidence remain synthetic. This is an incremental incident-management feature; full incidents, resolution tracking and independent notes are future work.

## Prepare

Run the normal setup/build and start the API/reference services. SQLite automatically upgrades through the current `0007_incident_sources` head. Before starting the updated API with PostgreSQL, back up useful data and run:

```sh
.venv/bin/python -m work4ce_assistant database migrate
```

The migration adds a coordination table and queue index. Existing reports, evidence, reviews, approvals and workflow requester bindings are preserved. Reads of an investigation without coordination return revision zero and create no row.

## Coordinate a case

1. Sign in as the investigation creator and open the report. Select **Assign case**, choose an eligible subject and save. Select **Change assignee** later to reassign or choose Unassigned.
2. Select **Escalate case**, explain the reason and submit. The request appears in **Case coordination** with its actor and timestamp.
3. Sign in as a manager/admin, open that case and choose **Acknowledge escalation**. Acknowledgment records management attention. Human report decisions and response approvals retain their separate controls.
4. If further attention is needed after acknowledgment, use **Re-escalate case** with a new reason. A pending escalation must be acknowledged before it can be replaced.

An assignment preserves the original workflow requester. The original requester continues to control resume/cancel and response requests under existing policy. Assigning responsibility does not make another principal the report author or grant approval/execution permissions.

## Roles and visibility

| Actor | Coordination scope |
|---|---|
| Analyst | Read/edit cases they created or are currently assigned; request escalation |
| Admin/manager | Read/edit any case in their trusted tenant; acknowledge pending escalations |
| Reviewer | Read tenant coordination; no assignment, escalation, directory or acknowledgment grants |

The backend assigns permissions; client bodies and JWT role claims cannot grant them. Demo mode offers `demo-analyst` and `demo-admin` as eligible assignees. OIDC mode derives the directory from configured analyst/admin subject mappings; reviewers are excluded. A removed subject cannot authenticate or be assigned again after the updated server configuration is loaded. Existing assignments can be cleared or replaced by an authorized actor.

The coordination queue includes explicitly stored assignments/escalations in the actor's scope. An unassigned but previously edited case remains visible to its creator and authorized reviewers/managers. The creator's investigation history remains owner-scoped; an assignee finds handed-off work through **Case coordination**. Reasons are private to the dedicated scoped APIs, even where general report-read access is tenant-wide.

## API contract

| Operation | Purpose |
|---|---|
| `GET /case-assignees` | Eligible trusted subjects for coordinators |
| `GET /cases?limit=50` | Explicit coordination records in current scope; maximum 100 |
| `GET /investigations/{id}/case` | Current coordination or revision-zero default |
| `POST /investigations/{id}/case/assignment` | `{"expected_revision":0,"assignee":"demo-admin"}`; null unassigns |
| `POST /investigations/{id}/case/escalation` | `{"expected_revision":1,"reason":"Inspect this synthetic evidence."}` |
| `POST /investigations/{id}/case/acknowledge` | `{"expected_revision":2}`; manager required |

Responses include the investigation ID, immutable creator, assignee, escalation state/reason, requester/acknowledger and timestamps, revision and latest updater. They contain no credentials, report data or approval material.

Every mutation requires the current expected revision. The transaction rereads creator/current assignee under lock, validates scope and revision, then commits state plus an audit reference. A stale edit returns `409 case_revision_conflict`; the workbench refreshes the case before another edit. Former assignees lose scope after reassignment unless another role still authorizes access. Invalid candidates/fields return 422; unrelated or foreign-tenant cases return 404. Missing current grants return 403.

Reasons are trimmed, nonempty and at most 1,000 characters. They render as text. The record retains one current reason; re-escalation after acknowledgment replaces it and clears the previous acknowledgment. Audit references retain actors/actions/revisions rather than a full prior-content history.

## Verification and limits

The backend suite covers tenant/role/assignee boundaries, signed-token directory admission, reassignment revocation, stale writes, a two-store race with one CAS winner, atomic audit rollback, restart persistence, SQLite v4 preservation and unchanged reports/workflows/reviews. Browser checks cover actual assignment, escalation, manager acknowledgment, literal hostile reason markup, stale-dialog rejection and mobile layout. Installed-wheel checks exercise migration 0005 and the API lifecycle. See [release readiness](../release-readiness.md).

The queue is bounded without UI pagination. [Linked incident management](incidents.md) now adds work/resolution status and authored note history. Unlink/merge governance, full case-reason content history, SLA routing, external directory synchronization and notifications remain incomplete. No messages are sent to other people. Production remains disabled.
