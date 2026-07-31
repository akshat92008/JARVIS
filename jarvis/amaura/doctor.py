"""Release certification and operator diagnostics for Amaura.

This module lives inside the installable package so the ``amaura doctor``
command works from any directory.  It performs source, configuration,
database-backup, secret-scan, infrastructure, and live model checks without
relying on repository-only helper scripts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.evaluation import evaluate_model
from jarvis.amaura.readiness import production_readiness

SECRET_PATTERNS = {
    "nvidia_api_key": re.compile(rb"\bnvapi-[A-Za-z0-9_-]{32,}\b"),
    "openai_api_key": re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "github_token": re.compile(rb"\bgh[opusr]_[A-Za-z0-9]{30,}\b"),
    "aws_access_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
}

_IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".amaura-data",
    ".jarvis-data",
    "dist",
    "build",
}


def _tracked_or_source_files(root: Path) -> Iterable[Path]:
    """Yield source-controlled files, with a safe archive fallback.

    Distributed ZIP files do not contain ``.git``.  The fallback therefore
    excludes local data, virtual environments, caches, and generated outputs.
    """

    try:
        completed = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if any(part in _IGNORED_PARTS for part in relative.parts):
                continue
            if path.name in {".env.amaura", ".env"}:
                continue
            yield path
        return

    for item in completed.stdout.split(b"\0"):
        if not item:
            continue
        path = root / item.decode("utf-8", errors="surrogateescape")
        if path.is_file():
            yield path


def scan_repository(root: str | Path) -> dict[str, Any]:
    """Detect credential-shaped material in distributable source files."""

    repository = Path(root).expanduser().resolve()
    findings: list[dict[str, str]] = []
    scanned = 0
    bytes_scanned = 0
    for path in _tracked_or_source_files(repository):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 10_000_000:
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        scanned += 1
        bytes_scanned += len(content)
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                findings.append(
                    {
                        "path": str(path.relative_to(repository)),
                        "kind": kind,
                    }
                )
    return {
        "ok": not findings,
        "files_scanned": scanned,
        "bytes_scanned": bytes_scanned,
        "findings": findings,
    }


def _backup_restore_probe(control: AmauraControlPlane, directory: Path) -> dict[str, Any]:
    backup_path = control.store.backup(directory / "amaura-backup.db")
    with sqlite3.connect(backup_path) as restored:
        integrity = restored.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = restored.execute("PRAGMA foreign_key_check").fetchall()
        schema_rows = restored.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY name"
        ).fetchall()
    schema_digest = hashlib.sha256(
        json.dumps(schema_rows, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return {
        "ok": integrity == "ok" and not foreign_keys,
        "path": str(backup_path),
        "bytes": backup_path.stat().st_size,
        "integrity": integrity,
        "foreign_key_violations": len(foreign_keys),
        "schema_sha256": schema_digest,
    }


def certify_release(
    *,
    repository_root: str | Path | None = None,
    static_only: bool = False,
) -> dict[str, Any]:
    """Run the complete fail-closed release gate and return structured JSON."""

    root = Path(repository_root or Path(__file__).resolve().parents[2]).resolve()
    with tempfile.TemporaryDirectory(prefix="amaura-release-gate-") as directory:
        temp_root = Path(directory)
        control = AmauraControlPlane(temp_root / "amaura.db")
        try:
            readiness = production_readiness(control, live=not static_only)
            backup_restore = _backup_restore_probe(control, temp_root)
        finally:
            control.close()

    security = scan_repository(root)
    evaluations: list[dict[str, Any]] = []
    evaluation_status = "skipped_static"
    if not static_only:
        live_checks = readiness["live_checks"]
        prerequisites = all(
            bool(live_checks.get(name))
            for name in (
                "ollama_reachable",
                "worker_model_installed",
                "reviewer_model_installed",
            )
        )
        if prerequisites:
            evaluation_status = "completed"
            ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
            models = (
                os.environ.get("AMAURA_LOCAL_MODEL", "").strip(),
                os.environ.get("AMAURA_LOCAL_REVIEW_MODEL", "").strip(),
            )
            for model in models:
                evaluations.append(evaluate_model(model, base_url=ollama_url).to_dict())
        else:
            evaluation_status = "skipped_unavailable_prerequisites"

    model_gate = (
        True
        if static_only
        else (
            evaluation_status == "completed"
            and len(evaluations) == 2
            and all(bool(item.get("ready")) for item in evaluations)
        )
    )
    source_certified = (
        bool(readiness["source_certified"])
        and bool(security["ok"])
        and bool(backup_restore["ok"])
    )
    production_ready = (
        source_certified
        and not static_only
        and bool(readiness["ready"])
        and model_gate
    )
    blockers = list(readiness.get("blockers", []))
    if not security["ok"]:
        blockers.append("repository_secret_scan")
    if not backup_restore["ok"]:
        blockers.append("backup_restore_probe")
    if not model_gate and not static_only:
        blockers.append("live_model_evaluation")

    return {
        "ready": production_ready,
        "source_certified": source_certified,
        "production_ready": production_ready,
        "mode": "static" if static_only else "production",
        "blockers": sorted(set(blockers)),
        "readiness": readiness,
        "security": security,
        "backup_restore": backup_restore,
        "model_evaluation": {
            "status": evaluation_status,
            "ready": model_gate,
            "results": evaluations,
        },
    }


__all__ = ["certify_release", "scan_repository"]
