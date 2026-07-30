# Current System Map

This map outlines the structure of the Amaura repository, identifying packages, entrypoints, orchestration loops, and persistent state models, serving as the basis for the Phase 1-10 migration.

## 1. Top-Level Entrypoints
- `jarvis.cli`: Main entrypoint (`jarvis` and `nexus` CLI scripts).
- `jarvis.amaura.supervisor`: Worker process entrypoint (`amaura-worker`).
- `jarvis.server`: REST API entrypoint for interacting with the AI agents and tools.

## 2. Core Python Packages

### `jarvis.amaura.*` (The Operating System)
- `control_plane.py`: Strict action and mutation gateway. Implements `AmauraControlPlane`.
- `supervisor.py`: Task leasing and execution loop (`AmauraSupervisor`). Linearly progresses tasks.
- `store.py`: Persistence layer using SQLite for `execution_runs`, `work_items`, `content_campaigns`, etc.
- `bus.py`: The command bus connecting commands to handlers within the same SQLite transaction.
- `executor.py`: Implements sandboxed task execution, including `GovernedTaskRunner` for the Nexus CLI fallback.
- `models.py`: Pydantic schemas representing domains (e.g., `RiskLevel`, `ApprovalStatus`, `TaskBudget`).
- `policy.py` & `policies.py`: Defines founder risk policies and business constraints.
- `evidence.py`: Cryptographic attestation and evidence vault storage.

### `jarvis.tools.*` (Agent Actions)
- `amaura.py`: Tools exposed to Jarvis/agents to interact with the Amaura system (e.g., `create_campaign`, `start_task`).
- `registry.py`: Global tool registry for mapping function calls to implementations.

## 3. Database Schema (SQLite)
Stored in `amaura_db_path`:
- `content_campaigns`: High-level business campaigns (marketing, research, software).
- `work_items`: Tasks fan-out from campaigns.
- `execution_runs`: Logs of individual agent runs attempting to satisfy a `work_item`.
- `content_assets`: Media, text, or research produced by agents.
- `approval_requests`: Immutable hashes awaiting founder signature.
- `telemetry_events`: Security/audit logging.

## 4. Current Workflows (The Problem)
- Currently, workflows are hardcoded linearly inside `supervisor.py` (i.e. `assigned` -> `in_progress` -> `awaiting_review` -> `completed`).
- Branching logic (e.g. revisions, escalations) is brittle and frequently stalls if a state transition fails.

## 5. Deployment and Tests
- **Tests**: Exhaustive suite in `tests/test_amaura_*.py` using Python `unittest` and `pytest`. 
  - *Current Status*: 4 failures related to cryptographic attestations for non-founder reviewers (recently enforced in P0 remediation).
- **CI**: GitHub actions (`.github/workflows/ci.yml`) enforce `ruff`, `mypy`, and `pytest`.
- **Docker**: `docker/amaura-sandbox.Dockerfile` sets up the restricted coding environment.

## 6. Known Configuration (Environment Variables)
- `AMAURA_DB_PATH`: Path to the SQLite store.
- `AMAURA_EVIDENCE_PATH`: Path to the file-backed evidence vault.
- `AMAURA_OPERATOR_KEY`: Founder cryptokey for authorizations.
- Model keys (`OPENAI_API_KEY`, etc.).
- `AMAURA_WORKSPACE_ROOT`: Path to host workspaces for repository cloning.

## Next Steps
This system provides excellent fundamental security, attestation, and data modeling. The migration plan will decouple the linear loop in `supervisor.py` and replace it with `LangGraph`, while strictly maintaining the security enforcement in `control_plane.py`.
