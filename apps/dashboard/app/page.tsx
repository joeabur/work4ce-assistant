"use client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

type Me = {
  subject: string;
  tenant_id: string;
  permissions: string[];
  synthetic: boolean;
  review_required: boolean;
  model_mode: string;
};
type Case = {
  id: string;
  subject: string;
  status: string;
  created_at: string;
  updated_at: string;
  query: string | null;
  assessment: string | null;
  evidence_count: number;
  review_state: string | null;
};
type QueuePage<T> = { items: T[]; next_cursor: string | null };
type CasePage = QueuePage<Case>;
type Review = {
  investigation_id: string;
  review_id: string;
  requester: string;
  state: string;
  expires_at: number;
  reviewer?: string;
  comment?: string;
};
type Evidence = {
  evidence_id: string;
  connector_id: string;
  protocol: string;
  content: {
    summary: string;
    kind: string;
    timestamp: string;
    synthetic: boolean;
  };
};
type CaseCoord = {
  investigation_id: string;
  creator: string;
  assignee: string | null;
  escalation_state: "none" | "requested" | "acknowledged";
  escalation_reason: string | null;
  escalated_by: string | null;
  escalated_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  revision: number;
  updated_by: string | null;
  updated_at: string | null;
};
type IncidentStatus = "open" | "in_progress" | "resolved" | "closed";
type Incident = {
  id: string;
  investigation_id: string;
  creator: string;
  assignee: string | null;
  title: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  status: IncidentStatus;
  revision: number;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
  resolution_note: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  closed_by: string | null;
  closed_at: string | null;
};
type IncidentReference = { investigation_id: string; evidence_id: string };
type IncidentSource = {
  investigation_id: string;
  primary: boolean;
  escalation_state: "none" | "requested" | "acknowledged";
  creator: string;
  assignee: string | null;
  query: string | null;
  linked_by: string;
  linked_at: string;
  evidence: { evidence_id: string; summary: string }[];
};
type IncidentEntry = {
  id: string;
  incident_id: string;
  sequence: number;
  kind: "created" | "note" | "status" | "linked";
  actor: string;
  body: string;
  evidence_ids: string[];
  references: IncidentReference[];
  linked_investigation_id: string | null;
  from_status: IncidentStatus | null;
  to_status: IncidentStatus | null;
  created_at: string;
};
const incidentStatusTitle = (status: IncidentStatus) =>
  status === "in_progress"
    ? "Start work"
    : status === "resolved"
      ? "Resolve incident"
      : status === "closed"
        ? "Close incident"
        : "Reopen incident";
type Report = {
  id: string;
  status: string;
  report: null | {
    query: string;
    assessment: string;
    evidence: Evidence[];
    findings: { statement: string; evidence_ids: string[] }[];
    limitations?: string[];
    reasoning?: { synthetic_fixture: boolean };
  };
  review?: Review;
  case?: CaseCoord;
  incident?: Incident;
  incident_activity?: IncidentEntry[];
  incident_sources?: IncidentSource[];
};
type Proposal = {
  id: string;
  investigation_id: string;
  requester: string;
  target: string;
  action: string;
  parameters: { duration_minutes: number };
  state: string;
  expires_at: number;
  approval_id?: string;
  simulation_result?: { dry_run: boolean; performed: boolean };
};
type Source = {
  connector_id: string;
  protocol: string;
  enabled: boolean;
  synthetic: boolean;
};
type View =
  | "investigations"
  | "coordination"
  | "incidents"
  | "reviews"
  | "responses"
  | "integrations";
type Modal =
  | { kind: "new" }
  | { kind: "incident_create"; record: Report }
  | { kind: "incident_status"; incident: Incident; status: IncidentStatus }
  | { kind: "incident_note"; incident: Incident; sources: IncidentSource[] }
  | { kind: "incident_link"; incident: Incident; sources: IncidentSource[] }
  | { kind: "case_assign"; coordination: CaseCoord }
  | { kind: "case_escalate"; coordination: CaseCoord }
  | { kind: "case_ack"; coordination: CaseCoord }
  | { kind: "review"; review: Review; decision: "approved" | "rejected" }
  | { kind: "proposal"; record: Report }
  | { kind: "decision"; proposal: Proposal; decision: "approved" | "rejected" }
  | { kind: "simulate"; proposal: Proposal }
  | { kind: "revoke"; proposal: Proposal };
const labels: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
  low: "Low severity",
  medium: "Medium severity",
  high: "High severity",
  critical: "Critical severity",
  requested: "Escalation requested",
  acknowledged: "Acknowledged",
  none: "Not escalated",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  queued: "Queued",
  running: "Investigating",
  collected: "Evidence collected",
  pending: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  review_rejected: "Review rejected",
  revoked: "Revoked",
  consumed: "Simulated",
  cancelled: "Cancelled",
  failed: "Failed",
  inconclusive: "Inconclusive",
  needs_analyst_review: "Analyst review needed",
};
const messages: Record<string, string> = {
  invalid_queue_cursor:
    "This queue position is no longer valid. Refresh the workspace to load the latest cases and incidents.",
  incident_source_conflict:
    "That investigation is already linked to an incident. Refresh and review the current sources before trying again.",
  incident_source_limit:
    "This incident has reached its 10-investigation limit. Refresh to review the current sources.",
  incident_not_active:
    "Investigations can be linked only while an incident is open or in progress. Refresh to read its current status.",
  incident_revision_conflict:
    "This incident changed. Refresh and review its latest state before trying again.",
  incident_exists:
    "This investigation already has an incident. Refresh to review its current details.",
  incident_escalation_pending:
    "A manager must acknowledge the pending case escalation before this incident can be resolved or closed.",
  incident_closed:
    "This incident is closed. A manager must reopen it before adding notes.",
  incident_management_required:
    "A manager must close or reopen a closed incident.",
  incident_transition_invalid:
    "That status change is no longer available. Refresh and review the current incident.",
  incident_history_limit:
    "This incident has reached its 200-entry activity limit. Its saved history remains available.",
  incident_source_incomplete:
    "Collect the synthetic investigation before creating or linking an incident.",
  invalid_incident_evidence:
    "Choose evidence from this incident’s linked investigations.",
  case_revision_conflict:
    "This case changed. Refresh and review its latest state before trying again.",
  case_assignee_ineligible:
    "That account is not eligible for assignment. Refresh the assignee list and choose another account.",
  invalid_case_assignee:
    "That account is not eligible for assignment. Choose an approved account.",
  case_escalation_not_requested:
    "This escalation is no longer awaiting acknowledgement. Refresh the case.",
  case_escalation_already_requested:
    "This case is already escalated. Refresh to see the current request.",
  case_escalation_pending:
    "This case already has a pending escalation. Refresh to read the current request.",
  case_not_escalated:
    "This case has no escalation awaiting acknowledgment. Refresh to read its current state.",
  case_management_required: "A manager must acknowledge this escalation.",
  authentication_required:
    "Your access token was not accepted. Connect again with a valid token.",
  permission_denied: "Your account does not have permission for this action.",
  separation_of_duties:
    "A different person must review or approve this request.",
  no_authorized_connector:
    "The original data source is unavailable or no longer authorized.",
  connectors_unavailable:
    "No authorized data source is available. Check Integrations and try again.",
  review_expired: "This review expired. Its owner can refresh the request.",
  review_mismatch: "This review changed. Refresh and read the latest request.",
  review_terminal: "A review decision has already been recorded.",
  report_review_required:
    "An approved report review is required before proposing a response.",
  approval_expired:
    "This approval expired. Revoke it and create a new proposal.",
  approval_reused:
    "This approval has already been consumed. The saved result is available.",
  approval_required: "A separate approval is required first.",
  approval_mismatch: "The approval no longer matches. Refresh the queue.",
  response_target_unobserved:
    "This target is not present in the report evidence.",
  response_connector_unavailable: "The report’s data source is disabled.",
  workflow_busy: "This investigation is already running.",
  workflow_deadline_exceeded: "The investigation deadline expired.",
  invalid_history_cursor:
    "This history position is no longer valid. Refresh to load the latest investigations.",
  model_budget_exhausted: "This investigation reached its model budget.",
};
class RequestError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(
      messages[code] ||
        (status === 422
          ? "Check the request fields and try again."
          : status === 404
            ? "This record is unavailable to your account."
            : "The request could not be completed. Refresh and try again."),
    );
  }
}
function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    shield: (
      <>
        <path d="m12 3-8 3v6c0 5 8 9 8 9s8-4 8-9V6Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    cases: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M8 5V3h8v2M3 11h18M10 10v3h4v-3" />
      </>
    ),
    review: (
      <>
        <path d="M9 4H5v17h14V4h-4" />
        <rect x="9" y="2" width="6" height="4" rx="1" />
        <path d="m8 13 3 3 5-6" />
      </>
    ),
    response: <path d="m13 2-9 12h7l-1 8 10-12h-7Z" />,
    plug: (
      <>
        <path d="M8 3v5m8-5v5M6 8h12v4a6 6 0 0 1-12 0Zm6 10v4" />
      </>
    ),
    arrow: <path d="m9 5 7 7-7 7" />,
    plus: <path d="M12 5v14M5 12h14" />,
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5" />
        <path d="M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    close: <path d="m6 6 12 12M6 18 18 6" />,
    logout: (
      <>
        <path d="M9 5H4v14h5m6-14 7 7-7 7M8 12h13" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    file: (
      <>
        <path d="M14 2H5v20h14V7Zm0 0v5h5M8 12h8M8 16h8" />
      </>
    ),
    link: (
      <>
        <path
          d="m10 14 4-4M8 16l-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m2 1 2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"
          transform="translate(2 0) scale(.9)"
        />
      </>
    ),
    lock: (
      <>
        <rect x="5" y="10" width="14" height="11" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.file}
    </svg>
  );
}
function Badge({ value }: { value: string }) {
  return (
    <span
      className={`badge ${["completed", "approved", "consumed", "acknowledged", "resolved"].includes(value) ? "positive" : ["pending", "awaiting_review", "queued", "running", "requested", "in_progress", "medium"].includes(value) ? "attention" : ["failed", "rejected", "review_rejected", "revoked", "high", "critical"].includes(value) ? "negative" : "neutral"}`}
    >
      <span />
      {labels[value] || value.replaceAll("_", " ")}
    </span>
  );
}
const date = (value: string | number | undefined) => {
  if (!value) return "—";
  const d =
    typeof value === "number" ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(d.valueOf())
    ? "—"
    : d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
};
const short = (id: string) => id.slice(0, 8).toUpperCase();
const expiry = (value: number) =>
  value <= Date.now() / 1000 ? "Expired" : `Expires ${date(value)}`;
function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Icon name="shield" size={23} />
      </span>
      <span>
        work4ce<span className="brand-sub">ASSISTANT</span>
      </span>
    </div>
  );
}
function Empty({
  icon,
  title,
  text,
  action,
}: {
  icon: string;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={28} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function Loading({ text }: { text: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" />
      {text}
    </div>
  );
}
function Dialog({
  title,
  busy,
  close,
  children,
}: {
  title: string;
  busy: boolean;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      className="modal"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else close();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button
          className="icon-button"
          disabled={busy}
          aria-label="Close dialog"
          onClick={close}
        >
          <Icon name="close" size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export default function Page() {
  const [me, setMe] = useState<Me | null>(null),
    [tokenInput, setTokenInput] = useState(""),
    [connecting, setConnecting] = useState(false),
    [view, setView] = useState<View>("investigations");
  const [cases, setCases] = useState<Case[]>([]),
    [nextCursor, setNextCursor] = useState<string | null>(null),
    [historyLoading, setHistoryLoading] = useState(false),
    [historyLoaded, setHistoryLoaded] = useState(false),
    [coordinationRows, setCoordinationRows] = useState<CaseCoord[]>([]),
    [coordinationCursor, setCoordinationCursor] = useState<string | null>(null),
    [coordinationLoading, setCoordinationLoading] = useState(false),
    [coordinationLoaded, setCoordinationLoaded] = useState(false),
    [incidents, setIncidents] = useState<Incident[]>([]),
    [incidentCursor, setIncidentCursor] = useState<string | null>(null),
    [incidentLoading, setIncidentLoading] = useState(false),
    [incidentLoaded, setIncidentLoaded] = useState(false),
    [assignees, setAssignees] = useState<{ subject: string }[]>([]),
    [reviews, setReviews] = useState<Review[]>([]),
    [responses, setResponses] = useState<Proposal[]>([]),
    [sources, setSources] = useState<Source[]>([]),
    [healthy, setHealthy] = useState<string[]>([]),
    [selected, setSelected] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false),
    [detailLoading, setDetailLoading] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all"),
    [highlight, setHighlight] = useState(""),
    [modal, setModal] = useState<Modal | null>(null);
  const token = useRef(""),
    epoch = useRef(0),
    requests = useRef(new Set<AbortController>()),
    selectedID = useRef(""),
    pendingCitation = useRef<{
      investigationID: string;
      evidenceID: string;
      sequence: number;
    } | null>(null),
    selection = useRef(0),
    historyVersion = useRef(0),
    historyBusy = useRef(false),
    coordinationBusy = useRef(false),
    incidentBusy = useRef(false),
    workspaceRefreshing = useRef(false),
    createIntent = useRef<{ signature: string; key: string } | null>(null);
  const has = (p: string) => Boolean(me?.permissions.includes(p));
  const logout = useCallback(() => {
    epoch.current++;
    token.current = "";
    createIntent.current = null;
    requests.current.forEach((c) => c.abort());
    requests.current.clear();
    selectedID.current = "";
    pendingCitation.current = null;
    selection.current++;
    historyVersion.current++;
    historyBusy.current = false;
    coordinationBusy.current = false;
    incidentBusy.current = false;
    workspaceRefreshing.current = false;
    setMe(null);
    setTokenInput("");
    setConnecting(false);
    setCases([]);
    setNextCursor(null);
    setHistoryLoading(false);
    setHistoryLoaded(false);
    setCoordinationRows([]);
    setCoordinationCursor(null);
    setCoordinationLoading(false);
    setCoordinationLoaded(false);
    setIncidents([]);
    setIncidentCursor(null);
    setIncidentLoading(false);
    setIncidentLoaded(false);
    setAssignees([]);
    setReviews([]);
    setResponses([]);
    setSources([]);
    setHealthy([]);
    setSelected(null);
    setModal(null);
    setError("");
    setNotice("");
    setLoading(false);
    setDetailLoading(false);
    setBusy(false);
    setView("investigations");
    setSearch("");
    setFilter("all");
    setHighlight("");
  }, []);
  useEffect(() => () => requests.current.forEach((c) => c.abort()), []);
  const request = useCallback(
    async <T,>(
      path: string,
      init: RequestInit = {},
      credential?: string,
    ): Promise<T> => {
      const generation = epoch.current,
        controller = new AbortController();
      requests.current.add(controller);
      const timer = window.setTimeout(
        () =>
          controller.abort(
            new DOMException("Request timed out", "TimeoutError"),
          ),
        40000,
      );
      try {
        const response = await fetch(path, {
          ...init,
          signal: controller.signal,
          cache: "no-store",
          credentials: "omit",
          headers: {
            Accept: "application/json",
            ...(init.body ? { "Content-Type": "application/json" } : {}),
            ...init.headers,
            Authorization: `Bearer ${credential ?? token.current}`,
          },
        });
        if (generation !== epoch.current)
          throw new DOMException("Session changed", "AbortError");
        const data = await response.json().catch(() => ({}));
        if (generation !== epoch.current)
          throw new DOMException("Session changed", "AbortError");
        if (!response.ok)
          throw new RequestError(
            response.status,
            typeof data.error === "string" ? data.error : "request_failed",
          );
        return data as T;
      } finally {
        clearTimeout(timer);
        requests.current.delete(controller);
      }
    },
    [],
  );
  const fail = useCallback(
    (cause: unknown) => {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      if (cause instanceof RequestError && cause.status === 401) {
        logout();
        setError(cause.message);
      } else
        setError(
          cause instanceof RequestError
            ? cause.message
            : "Connection interrupted. Refresh the workspace and try again.",
        );
    },
    [logout],
  );
  const refresh = useCallback(
    async (identity: Me) => {
      const generation = epoch.current,
        version = ++historyVersion.current;
      historyBusy.current = false;
      coordinationBusy.current = false;
      incidentBusy.current = false;
      workspaceRefreshing.current = true;
      setHistoryLoading(false);
      setCoordinationCursor(null);
      setCoordinationLoading(false);
      setCoordinationLoaded(false);
      setIncidentCursor(null);
      setIncidentLoading(false);
      setIncidentLoaded(false);
      setLoading(true);
      try {
        const [
          items,
          proposals,
          connectors,
          queue,
          ready,
          coordinated,
          candidates,
          incidentRows,
        ] = await Promise.all([
          request<CasePage>("/investigations/history?limit=50"),
          identity.permissions.includes("responses:read")
            ? request<Proposal[]>("/responses")
            : Promise.resolve([]),
          request<Source[]>("/connectors"),
          identity.permissions.includes("investigations:review")
            ? request<Review[]>("/reviews")
            : Promise.resolve([]),
          request<{ connectors: string[] }>("/ready").catch((cause) => {
            if (cause instanceof RequestError && cause.status === 503)
              return { connectors: [] };
            throw cause;
          }),
          identity.permissions.includes("cases:read")
            ? request<QueuePage<CaseCoord>>("/cases/history?limit=50")
            : Promise.resolve<QueuePage<CaseCoord>>({
                items: [],
                next_cursor: null,
              }),
          identity.permissions.includes("cases:coordinate")
            ? request<{ subject: string }[]>("/case-assignees")
            : Promise.resolve([]),
          identity.permissions.includes("cases:read")
            ? request<QueuePage<Incident>>("/incidents/history?limit=50")
            : Promise.resolve<QueuePage<Incident>>({
                items: [],
                next_cursor: null,
              }),
        ]);
        if (generation !== epoch.current || version !== historyVersion.current)
          return;
        setCases(items.items);
        setNextCursor(items.next_cursor);
        setHistoryLoaded(true);
        setResponses(proposals);
        setSources(connectors);
        setReviews(queue);
        setHealthy(ready.connectors);
        setCoordinationRows(coordinated.items);
        setCoordinationCursor(coordinated.next_cursor);
        setCoordinationLoaded(true);
        setAssignees(candidates);
        setIncidents(incidentRows.items);
        setIncidentCursor(incidentRows.next_cursor);
        setIncidentLoaded(true);
      } catch (cause) {
        if (generation === epoch.current && version === historyVersion.current)
          fail(cause);
      } finally {
        if (
          generation === epoch.current &&
          version === historyVersion.current
        ) {
          workspaceRefreshing.current = false;
          setLoading(false);
        }
      }
    },
    [request, fail],
  );
  const loadOlder = async () => {
    if (
      !me ||
      !nextCursor ||
      loading ||
      workspaceRefreshing.current ||
      busy ||
      historyBusy.current
    )
      return;
    const generation = epoch.current,
      version = historyVersion.current,
      cursor = nextCursor;
    historyBusy.current = true;
    setHistoryLoading(true);
    setError("");
    try {
      const page = await request<CasePage>(
        `/investigations/history?limit=50&cursor=${encodeURIComponent(cursor)}`,
      );
      if (generation !== epoch.current || version !== historyVersion.current)
        return;
      setCases((current) => {
        const known = new Set(current.map((item) => item.id));
        return [
          ...current,
          ...page.items.filter((item) => !known.has(item.id)),
        ];
      });
      setNextCursor(page.next_cursor);
    } catch (cause) {
      if (generation === epoch.current && version === historyVersion.current)
        fail(cause);
    } finally {
      if (generation === epoch.current && version === historyVersion.current) {
        historyBusy.current = false;
        setHistoryLoading(false);
      }
    }
  };
  const loadOlderCoordinatedCases = async () => {
    if (
      !me ||
      !coordinationCursor ||
      loading ||
      workspaceRefreshing.current ||
      busy ||
      coordinationBusy.current
    )
      return;
    const generation = epoch.current,
      version = historyVersion.current,
      cursor = coordinationCursor;
    coordinationBusy.current = true;
    setCoordinationLoading(true);
    setError("");
    try {
      const page = await request<QueuePage<CaseCoord>>(
        `/cases/history?limit=50&cursor=${encodeURIComponent(cursor)}`,
      );
      if (generation !== epoch.current || version !== historyVersion.current)
        return;
      setCoordinationRows((current) => {
        const known = new Set(current.map((item) => item.investigation_id));
        return [
          ...current,
          ...page.items.filter((item) => {
            if (known.has(item.investigation_id)) return false;
            known.add(item.investigation_id);
            return true;
          }),
        ];
      });
      setCoordinationCursor(page.next_cursor);
    } catch (cause) {
      if (generation === epoch.current && version === historyVersion.current)
        fail(cause);
    } finally {
      if (generation === epoch.current && version === historyVersion.current) {
        coordinationBusy.current = false;
        setCoordinationLoading(false);
      }
    }
  };
  const loadOlderIncidents = async () => {
    if (
      !me ||
      !incidentCursor ||
      loading ||
      workspaceRefreshing.current ||
      busy ||
      incidentBusy.current
    )
      return;
    const generation = epoch.current,
      version = historyVersion.current,
      cursor = incidentCursor;
    incidentBusy.current = true;
    setIncidentLoading(true);
    setError("");
    try {
      const page = await request<QueuePage<Incident>>(
        `/incidents/history?limit=50&cursor=${encodeURIComponent(cursor)}`,
      );
      if (generation !== epoch.current || version !== historyVersion.current)
        return;
      setIncidents((current) => {
        const known = new Set(current.map((item) => item.id));
        return [
          ...current,
          ...page.items.filter((item) => {
            if (known.has(item.id)) return false;
            known.add(item.id);
            return true;
          }),
        ];
      });
      setIncidentCursor(page.next_cursor);
    } catch (cause) {
      if (generation === epoch.current && version === historyVersion.current)
        fail(cause);
    } finally {
      if (generation === epoch.current && version === historyVersion.current) {
        incidentBusy.current = false;
        setIncidentLoading(false);
      }
    }
  };
  const openCase = useCallback(
    async (id: string, evidenceID?: string) => {
      const generation = epoch.current,
        sequence = ++selection.current;
      selectedID.current = id;
      pendingCitation.current = evidenceID
        ? { investigationID: id, evidenceID, sequence }
        : null;
      setHighlight("");
      setSelected(null);
      setDetailLoading(true);
      try {
        const [item, coordination, incidentData] = await Promise.all([
          request<Report>(`/investigations/${encodeURIComponent(id)}`),
          request<CaseCoord>(
            `/investigations/${encodeURIComponent(id)}/case`,
          ).catch((cause) => {
            if (
              cause instanceof RequestError &&
              [403, 404].includes(cause.status)
            )
              return undefined;
            throw cause;
          }),
          request<Incident>(
            `/investigations/${encodeURIComponent(id)}/incident`,
          )
            .catch((cause) => {
              if (
                cause instanceof RequestError &&
                [403, 404].includes(cause.status)
              )
                return undefined;
              throw cause;
            })
            .then(async (initial) => {
              if (!initial) return undefined;
              let incident = initial;
              for (let attempt = 0; attempt < 2; attempt++) {
                const [activity, sources] = await Promise.all([
                  request<IncidentEntry[]>(
                    `/incidents/${encodeURIComponent(incident.id)}/activity`,
                  ),
                  request<IncidentSource[]>(
                    `/incidents/${encodeURIComponent(incident.id)}/investigations`,
                  ),
                ]);
                const sourceEntries = activity.filter(
                  (entry) =>
                    entry.kind === "created" || entry.kind === "linked",
                );
                if (
                  activity.length === incident.revision &&
                  sources.length === sourceEntries.length
                )
                  return { incident, activity, sources };
                if (attempt === 0)
                  incident = await request<Incident>(
                    `/investigations/${encodeURIComponent(id)}/incident`,
                  );
              }
              throw new RequestError(409, "incident_revision_conflict");
            }),
        ]);
        item.case = coordination;
        item.incident = incidentData?.incident;
        item.incident_activity = incidentData?.activity;
        item.incident_sources = incidentData?.sources;
        if (generation === epoch.current && sequence === selection.current)
          setSelected(
            item.report
              ? {
                  ...item,
                  report: {
                    ...item.report,
                    evidence: Array.isArray(item.report.evidence)
                      ? item.report.evidence
                          .filter(
                            (e) =>
                              e &&
                              e.content &&
                              typeof e.content.summary === "string",
                          )
                          .map((e) => ({
                            ...e,
                            content: {
                              ...e.content,
                              kind:
                                typeof e.content.kind === "string"
                                  ? e.content.kind
                                  : "unknown",
                            },
                          }))
                      : [],
                    findings: Array.isArray(item.report.findings)
                      ? item.report.findings
                          .filter((f) => f && typeof f.statement === "string")
                          .map((f) => ({
                            ...f,
                            evidence_ids: Array.isArray(f.evidence_ids)
                              ? f.evidence_ids.filter(
                                  (id) => typeof id === "string",
                                )
                              : [],
                          }))
                      : [],
                  },
                }
              : item,
          );
      } catch (cause) {
        if (generation === epoch.current && sequence === selection.current)
          fail(cause);
      } finally {
        if (generation === epoch.current && sequence === selection.current)
          setDetailLoading(false);
      }
    },
    [request, fail],
  );
  useEffect(() => {
    const pending = pendingCitation.current;
    if (
      detailLoading ||
      !pending ||
      selected?.id !== pending.investigationID ||
      selection.current !== pending.sequence
    )
      return;
    pendingCitation.current = null;
    if (
      !selected.report?.evidence.some(
        (item) => item.evidence_id === pending.evidenceID,
      )
    )
      return;
    setHighlight(pending.evidenceID);
    document
      .getElementById(`evidence-${pending.evidenceID}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selected, detailLoading]);
  const connect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (connecting || !tokenInput.trim()) return;
    const credential = tokenInput.trim(),
      generation = ++epoch.current;
    setConnecting(true);
    setError("");
    setTokenInput("");
    try {
      const identity = await request<Me>("/me", {}, credential);
      if (generation !== epoch.current) return;
      token.current = credential;
      setMe(identity);
      setView(
        identity.permissions.includes("investigations:run")
          ? "investigations"
          : "reviews",
      );
      await refresh(identity);
    } catch (cause) {
      if (generation === epoch.current) fail(cause);
    } finally {
      if (generation === epoch.current) setConnecting(false);
    }
  };
  const navigate = (next: View) => {
    setView(next);
    setError("");
    setNotice("");
    if (me) void refresh(me);
  };
  const act = async (
    operation: () => Promise<unknown>,
    message: string,
    caseID?: string,
  ) => {
    if (!me || busy) return;
    const generation = epoch.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await operation();
      if (generation !== epoch.current) return;
      setModal(null);
      setNotice(message);
      await refresh(me);
      if (caseID && selectedID.current === caseID) await openCase(caseID);
    } catch (cause) {
      if (generation === epoch.current) {
        if (
          cause instanceof RequestError &&
          [
            "case_revision_conflict",
            "incident_revision_conflict",
            "incident_exists",
            "incident_source_conflict",
            "incident_source_limit",
            "incident_not_active",
          ].includes(cause.code)
        ) {
          setModal(null);
          await refresh(me);
          if (caseID && selectedID.current === caseID) await openCase(caseID);
        }
        if (generation === epoch.current) fail(cause);
      }
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  };
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!modal || !me || busy) return;
    const data = new FormData(e.currentTarget),
      current = modal,
      comment = String(data.get("comment") || "");
    if (current.kind === "new") {
      const generation = epoch.current;
      const payload = {
        query: String(data.get("query") || "").trim(),
        limit: 20,
      };
      const signature = JSON.stringify(payload);
      if (createIntent.current?.signature !== signature)
        createIntent.current = { signature, key: crypto.randomUUID() };
      setBusy(true);
      setError("");
      try {
        const record = await request<Report>("/investigations", {
          method: "POST",
          headers: { "Idempotency-Key": createIntent.current!.key },
          body: JSON.stringify(payload),
        });
        if (generation !== epoch.current) return;
        setModal(null);
        setView("investigations");
        createIntent.current = null;
        setNotice("Investigation collected. Review the evidence below.");
        await refresh(me);
        await openCase(record.id);
      } catch (cause) {
        if (generation === epoch.current) fail(cause);
      } finally {
        if (generation === epoch.current) setBusy(false);
      }
      return;
    }
    if (current.kind === "incident_create")
      return act(
        () =>
          request("/incidents", {
            method: "POST",
            body: JSON.stringify({
              investigation_id: current.record.id,
              title: String(data.get("title") || "").trim(),
              description: String(data.get("description") || "").trim(),
              severity: data.get("severity"),
            }),
          }),
        "Incident created. Case and response permissions remain independently enforced.",
        current.record.id,
      );
    if (current.kind === "incident_status")
      return act(
        () =>
          request(
            `/incidents/${encodeURIComponent(current.incident.id)}/status`,
            {
              method: "POST",
              body: JSON.stringify({
                expected_revision: current.incident.revision,
                status: current.status,
                comment: comment.trim(),
              }),
            },
          ),
        "Incident status updated.",
        selectedID.current,
      );
    if (current.kind === "incident_note") {
      const availableReferences = current.sources.flatMap((source) =>
        source.evidence.map((item) => ({
          investigation_id: source.investigation_id,
          evidence_id: item.evidence_id,
        })),
      );
      const references = data
        .getAll("references")
        .map((value) => availableReferences[Number(value)])
        .filter((value): value is IncidentReference => Boolean(value));
      if (references.length > 10) {
        setError("Choose up to 10 evidence citations for each note.");
        return;
      }
      return act(
        () =>
          request(
            `/incidents/${encodeURIComponent(current.incident.id)}/notes`,
            {
              method: "POST",
              body: JSON.stringify({
                expected_revision: current.incident.revision,
                body: String(data.get("body") || "").trim(),
                references,
              }),
            },
          ),
        "Incident note added.",
        selectedID.current,
      );
    }
    if (current.kind === "incident_link") {
      const chosen = String(data.get("related_investigation") || "").trim();
      const entered = String(data.get("investigation_id") || "").trim();
      if ((!chosen && !entered) || (chosen && entered && chosen !== entered)) {
        setError(
          "Choose one related investigation or enter its investigation ID.",
        );
        return;
      }
      return act(
        () =>
          request(
            `/incidents/${encodeURIComponent(current.incident.id)}/investigations`,
            {
              method: "POST",
              body: JSON.stringify({
                expected_revision: current.incident.revision,
                investigation_id: entered || chosen,
                comment: String(data.get("link_reason") || "").trim(),
              }),
            },
          ),
        "Investigation linked. Incident access now requires access to every linked case.",
        selectedID.current,
      );
    }
    if (current.kind === "case_assign")
      return act(
        () =>
          request(
            `/investigations/${encodeURIComponent(current.coordination.investigation_id)}/case/assignment`,
            {
              method: "POST",
              body: JSON.stringify({
                expected_revision: current.coordination.revision,
                assignee: String(data.get("assignee") || "") || null,
              }),
            },
          ),
        "Case assignment saved.",
        current.coordination.investigation_id,
      );
    if (current.kind === "case_escalate")
      return act(
        () =>
          request(
            `/investigations/${encodeURIComponent(current.coordination.investigation_id)}/case/escalation`,
            {
              method: "POST",
              body: JSON.stringify({
                expected_revision: current.coordination.revision,
                reason: String(data.get("reason") || "").trim(),
              }),
            },
          ),
        "Case escalation requested.",
        current.coordination.investigation_id,
      );
    if (current.kind === "case_ack")
      return act(
        () =>
          request(
            `/investigations/${encodeURIComponent(current.coordination.investigation_id)}/case/acknowledge`,
            {
              method: "POST",
              body: JSON.stringify({
                expected_revision: current.coordination.revision,
              }),
            },
          ),
        "Escalation acknowledged.",
        current.coordination.investigation_id,
      );
    if (current.kind === "review")
      return act(
        () =>
          request(
            `/investigations/${encodeURIComponent(current.review.investigation_id)}/review/decision`,
            {
              method: "POST",
              body: JSON.stringify({
                review_id: current.review.review_id,
                decision: current.decision,
                comment,
              }),
            },
          ),
        current.decision === "approved"
          ? "Report review approved."
          : "Report review rejected.",
        current.review.investigation_id,
      );
    if (current.kind === "proposal")
      return act(
        () =>
          request("/responses", {
            method: "POST",
            body: JSON.stringify({
              investigation_id: current.record.id,
              action: "endpoint.isolate",
              target: data.get("target"),
              parameters: { duration_minutes: Number(data.get("duration")) },
              lifetime_seconds: 300,
            }),
          }),
        "Dry-run proposal submitted for a separate approval.",
        current.record.id,
      );
    if (current.kind === "decision")
      return act(
        () =>
          request(
            `/responses/${encodeURIComponent(current.proposal.id)}/decision`,
            {
              method: "POST",
              body: JSON.stringify({ decision: current.decision, comment }),
            },
          ),
        current.decision === "approved"
          ? "Dry-run request approved."
          : "Dry-run request rejected.",
      );
    if (current.kind === "simulate")
      return act(
        () =>
          request(
            `/responses/${encodeURIComponent(current.proposal.id)}/simulate`,
            {
              method: "POST",
              body: JSON.stringify({
                approval_id: current.proposal.approval_id,
              }),
            },
          ),
        "Simulation recorded. No endpoint was changed.",
      );
    return act(
      () =>
        request(
          `/responses/${encodeURIComponent(current.proposal.id)}/revoke`,
          { method: "POST" },
        ),
      "Request revoked. Its approval can no longer be used.",
    );
  };
  const filtered = cases.filter(
    (c) =>
      (filter === "all" || c.status === filter) &&
      `${c.query} ${c.id} ${c.subject}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const linkCandidates = (() => {
    if (modal?.kind !== "incident_link") return [];
    const linked = new Set(
      modal.sources.map((source) => source.investigation_id),
    );
    const collected = new Set([
      "completed",
      "awaiting_review",
      "review_rejected",
    ]);
    const candidates = new Map<string, string>();
    cases
      .filter((item) => collected.has(item.status) && !linked.has(item.id))
      .forEach((item) =>
        candidates.set(
          item.id,
          `${item.query || "Investigation"} · INV-${short(item.id)}`,
        ),
      );
    coordinationRows
      .filter(
        (item) =>
          !linked.has(item.investigation_id) &&
          !candidates.has(item.investigation_id),
      )
      .forEach((item) => {
        const known = cases.find(
          (record) => record.id === item.investigation_id,
        );
        if (!known || collected.has(known.status))
          candidates.set(item.investigation_id, `INV-${item.investigation_id}`);
      });
    return Array.from(candidates, ([id, label]) => ({ id, label }));
  })();
  const pending = reviews.filter((r) => r.state === "pending");
  const hosts =
    selected?.report?.evidence
      .flatMap((e) =>
        ["demo-host-1", "demo-host-2"].filter((host) =>
          new RegExp(`(?<![A-Za-z0-9-])${host}(?![A-Za-z0-9-])`).test(
            e.content.summary,
          ),
        ),
      )
      .filter((host, index, all) => all.indexOf(host) === index) || [];
  const titles: Record<View, [string, string]> = {
    investigations: [
      "Investigations",
      "From a question to source-attributed evidence.",
    ],
    coordination: [
      "Case coordination",
      "Coordinate assignments and escalate cases for management attention.",
    ],
    incidents: [
      "Incidents",
      "Track case work, evidence notes and resolution decisions.",
    ],
    reviews: [
      "Review queue",
      "Independent decisions, grounded in the evidence.",
    ],
    responses: [
      "Response approvals",
      "A separate approval for every synthetic dry run.",
    ],
    integrations: [
      "Integrations",
      "The authorized sources behind your investigations.",
    ],
  };
  const closeModal = () => {
    if (!busy) {
      createIntent.current = null;
      setModal(null);
      setError("");
    }
  };
  const citation = (id: string) => {
    setHighlight(id);
    document
      .getElementById(`evidence-${id}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const incidentCitation = (investigationID: string, evidenceID: string) => {
    if (selected?.id === investigationID) citation(evidenceID);
    else void openCase(investigationID, evidenceID);
  };
  function detail() {
    if (!selected) return null;
    const report = selected.report,
      review = selected.review,
      own =
        cases.find((c) => c.id === selected.id)?.subject === me?.subject ||
        review?.requester === me?.subject,
      coordination = selected.case,
      incident = selected.incident,
      incidentSources = selected.incident_sources || [],
      incidentEscalated = incidentSources.some(
        (source) => source.escalation_state === "requested",
      ),
      canCoordinate = Boolean(
        coordination &&
        (has("cases:manage") ||
          (has("cases:coordinate") &&
            [coordination.creator, coordination.assignee].includes(
              me?.subject || "",
            ))),
      ),
      canReview =
        has("investigations:review") &&
        review?.requester !== me?.subject &&
        review?.state === "pending" &&
        review.expires_at > Date.now() / 1000;
    return (
      <section className="panel detail-panel" aria-label="Investigation report">
        <div className="detail-top">
          <span className="eyebrow">INV-{short(selected.id)}</span>
          <button
            className="icon-button"
            aria-label="Close report"
            onClick={() => {
              selectedID.current = "";
              pendingCitation.current = null;
              setHighlight("");
              selection.current++;
              setSelected(null);
            }}
          >
            <Icon name="close" size={17} />
          </button>
        </div>
        <h2>{report?.query || "Investigation report"}</h2>
        <div className="detail-status">
          <Badge value={selected.status} />
          <span className="synthetic-mini">Synthetic telemetry</span>
        </div>
        {coordination && (
          <section
            className="coordination-detail"
            aria-label="Case coordination details"
          >
            <div className="coordination-heading">
              <h3>Case coordination</h3>
              <Badge value={coordination.escalation_state} />
            </div>
            <dl className="coordination-facts">
              <div>
                <dt>Assignee</dt>
                <dd>{coordination.assignee || "Unassigned"}</dd>
              </div>
              <div>
                <dt>Created by</dt>
                <dd>{coordination.creator}</dd>
              </div>
            </dl>
            {coordination.escalation_reason && (
              <div className="coordination-escalation">
                <strong>Escalation reason</strong>
                <p>{coordination.escalation_reason}</p>
                <span>
                  Requested by {coordination.escalated_by || "—"} ·{" "}
                  {date(coordination.escalated_at || undefined)}
                </span>
                {coordination.escalation_state === "acknowledged" && (
                  <span>
                    Acknowledged by {coordination.acknowledged_by || "—"} ·{" "}
                    {date(coordination.acknowledged_at || undefined)}
                  </span>
                )}
              </div>
            )}
            <div className="button-row coordination-actions">
              {canCoordinate && (
                <button
                  className="button secondary small"
                  disabled={busy}
                  onClick={() =>
                    setModal({ kind: "case_assign", coordination })
                  }
                >
                  {coordination.assignee ? "Change assignee" : "Assign case"}
                </button>
              )}
              {canCoordinate && (
                <button
                  className="button secondary small"
                  disabled={
                    busy || coordination.escalation_state === "requested"
                  }
                  onClick={() =>
                    setModal({ kind: "case_escalate", coordination })
                  }
                >
                  {coordination.escalation_state === "acknowledged"
                    ? "Re-escalate case"
                    : "Escalate case"}
                </button>
              )}
              {has("cases:manage") &&
                coordination.escalation_state === "requested" && (
                  <button
                    className="button primary small"
                    disabled={busy}
                    onClick={() => setModal({ kind: "case_ack", coordination })}
                  >
                    Acknowledge escalation
                  </button>
                )}
            </div>
            <p className="coordination-boundary">
              Assignment coordinates this case. Collection, review and response
              permissions remain independently enforced.
            </p>
          </section>
        )}
        {has("cases:read") &&
          (incident ||
            (report &&
              canCoordinate &&
              ["completed", "awaiting_review", "review_rejected"].includes(
                selected.status,
              ))) && (
            <section className="incident-detail" aria-label="Incident details">
              <div className="coordination-heading">
                <h3>Incident</h3>
                {incident && <Badge value={incident.status} />}
              </div>
              {incident ? (
                <>
                  <h4 className="incident-title">{incident.title}</h4>
                  <Badge value={incident.severity} />
                  {incident.description && (
                    <p className="incident-prose">{incident.description}</p>
                  )}
                  <dl className="coordination-facts">
                    <div>
                      <dt>Incident</dt>
                      <dd>{short(incident.id)}</dd>
                    </div>
                    <div>
                      <dt>Assignee</dt>
                      <dd>{incident.assignee || "Unassigned"}</dd>
                    </div>
                    <div>
                      <dt>Created by</dt>
                      <dd>
                        {incident.created_by} · {date(incident.created_at)}
                      </dd>
                    </div>
                    <div>
                      <dt>Updated by</dt>
                      <dd>
                        {incident.updated_by} · {date(incident.updated_at)}
                      </dd>
                    </div>
                  </dl>
                  {incident.resolution_note && (
                    <div className="incident-resolution">
                      <strong>Resolution note</strong>
                      <p className="incident-prose">
                        {incident.resolution_note}
                      </p>
                    </div>
                  )}
                  {incident.resolved_by && (
                    <p className="incident-meta">
                      Resolved by {incident.resolved_by} ·{" "}
                      {date(incident.resolved_at || undefined)}
                    </p>
                  )}
                  {incident.closed_by && (
                    <p className="incident-meta">
                      Closed by {incident.closed_by} ·{" "}
                      {date(incident.closed_at || undefined)}
                    </p>
                  )}
                  {canCoordinate && incident.revision < 200 && (
                    <div className="button-row coordination-actions">
                      {incident.status === "open" && (
                        <button
                          className="button secondary small"
                          disabled={busy}
                          onClick={() =>
                            setModal({
                              kind: "incident_status",
                              incident,
                              status: "in_progress",
                            })
                          }
                        >
                          Start work
                        </button>
                      )}
                      {["open", "in_progress"].includes(incident.status) && (
                        <button
                          className="button primary small"
                          disabled={busy || incidentEscalated}
                          onClick={() =>
                            setModal({
                              kind: "incident_status",
                              incident,
                              status: "resolved",
                            })
                          }
                        >
                          Resolve incident
                        </button>
                      )}
                      {(incident.status === "resolved" ||
                        (incident.status === "closed" &&
                          has("cases:manage"))) && (
                        <button
                          className="button secondary small"
                          disabled={busy}
                          onClick={() =>
                            setModal({
                              kind: "incident_status",
                              incident,
                              status: "open",
                            })
                          }
                        >
                          Reopen incident
                        </button>
                      )}
                      {incident.status === "resolved" &&
                        has("cases:manage") && (
                          <button
                            className="button secondary small"
                            disabled={busy || incidentEscalated}
                            onClick={() =>
                              setModal({
                                kind: "incident_status",
                                incident,
                                status: "closed",
                              })
                            }
                          >
                            Close incident
                          </button>
                        )}
                      {incident.status !== "closed" && (
                        <button
                          className="button secondary small"
                          disabled={busy}
                          onClick={() =>
                            setModal({
                              kind: "incident_note",
                              incident,
                              sources: incidentSources,
                            })
                          }
                        >
                          Add incident note
                        </button>
                      )}
                    </div>
                  )}
                  {canCoordinate &&
                    ["open", "in_progress"].includes(incident.status) &&
                    incident.revision < 200 &&
                    incidentSources.length < 10 && (
                      <button
                        className="button secondary small incident-link-button"
                        disabled={busy}
                        onClick={() =>
                          setModal({
                            kind: "incident_link",
                            incident,
                            sources: incidentSources,
                          })
                        }
                      >
                        Link investigation
                      </button>
                    )}
                  {incidentEscalated && (
                    <p className="incident-pending">
                      A manager must acknowledge every pending source escalation
                      before this incident can be resolved or closed. Open a
                      flagged investigation to review its case escalation.
                    </p>
                  )}
                  <div className="section-title">
                    <h3>Linked investigations</h3>
                    <span>{incidentSources.length} loaded · up to 10</span>
                  </div>
                  <div
                    className="incident-sources"
                    aria-label="Linked investigations"
                  >
                    {incidentSources.map((source) => (
                      <article
                        className="incident-source"
                        key={source.investigation_id}
                        data-testid={`linked-investigation-${source.investigation_id}`}
                      >
                        <div className="incident-source-heading">
                          <strong>{source.query || "Investigation"}</strong>
                          {source.primary && (
                            <span className="pill">Primary</span>
                          )}
                          {source.escalation_state === "requested" && (
                            <Badge value="requested" />
                          )}
                        </div>
                        <code className="incident-source-id">
                          {source.investigation_id}
                        </code>
                        <p className="incident-meta">
                          {source.assignee
                            ? `Assigned to ${source.assignee}`
                            : "Unassigned"}{" "}
                          · Created by {source.creator}
                        </p>
                        <p className="incident-meta">
                          Linked by {source.linked_by} ·{" "}
                          {date(source.linked_at)}
                        </p>
                        <button
                          className="button secondary small"
                          aria-label={`View investigation ${short(source.investigation_id)}`}
                          disabled={detailLoading}
                          onClick={() => void openCase(source.investigation_id)}
                        >
                          View investigation
                        </button>
                      </article>
                    ))}
                  </div>
                  <p className="incident-meta">
                    Reading the combined incident requires access to every
                    linked case. Linking can narrow who can view it; source
                    report and response permissions remain independent.
                  </p>
                  <div className="section-title">
                    <h3>Activity</h3>
                    <span>
                      {selected.incident_activity?.length || 0} loaded
                    </span>
                  </div>
                  <ol
                    className="incident-activity"
                    aria-label="Incident activity"
                  >
                    {(selected.incident_activity || []).map((entry) => (
                      <li key={entry.id}>
                        <div className="incident-entry-heading">
                          <strong>
                            {entry.kind === "created"
                              ? "Incident created"
                              : entry.kind === "note"
                                ? "Note added"
                                : entry.kind === "linked"
                                  ? "Investigation linked"
                                  : `${entry.from_status ? labels[entry.from_status] || entry.from_status : "Status"} → ${entry.to_status ? labels[entry.to_status] || entry.to_status : "Updated"}`}
                          </strong>
                          <time>{date(entry.created_at)}</time>
                        </div>
                        <span className="incident-meta">{entry.actor}</span>
                        {entry.body && (
                          <p className="incident-prose">{entry.body}</p>
                        )}
                        {entry.linked_investigation_id && (
                          <div className="citation-row">
                            <button
                              onClick={() =>
                                void openCase(entry.linked_investigation_id!)
                              }
                            >
                              View INV-{short(entry.linked_investigation_id)}
                            </button>
                          </div>
                        )}
                        {(() => {
                          const references = entry.references?.length
                            ? entry.references
                            : entry.evidence_ids.map((evidence_id) => ({
                                investigation_id: incident.investigation_id,
                                evidence_id,
                              }));
                          return (
                            !!references.length && (
                              <div className="citation-row">
                                {references.map((reference) => {
                                  const source = incidentSources.find(
                                    (item) =>
                                      item.investigation_id ===
                                      reference.investigation_id,
                                  );
                                  const index =
                                    source?.evidence.findIndex(
                                      (item) =>
                                        item.evidence_id ===
                                        reference.evidence_id,
                                    ) ?? -1;
                                  return index < 0 ? (
                                    <span
                                      key={`${reference.investigation_id}:${reference.evidence_id}`}
                                    >
                                      Source unavailable
                                    </span>
                                  ) : (
                                    <button
                                      key={`${reference.investigation_id}:${reference.evidence_id}`}
                                      onClick={() =>
                                        incidentCitation(
                                          reference.investigation_id,
                                          reference.evidence_id,
                                        )
                                      }
                                    >
                                      <Icon name="link" size={12} />
                                      INV-{short(reference.investigation_id)} ·
                                      Evidence {index + 1}
                                    </button>
                                  );
                                })}
                              </div>
                            )
                          );
                        })()}
                      </li>
                    ))}
                  </ol>
                  {incident.revision >= 200 && (
                    <p className="incident-meta">
                      This incident has reached its 200-entry activity limit.
                      Its saved history remains available.
                    </p>
                  )}
                  <p className="coordination-boundary">
                    Activity shows up to 200 saved entries. Incident status does
                    not approve a report, execute a response or transfer
                    workflow ownership.
                  </p>
                </>
              ) : (
                <>
                  <p className="incident-prose">
                    Create an incident to track the work and resolution of this
                    investigation.
                  </p>
                  <button
                    className="button secondary small"
                    disabled={busy}
                    onClick={() =>
                      setModal({ kind: "incident_create", record: selected })
                    }
                  >
                    Create incident
                  </button>
                </>
              )}
            </section>
          )}
        {!report ? (
          <Empty
            icon="clock"
            title="Evidence collection is pending"
            text="Refresh after collection completes."
          />
        ) : (
          <>
            <div className="assessment-box">
              <span className="eyebrow">ASSESSMENT</span>
              <strong>
                {labels[report.assessment] || "No assessment available"}
              </strong>
              <p>
                {report.reasoning?.synthetic_fixture
                  ? "Structured assistance uses an offline fixture. No LLM was invoked."
                  : "Observed telemetry requires analyst judgment; malicious intent is not established."}
              </p>
            </div>
            {review && (
              <div className={`review-box ${review.state}`}>
                <div className="review-box-heading">
                  <Icon name="review" size={18} />
                  <strong>
                    {review.state === "pending"
                      ? "Independent review required"
                      : review.state === "approved"
                        ? "Report review approved"
                        : "Report review rejected"}
                  </strong>
                </div>
                <p>
                  {review.state === "pending"
                    ? `${review.requester === me?.subject ? "A different reviewer must decide." : `Requested by ${review.requester}.`} ${expiry(review.expires_at)}.`
                    : `Decision recorded${review.reviewer ? ` by ${review.reviewer}` : ""}.`}
                </p>
                {review.comment && <blockquote>{review.comment}</blockquote>}
                {canReview && (
                  <div className="button-row">
                    <button
                      className="button primary small"
                      disabled={busy}
                      onClick={() =>
                        setModal({
                          kind: "review",
                          decision: "approved",
                          review: { ...review, investigation_id: selected.id },
                        })
                      }
                    >
                      Approve report
                    </button>
                    <button
                      className="button secondary small"
                      disabled={busy}
                      onClick={() =>
                        setModal({
                          kind: "review",
                          decision: "rejected",
                          review: { ...review, investigation_id: selected.id },
                        })
                      }
                    >
                      Reject
                    </button>
                  </div>
                )}
                {review.state === "pending" &&
                  own &&
                  review.expires_at <= Date.now() / 1000 && (
                    <button
                      className="button secondary small"
                      disabled={busy}
                      onClick={() =>
                        void act(
                          () =>
                            request(
                              `/investigations/${encodeURIComponent(selected.id)}/review`,
                              { method: "POST" },
                            ),
                          "Review request refreshed.",
                          selected.id,
                        )
                      }
                    >
                      Refresh review request
                    </button>
                  )}
              </div>
            )}
            {!review &&
              own &&
              has("investigations:run") &&
              selected.status === "completed" && (
                <button
                  className="button secondary wide"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      () =>
                        request(
                          `/investigations/${encodeURIComponent(selected.id)}/review`,
                          { method: "POST" },
                        ),
                      "Report submitted for independent review.",
                      selected.id,
                    )
                  }
                >
                  <Icon name="review" size={16} />
                  Request independent review
                </button>
              )}
            <div className="section-title">
              <h3>Findings</h3>
              <span>{report.findings.length}</span>
            </div>
            {report.findings.length ? (
              report.findings.map((finding, index) => (
                <article className="finding" key={index}>
                  <span className="finding-number">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <p>{finding.statement}</p>
                    <div className="citation-row">
                      {finding.evidence_ids.map((id) => {
                        const index = report.evidence.findIndex(
                          (item) => item.evidence_id === id,
                        );
                        return index < 0 ? (
                          <span key={id}>Source unavailable</span>
                        ) : (
                          <button key={id} onClick={() => citation(id)}>
                            <Icon name="link" size={12} />
                            Evidence {index + 1}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <p className="muted small-copy">
                No evidence-backed findings were produced.
              </p>
            )}
            <div className="section-title">
              <h3>Evidence timeline</h3>
              <span>{report.evidence.length}</span>
            </div>
            <div className="evidence-timeline">
              {report.evidence.map((item, index) => (
                <article
                  data-testid={`evidence-${item.evidence_id}`}
                  id={`evidence-${item.evidence_id}`}
                  className={`evidence-card ${highlight === item.evidence_id ? "highlight" : ""}`}
                  key={item.evidence_id}
                >
                  <div className="timeline-dot" />
                  <div className="evidence-meta">
                    <strong>Evidence {index + 1}</strong>
                    <time>{date(item.content.timestamp)}</time>
                  </div>
                  <p>{item.content.summary}</p>
                  <div className="evidence-source">
                    <span className="protocol">
                      {item.protocol.toUpperCase()}
                    </span>
                    <code>{item.connector_id}</code>
                    <span>· {item.content.kind.replaceAll("_", " ")}</span>
                  </div>
                </article>
              ))}
            </div>
            {!report.evidence.length && (
              <p className="muted small-copy">
                No matching telemetry. Missing evidence does not establish
                safety.
              </p>
            )}
            {review?.state === "approved" &&
              own &&
              has("responses:propose") &&
              hosts.length > 0 && (
                <div className="response-callout">
                  <Icon name="shield" size={20} />
                  <div>
                    <strong>Propose a controlled dry run</strong>
                    <p>An independent action approval is still required.</p>
                  </div>
                  <button
                    className="button secondary small"
                    disabled={busy}
                    onClick={() =>
                      setModal({ kind: "proposal", record: selected })
                    }
                  >
                    Propose
                    <Icon name="arrow" size={13} />
                  </button>
                </div>
              )}
            <details className="limitations">
              <summary>Scope & limitations</summary>
              {(report.limitations || []).map((text, i) => (
                <p key={i}>{text}</p>
              ))}
              <p>
                Evidence is synthetic. Response simulations never change an
                endpoint.
              </p>
            </details>
          </>
        )}
      </section>
    );
  }

  if (!me)
    return (
      <div className="login-shell">
        <section className="login-story">
          <Brand />
          <div className="login-heading">
            <span className="eyebrow mint">THE ANALYST WORKBENCH</span>
            <h1>
              Evidence first.
              <br />
              Human judgment
              <br />
              <span>at the center.</span>
            </h1>
            <p>
              Investigate synthetic security events, follow the evidence, and
              keep every response under human control.
            </p>
          </div>
          <div className="login-principles">
            <span>
              <Icon name="link" />
              Source-attributed evidence
            </span>
            <span>
              <Icon name="review" />
              Independent review
            </span>
            <span>
              <Icon name="lock" />
              Controlled approvals
            </span>
          </div>
          <p className="login-foot">
            WORK4CE ASSISTANT <span>Security operations, connected.</span>
          </p>
        </section>
        <section className="login-panel">
          <div className="login-card">
            <span className="workspace-tag">
              <span />
              SYNTHETIC WORKSPACE
            </span>
            <h2>Connect to your workspace</h2>
            <p>Use your analyst or reviewer access token to continue.</p>
            <form onSubmit={connect}>
              <label htmlFor="access-token">Access token</label>
              <input
                id="access-token"
                type="password"
                autoComplete="off"
                spellCheck={false}
                autoFocus
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Enter your access token"
                required
              />
              <p className="field-note">
                Your token stays in this tab and is cleared when you sign out or
                reload.
              </p>
              {error && (
                <div className="alert error" role="alert">
                  {error}
                </div>
              )}
              <button
                className="button primary wide"
                disabled={connecting || !tokenInput.trim()}
              >
                {connecting ? "Connecting…" : "Connect to workspace"}
                <Icon name="arrow" size={17} />
              </button>
            </form>
            <div className="login-boundary">
              <Icon name="shield" />
              <p>
                This workspace contains synthetic telemetry. Response
                simulations never change an endpoint.
              </p>
            </div>
          </div>
        </section>
      </div>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="workspace-box">
          <span className="workspace-symbol">S</span>
          <div>
            <strong>Synthetic workspace</strong>
            <small>Security operations</small>
          </div>
          <span className="workspace-dot" />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Workspace navigation">
          {(
            [
              ["investigations", "cases", "Investigations", cases.length],
              [
                "coordination",
                "cases",
                "Case coordination",
                coordinationRows.length,
              ],
              ["incidents", "cases", "Incidents", incidents.length],
              ["reviews", "review", "Review queue", pending.length],
              [
                "responses",
                "response",
                "Response approvals",
                responses.filter((r) => r.state === "pending").length,
              ],
              ["integrations", "plug", "Integrations", sources.length],
            ] as const
          )
            .filter(
              (item) =>
                (item[0] !== "reviews" || has("investigations:review")) &&
                (!["coordination", "incidents"].includes(item[0]) ||
                  has("cases:read")),
            )
            .map(([id, icon, label, count]) => (
              <button
                key={id}
                className={`nav-item ${view === id ? "active" : ""}`}
                onClick={() => navigate(id)}
                aria-current={view === id ? "page" : undefined}
              >
                <Icon name={icon} />
                <span>{label}</span>
                <span className="nav-count">{count}</span>
              </button>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="boundary-card">
            <Icon name="shield" />
            <strong>Human-governed by design</strong>
            <p>
              Evidence is synthetic.
              <br />
              Response actions are dry runs.
            </p>
          </div>
          <div className="profile">
            <span className="avatar">
              {me.subject.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong title={me.subject}>{me.subject}</strong>
              <small>
                {has("investigations:review")
                  ? "Reviewer access"
                  : "Analyst access"}
              </small>
            </div>
            <button
              className="icon-button"
              onClick={logout}
              aria-label="Sign out"
              title="Sign out"
            >
              <Icon name="logout" size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace<span>/</span>
            <strong>{titles[view][0]}</strong>
          </div>
          <span
            className={`connection-status ${healthy.length ? "online" : ""}`}
          >
            <span />
            {healthy.length ? "Sources available" : "Sources unavailable"}
          </span>
          <button className="mobile-signout button subtle" onClick={logout}>
            Sign out
          </button>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <span className="eyebrow">ANALYST WORKBENCH</span>
              <h1>{titles[view][0]}</h1>
              <p>{titles[view][1]}</p>
            </div>
            <div className="heading-actions">
              <button
                className="button secondary"
                disabled={loading || busy}
                onClick={() => {
                  const id = selectedID.current,
                    generation = epoch.current;
                  void refresh(me).then(() => {
                    if (
                      id &&
                      generation === epoch.current &&
                      selectedID.current === id
                    )
                      void openCase(id);
                  });
                }}
              >
                <Icon name="refresh" size={16} />
                {loading ? "Refreshing…" : "Refresh"}
              </button>
              {has("investigations:run") && (
                <button
                  className="button primary"
                  onClick={() => {
                    setError("");
                    setModal({ kind: "new" });
                  }}
                >
                  <Icon name="plus" size={17} />
                  New investigation
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="alert error" role="alert">
              <Icon name="shield" size={17} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              <Icon name="check" size={17} />
              <span>{notice}</span>
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {view === "investigations" && (
            <>
              <section className="stats" aria-label="Investigation overview">
                {[
                  [
                    "Visible investigations",
                    cases.length,
                    "cases",
                    "Your current case view",
                  ],
                  [
                    "Awaiting review",
                    cases.filter((c) => c.status === "awaiting_review").length,
                    "review",
                    "Independent decision needed",
                  ],
                  [
                    "Evidence collected",
                    cases.reduce((n, c) => n + c.evidence_count, 0),
                    "file",
                    "Source-attributed items",
                  ],
                ].map(([label, value, icon, note]) => (
                  <article className="stat" key={String(label)}>
                    <div>
                      <span>{label}</span>
                      <strong>{Number(value).toLocaleString()}</strong>
                      <p>{note}</p>
                    </div>
                    <span className="stat-icon">
                      <Icon name={String(icon)} />
                    </span>
                  </article>
                ))}
              </section>
              <div
                className={`case-layout ${selected || detailLoading ? "has-detail" : ""}`}
              >
                <section className="panel case-list">
                  <div className="panel-heading">
                    <div>
                      <h2>Case queue</h2>
                      <p>Investigation history in your scope</p>
                    </div>
                    <span className="pill">{filtered.length} visible</span>
                  </div>
                  <div className="list-tools">
                    <div className="search-input">
                      <Icon name="search" size={17} />
                      <input
                        aria-label="Search loaded investigations"
                        placeholder="Search loaded cases…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </div>
                    <select
                      aria-label="Filter investigation status"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    >
                      <option value="all">All statuses</option>
                      <option value="awaiting_review">Awaiting review</option>
                      <option value="completed">Completed</option>
                      <option value="failed">Failed</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  </div>
                  {loading && !cases.length ? (
                    <Loading text="Loading investigations…" />
                  ) : filtered.length ? (
                    <div className="case-rows">
                      {filtered.map((item) => (
                        <button
                          data-testid={`case-row-${item.id}`}
                          className={`case-row ${selectedID.current === item.id ? "selected" : ""}`}
                          key={item.id}
                          onClick={() => void openCase(item.id)}
                        >
                          <span className="case-symbol">
                            <Icon name="file" size={19} />
                          </span>
                          <span className="case-row-content">
                            <span className="case-row-title">
                              {item.query || "Investigation"}
                              <Badge value={item.status} />
                            </span>
                            <span className="case-row-sub">
                              <code>INV-{short(item.id)}</code>
                              <span>·</span>
                              {item.evidence_count} evidence items<span>·</span>
                              {date(item.created_at)}
                            </span>
                          </span>
                          <Icon name="arrow" size={16} />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <Empty
                      icon="cases"
                      title={
                        search || filter !== "all"
                          ? "No matching investigations"
                          : "Start with a security question"
                      }
                      text={
                        search || filter !== "all"
                          ? "Try another query or status filter."
                          : "Investigate the synthetic telemetry and build your first evidence-backed report."
                      }
                      action={
                        has("investigations:run") &&
                        !search &&
                        filter === "all" ? (
                          <button
                            className="button primary"
                            onClick={() => setModal({ kind: "new" })}
                          >
                            <Icon name="plus" size={16} />
                            New investigation
                          </button>
                        ) : undefined
                      }
                    />
                  )}
                  <div className="history-footer" aria-live="polite">
                    <p>
                      {cases.length} loaded · Search and counts cover loaded
                      history.
                      {historyLoaded &&
                        !loading &&
                        !nextCursor &&
                        " All available investigations loaded."}
                    </p>
                    {nextCursor && (
                      <button
                        className="button secondary"
                        disabled={loading || historyLoading || busy}
                        onClick={() => void loadOlder()}
                      >
                        {historyLoading
                          ? "Loading older investigations…"
                          : "Load older investigations"}
                      </button>
                    )}
                  </div>
                </section>
                {detailLoading ? (
                  <section className="panel">
                    <Loading text="Opening evidence…" />
                  </section>
                ) : (
                  selected && detail()
                )}
              </div>
            </>
          )}
          {view === "coordination" && (
            <div
              className={`case-layout ${selected || detailLoading ? "has-detail" : ""}`}
            >
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Coordinated cases</h2>
                    <p>
                      Assigned and escalated investigations · Newest first by
                      investigation creation
                    </p>
                  </div>
                  <span className="pill">{coordinationRows.length} loaded</span>
                </div>
                {loading && !coordinationRows.length ? (
                  <Loading text="Loading case coordination…" />
                ) : coordinationRows.length ? (
                  <div className="case-rows">
                    {coordinationRows.map((item) => (
                      <button
                        data-testid={`coordination-row-${item.investigation_id}`}
                        key={item.investigation_id}
                        className={`case-row coordination-row ${selectedID.current === item.investigation_id ? "selected" : ""}`}
                        onClick={() => void openCase(item.investigation_id)}
                      >
                        <span className="case-symbol">
                          <Icon name="cases" size={19} />
                        </span>
                        <span className="case-row-content">
                          <span className="case-row-title">
                            Case {short(item.investigation_id)}
                            <Badge value={item.escalation_state} />
                          </span>
                          <span className="case-row-sub">
                            {item.assignee
                              ? `Assigned to ${item.assignee}`
                              : "Unassigned"}
                            <span>·</span>Created by {item.creator}
                          </span>
                          {item.escalation_reason && (
                            <span className="coordination-row-reason">
                              {item.escalation_reason}
                            </span>
                          )}
                        </span>
                        <Icon name="arrow" size={16} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty
                    icon="cases"
                    title="No coordinated cases yet"
                    text="Open an investigation to assign responsibility or request an escalation. Existing assignments and escalations will appear here."
                  />
                )}
                <div
                  className="history-footer queue-footer"
                  role="status"
                  aria-live="polite"
                >
                  <p>
                    {coordinationRows.length} loaded · Newest first by
                    investigation creation. Assignment and escalation updates do
                    not change this order.
                    {coordinationLoaded &&
                      !loading &&
                      !coordinationCursor &&
                      " All available coordinated cases loaded."}
                  </p>
                  {coordinationCursor && (
                    <button
                      className="button secondary"
                      disabled={loading || busy || coordinationLoading}
                      onClick={() => void loadOlderCoordinatedCases()}
                    >
                      {coordinationLoading
                        ? "Loading older coordinated cases…"
                        : "Load older coordinated cases"}
                    </button>
                  )}
                </div>
              </section>
              {detailLoading ? (
                <section className="panel">
                  <Loading text="Opening case…" />
                </section>
              ) : (
                selected && detail()
              )}
            </div>
          )}
          {view === "incidents" && (
            <div
              className={`case-layout ${selected || detailLoading ? "has-detail" : ""}`}
            >
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Incidents in your scope</h2>
                    <p>
                      Saved incident work · Newest first by incident creation
                    </p>
                  </div>
                  <span className="pill">{incidents.length} loaded</span>
                </div>
                {loading && !incidents.length ? (
                  <Loading text="Loading incidents…" />
                ) : incidents.length ? (
                  <div className="case-rows">
                    {incidents.map((item) => (
                      <button
                        data-testid={`incident-row-${item.id}`}
                        key={item.id}
                        className={`case-row ${selectedID.current === item.investigation_id ? "selected" : ""}`}
                        onClick={() => void openCase(item.investigation_id)}
                      >
                        <span className="case-symbol">
                          <Icon name="cases" size={19} />
                        </span>
                        <span className="case-row-content">
                          <span className="case-row-title">
                            {item.title}
                            <Badge value={item.status} />
                          </span>
                          <span className="case-row-sub">
                            <Badge value={item.severity} />
                            <span>·</span>
                            {item.assignee
                              ? `Assigned to ${item.assignee}`
                              : "Unassigned"}
                          </span>
                          <span className="incident-meta">
                            Source INV-{short(item.investigation_id)} · Created{" "}
                            {date(item.created_at)}
                          </span>
                        </span>
                        <Icon name="arrow" size={16} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty
                    icon="cases"
                    title="No incidents yet"
                    text="Open a collected investigation and create an incident to track its work and resolution."
                  />
                )}
                <div
                  className="history-footer queue-footer"
                  role="status"
                  aria-live="polite"
                >
                  <p>
                    {incidents.length} loaded · Newest first by incident
                    creation. Status updates do not change this order.
                    {incidentLoaded &&
                      !loading &&
                      !incidentCursor &&
                      " All available incidents loaded."}
                  </p>
                  {incidentCursor && (
                    <button
                      className="button secondary"
                      disabled={loading || busy || incidentLoading}
                      onClick={() => void loadOlderIncidents()}
                    >
                      {incidentLoading
                        ? "Loading older incidents…"
                        : "Load older incidents"}
                    </button>
                  )}
                </div>
              </section>
              {detailLoading ? (
                <section className="panel">
                  <Loading text="Opening incident evidence…" />
                </section>
              ) : (
                selected && detail()
              )}
            </div>
          )}
          {view === "reviews" && (
            <div
              className={`case-layout ${selected || detailLoading ? "has-detail" : ""}`}
            >
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Reports for review</h2>
                    <p>Read the evidence before deciding</p>
                  </div>
                  <span className="pill">{pending.length} pending</span>
                </div>
                {loading && !reviews.length ? (
                  <Loading text="Loading review queue…" />
                ) : reviews.length ? (
                  <div className="case-rows">
                    {reviews.map((item) => (
                      <button
                        data-testid={`review-row-${item.investigation_id}`}
                        className={`case-row ${selectedID.current === item.investigation_id ? "selected" : ""}`}
                        key={item.review_id}
                        onClick={() => void openCase(item.investigation_id)}
                      >
                        <span className="case-symbol">
                          <Icon name="review" size={19} />
                        </span>
                        <span className="case-row-content">
                          <span className="case-row-title">
                            Report {short(item.investigation_id)}
                            <Badge value={item.state} />
                          </span>
                          <span className="case-row-sub">
                            {item.requester}
                            <span>·</span>
                            {item.state === "pending"
                              ? expiry(item.expires_at)
                              : "Decision recorded"}
                          </span>
                        </span>
                        <Icon name="arrow" size={16} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty
                    icon="review"
                    title="The review queue is clear"
                    text="Reports awaiting an independent decision will appear here."
                  />
                )}
              </section>
              {detailLoading ? (
                <section className="panel">
                  <Loading text="Opening report…" />
                </section>
              ) : (
                selected && detail()
              )}
            </div>
          )}
          {view === "responses" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Response approval queue</h2>
                  <p>Every proposal is scoped, expiring, and single use.</p>
                </div>
                <span className="dry-run-tag">
                  <Icon name="shield" size={14} />
                  DRY RUN ONLY
                </span>
              </div>
              {loading && !responses.length ? (
                <Loading text="Loading response proposals…" />
              ) : responses.length ? (
                <div className="proposal-grid">
                  {responses.map((item) => (
                    <article
                      className="proposal-card"
                      data-testid={`response-row-${item.id}`}
                      key={item.id}
                    >
                      <div className="proposal-top">
                        <span className="response-symbol">
                          <Icon name="response" />
                        </span>
                        <Badge value={item.state} />
                      </div>
                      <h3>Simulate endpoint isolation</h3>
                      <div className="target-label">{item.target}</div>
                      <dl className="proposal-facts">
                        <div>
                          <dt>Duration</dt>
                          <dd>{item.parameters.duration_minutes} minutes</dd>
                        </div>
                        <div>
                          <dt>Requested by</dt>
                          <dd>{item.requester}</dd>
                        </div>
                        <div>
                          <dt>Approval window</dt>
                          <dd>{expiry(item.expires_at)}</dd>
                        </div>
                      </dl>
                      <button
                        className="text-button"
                        onClick={() => {
                          setView("investigations");
                          void openCase(item.investigation_id);
                        }}
                      >
                        <Icon name="file" size={15} />
                        Open supporting report
                        <Icon name="arrow" size={13} />
                      </button>
                      {item.simulation_result && (
                        <div className="simulation-result">
                          <Icon name="check" size={17} />
                          <div>
                            <strong>Simulation recorded</strong>
                            <p>No endpoint was changed.</p>
                          </div>
                        </div>
                      )}
                      <div className="proposal-actions">
                        {item.state === "pending" &&
                          has("responses:approve") && (
                            <>
                              <button
                                className="button primary"
                                disabled={
                                  busy ||
                                  item.requester === me.subject ||
                                  item.expires_at <= Date.now() / 1000
                                }
                                onClick={() =>
                                  setModal({
                                    kind: "decision",
                                    decision: "approved",
                                    proposal: item,
                                  })
                                }
                              >
                                Approve dry run
                              </button>
                              <button
                                className="button secondary"
                                disabled={
                                  busy ||
                                  item.requester === me.subject ||
                                  item.expires_at <= Date.now() / 1000
                                }
                                onClick={() =>
                                  setModal({
                                    kind: "decision",
                                    decision: "rejected",
                                    proposal: item,
                                  })
                                }
                              >
                                Reject
                              </button>
                            </>
                          )}
                        {item.state === "approved" &&
                          item.requester === me.subject &&
                          has("responses:simulate") && (
                            <button
                              className="button primary"
                              disabled={
                                busy || item.expires_at <= Date.now() / 1000
                              }
                              onClick={() =>
                                setModal({ kind: "simulate", proposal: item })
                              }
                            >
                              Record simulation
                              <Icon name="arrow" size={15} />
                            </button>
                          )}
                        {["pending", "approved"].includes(item.state) &&
                          (item.requester === me.subject ||
                            has("responses:approve")) && (
                            <button
                              className="button quiet"
                              disabled={busy}
                              onClick={() =>
                                setModal({ kind: "revoke", proposal: item })
                              }
                            >
                              Revoke
                            </button>
                          )}
                      </div>
                      {item.requester === me.subject &&
                        item.state === "pending" && (
                          <p className="field-note">
                            A different reviewer must approve this request.
                          </p>
                        )}
                    </article>
                  ))}
                </div>
              ) : (
                <Empty
                  icon="response"
                  title="No response proposals yet"
                  text="An approved report can support a synthetic dry-run proposal. Every proposal needs a separate approval."
                />
              )}
            </section>
          )}
          {view === "integrations" && (
            <>
              <div className="integration-intro">
                <Icon name="plug" size={25} />
                <div>
                  <h2>One capability. Interchangeable sources.</h2>
                  <p>
                    Investigations use authorized capabilities while evidence
                    records its actual source.
                  </p>
                </div>
              </div>
              <section className="integration-grid">
                {sources.map((source) => (
                  <article
                    className="panel integration-card"
                    key={source.connector_id}
                  >
                    <div className="integration-card-top">
                      <span className="source-icon">
                        {source.protocol.toUpperCase()}
                      </span>
                      <span
                        className={`source-status ${source.enabled && healthy.includes(source.connector_id) ? "available" : ""}`}
                      >
                        <span />
                        {!source.enabled
                          ? "Disabled"
                          : healthy.includes(source.connector_id)
                            ? "Available"
                            : "Unavailable"}
                      </span>
                    </div>
                    <h2>
                      {source.protocol === "mcp"
                        ? "MCP security events"
                        : source.protocol === "rest"
                          ? "REST security events"
                          : source.connector_id}
                    </h2>
                    <p>Synthetic security event collection</p>
                    <div className="capability-chip">
                      security.events.search <span>v1.0</span>
                    </div>
                    <div className="integration-card-bottom">
                      <code>{source.connector_id}</code>
                      <span>Synthetic</span>
                    </div>
                  </article>
                ))}
              </section>
              {!sources.length && (
                <section className="panel">
                  <Empty
                    icon="plug"
                    title="No authorized sources"
                    text="No connectors are available within this account’s current grants."
                  />
                </section>
              )}
            </>
          )}
          <footer className="workspace-footer">
            <span>
              <Icon name="shield" size={13} />
              Synthetic evidence · Human review · Dry-run responses
            </span>
            <span>Work4ce Assistant</span>
          </footer>
        </main>
      </div>
      {modal && (
        <Dialog
          title={
            modal.kind === "incident_create"
              ? "Create incident"
              : modal.kind === "incident_status"
                ? incidentStatusTitle(modal.status)
                : modal.kind === "incident_link"
                  ? "Link investigation"
                  : modal.kind === "incident_note"
                    ? "Add incident note"
                    : modal.kind === "case_assign"
                      ? "Assign case"
                      : modal.kind === "case_escalate"
                        ? "Escalate case"
                        : modal.kind === "case_ack"
                          ? "Acknowledge escalation"
                          : modal.kind === "new"
                            ? "Start an investigation"
                            : modal.kind === "review"
                              ? `${modal.decision === "approved" ? "Approve" : "Reject"} report review`
                              : modal.kind === "proposal"
                                ? "Propose a synthetic dry run"
                                : modal.kind === "decision"
                                  ? `${modal.decision === "approved" ? "Approve" : "Reject"} dry-run request`
                                  : modal.kind === "simulate"
                                    ? "Record this simulation?"
                                    : "Revoke this request?"
          }
          busy={busy}
          close={closeModal}
        >
          <form onSubmit={submit}>
            {modal.kind === "incident_create" ? (
              <>
                <p className="modal-copy">
                  Track incident work for INV-{short(modal.record.id)}. Case
                  permissions and independent report review still apply.
                </p>
                <label htmlFor="incident-title">Incident title</label>
                <input
                  id="incident-title"
                  name="title"
                  defaultValue={(
                    modal.record.report?.query || "Investigation incident"
                  ).slice(0, 200)}
                  maxLength={200}
                  required
                  autoFocus
                />
                <label htmlFor="incident-description">
                  Incident description{" "}
                  <span className="optional">optional</span>
                </label>
                <textarea
                  id="incident-description"
                  aria-label="Incident description"
                  name="description"
                  rows={4}
                  maxLength={2000}
                />
                <label htmlFor="incident-severity">Incident severity</label>
                <select
                  id="incident-severity"
                  name="severity"
                  defaultValue="medium"
                >
                  {["low", "medium", "high", "critical"].map((value) => (
                    <option key={value} value={value}>
                      {value.charAt(0).toUpperCase() + value.slice(1)}
                    </option>
                  ))}
                </select>
              </>
            ) : modal.kind === "incident_status" ? (
              <>
                <p className="modal-copy">
                  {incidentStatusTitle(modal.status)} for {modal.incident.title}
                  . This records the incident’s work status; report review and
                  response approvals remain separate.
                </p>
                <label htmlFor="incident-status-comment">
                  Status comment
                  {modal.status === "in_progress" && (
                    <span className="optional"> optional</span>
                  )}
                </label>
                <textarea
                  id="incident-status-comment"
                  name="comment"
                  rows={4}
                  maxLength={2000}
                  required={modal.status !== "in_progress"}
                  autoFocus
                />
              </>
            ) : modal.kind === "incident_link" ? (
              <>
                <p className="modal-copy">
                  Link a collected investigation to {modal.incident.title}.
                  Anyone reading the combined incident must have access to every
                  linked case; linking can narrow its viewers.
                </p>
                <label htmlFor="related-investigation">
                  Related investigation
                </label>
                <select
                  id="related-investigation"
                  name="related_investigation"
                  defaultValue=""
                  autoFocus
                >
                  <option value="">Choose a loaded investigation</option>
                  {linkCandidates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <label htmlFor="link-investigation-id">
                  Investigation ID <span className="optional">optional</span>
                </label>
                <input
                  id="link-investigation-id"
                  aria-label="Investigation ID"
                  name="investigation_id"
                  maxLength={36}
                  pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                  placeholder="Or enter another investigation’s UUID"
                />
                <p className="field-note">
                  Choose a loaded investigation or enter one ID. The server
                  checks access to every source independently.
                </p>
                <label htmlFor="link-reason">Link reason</label>
                <textarea
                  id="link-reason"
                  name="link_reason"
                  rows={4}
                  maxLength={2000}
                  required
                />
              </>
            ) : modal.kind === "incident_note" ? (
              <>
                <p className="modal-copy">
                  Add a saved note to {modal.incident.title}. Choose up to 10
                  evidence citations across linked investigations.
                </p>
                <label htmlFor="incident-note">Incident note</label>
                <textarea
                  id="incident-note"
                  name="body"
                  rows={4}
                  maxLength={2000}
                  required
                  autoFocus
                />
                {!!modal.sources.some((source) => source.evidence.length) && (
                  <fieldset className="incident-evidence-choices">
                    <legend>
                      Evidence citations{" "}
                      <span className="optional">optional · up to 10</span>
                    </legend>
                    {modal.sources.map((source, sourceIndex) => (
                      <div
                        className="incident-source-choice"
                        key={source.investigation_id}
                      >
                        <div className="incident-source-heading">
                          <strong>{source.query || "Investigation"}</strong>
                          {source.primary && (
                            <span className="pill">Primary</span>
                          )}
                          {source.escalation_state === "requested" && (
                            <Badge value="requested" />
                          )}
                        </div>
                        <code className="incident-source-id">
                          {source.investigation_id}
                        </code>
                        {source.evidence.map((item, index) => (
                          <label key={item.evidence_id}>
                            <input
                              type="checkbox"
                              aria-label={`INV-${short(source.investigation_id)} · Evidence ${index + 1}`}
                              name="references"
                              value={
                                modal.sources
                                  .slice(0, sourceIndex)
                                  .reduce(
                                    (count, item) =>
                                      count + item.evidence.length,
                                    0,
                                  ) + index
                              }
                            />
                            <span>
                              INV-{short(source.investigation_id)} · Evidence{" "}
                              {index + 1}
                              <small>{item.summary}</small>
                            </span>
                          </label>
                        ))}
                      </div>
                    ))}
                  </fieldset>
                )}
              </>
            ) : modal.kind === "case_assign" ? (
              <>
                <p className="modal-copy">
                  Choose an approved analyst for case{" "}
                  {short(modal.coordination.investigation_id)}. This changes
                  coordination only; investigation and response authority stay
                  with their original policy.
                </p>
                <label htmlFor="case-assignee">Case assignee</label>
                <select
                  id="case-assignee"
                  name="assignee"
                  defaultValue={modal.coordination.assignee || ""}
                  autoFocus
                >
                  <option value="">Unassigned</option>
                  {modal.coordination.assignee &&
                    !assignees.some(
                      (item) => item.subject === modal.coordination.assignee,
                    ) && (
                      <option value={modal.coordination.assignee}>
                        {modal.coordination.assignee} (current; no longer
                        eligible)
                      </option>
                    )}
                  {assignees.map((item) => (
                    <option key={item.subject} value={item.subject}>
                      {item.subject}
                    </option>
                  ))}
                </select>
              </>
            ) : modal.kind === "case_escalate" ? (
              <>
                <p className="modal-copy">
                  Request management attention for case{" "}
                  {short(modal.coordination.investigation_id)}. Explain the
                  evidence or coordination need.
                </p>
                <label htmlFor="escalation-reason">Escalation reason</label>
                <textarea
                  id="escalation-reason"
                  name="reason"
                  rows={4}
                  minLength={1}
                  maxLength={1000}
                  required
                  autoFocus
                  placeholder="Describe why this case needs escalation…"
                />
              </>
            ) : modal.kind === "case_ack" ? (
              <>
                <p className="modal-copy">
                  Acknowledge the current escalation for case{" "}
                  {short(modal.coordination.investigation_id)}. This records
                  management review; it does not approve a response action.
                </p>
                <div className="confirmation-target">
                  <Icon name="review" size={25} />
                  <div>
                    <strong>Escalation requested</strong>
                    <span>
                      {modal.coordination.escalated_by ||
                        modal.coordination.creator}
                    </span>
                  </div>
                </div>
                <p className="coordination-note">
                  {modal.coordination.escalation_reason}
                </p>
              </>
            ) : modal.kind === "new" ? (
              <>
                <p className="modal-copy">
                  Search the synthetic event sources. Your report will preserve
                  the evidence and its provenance.
                </p>
                <label htmlFor="query">Investigation query</label>
                <input
                  id="query"
                  name="query"
                  placeholder="e.g. PowerShell"
                  defaultValue="PowerShell"
                  maxLength={200}
                  required
                  autoFocus
                />
                <div className="form-help">
                  <Icon name="search" size={16} />
                  <span>
                    A literal search across synthetic telemetry. Up to 20
                    evidence items.
                  </span>
                </div>
              </>
            ) : modal.kind === "proposal" ? (
              <>
                <p className="modal-copy">
                  This requests approval for a simulation only. It will not
                  isolate an endpoint.
                </p>
                <label htmlFor="target">Observed synthetic target</label>
                <select id="target" name="target" required autoFocus>
                  {hosts.map((host) => (
                    <option key={host}>{host}</option>
                  ))}
                </select>
                <label htmlFor="duration">
                  Isolation duration to simulate (minutes)
                </label>
                <input
                  id="duration"
                  name="duration"
                  type="number"
                  min={1}
                  max={60}
                  defaultValue={15}
                  required
                />
                <p className="field-note">
                  Approval expires five minutes after this proposal is created.
                </p>
              </>
            ) : modal.kind === "review" || modal.kind === "decision" ? (
              <>
                <p className="modal-copy">
                  {modal.kind === "review"
                    ? `Record your independent decision for report ${short(modal.review.investigation_id)}.`
                    : `Record your independent decision for ${modal.proposal.target}, ${modal.proposal.parameters.duration_minutes} minutes. This permits a dry run only.`}
                </p>
                <label htmlFor="comment">
                  Review note <span className="optional">optional</span>
                </label>
                <textarea
                  id="comment"
                  name="comment"
                  rows={4}
                  maxLength={2000}
                  placeholder="Record the basis for your decision…"
                  autoFocus
                />
                <div className="form-help">
                  <Icon name="lock" size={16} />
                  <span>
                    Your identity and decision are recorded in the audit trail.
                  </span>
                </div>
              </>
            ) : modal.kind === "simulate" ? (
              <>
                <div className="confirmation-target">
                  <Icon name="response" size={25} />
                  <div>
                    <strong>{modal.proposal.target}</strong>
                    <span>
                      {modal.proposal.parameters.duration_minutes} minutes ·
                      Synthetic isolation
                    </span>
                  </div>
                </div>
                <p className="modal-copy">
                  This consumes the approved request once and records a dry-run
                  result. No endpoint will be changed.
                </p>
              </>
            ) : (
              <p className="modal-copy">
                This prevents the request’s approval from being used. A new
                proposal will need a new independent approval.
              </p>
            )}
            {error && (
              <div className="alert error" role="alert">
                {error}
              </div>
            )}
            <div className="modal-actions">
              <button
                className="button secondary"
                type="button"
                disabled={busy}
                onClick={closeModal}
              >
                Cancel
              </button>
              <button
                className={`button ${modal.kind === "revoke" || ((modal.kind === "review" || modal.kind === "decision") && modal.decision === "rejected") ? "danger" : "primary"}`}
                disabled={busy || (modal.kind === "proposal" && !hosts.length)}
              >
                {busy
                  ? "Working…"
                  : modal.kind === "incident_create"
                    ? "Create incident"
                    : modal.kind === "incident_status"
                      ? "Confirm status"
                      : modal.kind === "incident_link"
                        ? "Link investigation"
                        : modal.kind === "incident_note"
                          ? "Add note"
                          : modal.kind === "case_assign"
                            ? "Save assignment"
                            : modal.kind === "case_escalate"
                              ? "Request escalation"
                              : modal.kind === "case_ack"
                                ? "Acknowledge"
                                : modal.kind === "new"
                                  ? "Investigate"
                                  : modal.kind === "proposal"
                                    ? "Request approval"
                                    : modal.kind === "simulate"
                                      ? "Record dry run"
                                      : modal.kind === "revoke"
                                        ? "Revoke request"
                                        : modal.decision === "approved"
                                          ? "Approve"
                                          : "Reject"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
