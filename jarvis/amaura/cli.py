"""Operator CLI for the local, internal Amaura workforce."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.amaura.runtime import load_amaura_env


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env.amaura"
ENV_TEMPLATE = REPOSITORY_ROOT / ".env.amaura.example"
_SECRET_NAMES = {
    "AMAURA_OPERATOR_KEY",
    "AMAURA_APPROVAL_KEY",
    "AMAURA_REVIEW_ATTESTATION_KEY",
    "AMAURA_PROVIDER_RECEIPT_KEY",
    "JARVIS_API_KEY",
}


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def load_env_file(path: str | Path, *, override: bool = False) -> dict[str, str]:
    """Compatibility wrapper around the strict Amaura environment loader."""

    loaded = load_amaura_env(
        path,
        override=override,
        require_private_permissions=True,
    )
    return {"path": str(loaded)} if loaded else {}


def _render_env_template() -> str:
    if not ENV_TEMPLATE.exists():
        raise RuntimeError(f"Missing environment template: {ENV_TEMPLATE}")
    directory_values = {
        "AMAURA_DATA_DIR": str(REPOSITORY_ROOT / ".amaura-data"),
        "JARVIS_DATA_DIR": str(REPOSITORY_ROOT / ".jarvis-data"),
        "AMAURA_EVIDENCE_DIR": str(REPOSITORY_ROOT / ".amaura-data" / "evidence"),
        "AMAURA_BACKUP_DIR": str(REPOSITORY_ROOT / ".amaura-data" / "backups"),
    }
    lines: list[str] = []
    generated_secrets: set[str] = set()
    for raw_line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line or raw_line.lstrip().startswith("#"):
            lines.append(raw_line)
            continue
        name, value = raw_line.split("=", 1)
        if name in _SECRET_NAMES:
            value = secrets.token_urlsafe(48)
            generated_secrets.add(value)
        elif name in directory_values:
            value = directory_values[name]
        lines.append(f"{name}={value}")
    if len(generated_secrets) != len(_SECRET_NAMES):
        raise RuntimeError("Failed to generate independent Amaura secrets")
    return "\n".join(lines) + "\n"


def _build_sandbox() -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        return {"ok": False, "error": "docker_not_installed"}
    dockerfile = REPOSITORY_ROOT / "docker" / "amaura-sandbox.Dockerfile"
    image = os.environ.get("AMAURA_SANDBOX_IMAGE", "amaura-sandbox:1.2.0")
    completed = subprocess.run(
        [docker, "build", "-f", str(dockerfile), "-t", image, str(REPOSITORY_ROOT)],
        capture_output=True,
        text=True,
        timeout=1200,
        check=False,
    )
    smoke = None
    if completed.returncode == 0:
        smoke = subprocess.run(
            [
                docker,
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=128m",
                image,
                "sh",
                "-lc",
                (
                    "python --version && python -m pytest --version && "
                    "ruff --version && mypy --version && node --version && "
                    "npm --version && git --version && rg --version"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    ok = completed.returncode == 0 and smoke is not None and smoke.returncode == 0
    return {
        "ok": ok,
        "image": image,
        "build_returncode": completed.returncode,
        "smoke_returncode": None if smoke is None else smoke.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "smoke_stdout": "" if smoke is None else smoke.stdout[-4000:],
        "smoke_stderr": "" if smoke is None else smoke.stderr[-4000:],
    }


def command_init(args: argparse.Namespace) -> int:
    env_path = Path(args.env_file).expanduser().resolve()
    if env_path.exists() and not args.force:
        _emit({"ok": False, "error": "env_file_exists", "path": str(env_path)})
        return 2
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(_render_env_template(), encoding="utf-8")
    if os.name == "posix":
        env_path.chmod(0o600)
    load_env_file(env_path, override=True)
    for name in (
        "AMAURA_DATA_DIR",
        "JARVIS_DATA_DIR",
        "AMAURA_EVIDENCE_DIR",
        "AMAURA_BACKUP_DIR",
    ):
        value = os.environ.get(name, "")
        if value:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = REPOSITORY_ROOT / path
            path.mkdir(parents=True, exist_ok=True)
    sandbox = _build_sandbox() if args.build_sandbox else {"ok": None, "skipped": True}
    _emit(
        {
            "ok": sandbox.get("ok") is not False,
            "env_file": str(env_path),
            "sandbox": sandbox,
            "next_required_configuration": [
                "Confirm AMAURA_LOCAL_MODEL and AMAURA_LOCAL_REVIEW_MODEL are installed and distinct.",
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID together only when Telegram control is enabled.",
                "Set Gmail credentials only when outbound delivery is intentionally enabled.",
                "Run: amaura doctor",
            ],
        }
    )
    return 0 if sandbox.get("ok") is not False else 1


def command_build_sandbox(args: argparse.Namespace) -> int:
    result = _build_sandbox()
    _emit(result)
    return 0 if result.get("ok") else 1


def _control():
    from jarvis.amaura.control_plane import AmauraControlPlane

    return AmauraControlPlane()


def command_doctor(args: argparse.Namespace) -> int:
    from jarvis.amaura.doctor import certify_release

    report = certify_release(repository_root=REPOSITORY_ROOT, static_only=args.static)
    _emit(report)
    key = "source_certified" if args.static else "production_ready"
    return 0 if report.get(key) else 1


def command_status(args: argparse.Namespace) -> int:
    control = _control()
    try:
        from jarvis.amaura.readiness import production_readiness
        from jarvis.amaura.supervisor import AmauraSupervisor

        supervisor = AmauraSupervisor(
            control,
            lease_seconds=int(os.environ.get("AMAURA_LEASE_SECONDS", "900")),
            max_attempts=int(os.environ.get("AMAURA_MAX_ATTEMPTS", "3")),
            outbox_max_attempts=int(os.environ.get("AMAURA_OUTBOX_MAX_ATTEMPTS", "3")),
            outbox_lease_seconds=int(os.environ.get("AMAURA_OUTBOX_LEASE_SECONDS", "120")),
        )
        _emit(
            {
                "supervisor": supervisor.status(),
                "company": control.dashboard(),
                "readiness": production_readiness(control, live=not args.no_live),
            }
        )
    finally:
        control.close()
    return 0


def command_worker(args: argparse.Namespace) -> int:
    from jarvis.amaura.supervisor import AmauraSupervisor

    control = _control()
    supervisor = AmauraSupervisor(
        control,
        lease_seconds=int(os.environ.get("AMAURA_LEASE_SECONDS", "900")),
        max_attempts=int(os.environ.get("AMAURA_MAX_ATTEMPTS", "3")),
        outbox_max_attempts=int(os.environ.get("AMAURA_OUTBOX_MAX_ATTEMPTS", "3")),
        outbox_lease_seconds=int(os.environ.get("AMAURA_OUTBOX_LEASE_SECONDS", "120")),
        automatic_reviews=not args.no_auto_review,
    )
    try:
        if args.once:
            _emit(supervisor.tick(workflow_id=args.workflow or None))
        elif args.drain:
            _emit(supervisor.drain(workflow_id=args.workflow or None, max_ticks=args.max_ticks))
        else:
            supervisor.run_forever(workflow_id=args.workflow or None, poll_seconds=args.poll_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        control.close()
    return 0


def command_backup(args: argparse.Namespace) -> int:
    control = _control()
    try:
        if args.destination:
            destination = Path(args.destination).expanduser().resolve()
        else:
            backup_dir = Path(os.environ["AMAURA_BACKUP_DIR"]).expanduser().resolve()
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            destination = backup_dir / f"amaura-{timestamp}.db"
        path = control.store.backup(destination)
        _emit(
            {
                "ok": True,
                "backup": str(path),
                "bytes": path.stat().st_size,
                "integrity": control.store.integrity_check(),
            }
        )
    finally:
        control.close()
    return 0


def command_reconcile(args: argparse.Namespace) -> int:
    control = _control()
    try:
        if args.reconcile_action == "list":
            _emit(
                {
                    "events": control.store.list_outbox_events(
                        status="reconciliation_required",
                        limit=args.limit,
                    )
                }
            )
            return 0
        receipt: dict[str, Any] | None = None
        if args.receipt_json:
            receipt = json.loads(Path(args.receipt_json).read_text(encoding="utf-8"))
        event = control.reconcile_outbox_event(
            args.event_id,
            resolution=args.resolution,
            reason=args.reason,
            provider_receipt=receipt,
            actor=control.founder_id,
        )
        _emit({"ok": True, "event": event})
    finally:
        control.close()
    return 0


def command_create_program(args: argparse.Namespace) -> int:
    control = _control()
    try:
        inputs = json.loads(args.inputs_json) if args.inputs_json else {}
        created = control.create_program(
            objective=args.objective,
            success_metric=args.success_metric,
            workflow_key=args.workflow,
            title=args.title or None,
            priority=args.priority,
            deadline=args.deadline or None,
            inputs=inputs,
        )
        _emit(created)
    finally:
        control.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the local Amaura internal workforce")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a secure local environment file")
    init.add_argument("--force", action="store_true")
    init.add_argument("--build-sandbox", action="store_true")
    init.set_defaults(handler=command_init)

    sandbox = subparsers.add_parser("build-sandbox", help="Build the governed Docker execution image")
    sandbox.set_defaults(handler=command_build_sandbox)

    doctor = subparsers.add_parser("doctor", help="Run the release gate")
    doctor.add_argument("--static", action="store_true")
    doctor.set_defaults(handler=command_doctor)

    status = subparsers.add_parser("status", help="Show readiness and workforce state")
    status.add_argument("--no-live", action="store_true")
    status.set_defaults(handler=command_status)

    worker = subparsers.add_parser("worker", help="Run the durable workforce supervisor")
    mode = worker.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--drain", action="store_true")
    worker.add_argument("--workflow", default="")
    worker.add_argument("--poll-seconds", type=float, default=5.0)
    worker.add_argument("--max-ticks", type=int, default=100)
    worker.add_argument("--no-auto-review", action="store_true")
    worker.set_defaults(handler=command_worker)

    backup = subparsers.add_parser("backup", help="Create a transactionally consistent database backup")
    backup.add_argument("destination", nargs="?", default="")
    backup.set_defaults(handler=command_backup)

    reconcile = subparsers.add_parser("reconcile", help="Resolve ambiguous provider operations")
    reconcile_sub = reconcile.add_subparsers(dest="reconcile_action", required=True)
    reconcile_list = reconcile_sub.add_parser("list")
    reconcile_list.add_argument("--limit", type=int, default=100)
    reconcile_list.set_defaults(handler=command_reconcile)
    reconcile_resolve = reconcile_sub.add_parser("resolve")
    reconcile_resolve.add_argument("event_id")
    reconcile_resolve.add_argument("--resolution", choices=("completed", "failed", "requeue"), required=True)
    reconcile_resolve.add_argument("--receipt-json", default="")
    reconcile_resolve.add_argument("--reason", required=True)
    reconcile_resolve.set_defaults(handler=command_reconcile)

    create = subparsers.add_parser("create-program", help="Create a governed company programme")
    create.add_argument("--workflow", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--success-metric", required=True)
    create.add_argument("--title", default="")
    create.add_argument("--priority", type=int, default=3)
    create.add_argument("--deadline", default="")
    create.add_argument("--inputs-json", default="{}")
    create.set_defaults(handler=command_create_program)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command != "init":
            loaded = load_amaura_env(
                args.env_file,
                require_private_permissions=True,
            )
            if loaded is None:
                raise RuntimeError("Amaura is not initialised. Run: amaura init")
        return int(args.handler(args))
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1
    except Exception as exc:  # fail closed with machine-readable operator output
        _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
