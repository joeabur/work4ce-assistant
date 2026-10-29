# Linked incidents and note history

Create an incident from a collected synthetic investigation to track human work, notes, resolution and management disposition. Each incident has one primary investigation and up to nine related investigations. Viewing or editing the combined record requires current case scope for every source; original reports and approval bindings stay intact.

## Prepare and create

Use the normal dashboard build/start workflow. SQLite upgrades automatically to `0007_incident_sources`. Before starting the updated API against PostgreSQL, back up useful data and run:

```sh
.venv/bin/python -m work4ce_assistant database migrate
```

Open a collected investigation and select **Create incident**. Enter a title, optional description and severity. Severity is a human triage choice. The backend requires completed, integrity-checked synthetic collection and binds the report hash to the incident. Pending or rejected human report review remains a separate state.

An investigation can belong to only one incident, as its primary or a related source. A repeated create returns `409 incident_exists`; refresh/open the existing incident. Reads create no incident or activity implicitly. Migration7 adds source membership and qualified-reference fields, preserving v6 incidents, revisions, reports, assignments and legacy notes.

## Work status and resolution

| Current status | Available next status | Requirements |
|---|---|---|
| Open | In progress | Creator/current assignee or manager; comment optional |
| Open or In progress | Resolved | Authorized coordinator, resolution comment, no pending escalation |
| Resolved | Closed | Manager, closing comment, no pending escalation |
| Resolved | Open | Authorized coordinator and reopening comment |
| Closed | Open | Manager and reopening comment |

Use **Start work**, **Resolve incident**, **Close incident** or **Reopen incident**. Closing and reopening require manager authority where shown above. A manager must acknowledge pending escalation on every linked case before resolution/closing. Reopening clears current resolution/closure fields and retains the original entries in activity history.

Incident resolution records an operational disposition. It does not approve the report or a response action, change the workflow requester, or execute a connector. Independent report and response controls continue to apply.

## Notes and activity

Select **Add incident note**, enter text and optionally select up to ten evidence items across linked sources. References pair an investigation ID with an exact evidence ID in that report. Select a saved citation to open its source report and highlight the evidence. Investigation-qualified labels distinguish identical local evidence IDs in different reports. Notes and comments render as text, including markup copied from telemetry.

Creation, links, notes and status changes append authored activity with a sequence and timestamp. Entries cannot be edited/deleted through this API. A closed incident requires manager reopening before more notes. The current resolution/closure fields must agree with the retained transition history.

Activity is bounded to **200 entries per incident**, including creation, links and status changes. Each successful mutation increments the revision and appends exactly one entry in the same transaction as audit. The UI shows saved history at the limit and disables further incident edits. Larger histories and retention governance require a later design.

## Scope and concurrency

Creators/current assignees coordinate their source cases; a non-manager must have that scope for all linked sources to coordinate the combined incident. Managers can coordinate any tenant case. Reviewers read tenant incidents/activity without edit grants. Linking never expands another principal’s permissions and can narrow the incident’s audience. Incident authorship does not retain access after reassignment unless another role authorizes it. Notes and dispositions remain on scoped incident APIs, separate from tenant-wide report responses.

Every note/status change requires `expected_revision`. A concurrent edit returns `409 incident_revision_conflict`; the dashboard refreshes details before another edit. Read snapshots keep incident state and activity consistent during database commits. The dashboard retries one version mismatch between separate detail/activity requests and refreshes a selected report when the workspace is refreshed.

## API

| Operation | Purpose |
|---|---|
| `POST /incidents` | `{investigation_id,title,description,severity}`; severity is low/medium/high/critical |
| `GET /incidents?limit=50` | Current scoped queue; maximum 100 |
| `GET /investigations/{id}/incident` | Linked incident; 404 if absent or outside scope |
| `GET /incidents/{id}` | Current incident details |
| `GET /incidents/{id}/investigations` | Safe source metadata and evidence choices |
| `POST /incidents/{id}/investigations` | `{expected_revision,investigation_id,comment}`; add a related source |
| `GET /incidents/{id}/activity` | Bounded authored activity in sequence order |
| `POST /incidents/{id}/status` | `{expected_revision,status,comment}` |
| `POST /incidents/{id}/notes` | `{expected_revision,body,references:[{investigation_id,evidence_id}]}` |

Titles are nonempty and at most 200 characters. Descriptions, notes and status comments are at most 2,000 characters; notes and required comments must be nonempty after trimming. Client bodies cannot set actors, tenant, management flags, report hashes or permissions.

## Verification and limits

The PostgreSQL/SQLite suite covers source bindings, current case scope, reassignment revocation, legal/illegal transitions, escalation barriers, evidence references, duplicate creation/CAS races, audit rollback, snapshot consistency, disposition/history integrity and the 200-entry bound. SQLite v5 data preservation is verified. Browser checks exercise the full lifecycle, hostile text, citations, stale edits and concurrent view loading; the installed wheel exercises migration6 and authenticated incident operations. See [release readiness](../release-readiness.md).

The queue loads at most 50 incidents by default without cursor pagination. Standalone incidents, unlinking/merging, title/severity editing, SLAs, notifications and broader enterprise routing remain future work. Application-level append-only history is not tamper-resistant against privileged database writers. All evidence remains synthetic and production mode remains disabled.

## Link related investigations

Open an active incident and choose **Link investigation**. Select a loaded investigation or enter its full UUID, then explain the relationship. The backend checks current access to the existing group and the candidate source, completed synthetic collection, report integrity, unique membership and the expected incident revision. A resolved/closed incident must be reopened first. Sources already belonging to an incident cannot be linked again or implicitly merged.

A maximum of ten sources includes the primary. Every link appends activity and consumes one of the 200 entries. **Linked investigations** shows source IDs, who linked them, their current assignees and pending escalation flags. **View investigation** opens the corresponding report. The primary incident ID, original primary investigation and primary assignment fields remain stable.

Access is the intersection of current source-case scopes. If a manager links a case you cannot access, the combined incident and its history disappear from your scoped reads/queue; later assignment can restore access. Incident authorship is not an exception. Queue filtering happens before the requested limit. Report-review notes and approval material are excluded from source descriptors.

New notes send at most ten distinct `references` with exact investigation/evidence pairs. Existing callers may continue using `evidence_ids` for primary-only citations. Do not send both nonempty forms. Activity retains the primary-only subset for legacy clients and adds normalized `references` plus `linked_investigation_id` for link events. History verifies that each referenced source was already linked at that activity sequence. Links are retained; unlink/merge governance remains future work.
