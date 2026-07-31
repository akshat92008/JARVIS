#!/usr/bin/env python3
"""Structured fail-closed release certification for Amaura."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

try:
    from security_gate import scan_repository  # type: ignore[import-not-found]  # noqa: E402
except ModuleNotFoundError:
    from scripts.security_gate import scan_repository  # noqa: E402

from jarvis.amaura.control_plane import AmauraControlPlane  # noqa: E402
from jarvis.amaura.evaluation import evaluate_model  # noqa: E402
from jarvis.amaura.readiness import production_readiness  # noqa: E402


def _run(static_only: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="amaura-release-gate-") as directory:
        control = AmauraControlPlane(Path(directory) / "amaura.db")
        try:
            readiness = production_readiness(control, live=not static_only)
        finally:
            control.close()
    security = scan_repository(REPOSITORY_ROOT)
    evaluations: list[dict[str, Any]] = []
    evaluation_status = "skipped_static"
    if not static_only:
        live_checks = readiness["live_checks"]
        prerequisites = all(
            live_checks.get(name, False)
            for name in (
                "ollama_reachable",
                "worker_model_installed",
                "reviewer_model_installed",
            )
        )
        if prerequisites:
            evaluation_status = "completed"
            ollama_url = os.environ.get(
                "OLLAMA_URL",
                "http://127.0.0.1:11434",
            )
            for model in (
                os.environ.get("AMAURA_LOCAL_MODEL", ""),
                os.environ.get("AMAURA_LOCAL_REVIEW_MODEL", ""),
            ):
                evaluations.append(
                    evaluate_model(model, base_url=ollama_url).to_dict()
                )
        else:
            evaluation_status = "skipped_unavailable_prerequisites"

    model_gate = (
        True
        if static_only
        else (
            evaluation_status == "completed"
            and len(evaluations) == 2
            and all(item["ready"] for item in evaluations)
        )
    )
    source_certified = bool(readiness["source_certified"]) and bool(security["ok"])
    production_ready = (
        source_certified
        and not static_only
        and bool(readiness["ready"])
        and model_gate
    )
    return {
        "ready": production_ready,
        "source_certified": source_certified,
        "production_ready": production_ready,
        "mode": "static" if static_only else "production",
        "readiness": readiness,
        "security": security,
        "model_evaluation": {
            "status": evaluation_status,
            "ready": model_gate,
            "results": evaluations,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Validate source contracts without requiring local infrastructure.",
    )
    args = parser.parse_args()
    try:
        report = _run(args.static_only)
    except Exception as exc:  # noqa: BLE001 - gate must always emit structured JSON
        report = {
            "ready": False,
            "source_certified": False,
            "production_ready": False,
            "mode": "static" if args.static_only else "production",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    gate_key = "source_certified" if args.static_only else "production_ready"
    return 0 if report.get(gate_key) else 1


if __name__ == "__main__":
    raise SystemExit(main())
