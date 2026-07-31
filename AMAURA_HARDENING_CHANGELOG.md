# Amaura launch-candidate hardening changelog

## Release objective

Convert the internal Amaura workforce from a supervised prototype into a fail-closed local launch candidate with recoverable task execution, criterion-bound verification, safe repository delivery, crash-safe provider dispatch, and one canonical operator interface.

## Core additions

### Governed Git delivery

Added `jarvis/amaura/gitops.py` with:

- Exact base branch and base commit capture
- Clean-repository requirement
- Isolated task branches and worktrees
- Validated Git command return codes
- Immutable base-relative diffs
- No-change task rejection
- Exclusive cross-process repository merge locks
- Reviewed-commit and target-head checks
- Allowlisted post-merge validation
- Automatic validation rollback
- Compensating rollback when durable task completion fails
- Recoverable worktree cleanup events

### Strict evidence and independent review

Enhanced `jarvis/amaura/evidence.py`, `executor.py`, and `control_plane.py` with:

- Content-addressed evidence enforcement
- Exact acceptance-criterion coverage
- Evidence references bound to each criterion
- Vault integrity verification
- Worker/reviewer model separation
- Signed review attestations
- Submission hash binding and replay prevention
- Founder approval payloads bound to the exact Git snapshot

### Durable provider outbox

Enhanced `jarvis/amaura/store.py` and `supervisor.py` with:

- Worker-owned outbox leases
- Lease expiry and recovery
- Bounded attempts and exponential backoff
- Persisted provider receipts
- Dead-letter-style reconciliation state
- Conservative email handling: ambiguous sends are never automatically replayed
- Founder-only reconciliation through the CLI and authenticated API
- Exact signed-receipt binding to recipient, subject, body, operation, and idempotency key
- Atomic linked-message and outbox state transitions for completed, failed, and requeued operations

### Atomic founder decisions

Founder approval resolution, task completion, merge receipt persistence, event publication, and audit records now commit together. A failed merge or persistence step leaves the operation recoverable instead of consuming the approval and stranding the task.

### Canonical local operator CLI

Added `jarvis/amaura/cli.py` and the `amaura` console command:

- `amaura init`
- `amaura build-sandbox`
- `amaura doctor`
- `amaura status`
- `amaura worker`
- `amaura backup`
- `amaura reconcile`
- `amaura create-program`

The legacy `scripts/amaura_local.py` is now only a compatibility wrapper.
`Launch_Amaura.command` starts the loopback API/HUD and durable supervisor as
one local stack and shuts both down together.

### Local runtime controls

Added or hardened:

- Strict `.env.amaura` parser that never executes shell syntax
- Private `0600` secret-file permissions
- Five independently generated keys
- Absolute private data/evidence/backup paths
- Docker sandbox launch gate
- Distinct local worker/reviewer model gate
- Backup-and-restore certification
- Experimental LangGraph disabled by default
- Mac double-click installer and launcher
- Separate runtime setup/certification command so source installation is reproducible before Docker/Ollama setup
- Complete verification script

## Experimental orchestration

The incomplete LangGraph supervisor no longer silently falls back to an unrelated workflow. It remains disabled unless explicitly enabled and should not be enabled for company operations until its nodes and interfaces are completed and separately certified.

## Test coverage added

Added adversarial tests for:

- Strict environment-file parsing and permissions
- Criterion/evidence coverage
- Wrong-worker outbox completion
- Expired email lease reconciliation
- Ambiguous email non-replay
- Founder reconciliation with exact provider receipts
- Forged or mismatched receipt rejection
- Linked outbox/message failure and requeue consistency
- Exact reviewed Git merges
- Base-branch drift rejection
- Validation rollback
- Review-attestation replay protection

## Verification result in the build environment

- Full repository suite: **144 passed**
- Python compile check: passed
- Static source release gate: passed
- Repository security gate: passed

Live production readiness remains machine-specific and must be confirmed with `amaura doctor` after Docker, Ollama, the two distinct models, and local credentials are configured. Telegram founder binding is required only when the Telegram bot is enabled.
