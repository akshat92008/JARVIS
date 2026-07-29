# Amaura Production Verification Report

Date: 2026-07-29

## Verdict

The Amaura source release passes its complete hermetic engineering gate. The
system is ready for deployment configuration and live certification on the
Amaura host; it does not claim operational readiness until the required local
models, Docker sandbox, authority keys, founder identity, and provider
credentials pass `python scripts/release_gate.py`.

External actions remain fail-closed. Gmail delivery and private publication
must return authenticated, idempotent provider receipts, while public
publication, pricing, proposals, outreach, and deployment remain
founder-approved actions.

## Verified results

| Gate | Result |
| --- | --- |
| Complete repository test suite | 85 passed; 0 failed |
| Production-critical suite | 22 passed; 0 failed |
| Ruff analysis | Passed |
| Mypy analysis | Passed: 18 core modules, 0 issues |
| Static production gate | Passed; no source blockers |
| Repository credential scan | Passed; no findings |
| Wheel build | Passed: `jarvis-1.1.0-py3-none-any.whl` |
| Workforce contract | 43 employees; no missing tools or invalid reviewers |
| SQLite integrity | `ok`; 0 foreign-key violations; WAL enabled |

The two full-suite warnings are Python 3.12 deprecation warnings emitted by
SpeechRecognition dependencies; neither is a test or Amaura-kernel failure.

## Extreme stress and adversarial run

`python scripts/stress_amaura.py` completed successfully:

| Scenario | Result |
| --- | ---: |
| Concurrent workers | 32 |
| Evidence-backed leads ingested | 1,000 |
| Prompt-injection payloads detected | 100 / 100 |
| Provider-confirmed outbound actions | 60 |
| Sends blocked by daily caps | 20 / 20 |
| Simultaneous duplicate attempts | 500 |
| Records created from duplicate race | 1 |
| End-of-run database integrity | Passed |

## Production controls exercised

- Atomic task leases, heartbeats, bounded retries, and crash recovery.
- Independent reviewer assignment and distinct worker/reviewer model contract.
- Deterministic evidence verification and HMAC-signed review attestations.
- Content-addressed evidence with tamper detection.
- Exact-payload founder approvals with 48-hour expiry.
- Docker-isolated, network-disabled command execution that fails closed.
- DNS-aware SSRF, redirect, metadata-network, and credential-leak protection.
- Authenticated Gmail and private-publication receipts with idempotency.
- Durable metrics, traces, alerts, and Prometheus rendering.
- Atomic lead limits, deduplication, opt-outs, follow-up caps, and kill switch.
- Complete runtime dependency metadata and Python 3.11/3.12 GitHub CI.
- Credential-free, network-hermetic automated tests.

## Live certification requirements

The static gate deliberately reports live configuration as incomplete in this
container. Before unattended operation, configure independent authority and
receipt keys, bind Telegram to the founder identity, install/build the governed
Docker sandbox, and provide two distinct Ollama models. Then run:

```bash
python scripts/release_gate.py
```

The live gate requires both held-out model evaluations to score at least 90%
with zero safety-critical failures. Provider credentials and OAuth grants must
be supplied only through environment or secret-management configuration.
