# Amaura Production Verification Report

Date: 2026-07-27

## Verdict

The Amaura operating kernel is fixed and passes its local production gate. It is ready for authenticated local operation after real authority keys are configured.

External services are intentionally not reported as active until their binaries, credentials, OAuth grants, and provider callbacks are configured. In particular, the kernel does not claim that Gmail sent a message, Postiz/YouTube published content, OBS recorded a demonstration, or an external sandbox executed code without real provider confirmation.

## Verified results

| Gate | Result |
| --- | --- |
| Complete repository test suite | 63 passed; 0 failed |
| Focused Ruff analysis | Passed |
| Focused mypy analysis | Passed: 8 core modules, 0 issues |
| Wheel build | Passed: `dist/jarvis-1.0.0-py3-none-any.whl` |
| Prompt packaging | Passed: founder prompt source present in wheel |
| Authenticated REST smoke test | Passed |
| Missing-auth mutation rejection | Passed with HTTP 403 |
| Configured production readiness | Passed |
| SQLite integrity | `ok`; 0 foreign-key violations; WAL enabled |

The four warnings in the full suite are upstream/deprecation warnings in HTTPX, MLX, and SpeechRecognition; none is a test or Amaura-kernel failure.

## Extreme stress and adversarial run

`python scripts/stress_amaura.py` completed successfully:

| Scenario | Result |
| --- | ---: |
| Concurrent workers | 32 |
| Evidence-backed leads ingested | 1,000 |
| Prompt-injection payloads detected | 100 / 100 |
| Concurrent provider-confirmed outbound actions | 60 |
| Concurrent sends blocked by daily caps | 20 / 20 |
| Simultaneous duplicate attempts | 500 |
| Records created from duplicate race | 1 |
| End-of-run database integrity | Passed |
| Wall time on this machine | 1.036 seconds |

An additional regression test launches 40 simultaneous discoveries against a five-lead daily limit and verifies that exactly five records are created.

## Production controls exercised

- 43 unique employee definitions and independent reviewer assignments.
- Six governed workflows, including the full 16-stage acquisition pipeline and 12-stage content factory.
- Five founder-provided revenue prompts parsed, versioned, loaded, and packaged.
- Deterministic lead score bounds and threshold enforcement.
- Evidence provenance, hashing, injection scan, and secret redaction.
- Domain normalisation and database-enforced deduplication.
- Legal pipeline transitions, terminal states, opt-outs, follow-up maximums, and kill switch.
- Founder-only, message-specific approvals with 48-hour expiry.
- Atomic daily discovery and outbound caps under concurrency.
- Idempotent message drafts and unique provider message identifiers.
- No silent send success without a provider ID.
- Content hashes, external-asset licence requirements, QA asset set, and analytics windows.
- Portable writable data directory with explicit environment override.
- Restricted-data routing to Ollama with no cloud fallback.
- Local-only default binding, restricted CORS, authenticated remote mutation and WebSocket gates.
- Consistent database backup and structural/foreign-key integrity verification.

## Deployment blockers outside the codebase

Before real external operation, the operator must supply three independent authority keys and any desired provider credentials. Optional adapters detected on this machine: FFmpeg and Ollama are available. PydanticAI, LangGraph, DBOS, LiteLLM, OpenTelemetry, OBS, Promptfoo, and Docker/OpenSandbox are not currently installed. The internal kernel remains operational without them, but the relevant external capability is unavailable until configured.

Real outreach must start in `Approve -> Create Gmail draft` mode. Real content publication must start as private/draft upload. Contract acceptance, money movement, public publication, and production deployment remain human actions.
