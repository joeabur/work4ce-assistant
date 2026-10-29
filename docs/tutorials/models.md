# Structured model assistance

The model gateway implements part of master specification §11 and Phase 5. It is a constrained planning/quotation workflow, not a complete autonomous SOC analyst. Production remains disabled and the authenticated data realm remains synthetic.

## Modes

| `WORK4CE_REASONING_MODE` | Behavior |
|---|---|
| `deterministic` (default) | Existing durable investigator; no provider calls or model credentials |
| `fixture` | Offline deterministic provider through the same structured gateway, grounding checks and durable usage ledger; reports explicitly identify a fixture |
| `provider` | Explicitly configured HTTPS chat-completions adapter; live interoperability and billing are unverified |

To exercise the offline model path, configure `WORK4CE_REASONING_MODE=fixture` in addition to the normal API authentication, then start the REST service/API and run the usual investigation. No external model key is needed. Reports identify `structured-fixture-v1` and `reasoning.synthetic_fixture=true`; this is not an LLM invocation.

## Optional provider configuration

Configure values securely before choosing provider mode. Never put credentials in source, command histories, reports or chat.

| Variable | Requirement |
|---|---|
| `WORK4CE_MODEL_ENDPOINT` | Explicit trusted HTTPS URL ending `/chat/completions`; no embedded credentials, query or fragment |
| `WORK4CE_MODEL_NAME` | Operator-approved model identifier |
| `WORK4CE_MODEL_API_KEY` | Credential supplied through secure environment configuration |
| `WORK4CE_MODEL_ALLOW_SYNTHETIC_EGRESS` | Must be exactly `true` to authorize sending admitted synthetic payloads to the configured provider |
| `WORK4CE_MODEL_INPUT_PRICE_MICROUSD_PER_MILLION` | Explicit nonnegative integer price per million input tokens, in microUSD |
| `WORK4CE_MODEL_OUTPUT_PRICE_MICROUSD_PER_MILLION` | Explicit nonnegative integer price per million output tokens, in microUSD |

One USD is 1,000,000 microUSD. These prices are operator inputs, not a built-in price catalog or a verified billing feed. Zero must be an intentional price choice. The destination hostname must also be allowed by the environment network policy; proxy-secret bindings must target that exact destination. Do not disable TLS or bypass the platform proxy. No particular provider or missing secret requirement is added automatically.

The adapter uses HTTPX with normal proxy/CA trust and no redirects. Its structured chat-completions fields were checked against the [official OpenAI Python SDK source](https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py): messages, `response_format=json_schema`, and `max_completion_tokens`. This does not establish support for every OpenAI-compatible deployment, every model, Responses API, remote OAuth, or other vendors' wire protocols. New providers can implement the `Provider` contract without changing the investigator.

## Authorization and grounding

The plan may choose only the currently supported, authorized `security.events.search` version `1.0`, with the original literal query and event limit. It cannot expand the query, set tenant/permission context, choose an endpoint, or request response actions. The integration gateway independently authorizes execution after plan validation.

Assessment outputs contain only an inconclusive/review decision and evidence identifiers with exact full summary quotations. The backend validates identifiers, source hashes, exact quotations, duplicate references and supported assessment combinations. It constructs factual report text itself. Invented facts, partial quotations, unknown references, unsupported verdicts, extra fields and tool calls fail closed. A quoted prompt-injection string remains attributed telemetry, never an instruction.

Outgoing payloads contain only the fields needed for these stages: the literal query/limit and approved capability IDs/versions, or evidence IDs/summaries. Tenant identity, credentials, full raw event objects and connector descriptions are not sent. Recognizable credential patterns are rejected before provider calls. This field allowlist and pattern blocker are not comprehensive secret detection, PII redaction or enterprise DLP. Live data sharing remains unsupported.

## Persistent budgets and recovery

| Trusted server variable | Default | Accepted range |
|---|---|---|
| `WORK4CE_MAX_MODEL_CALLS` | `4` | 1–8 provider attempts per workflow |
| `WORK4CE_MAX_MODEL_TOKENS` | `36000` | 1–262144 reserved tokens per workflow |
| `WORK4CE_MAX_MODEL_COST_MICROUSD` | `1000000` | 0–1000000000 reserved microUSD per workflow |

Each call reserves 8192 input plus 512 output tokens and the ceiling cost at configured prices before dispatch. Every retry, failed call and unknown interrupted outcome consumes its reservation; there are no automatic refunds. Completed attempts separately record reported input/output usage and calculated cost. This bounds application admission; it is not a tokenizer or external billing guarantee. Request bytes are conservatively bounded, reported usage must fit the reservation, and provider-reported usage is not independently authenticated billing.

Transient errors can retry twice per stage; permanent failures, invalid schemas and grounding failures do not silently fall back to another model or the deterministic engine. Calls have a five-second timeout, each gateway stage has a ten-second bound, and a process-local circuit opens after three transient failures for 30 seconds. The investigator's existing worker/deadline bounds remain authoritative. Token reservations can be exhausted before the call count limit.

Migration `0003_models` stores attempts, usage, validated cached results and reasoning configuration. Route/model/prompt/schema/prices/limits are fingerprinted, excluding credentials. Changing mode or configuration cannot silently reinterpret an existing workflow. Credential rotation alone does not alter the fingerprint. Existing version-2 deterministic idempotency keys remain compatible.

Cached plans and assessments are bound to tenant, subject, workflow, stage, input hash and configuration hash, and are revalidated before reuse. Workflow leases, deadlines and cancellation fence result commits. A crash before result commit may repeat a paid inference within the remaining reservation budget; a completed cached result is reused. Evidence checkpoint recovery still preserves original attribution and identifiers.

The ledger is local application accounting, not a tamper-resistant billing service. Authentication, database operations, live-provider validation, independent AI evaluations, broader reasoning, human review and response approval requirements retain the limitations recorded in release readiness.
