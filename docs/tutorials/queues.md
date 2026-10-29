# Operational queue pagination

**Case coordination** and **Incidents** initially load 50 records in the workbench. Select **Load older coordinated cases** or **Load older incidents** to append another page. Counts describe loaded records. Refresh or workspace navigation starts again at the first page; delayed responses from a previous refresh or session cannot repopulate it.

## API contract

| Endpoint | Descending order |
|---|---|
| `GET /cases/history?limit=50` | Investigation creation time, then investigation ID |
| `GET /incidents/history?limit=50` | Incident creation time, then incident ID |

Both return `{"items":[...],"next_cursor":"..."}`. Pass the returned marker as the next request's `cursor` parameter. A null cursor marks the end of the currently visible results. Limits are 1–100. Item fields match the existing scoped queue DTOs; report bodies, private review notes and approval material are excluded. The original `/cases` and `/incidents` routes retain their bounded arrays ordered by latest update.

Assignment, escalation, notes and status changes do not move records between pages. Case coordination includes only explicitly stored coordination records and follows the parent investigation's creation time, even if coordination was added later. Pagination itself adds no schema or dependency requirement; the current application migration head is `0008_connector_controls`.

## Current access and live changes

Every request requires current bearer authentication, `cases:read`, `investigations:read` and synthetic tenant context. Creators/current assignees see their cases; trusted managers/reviewers have tenant-wide read scope. An incident requires current case scope for every source. SQL applies these filters before the page limit, so hidden rows do not consume visible page slots. Reassignment or linking can revoke access between requests.

Cursors are unsigned position markers bound to queue kind, tenant and read scope. They contain no credentials and grant no authority; server filters apply independently of their contents. Canonical URL-safe base64, exact fields, version, aware timestamp and UUID are validated within a 512-character bound. Malformed or mismatched markers return `422 invalid_queue_cursor`. Investigation-history markers and markers from another queue/read scope cannot be exchanged.

Paging does not freeze a historical database snapshot. State and access are evaluated per request. New records or newly visible records that sort before the current marker require Refresh; older newly visible records can appear on later pages. Refresh also discards appended pages and reloads current details. Review/response queues remain bounded arrays. Server-side queue search, large-queue load measurements and remote-database performance remain incomplete.

## Verification

SQLite/PostgreSQL tests cover tied timestamps, exact/final/empty pages, stable order during mutations and inserts, strict marker parsing, cross-scope rejection, current permissions, all-source filtering, legacy compatibility and safe projections. Browser checks load beyond 50 records in both queues, verify unique coverage, reject delayed pages after Refresh and check mobile layout. The installed wheel serves both paginated APIs. See [release readiness](../release-readiness.md) for current totals and limits.
