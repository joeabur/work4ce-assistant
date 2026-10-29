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
type CasePage = { items: Case[]; next_cursor: string | null };
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
type View = "investigations" | "reviews" | "responses" | "integrations";
type Modal =
  | { kind: "new" }
  | { kind: "review"; review: Review; decision: "approved" | "rejected" }
  | { kind: "proposal"; record: Report }
  | { kind: "decision"; proposal: Proposal; decision: "approved" | "rejected" }
  | { kind: "simulate"; proposal: Proposal }
  | { kind: "revoke"; proposal: Proposal };
const labels: Record<string, string> = {
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
      className={`badge ${["completed", "approved", "consumed"].includes(value) ? "positive" : ["pending", "awaiting_review", "queued", "running"].includes(value) ? "attention" : ["failed", "rejected", "review_rejected", "revoked"].includes(value) ? "negative" : "neutral"}`}
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
    selection = useRef(0),
    historyVersion = useRef(0),
    historyBusy = useRef(false),
    createIntent = useRef<{ signature: string; key: string } | null>(null);
  const has = (p: string) => Boolean(me?.permissions.includes(p));
  const logout = useCallback(() => {
    epoch.current++;
    token.current = "";
    createIntent.current = null;
    requests.current.forEach((c) => c.abort());
    requests.current.clear();
    selectedID.current = "";
    selection.current++;
    historyVersion.current++;
    historyBusy.current = false;
    setMe(null);
    setTokenInput("");
    setConnecting(false);
    setCases([]);
    setNextCursor(null);
    setHistoryLoading(false);
    setHistoryLoaded(false);
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
      setHistoryLoading(false);
      setLoading(true);
      try {
        const [items, proposals, connectors, queue, ready] = await Promise.all([
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
      } catch (cause) {
        if (generation === epoch.current && version === historyVersion.current)
          fail(cause);
      } finally {
        if (generation === epoch.current && version === historyVersion.current)
          setLoading(false);
      }
    },
    [request, fail],
  );
  const loadOlder = async () => {
    if (!me || !nextCursor || loading || historyBusy.current) return;
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
  const openCase = useCallback(
    async (id: string) => {
      const generation = epoch.current,
        sequence = ++selection.current;
      selectedID.current = id;
      setSelected(null);
      setDetailLoading(true);
      try {
        const item = await request<Report>(
          `/investigations/${encodeURIComponent(id)}`,
        );
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
      if (generation === epoch.current) fail(cause);
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
  function detail() {
    if (!selected) return null;
    const report = selected.report,
      review = selected.review,
      own =
        cases.find((c) => c.id === selected.id)?.subject === me?.subject ||
        review?.requester === me?.subject,
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
              (item) => item[0] !== "reviews" || has("investigations:review"),
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
                onClick={() => void refresh(me)}
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
            modal.kind === "new"
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
            {modal.kind === "new" ? (
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
