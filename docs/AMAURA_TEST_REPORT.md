# Amaura Launch-Candidate Verification Report

Date: 2026-07-31

## Verdict

The Amaura source tree passes its complete hermetic regression suite and static release-certification gate. It is a **local launch candidate**, not an unconditional claim of operational perfection. The actual Mac must still pass live Docker, Ollama, distinct-model, configuration, and model-quality checks through `amaura doctor`.

External email and public publishing remain disabled by default. Founder approval, criterion-bound evidence, signed review attestations, exact Git snapshots, and provider receipts fail closed.

## Verified in the build environment

| Gate | Result |
| --- | --- |
| Complete repository test suite | **144 passed; 0 failed** |
| Launch-critical strict-control subset | **48 passed; 0 failed** |
| Python compile check | Passed |
| Static release certification | Passed; no source blockers |
| Repository credential scan | Passed; no findings |
| SQLite backup restoration | Passed; integrity `ok`, 0 foreign-key violations |
| Workforce contract | 43+ employees; no missing tools or invalid reviewers |
| Strict Git regression | Exact commit merge, drift rejection, rollback passed |
| Outbox regression | Leases, ownership, ambiguous-send reconciliation passed |

## Environment limitation

The restricted build container could not download the declared `openai`, build, Ruff, or mypy packages from its internal package mirror. The test suite was therefore collected with a temporary **out-of-repository OpenAI import stub**; model calls remained mocked as designed by the hermetic tests. No stub is included in the release archive.

A wheel build, Ruff run, mypy run, live Docker build, and live Ollama evaluation must be executed by `Install_Amaura.command`, `scripts/verify_amaura.sh`, and `amaura doctor` on the target Mac with normal package access.

## Controls exercised

- Durable task leases, heartbeats, bounded retries, and crash recovery.
- Worker-owned provider outbox leases with retry and reconciliation states.
- Ambiguous email attempts quarantined instead of automatically replayed.
- Independent reviewer assignment and distinct-model routing contract.
- Content-addressed evidence and exact acceptance-criterion coverage.
- Signed review attestations bound to the current submission hash.
- Founder approval bound to the exact summary, evidence, cost, and Git snapshot.
- Isolated Git worktrees, repository merge locks, head-drift checks, post-merge validation, and compensating rollback.
- Atomic founder decision and durable task-completion transitions.
- Docker-isolated, network-disabled command execution that fails closed.
- Prompt-injection quarantine, SSRF controls, path controls, credential redaction, and repository secret scanning.
- Transactionally consistent SQLite backups with restoration verification.
- Experimental LangGraph orchestration disabled by default.

## Live certification

After local installation, run:

```bash
.venv/bin/amaura doctor
```

Continuous operation is allowed only when the output reports:

```json
{
  "production_ready": true
}
```

The live gate requires Docker health, both distinct Ollama models, successful held-out evaluations, independent keys, strict evidence/review/Git modes, a writable backup destination, and valid configuration for every explicitly enabled external provider. Telegram founder binding is required only when the Telegram bot token is configured.
