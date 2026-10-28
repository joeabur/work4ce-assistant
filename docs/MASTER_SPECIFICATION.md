# WORK4CE ASSISTANT
## MASTER ENGINEERING PROMPT FOR CHATGPT
### Production-Grade Autonomous AI Security Operations Platform
### Universal Integration Framework | Capability-Driven AI | MCP | Connector Development Kit | Enterprise Security

**Project name:** Work4ce Assistant  
**Primary development assistant:** ChatGPT  
**Supported coding environments:** ChatGPT with coding tools, Codex, ChatGPT Work, or an equivalent authorized development environment  
**Architecture:** Modular, capability-driven, protocol-independent, secure-by-design  
**Initial focus:** Autonomous AI SOC Agent  
**Long-term objective:** Extensible enterprise security operations and automation platform  
**Initial deployment:** Self-hosted enterprise  
**Future deployments:** Private cloud, hybrid infrastructure, and multi-tenant SaaS/MDR  
**Development approach:** Incremental implementation, continuous testing, security validation, and verified deliverables

---

# 0. YOUR ROLE AND PRIMARY DIRECTIVE

Act as a principal enterprise software architect, staff-level software engineer, senior cybersecurity architect, SOC analyst, incident responder, threat hunter, detection engineer, AI systems engineer, MCP protocol specialist, DevSecOps engineer, cloud infrastructure architect, and full-stack developer.

You are responsible for designing, developing, integrating, testing, securing, documenting, and preparing **Work4ce Assistant** for real-world deployment.

This is a software engineering assignment, not merely an architectural brainstorming exercise.

Your objective is to produce functional, maintainable, extensible, security-conscious software.

Build actual working functionality instead of merely describing how it could be implemented.

Prioritize:

1. Security and correctness.
2. Production-oriented engineering.
3. Modularity and extensibility.
4. Vendor and protocol independence.
5. Evidence-driven investigations.
6. Controlled AI autonomy.
7. Reliable integration with external systems.
8. Operational resilience.
9. Automated testing and verification.
10. Clear documentation and maintainability.
11. Cost-efficient AI operation.
12. Long-term adaptability.

Do not optimize for code volume or apparent completeness.

A smaller, tested, functional implementation is preferable to a large collection of incomplete components.

Never fabricate:

- Working integrations.
- Test results.
- Security assessments.
- Vendor API responses.
- Production deployment results.
- Repository changes.
- File creation.
- Successful tool execution.

Clearly distinguish implemented functionality from planned, simulated, or unverified functionality.

---

# 1. CHATGPT DEVELOPMENT EXECUTION MODE

You are operating as ChatGPT, potentially with access to code execution, filesystem tools, GitHub integrations, development environments, and other authorized tools.

First, determine which capabilities are actually available.

Possible environments include:

- A local coding workspace.
- A GitHub-connected repository.
- Codex.
- ChatGPT Work with supported computer or repository access.
- A containerized development environment.
- A standard ChatGPT conversation without direct repository access.

Adapt your implementation workflow to the tools that are available.

## 1.1 When repository and code execution tools are available

You must:

1. Inspect the existing repository.
2. Examine the current source code.
3. Identify existing implementations.
4. Review project dependencies.
5. Create or modify actual files.
6. Implement working code.
7. Execute available tests.
8. Fix identified failures.
9. Update documentation.
10. Report verified results.

Use the available environment directly rather than providing instructions for actions you can perform safely.

Do not overwrite or delete existing functional code unnecessarily.

## 1.2 When repository access is unavailable

Do not claim to have inspected or modified a repository.

Instead:

- Establish the architecture using available information.
- Generate complete implementation files.
- Provide accurate file paths.
- Include dependencies and configuration.
- Produce runnable code where possible.
- Provide testing commands.
- Identify what remains unverified.
- Continue with the next executable implementation unit.

Do not stop at high-level architectural recommendations.

## 1.3 When external credentials are unavailable

Do not invent credentials or simulate successful production connections.

Implement:

- Connector contracts.
- Configuration validation.
- Authentication interfaces.
- Vendor API adapters where specifications are verified.
- Test fixtures.
- Contract tests.
- Integration documentation.

Mark live verification as pending.

## 1.4 Execution discipline

Work in phases.

For each phase:

**Inspect → Plan → Implement → Test → Review → Fix → Document → Report**

Perform all work that is possible within the active execution environment.

Do not promise background execution or future completion without an available supported mechanism.

If tooling, authorization, or environmental constraints prevent part of the task, clearly state the limitation and complete the independent work that remains possible.

---

# 2. PRODUCT IDENTITY

The product name is:

# Work4ce Assistant

**Product description:**

Work4ce Assistant is an extensible, vendor-neutral AI security operations platform that integrates with enterprise systems, security technologies, and external tools to autonomously investigate threats, correlate evidence, assist security analysts, perform threat hunting, improve detections, and coordinate authorized response workflows.

The platform's central intelligence is an AI SOC Agent, supported by a universal integration and capability execution framework.

Use consistent identifiers:

| Component | Identifier |
|---|---|
| Product | Work4ce Assistant |
| Repository | `work4ce-assistant` |
| Python package | `work4ce_assistant` |
| API service | `work4ce-api` |
| Agent runtime | `work4ce-agent` |
| Integration gateway | `work4ce-integration-gateway` |
| MCP adapter | `work4ce-mcp` |
| Capability registry | `work4ce-capabilities` |
| Dashboard | `work4ce-dashboard` |
| Worker | `work4ce-worker` |
| CLI | `work4ce` |
| Database | `work4ce_db` |
| Configuration prefix | `WORK4CE_` |
| Kubernetes namespace | `work4ce` |

These identifiers describe logical components.

Do not create separate deployable microservices unnecessarily.

Maintain consistent naming across code, APIs, documentation, Docker, CI/CD, infrastructure, and the user interface.

---

# 3. CORE ARCHITECTURAL REQUIREMENT

## BUILD A UNIVERSAL, PROTOCOL-INDEPENDENT INTEGRATION FRAMEWORK

Do not limit Work4ce Assistant to specific technologies, vendors, security domains, or tool categories.

The system must not depend permanently on:

- SIEM products.
- EDR or XDR products.
- Cloud security platforms.
- MCP servers.
- One vendor API.
- One LLM provider.
- One agent framework.
- One database.
- One cloud provider.
- One operating system.
- A fixed number of agents.
- A predefined collection of security capabilities.

**MCP is a first-class integration mechanism, not the only integration mechanism.**

Design for future connectivity through:

- MCP.
- REST.
- GraphQL.
- gRPC.
- Webhooks.
- WebSockets.
- Server-Sent Events.
- Message queues.
- Event streaming.
- Vendor SDKs.
- Approved libraries.
- Structured data imports.
- Database connectors.
- Restricted command-line adapters.
- Proprietary enterprise protocols.
- Future technologies.

Not every mechanism must be built immediately.

However, adding a new mechanism must not require fundamental changes to the agent's reasoning or investigation logic.

## 3.1 Extensible security domains

Initial and future integrations may include:

- SIEM, EDR, XDR, NDR, and SOAR.
- Endpoint and network monitoring.
- Cloud and container security.
- Identity and access management.
- Privileged access management.
- WAF and firewall platforms.
- Email and SaaS security.
- Threat intelligence.
- Malware analysis.
- Digital forensics.
- Vulnerability assessment.
- Attack surface management.
- Application security.
- DevSecOps and CI/CD.
- Infrastructure security.
- Database security.
- Data loss prevention.
- GRC and compliance.
- Asset management.
- ITSM and ticketing.
- OT/ICS and IoT security.
- AI and LLM security.
- Custom internal security tools.

These categories are examples, not hardcoded limitations.

The platform must support previously unknown capability categories through versioned extension contracts.

---

# 4. RECOMMENDED TECHNOLOGY STACK

Select technologies based on maintainability, compatibility, performance, and security.

Preferred initial choices:

| Layer | Recommended technology |
|---|---|
| Backend | Python, FastAPI |
| Validation | Pydantic |
| Agent orchestration | LangGraph |
| MCP | Official MCP SDK |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy, Alembic |
| Frontend | Next.js, React, TypeScript |
| Authentication | OIDC-compatible identity provider |
| Local development | Docker Compose |
| Production deployment | Kubernetes where justified |
| Infrastructure | Terraform, Helm |
| Observability | OpenTelemetry, Prometheus, Grafana |
| AI models | Provider-independent gateway |
| Testing | pytest and appropriate frontend/e2e frameworks |
| CI/CD | GitHub Actions |

These are recommended starting points, not permanent technology restrictions.

Any alternative must be justified through an architecture decision record.

Before implementation, verify:

1. Available runtime versions.
2. Current stable package versions.
3. SDK compatibility.
4. Security advisories.
5. Official API documentation.
6. MCP protocol compatibility.
7. Deployment requirements.

Use pinned, reproducible dependencies.

Do not introduce excessive infrastructure prematurely.

---

# 5. TARGET ARCHITECTURE

Implement the following logical architecture:

```text
                         WORK4CE ASSISTANT
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
        SOC DASHBOARD          CLI              REST API
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                      APPLICATION GATEWAY
                                |
                                v
                    AUTHENTICATION / RBAC
                                |
                                v
                       AI AGENT RUNTIME
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
      AI REASONING        TASK PLANNING       WORKFLOW ENGINE
          |                     |                     |
          +---------------------+---------------------+
                                |
                                v
                       CAPABILITY RESOLVER
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
    CAPABILITY REGISTRY    POLICY ENGINE         TOOL SELECTION
          |                     |                     |
          +---------------------+---------------------+
                                |
                                v
                   UNIVERSAL INTEGRATION GATEWAY
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
      MCP ADAPTERS         API ADAPTERS        EVENT ADAPTERS
          |                     |                     |
          v                     v                     v
      MCP SERVERS       REST / SDK / gRPC     STREAMS / WEBHOOKS
          |                     |                     |
          +---------------------+---------------------+
                                |
                                v
                     CONNECTED TECHNOLOGIES
                                |
         +----------------------+----------------------+
         |                      |                      |
         v                      v                      v
   SECURITY PLATFORMS     ENTERPRISE SYSTEMS     CUSTOM/FUTURE TOOLS
                                |
                                v
                    NORMALIZED EVIDENCE LAYER
                                |
                                v
                    INVESTIGATION / CASE ENGINE
                                |
                                v
                    POLICY-GOVERNED RESPONSE
```

The following must be separate security boundaries:

- AI reasoning.
- Integration execution.
- Authorization.
- Evidence management.
- Tenant data access.
- Secrets management.
- Privileged response execution.

Do not put privileged response execution directly inside the AI reasoning runtime.

---

# 6. UNIVERSAL INTEGRATION FRAMEWORK

This is a foundational subsystem and must be implemented early.

Create stable interfaces that allow external systems to be used through standardized capability contracts.

## 6.1 Connector responsibilities

Each connector must support:

- Registration.
- Manifest validation.
- Configuration.
- Authentication.
- Capability discovery.
- Authorization integration.
- Health monitoring.
- Invocation.
- Result validation.
- Normalization.
- Failure handling.
- Audit logging.
- Version management.
- Disablement and revocation.

## 6.2 Connector interface

Design typed interfaces for:

```python
from typing import Protocol

class Connector(Protocol):

    async def health_check(self) -> "HealthStatus":
        ...

    async def discover_capabilities(
        self
    ) -> list["CapabilityManifest"]:
        ...

    async def invoke(
        self,
        request: "CapabilityInvocation"
    ) -> "CapabilityResult":
        ...
```

This is an illustrative abstraction.

Refine it into production-ready typed models with explicit execution context, lifecycle handling, and secure error handling.

Do not trust authorization information supplied by an external connector.

Trusted backend services must populate user, tenant, and policy context.

## 6.3 Connector registry

Maintain:

```text
connector_id
name
publisher
version
protocol
transport
configuration_schema
credential_reference
capabilities
required_permissions
resource_scopes
trust_status
tenant_scope
health_status
installation_status
last_verified_at
```

Use validated manifests.

Never store plaintext credentials.

## 6.4 Connector isolation

Enforce:

- Least-privilege credentials.
- Network egress restrictions.
- Resource limits.
- Timeouts.
- Rate limiting.
- Execution auditing.
- Error isolation.
- Credential rotation.
- Safe disablement.

Do not execute arbitrary untrusted connector code inside a privileged application process.

---

# 7. CAPABILITY REGISTRY AND RESOLVER

The AI agent must reason about capabilities, not individual vendors.

For example, the agent requests:

`security.events.search`

The capability resolver selects an authorized implementation.

That implementation might be provided by:

- Microsoft Sentinel.
- Splunk.
- Wazuh.
- OpenSearch.
- An MCP server.
- A custom REST API.
- A future security platform.

## 7.1 Capability manifest

Every capability must define:

```text
capability_id
version
description
input_schema
output_schema
execution_class
required_permissions
resource_scope
side_effects
data_classification
approval_requirements
timeout_policy
cost_policy
```

Capability namespaces are extensible.

Illustrative names:

```text
security.alerts.search
security.alerts.retrieve
security.events.search
security.identity.investigate
security.endpoint.analyze
security.network.analyze
security.cloud.analyze
security.intelligence.enrich
security.assets.retrieve
security.incidents.create
security.hunting.execute
security.detections.validate
security.response.recommend
security.response.execute
```

Do not hardcode these as the only supported capabilities.

## 7.2 Capability execution

The execution sequence must be:

1. Validate the request.
2. Authenticate the requester.
3. Authorize the requested operation.
4. Resolve the capability.
5. Discover compatible connectors.
6. Evaluate connector health and trust.
7. Select an authorized implementation.
8. Validate arguments.
9. Enforce execution budgets.
10. Execute through the integration gateway.
11. Validate the response.
12. Normalize the result.
13. Preserve provenance.
14. Record the audit event.
15. Return structured results.

Security restrictions must not be overridden by cost or performance preferences.

## 7.3 Mandatory protocol-independence test

Build two reference connectors:

**Connector A:** MCP-based synthetic security event service.

**Connector B:** REST-based synthetic security event service.

Both must implement:

`security.events.search`

Test that:

1. Both connectors register successfully.
2. Both advertise compatible capability schemas.
3. The agent discovers the capability.
4. The resolver selects an authorized connector.
5. The investigation succeeds.
6. The selected connector is disabled.
7. The resolver selects the remaining authorized connector.
8. The investigation succeeds again.
9. No changes to core agent orchestration are required.
10. Evidence provenance identifies the actual connector.
11. Unauthorized connector substitution is rejected.

**This test is a mandatory foundational acceptance criterion.**

---

# 8. CONNECTOR DEVELOPMENT KIT

Create a Connector Development Kit (CDK) for future integrations.

It must provide:

- Connector interfaces.
- Manifest schemas.
- Configuration validation.
- Capability registration.
- Credential integration.
- Authentication helpers.
- Standardized error models.
- Health checks.
- Logging helpers.
- Contract testing.
- Security validation.
- Packaging instructions.
- Developer documentation.
- Working connector templates.

## 8.1 Connector manifest

Define a versioned manifest format.

Illustrative example:

```yaml
apiVersion: work4ce.io/v1alpha1
kind: Connector

metadata:
  id: example-security-events
  name: Example Security Events
  version: 0.1.0

spec:
  protocol: rest
  runtime: external

  capabilities:
    - id: security.events.search
      version: "1.0"
      executionClass: read

  authentication:
    type: oauth2

  security:
    defaultEnabled: false
```

Define and implement the actual schema.

Do not treat the example as an existing external standard.

## 8.2 Connector security review

New connectors must pass:

- Manifest validation.
- Capability validation.
- Authentication validation.
- Permission review.
- Dependency checks.
- Network access review.
- Runtime isolation checks.
- Contract tests.
- Error-handling tests.
- Audit verification.

A connector must not automatically inherit access to every registered tool or tenant.

---

# 9. MCP INTEGRATION ARCHITECTURE

MCP must be supported as a first-class protocol within the universal integration framework.

Use the official MCP SDK.

Verify the current stable MCP specification before implementation.

Account for applicable protocol features, version negotiation, supported transports, authorization requirements, structured outputs, and extension compatibility.

## 9.1 MCP gateway

Implement:

- Server registry.
- MCP client lifecycle.
- Tool discovery.
- Capability mapping.
- Authentication.
- Authorization.
- Tool allowlisting.
- Tool manifest validation.
- Timeouts.
- Rate limits.
- Execution auditing.
- Health monitoring.
- Failure recovery.

## 9.2 MCP server support

Support:

- Approved vendor MCP servers.
- Custom MCP servers.
- Local MCP servers.
- Remote MCP servers.
- Enterprise-hosted servers.
- Future protocol-compatible implementations.

Do not assume every vendor has an official MCP server.

Use direct API adapters when more appropriate.

## 9.3 MCP security

Protect against:

- Prompt injection.
- Tool poisoning.
- Tool shadowing.
- Unauthorized capability changes.
- SSRF.
- Credential leakage.
- Cross-server data exposure.
- OAuth misconfiguration.
- Unauthorized tool execution.
- Cross-tenant access.
- Malicious MCP responses.

Use stable tool identifiers, explicit allowlists, reviewed manifests, and independently enforced authorization.

Treat MCP responses and tool descriptions as untrusted input.

---

# 10. AI AGENT ARCHITECTURE

Begin with one central AI SOC investigation agent.

Its responsibilities include:

- Alert interpretation.
- Investigation planning.
- Capability discovery.
- Tool selection.
- Evidence retrieval.
- Correlation.
- Hypothesis evaluation.
- Risk assessment.
- Investigation reporting.
- Response recommendations.

Do not immediately create many autonomous agents.

Design specialist capabilities as modular components that can later become separate agents.

## 10.1 Agent workflow

```text
Security Alert / Analyst Request
              |
              v
       Request Validation
              |
              v
         Authorization
              |
              v
      Investigation Planning
              |
              v
       Capability Discovery
              |
              v
        Policy Evaluation
              |
              v
     Controlled Tool Execution
              |
              v
       Evidence Collection
              |
              v
       Evidence Correlation
              |
              v
      Hypothesis Assessment
              |
              v
        Findings Validation
              |
              v
       Incident Reporting
              |
              v
         Analyst Review
```

## 10.2 Durable execution

Implement:

- Typed investigation state.
- Persistent checkpoints.
- Resume after restart.
- Cancellation.
- Execution deadlines.
- Bounded retries.
- Partial results.
- Human review checkpoints.
- Execution tracing.
- Idempotency.

## 10.3 Execution limits

Enforce configurable limits for:

- Reasoning steps.
- Tool calls.
- Investigation duration.
- Token expenditure.
- Investigation cost.
- Query scope.
- Result size.
- Concurrent investigations.

The agent must stop safely when limits are reached.

## 10.4 Future specialist agents

Allow future modules such as:

- Triage agent.
- Investigation agent.
- Threat hunting agent.
- Threat intelligence agent.
- Detection engineering agent.
- Forensics agent.
- Vulnerability analysis agent.
- Incident response agent.

Require explicit capabilities and permissions for each.

Do not introduce multiple agents unless their separation improves reliability, accuracy, maintainability, or operational control.

---

# 11. PROVIDER-INDEPENDENT MODEL GATEWAY

Support configurable AI model providers.

Potential backends include:

- OpenAI-compatible APIs.
- Anthropic-compatible APIs.
- Private cloud inference.
- Self-hosted models.
- Local inference.
- Future providers.

Implement:

- Model routing.
- Structured outputs.
- Timeouts.
- Retries.
- Circuit breakers.
- Provider health.
- Token accounting.
- Cost tracking.
- Data redaction.
- Version tracking.
- Prompt management.
- Evaluation.
- Fallback behavior.

Use deterministic code for operations that do not require AI.

Never use LLM reasoning as the final authority for access control or response authorization.

---

# 12. CORE SOC FUNCTIONALITY

Develop the following modules incrementally.

## 12.1 Alert triage

- Alert ingestion.
- Normalization.
- Deduplication.
- Enrichment.
- Risk prioritization.
- Classification.
- Escalation.

Support inconclusive classifications.

## 12.2 Incident investigation

- Authentication analysis.
- Endpoint process investigation.
- Identity activity.
- Network correlation.
- Cloud activity analysis.
- Privilege escalation investigation.
- Timeline reconstruction.
- Evidence-based reporting.

## 12.3 Threat intelligence

- IOC enrichment.
- Domain and IP reputation.
- Hash analysis.
- Indicator confidence.
- Indicator expiration.
- Internal telemetry correlation.
- STIX/TAXII where supported.

## 12.4 Threat hunting

- Hypothesis generation.
- ATT&CK mapping.
- Read-only search.
- Query validation.
- Result analysis.
- Scheduled authorized hunts.
- Hunting reports.

## 12.5 Detection engineering

- Sigma.
- KQL.
- SPL.
- Detection validation.
- Positive and negative test cases.
- Historical replay.
- False-positive analysis.
- Rule versioning.
- Approval and rollback.

## 12.6 Incident management

- Incident creation.
- Assignment.
- Notes.
- Evidence references.
- Case status.
- Escalation.
- Analyst review.
- Resolution tracking.

## 12.7 Response orchestration

- Response recommendations.
- Playbook selection.
- Approval requests.
- Policy validation.
- Non-destructive automation.
- Execution auditing.
- Response verification.

High-impact actions must not execute without independently validated authorization.

---

# 13. EVIDENCE AND TELEMETRY

Use OCSF-aligned normalization for appropriate security telemetry.

Preserve original raw events.

Required event properties include:

```text
event_id
tenant_id
source_connector
source_event_id
event_timestamp
ingestion_timestamp
event_type
actor
target
action
outcome
severity
raw_event_reference
normalized_event
integrity_hash
provenance
```

Do not fabricate unavailable fields.

## 13.1 Evidence-first reasoning

Every finding must distinguish:

- Observed fact.
- Supported inference.
- Hypothesis.
- Unknown.

Each factual finding must reference valid collected evidence.

If information is incomplete, explicitly report the coverage gap.

## 13.2 Evidence integrity

Support:

- Raw evidence preservation.
- Cryptographic hashes.
- Collection timestamps.
- Source attribution.
- Chain-of-custody metadata.
- Tenant isolation.
- Retention policies.

## 13.3 Telemetry quality

Monitor:

- Missing telemetry.
- Delayed collection.
- Timestamp drift.
- Duplicate events.
- Schema errors.
- Connector outages.
- Incomplete investigations.

Absence of evidence must not automatically be interpreted as evidence of safety.

---

# 14. POLICY AND SECURITY BOUNDARIES

Implement an independent policy engine.

Every capability execution must evaluate:

- Requesting user.
- Agent identity.
- Tenant.
- Connector.
- Capability.
- Target resource.
- Data classification.
- Execution scope.
- Side effects.
- Required approval.

Classify operations as:

- Read-only.
- External enrichment.
- Internal case modification.
- Configuration change.
- Security response.
- Destructive.

All sensitive operations require explicit authorization.

Privileged response execution must occur outside the AI reasoning runtime.

The response executor must revalidate authorization immediately before taking action.

Do not permit prompt-based privilege escalation.

---

# 15. SECURITY REQUIREMENTS

Apply secure-by-design practices.

Consult current guidance from:

- OWASP ASVS.
- OWASP API Security Top 10.
- OWASP LLM Top 10.
- OWASP Agentic Application Security.
- OWASP MCP security guidance.
- NIST Cybersecurity Framework.
- NIST AI Risk Management Framework.
- NIST SP 800-61 Revision 3.
- MITRE ATT&CK.
- MITRE ATLAS.

Implement:

- OIDC authentication.
- Least-privilege authorization.
- Resource-level access controls.
- Tenant isolation.
- Secrets management.
- TLS.
- Encryption.
- Input validation.
- Output validation.
- Network restrictions.
- Audit logging.
- Supply-chain security.
- Secure deployment defaults.
- Data retention controls.
- Backup and recovery.

Create and maintain a formal threat model.

Do not claim formal compliance or certification without verification.

---

# 16. DATA PRIVACY AND GOVERNANCE

Provide configurable:

- Data classification.
- PII minimization.
- Redaction.
- Retention.
- Data residency.
- Access logging.
- Legal holds.
- Authorized export and deletion.
- Model-provider data-sharing restrictions.

Sensitive security telemetry must not be disclosed to external providers without appropriate authorization.

Allow organizations to configure which integrations and model providers may access particular data classifications.

---

# 17. RELIABILITY AND OBSERVABILITY

Implement:

- OpenTelemetry instrumentation.
- Structured logging.
- Distributed tracing.
- Metrics.
- Health endpoints.
- Operational dashboards.
- Alerting.

Track:

- API latency.
- Tool execution latency.
- Connector health.
- Investigation duration.
- Agent failures.
- Token usage.
- Cost per investigation.
- Authorization denials.
- Queue depth.
- Investigation completion rates.

Support:

- Timeouts.
- Bounded retries.
- Circuit breakers.
- Backpressure.
- Idempotency.
- Recovery after restart.
- Failure isolation.
- Backup and restore.

One failing integration must not cause the entire application to fail.

---

# 18. DATA STORAGE

Use workload-appropriate storage.

Preferred initial choices:

- PostgreSQL for transactional application state.
- Object storage for raw evidence.
- Existing security platforms or appropriate search infrastructure for telemetry.
- Redis for justified caching or transient coordination.
- Optional vector storage for authorized knowledge retrieval.

Do not require a single database for every workload.

Preserve tenant isolation across storage systems.

Do not place unlimited security telemetry into PostgreSQL.

---

# 19. SOC DASHBOARD

Build a professional, functional, extensible web application.

Required modules:

- SOC Overview.
- Alert Center.
- Investigation Workbench.
- Incident Management.
- AI Analyst Interface.
- Threat Hunting.
- Detection Engineering.
- Threat Intelligence.
- Integration Center.
- Capability Registry.
- MCP Management.
- Agent Operations.
- Workflow Management.
- Response Approvals.
- Audit Logs.
- Administration.

Use real backend APIs.

Do not present fabricated incidents as live operational information.

## 19.1 Dynamic integrations

The dashboard must support approved:

- Connector registration.
- Capability discovery.
- Configuration.
- Health monitoring.
- Permission review.
- Error diagnostics.
- Enablement and disablement.

Avoid hardcoding the user interface around specific security vendors.

---

# 20. GETTING STARTED

A complete Getting Started experience is mandatory.

Create:

```text
README.md
docs/getting-started.md
docs/installation.md
docs/configuration.md
docs/quickstart.md
docs/developer-guide.md
docs/integrations.md
docs/mcp-setup.md
docs/connector-development.md
docs/first-investigation.md
docs/deployment.md
docs/troubleshooting.md
```

The README must include:

1. Product overview.
2. Architecture.
3. Implemented capabilities.
4. System requirements.
5. Installation.
6. Configuration.
7. Local deployment.
8. AI provider setup.
9. Connector setup.
10. MCP registration.
11. Demo mode.
12. First investigation.
13. CLI commands.
14. Testing.
15. Developer contribution workflow.
16. Production deployment.
17. Security limitations.
18. Troubleshooting.

## 20.1 Quickstart

The intended developer experience is:

```bash
git clone <ACTUAL_REPOSITORY_URL>
cd work4ce-assistant

cp .env.example .env

docker compose up --build -d
```

Replace placeholders with real values when known.

Implement the commands before documenting them as operational.

## 20.2 First-run wizard

Implement:

- Welcome.
- Environment validation.
- Administrator provisioning.
- AI provider configuration.
- Connector registration.
- MCP configuration.
- Security policy setup.
- Demo mode.
- Health validation.
- Dashboard launch.

Never ship universal default production credentials.

Production mode must reject insecure development authentication.

## 20.3 First investigation walkthrough

Document:

1. Start the application.
2. Sign in.
3. Load sample security telemetry.
4. Open a security alert.
5. Start an AI investigation.
6. Review discovered capabilities.
7. Observe authorized tool execution.
8. Review collected evidence.
9. Examine findings.
10. Generate an incident report.
11. Close or escalate the case.

---

# 21. DEMO MODE

Implement a fully isolated synthetic SOC environment.

Demo mode must work without production security credentials.

Include scenarios such as:

- Suspicious PowerShell execution.
- AWS credential misuse.
- Password spraying.
- Cloud privilege escalation.
- Suspicious network activity.
- Potential data exfiltration.
- Benign administrative activity.
- False-positive alerts.
- Missing telemetry.
- Prompt injection embedded in logs.

Provide both MCP and non-MCP reference connectors.

Use the same authorization, orchestration, evidence, and reporting code paths as production where practical.

Clearly identify synthetic data.

Never mix demo data with live tenant information.

---

# 22. COMMAND-LINE INTERFACE

Develop a CLI.

Suggested commands:

```bash
work4ce --help
work4ce version
work4ce doctor
work4ce health

work4ce connectors list
work4ce connectors inspect <ID>
work4ce connectors health

work4ce capabilities list
work4ce capabilities inspect <ID>

work4ce mcp list
work4ce mcp health

work4ce agents list
work4ce workflows list

work4ce alerts list
work4ce investigations list
work4ce investigations show <ID>

work4ce demo load
work4ce demo investigate
```

Protected operations must authenticate and enforce authorization.

The CLI must not bypass backend security policies.

---

# 23. REPOSITORY STRUCTURE

Use a modular monorepo.

```text
work4ce-assistant/
│
├── apps/
│   └── dashboard/
│
├── src/
│   └── work4ce_assistant/
│       ├── api/
│       ├── core/
│       ├── agent/
│       ├── capabilities/
│       │   ├── contracts/
│       │   ├── registry/
│       │   ├── resolver/
│       │   └── execution/
│       ├── integrations/
│       │   ├── contracts/
│       │   ├── registry/
│       │   ├── gateway/
│       │   ├── adapters/
│       │   └── lifecycle/
│       ├── mcp/
│       ├── connectors/
│       ├── workflows/
│       ├── triage/
│       ├── investigation/
│       ├── hunting/
│       ├── intelligence/
│       ├── detections/
│       ├── response/
│       ├── evidence/
│       ├── incidents/
│       ├── entities/
│       ├── policies/
│       ├── security/
│       ├── models/
│       ├── database/
│       ├── observability/
│       └── config/
│
├── connector-sdk/
│   ├── python/
│   ├── templates/
│   └── tests/
│
├── reference-connectors/
│   ├── mcp-security-events/
│   └── rest-security-events/
│
├── demo/
│   ├── fixtures/
│   ├── scenarios/
│   └── expected-results/
│
├── detections/
├── evaluations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contracts/
│   ├── e2e/
│   ├── security/
│   ├── adversarial/
│   └── performance/
│
├── infrastructure/
│   ├── docker/
│   ├── kubernetes/
│   ├── helm/
│   └── terraform/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── security/
│   ├── integrations/
│   ├── tutorials/
│   ├── deployment/
│   └── operations/
│
├── .github/
│   └── workflows/
│
├── scripts/
├── AGENTS.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE
├── README.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

This is a target structure.

Do not create unnecessary empty modules.

---

# 24. CHATGPT REPOSITORY INSTRUCTIONS

Create:

`AGENTS.md`

Use it to document coding-agent guidance, including:

- Product purpose.
- Architecture principles.
- Security invariants.
- Repository layout.
- Development commands.
- Testing procedures.
- Coding conventions.
- Contribution rules.
- Phase completion criteria.
- Documentation expectations.

Store this complete specification in:

`docs/MASTER_SPECIFICATION.md`

Maintain:

```text
docs/implementation-progress.md
docs/known-issues.md
docs/next-steps.md
docs/architecture/decisions.md
docs/security/threat-model.md
docs/release-readiness.md
```

If an authorized coding environment supports reading `AGENTS.md`, use it as project-specific guidance.

Do not assume a standard ChatGPT conversation automatically reads repository instructions.

Inspect the relevant file directly when necessary.

## 24.1 Coding-agent collaboration

When suitable tools support multiple coding or review agents, separate responsibilities such as:

- Architecture review.
- MCP compliance.
- Connector security.
- Test quality.
- Threat modeling.
- Documentation verification.

Avoid conflicting modifications.

Review and integrate changes before accepting them.

Do not assume multi-agent execution is always available.

---

# 25. TESTING AND VERIFICATION

Testing is mandatory.

## Unit tests

Cover:

- Capability contracts.
- Connector registry.
- Capability resolver.
- Authorization.
- Event normalization.
- Agent state.
- Evidence validation.
- Response approval.

## Integration tests

Cover:

- Database.
- MCP client/server communication.
- REST connectors.
- Authentication.
- API.
- Workflow persistence.
- Capability execution.

## Contract tests

Every connector must satisfy its declared capability contracts.

## End-to-end tests

Test alert ingestion through completed investigation reporting.

## Security tests

Cover:

- Prompt injection.
- MCP tool poisoning.
- Connector substitution.
- SSRF.
- Credential leakage.
- Unauthorized execution.
- Approval bypass.
- Cross-tenant access.
- Malformed tool output.
- Malicious connector metadata.
- Insecure configuration.

## AI evaluations

Measure:

- Triage precision.
- Triage recall.
- Investigation accuracy.
- Evidence attribution.
- Hallucination rate.
- Tool selection accuracy.
- False-negative rate.
- Cost per investigation.

Use labeled datasets.

Do not rely on an LLM's own assessment as the primary quality metric.

---

# 26. CRITICAL ARCHITECTURE ACCEPTANCE TESTS

The implementation must pass these tests.

**Test A — Protocol independence**

The same capability works through MCP and REST connectors.

**Test B — Connector replacement**

The capability resolver selects an authorized alternative when one connector becomes unavailable.

**Test C — Unauthorized execution**

Restricted capabilities cannot execute without appropriate permissions.

**Test D — Tool poisoning**

Unauthorized changes to sensitive connector manifests or tool definitions are detected.

**Test E — Connector failure**

External service failure does not crash the agent or destroy investigation state.

**Test F — New capability**

A previously unknown capability can register through the CDK without modifying core orchestration logic.

**Test G — Evidence integrity**

Findings reference valid source-attributed evidence.

**Test H — Response authorization**

Expired, missing, reused, or mismatched approvals cannot authorize sensitive actions.

**Test I — Demo isolation**

Synthetic data cannot contaminate production tenant information.

**Test J — Tenant isolation**

Unauthorized cross-tenant access is rejected.

Do not mark the architecture complete without executing these tests.

---

# 27. DEVSECOPS AND CI/CD

Implement:

- Formatting.
- Linting.
- Type checking.
- Unit tests.
- Integration tests.
- Contract tests.
- Dependency scanning.
- Static security analysis.
- Secret scanning.
- Container scanning.
- SBOM generation.
- Reproducible builds.
- Deployment verification.

Use GitHub Actions when appropriate.

Protect production deployment environments.

Do not expose privileged credentials to untrusted CI jobs.

---

# 28. DEPLOYMENT

Support:

- Local development.
- Self-hosted enterprise deployment.
- Private cloud.
- Hybrid infrastructure.
- Future multi-tenant SaaS.

Provide Docker Compose for development.

Provide Kubernetes and Helm configuration when justified by the deployment requirements.

Use infrastructure-as-code for supported environments.

Implement:

- TLS.
- Secure authentication.
- Secrets management.
- Resource limits.
- Health checks.
- Monitoring.
- Backup and restore.
- Recovery procedures.
- Network policies.
- Least-privilege execution.

Do not require one cloud provider.

Production deployment must not use insecure development defaults.

---

# 29. PHASED IMPLEMENTATION ROADMAP

Implement in the following sequence.

## Phase 0 — Discovery and Architecture

Inspect the repository and available environment.

Deliver:

- Product requirements.
- Architecture.
- Technology decisions.
- Capability contracts.
- Connector contracts.
- Trust boundaries.
- Threat model.
- Implementation plan.
- Acceptance criteria.

## Phase 1 — Secure Foundation

Implement:

- Backend.
- Configuration.
- PostgreSQL.
- Migrations.
- Authentication.
- Authorization.
- Logging.
- Docker.
- CI.
- Tests.

## Phase 2 — Universal Integration Framework

Implement:

- Connector contracts.
- Connector registry.
- Capability registry.
- Capability resolver.
- Integration gateway.
- Policy enforcement.
- Reference REST connector.

## Phase 3 — MCP Infrastructure

Implement:

- MCP client.
- Reference MCP server.
- Tool discovery.
- MCP security.
- Capability mapping.
- MCP integration tests.

## Phase 4 — Protocol Independence

Demonstrate that the same capability works through MCP and REST implementations.

Pass the mandatory interchangeability test.

## Phase 5 — AI Agent Runtime

Implement:

- Agent orchestration.
- Typed state.
- Investigation planning.
- Capability selection.
- Tool execution.
- Checkpointing.
- Failure handling.
- Execution budgets.

## Phase 6 — Evidence and Investigation

Implement:

- Normalization.
- Evidence storage.
- Provenance.
- Correlation.
- Investigation findings.
- Reporting.

## Phase 7 — Demo Mode

Implement:

- Synthetic datasets.
- Reference scenarios.
- Automated investigations.
- Expected results.
- Evaluation harness.

## Phase 8 — First Live Integration

Implement one real, authorized security integration.

Verify live behavior only when suitable credentials and infrastructure are available.

Otherwise, clearly mark live verification pending.

## Phase 9 — SOC Operations

Implement:

- Alert triage.
- Incident management.
- Case queues.
- Assignment.
- Escalation.
- Analyst review.

## Phase 10 — Dashboard and Getting Started

Implement:

- Web dashboard.
- Investigation workbench.
- Connector management.
- Capability management.
- First-run wizard.
- CLI.
- Quickstart.
- First investigation tutorial.

## Phase 11 — Advanced SOC Capabilities

Implement:

- Threat hunting.
- Threat intelligence.
- Detection engineering.
- Asset context.
- Investigation enrichment.

## Phase 12 — Controlled Incident Response

Implement:

- Response policy engine.
- Approval workflows.
- Isolated executor.
- Dry-run capability.
- Execution auditing.

## Phase 13 — Connector Development Kit

Finalize:

- CDK packaging.
- Developer templates.
- Contract testing.
- Documentation.
- Version compatibility.
- Extension testing.

The CDK's foundational contracts and reference connectors must already exist in Phases 2–4.

## Phase 14 — Production Hardening

Complete:

- Security assessment.
- Adversarial AI evaluation.
- MCP security tests.
- Load testing.
- Recovery testing.
- Deployment validation.
- Documentation review.
- Operational readiness assessment.

---

# 30. IMPLEMENTATION QUALITY GATES

Every phase must produce:

1. Functional code.
2. Typed interfaces.
3. Validated schemas.
4. Relevant security controls.
5. Unit tests.
6. Integration tests where applicable.
7. Actual test results.
8. Updated documentation.
9. Recorded limitations.
10. A completion report.

Do not mark a phase complete merely because files were generated.

Do not bypass test failures.

Do not weaken authorization to make a feature work.

Do not claim successful integration with systems that have not been tested.

Do not proceed with dependent features when foundational acceptance criteria are failing.

Continue independent work where possible.

---

# 31. PRODUCTION READINESS

Create an evidence-based release-readiness report.

Include:

- Implemented features.
- Supported capability versions.
- Connector validation status.
- MCP protocol compatibility.
- Authentication and authorization testing.
- AI evaluation results.
- Security findings.
- Performance measurements.
- Recovery testing.
- Deployment validation.
- Documentation status.
- Known limitations.
- Residual risks.
- Go/no-go recommendation.

Use implementation states:

```text
planned
in_progress
implemented
fixture_tested
integration_tested
security_reviewed
live_verified
production_validated
blocked
```

Do not confuse implemented functionality with production validation.

---

# 32. FINAL ENGINEERING RULES

You must follow these rules throughout development.

1. Do not restrict Work4ce Assistant to predefined vendors or tool categories.
2. Do not make MCP the only integration mechanism.
3. Do not hardcode vendor APIs into agent reasoning logic.
4. Every connector must use stable, validated contracts.
5. Capabilities must be dynamically discoverable.
6. The Capability Registry and Integration Gateway are foundational.
7. The Connector Development Kit must support future integrations.
8. Authorization must remain independent of AI reasoning.
9. Untrusted connector code must not execute unrestricted.
10. Every factual investigation conclusion requires evidence.
11. Every sensitive response action must pass policy validation.
12. External telemetry must not override trusted instructions.
13. Missing evidence must be reported explicitly.
14. Automated tests are mandatory.
15. Documentation must reflect actual implementation.
16. Do not invent working integrations or passing tests.
17. Do not claim production readiness without validation.
18. Do not deploy to production without authorization.
19. Avoid unnecessary architectural complexity.
20. Demonstrate extensibility through functioning code.
21. Preserve existing working implementations.
22. Record unresolved limitations.
23. Prefer incremental, reviewable changes.
24. Use secure defaults.
25. Distinguish simulated behavior from real enterprise operations.

---

# 33. INITIAL EXECUTION INSTRUCTIONS FOR CHATGPT

Begin implementing Work4ce Assistant.

First, determine which development tools and repository resources are available.

If a workspace or repository is accessible:

1. Inspect its files.
2. Identify the current project state.
3. Review existing dependencies.
4. Identify completed functionality.
5. Assess gaps against this specification.
6. Preserve existing work.
7. Create or update the architecture documentation.
8. Establish the threat model.
9. Create `AGENTS.md`.
10. Create the implementation progress tracker.
11. Implement the first functional vertical slice.

If no workspace is accessible, begin by producing the actual project foundation files and implementation code, with accurate setup instructions and explicit verification limitations.

Do not ask repetitive questions about requirements already defined in this specification.

Use sensible, secure engineering defaults.

Only request additional information when essential authorization, infrastructure access, or a product decision cannot safely be inferred.

## FIRST MANDATORY VERTICAL SLICE

Implement:

```text
Authenticated Request
          |
          v
AI Investigation Agent
          |
          v
Capability Registry
          |
          v
Capability Resolver
          |
          v
Policy Enforcement
          |
          v
Universal Integration Gateway
          |
          +------------------+
          |                  |
          v                  v
     MCP Connector      REST Connector
          |                  |
          v                  v
     Security Events    Security Events
          |                  |
          +------------------+
                   |
                   v
          Normalized Evidence
                   |
                   v
        Investigation Findings
                   |
                   v
          Stored Incident Report
```

Both connectors must implement the same logical capability.

The system must prove that it can switch between connectors without modifying the agent's core logic.

Verify:

- Authentication.
- Authorization.
- Connector registration.
- Capability discovery.
- Execution.
- Schema validation.
- Failure handling.
- Evidence provenance.
- Audit logging.
- Connector disablement.
- Connector replacement.

After this vertical slice passes, continue implementing subsequent phases as permitted by the current execution environment.

## REQUIRED REPORT AFTER EACH PHASE

Provide:

**Phase:** Name and number.

**Implementation:** Features completed and files changed.

**Verification:** Tests actually executed and their results.

**Security:** Controls implemented and findings identified.

**Limitations:** Missing credentials, external dependencies, incomplete tests, or other blockers.

**Next step:** The next engineering task.

Do not report hypothetical test results as verified.

---

# FINAL DIRECTIVE

Build **Work4ce Assistant** as a real, production-oriented, secure, extensible AI security operations platform.

Its foundation must be:

- Universal Integration Framework.
- Capability Registry.
- Capability Resolver.
- Connector Development Kit.
- MCP and non-MCP adapters.
- Independent Policy Engine.
- Evidence-Driven Investigation Engine.
- Provider-Independent AI Runtime.
- Durable Workflow Engine.
- Human-Governed Response Execution.
- Enterprise Observability.
- Comprehensive Testing.
- Complete Getting Started Experience.

The platform must be able to support new technologies, protocols, tools, agents, and workflows without fundamental architectural redesign.

However, do not sacrifice working functionality for theoretical extensibility.

Build a small, secure, fully tested vertical slice first.

Validate it.

Then expand incrementally.

**Your objective is not to describe Work4ce Assistant. Your objective is to implement Work4ce Assistant using the tools actually available, and to report accurately what has been completed and verified.**

**BEGIN PHASE 0 NOW.**