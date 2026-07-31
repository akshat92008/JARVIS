# Amaura internal workforce — local launch

Amaura is configured for **internal, founder-controlled use**. External email and publication adapters are disabled by default. High-risk actions remain approval-gated.

## One-time installation on macOS

1. Install Homebrew if it is not already installed.
2. Install the local runtime prerequisites:

```bash
brew install python@3.12 ollama
brew install --cask docker
```

3. Open Docker Desktop once, then run:

```bash
./Install_Amaura.command
```

The installer creates `.venv`, installs the package, generates five independent secrets in a mode-`0600` `.env.amaura`, runs the full regression suite, performs source certification, installs/checks the two distinct Ollama models, builds the governed Docker sandbox, and runs live certification.

The default worker model is `nova:3b`; that model must already exist in Ollama or be available to pull. The independent reviewer defaults to `qwen2.5-coder:3b`.

## Start Amaura

```bash
./Launch_Amaura.command
```

Launch fails closed unless Docker, Ollama, both distinct models, secrets, database integrity, backup restoration, evidence/review enforcement, Git controls, and source security checks pass.

## Core operator commands

```bash
.venv/bin/amaura doctor                 # full live certification
.venv/bin/amaura doctor --static        # source/config certification
.venv/bin/amaura status                 # workforce and readiness state
.venv/bin/amaura worker --once          # advance one safe unit
.venv/bin/amaura worker --drain         # drain currently executable work
.venv/bin/amaura backup                 # timestamped SQLite backup
.venv/bin/amaura create-program \
  --workflow software_delivery \
  --objective "Implement a bounded internal feature" \
  --success-metric "All acceptance tests pass" \
  --inputs-json '{"repository_path":"/absolute/path/to/repository"}'
```

## Safety boundaries

- No automatic public publishing by default.
- No automatic outbound email by default.
- Signed provider receipts bind every send to the exact approved payload.
- Ambiguous provider timeouts enter manual reconciliation rather than replaying.
- Engineering work uses isolated Git worktrees and immutable reviewed commits.
- Automatic merge requires an unchanged base, an exclusive repository lock, post-merge validation, and rollback on failure.
- Experimental LangGraph orchestration is disabled.
- Worker and reviewer models must be distinct.
- Every strict review must cover every acceptance criterion with submitted content-addressed evidence.

## Runtime recovery

After an interruption, rerun `./Launch_Amaura.command`. Expired task leases are reclaimed automatically. Ambiguous external operations are not replayed; inspect them with:

```bash
.venv/bin/amaura reconcile list
```
