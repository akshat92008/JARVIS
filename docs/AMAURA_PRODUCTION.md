# Amaura Workforce — Production Operations

This repository now contains one integrated, local-first operating kernel for Amaura Labs. JARVIS is the only orchestrator; 43 registered employees execute six dependency-ordered workflows. The two full operating systems are:

- `client_acquisition`: 16 stages from bounded campaign design through evidence, deterministic qualification, founder-approved contact, proposal, and delivery handoff.
- `content_factory`: 12 stages from research through script, real demonstration, licensed assets, rendering, independent media QA, founder-approved publication, and measured learning.

The five founder-supplied revenue prompts are packaged verbatim, versioned, and loaded into the matching employee definitions. The content and acquisition blueprints are implemented as enforceable workflows and data controls rather than as untrusted runtime instructions.

## Durable supervisor

The workforce is advanced by `AmauraSupervisor`, a SQLite-backed worker that is safe to restart and safe to run from multiple processes:

- it atomically leases only dependency-ready tasks;
- one active execution is permitted per task;
- a heartbeat extends the lease while a model or tool is working;
- expired leases are recovered after a crash;
- transient provider failures retry once by default;
- policy, validation, and evidence failures fail closed;
- employee output stops at `awaiting_review`;
- a separately registered reviewer verifies the evidence;
- founder review is never automated.

Run one unit of work, drain all currently safe work, or keep a worker alive:

```bash
python -m jarvis.amaura.supervisor --once
python -m jarvis.amaura.supervisor --drain --max-ticks 100
python -m jarvis.amaura.supervisor --poll-seconds 5
```

The installed console entry point is `amaura-worker`. `AMAURA_LEASE_SECONDS` and `AMAURA_MAX_ATTEMPTS` tune recovery. The recommended values are 900 seconds and two attempts.

The supervisor can execute internal work and independent reviews. It deliberately stops at founder approvals, public publication, production deployment, pricing commitments, external outreach, payments, and other authority boundaries.

## Zero-cost model mode

Set the following values to route every employee and reviewer to the local Ollama endpoint with no cloud fallback:

```bash
export AMAURA_MODEL_MODE=local
export OLLAMA_URL=http://127.0.0.1:11434
export AMAURA_LOCAL_MODEL=nova:3b
export AMAURA_LOCAL_REVIEW_MODEL=nova:3b
```

`nova:3b` must already exist in Ollama under that tag. A different installed local model can be selected without changing code. Restricted or client-confidential data is device-only regardless of the general routing mode.

## Safety and reliability guarantees

- Public prospect facts require a URL, excerpt, retrieval time, confidence, and content hash.
- Crawled text is scanned for prompt injection and secrets and stored as evidence, never system instruction.
- Company domains are globally unique and normalised before insertion.
- Lead scores are a deterministic 100-point sum; campaigns cannot lower the threshold below 70.
- First contact needs evidence, a qualifying score, 70–170 words, founder approval, and a provider message ID.
- Duplicate drafts are idempotent. Daily outbound caps are enforced atomically under concurrency.
- Opt-out and terminal states prevent any later outreach.
- Campaign approvals expire after 48 hours. Follow-ups stop after two.
- External communications, public content, pricing, commitments, and releases remain founder-gated.
- Content assets require hashes. External assets require source and licence records.
- SQLite uses foreign keys and WAL, has integrity checks, and supports consistent online backups.
- Execution leases prevent duplicate workers and recover abandoned in-progress tasks.
- Audit entries form a SHA-256 hash chain so direct database tampering is detectable.
- Founder approvals expire after 48 hours and are bound to the exact summary, evidence, risk, action, and cost payload reviewed.
- Task-relative file arguments resolve to the assigned workspace before both policy evaluation and execution.
- Web fetch policy blocks loopback, private, link-local, reserved, credential-bearing, and metadata-service URLs.
- Telegram refuses to start without a bound founder user ID; file uploads and exports are path-confined.
- The acquisition kill switch stops discovery and sending immediately.

## Configure

Copy `.env.amaura.example` to your secret environment manager and replace every placeholder. Do not commit the resulting values. The three authority keys must be independent and at least 24 characters.

For a local-only server:

```bash
export AMAURA_OPERATOR_KEY="..."
export AMAURA_APPROVAL_KEY="..."
export JARVIS_API_KEY="..."
export AMAURA_DATA_DIR="$PWD/.amaura-data"
export JARVIS_DATA_DIR="$PWD/.jarvis-data"
python -m jarvis.server
```

Keep `JARVIS_HOST=127.0.0.1` unless a trusted reverse proxy supplies TLS, rate limiting, network access control, and secret injection. Remote mode refuses general mutations unless `JARVIS_API_KEY` is configured. Amaura operator and founder actions still require their separate keys.

## First recommended campaign

Create a `client_acquisition` programme using:

```json
{
  "campaign_id": "agency_partner_14d",
  "campaign_name": "14-day agency partnership campaign",
  "target_segment": "Small branding, SEO, marketing and design agencies",
  "offer": "White-label websites, SaaS MVPs, web applications and AI product development",
  "minimum_score": 70,
  "daily_lead_limit": 10,
  "daily_outreach_limit": 3,
  "daily_followup_limit": 5,
  "maximum_followups": 2,
  "proof_assets": ["VEXO", "Cognition OS", "Solar Dynamics", "LeadGenPro"]
}
```

Agents research, qualify, personalise, and prepare. The founder approves consequential actions and performs or confirms the actual external send.

## Core endpoints

All detailed reads and ordinary mutations use `X-Amaura-Operator-Key`. Founder decisions use `X-Amaura-Approval-Key`.

```text
GET  /api/amaura/readiness
GET  /api/amaura/dashboard
POST /api/amaura/programmes
GET  /api/amaura/supervisor/status
POST /api/amaura/supervisor/tick

GET  /api/amaura/revenue
POST /api/amaura/revenue/campaigns
POST /api/amaura/revenue/leads
POST /api/amaura/revenue/leads/{id}/evidence
POST /api/amaura/revenue/leads/{id}/score
POST /api/amaura/revenue/leads/{id}/messages
POST /api/amaura/revenue/messages/{id}/decision
POST /api/amaura/revenue/messages/{id}/sent
POST /api/amaura/revenue/kill-switch

POST /api/amaura/content/campaigns
POST /api/amaura/content/campaigns/{id}/assets
GET  /api/amaura/content/campaigns/{id}/readiness
POST /api/amaura/content/campaigns/{id}/metrics
```

`/messages/{id}/sent` is a confirmation boundary, not an email client. Call it only after an approved Gmail/other adapter returns a real provider identifier. This prevents silent or fabricated success.

## Validation and release commands

```bash
pytest -q
ruff check jarvis/amaura jarvis/paths.py tests/test_amaura_os.py tests/test_amaura_growth.py
mypy --follow-imports=skip --ignore-missing-imports \
  jarvis/amaura/models.py jarvis/amaura/store.py jarvis/amaura/pipeline.py \
  jarvis/amaura/content_factory.py jarvis/amaura/security.py jarvis/amaura/readiness.py \
  jarvis/amaura/registry.py jarvis/amaura/workflows.py
python scripts/stress_amaura.py
python -m build --wheel --no-isolation
```

The readiness endpoint intentionally reports missing optional adapters. PydanticAI, LangGraph, DBOS, LiteLLM, MCP/OPA, OpenSandbox, Langfuse, Promptfoo, FFmpeg, OBS, Ollama, Gmail, Telegram, and publishing platforms are not claimed as active unless actually installed and configured. The core kernel runs without them; they extend execution, observability, media rendering, or external delivery.

The local supervisor now supplies the core durability previously delegated to DBOS/LangGraph: dependency scheduling, atomic leases, heartbeats, recovery, retries, review routing, and persisted state. External packages remain optional adapters rather than false prerequisites. Host command execution is still process-level isolation, not a substitute for OpenSandbox or a locked-down container; use a disposable repository workspace and Docker/OpenSandbox before allowing untrusted repositories to execute tests.

## Backup and recovery

Use `CompanyStore.backup()` for a consistent live database backup, store backups outside the active data directory, and regularly test restoration. The database integrity check verifies both SQLite structure and foreign keys. Employee pause and acquisition kill-switch operations preserve all evidence and audit records.
