"""Truthful static and live readiness checks for the Amaura workforce."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis.amaura.capabilities import EXECUTABLE_EMPLOYEE_TOOLS
from jarvis.amaura.prompts import load_prompt_catalogue
from jarvis.amaura.registry import ALL_AGENTS
from jarvis.amaura.workflows import WORKFLOWS

if TYPE_CHECKING:
    from jarvis.amaura.control_plane import AmauraControlPlane


@dataclass(frozen=True, slots=True)
class Integration:
    name: str
    kind: str
    probe: str
    configured: bool = False


OPTIONAL_INTEGRATIONS = (
    Integration("PydanticAI", "python", "pydantic_ai"),
    Integration("LangGraph", "python", "langgraph"),
    Integration("DBOS", "python", "dbos"),
    Integration("LiteLLM", "python", "litellm"),
    Integration("OpenTelemetry", "python", "opentelemetry"),
    Integration("FFmpeg", "binary", "ffmpeg"),
    Integration("Crawl4AI", "python", "crawl4ai"),
    Integration("OBS", "binary", "obs"),
    Integration("Promptfoo", "binary", "promptfoo"),
)


def _integration_status(integration: Integration) -> dict[str, object]:
    available = (
        importlib.util.find_spec(integration.probe) is not None
        if integration.kind == "python"
        else shutil.which(integration.probe) is not None
    )
    return {**asdict(integration), "available": available}


def _configured_secret(name: str, *, minimum: int = 32) -> bool:
    value = os.environ.get(name, "")
    placeholders = (
        "replace-",
        "changeme",
        "example",
        "your-",
    )
    return len(value.encode()) >= minimum and not value.lower().startswith(placeholders)


def _probe_ollama(
    base_url: str,
    *,
    worker_model: str,
    reviewer_model: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/tags",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read(1_000_000).decode())
        names = {
            str(item.get("name", "")).split(":latest", 1)[0]
            for item in payload.get("models", [])
            if isinstance(item, dict)
        }
        return {
            "reachable": True,
            "worker_model_installed": worker_model in names,
            "reviewer_model_installed": reviewer_model in names,
            "models": sorted(names),
            "error": "",
        }
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as exc:
        return {
            "reachable": False,
            "worker_model_installed": False,
            "reviewer_model_installed": False,
            "models": [],
            "error": type(exc).__name__,
        }


def _probe_docker(image: str) -> dict[str, Any]:
    binary = shutil.which("docker")
    if not binary:
        return {
            "installed": False,
            "healthy": False,
            "image_available": False,
            "image_smoke": False,
            "error": "not_installed",
        }
    try:
        daemon = subprocess.run(
            [binary, "info", "--format", "{{json .ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "installed": True,
            "healthy": False,
            "image_available": False,
            "image_smoke": False,
            "error": type(exc).__name__,
        }
    if daemon.returncode != 0:
        return {
            "installed": True,
            "healthy": False,
            "image_available": False,
            "image_smoke": False,
            "error": "daemon_unavailable",
        }
    try:
        inspected = subprocess.run(
            [binary, "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if inspected.returncode != 0:
            return {
                "installed": True,
                "healthy": True,
                "image_available": False,
                "image_smoke": False,
                "error": "sandbox_image_missing",
            }
        smoke = subprocess.run(
            [
                binary,
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
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "installed": True,
            "healthy": True,
            "image_available": True,
            "image_smoke": False,
            "error": type(exc).__name__,
        }
    return {
        "installed": True,
        "healthy": True,
        "image_available": True,
        "image_smoke": smoke.returncode == 0,
        "error": "" if smoke.returncode == 0 else "sandbox_image_smoke_failed",
        "smoke_stdout": smoke.stdout[-2000:],
        "smoke_stderr": smoke.stderr[-2000:],
    }


def production_readiness(
    control: AmauraControlPlane,
    *,
    live: bool = True,
) -> dict[str, object]:
    operator_key = os.environ.get("AMAURA_OPERATOR_KEY", "")
    approval_key = os.environ.get("AMAURA_APPROVAL_KEY", "")
    host = os.environ.get("JARVIS_HOST", "127.0.0.1")
    jarvis_key = os.environ.get("JARVIS_API_KEY", "")
    model_mode = os.environ.get("AMAURA_MODEL_MODE", "balanced").strip().lower()
    worker_model = os.environ.get("AMAURA_LOCAL_MODEL", "").strip()
    reviewer_model = os.environ.get("AMAURA_LOCAL_REVIEW_MODEL", "").strip()
    sandbox_mode = os.environ.get("AMAURA_SANDBOX_MODE", "docker").strip().lower()
    telegram_user = os.environ.get("TELEGRAM_USER_ID", "").strip()
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    prompts = load_prompt_catalogue()
    database = control.store.integrity_check()
    dockerfile = Path(__file__).resolve().parents[2] / "docker" / "amaura-sandbox.Dockerfile"
    dockerfile_text = dockerfile.read_text(encoding="utf-8") if dockerfile.is_file() else ""

    declared_tools = {tool for agent in ALL_AGENTS for tool in agent.tools}
    missing_tools = sorted(declared_tools - EXECUTABLE_EMPLOYEE_TOOLS)
    duplicate_agents = len(ALL_AGENTS) != len({agent.agent_id for agent in ALL_AGENTS})
    invalid_reviewers = sorted(
        agent.agent_id
        for agent in ALL_AGENTS
        if agent.agent_id != "jarvis"
        and agent.reviewer_id not in {"founder", *{item.agent_id for item in ALL_AGENTS}}
    )
    from jarvis.amaura.policy import PolicyEngine
    invalid_permission_agents = [
        agent.agent_id for agent in ALL_AGENTS
        if not PolicyEngine.validate_employee_permissions(agent.agent_id).allowed
    ]
    source_checks = {
        "database_integrity": bool(database["ok"]),
        "tamper_evident_audit_chain": bool(database["audit_chain"]["ok"]),
        "workforce_registry": len(ALL_AGENTS) >= 43 and not duplicate_agents,
        "workforce_tool_contract": not missing_tools,
        "workforce_permission_contract": not invalid_permission_agents,
        "reviewer_contract": not invalid_reviewers,
        "workflow_catalogue": {
            "client_acquisition",
            "content_factory",
            "software_delivery",
        }.issubset(WORKFLOWS),
        "founder_prompt_catalogue": len(prompts) >= 43
        and all(len(prompt) > 500 for prompt in prompts.values()),
        "durable_supervisor_store": isinstance(
            control.store.execution_status(),
            dict,
        ),
        "leased_outbox_delivery": all(
            hasattr(control.store, name)
            for name in (
                "claim_outbox_events",
                "recover_expired_outbox_events",
                "resolve_outbox_reconciliation",
            )
        ),
        "content_addressed_evidence": control.evidence.root.is_dir(),
        "durable_telemetry": isinstance(control.telemetry.snapshot(), dict),
        "sandbox_fail_closed": sandbox_mode == "docker"
        or (
            sandbox_mode == "host"
            and os.environ.get("AMAURA_ALLOW_HOST_EXECUTION") == "1"
        ),
        "sandbox_toolchain_contract": all(
            token in dockerfile_text
            for token in (
                "python:3.12-slim-bookworm",
                "node:22-bookworm-slim",
                "git",
                "ripgrep",
                "pytest==",
                "ruff==",
                "mypy==",
                "USER 10001:10001",
            )
        ),
    }
    configuration_checks = {
        "zero_cost_local_routing": model_mode == "local" and bool(worker_model),
        "distinct_reviewer_model": bool(reviewer_model)
        and reviewer_model != worker_model,
        "operator_key": _configured_secret("AMAURA_OPERATOR_KEY", minimum=24),
        "approval_key": _configured_secret("AMAURA_APPROVAL_KEY", minimum=24),
        "review_attestation_key": _configured_secret(
            "AMAURA_REVIEW_ATTESTATION_KEY"
        ),
        "provider_receipt_key": _configured_secret("AMAURA_PROVIDER_RECEIPT_KEY"),
        "keys_are_separate": len(
            {
                operator_key,
                approval_key,
                os.environ.get("AMAURA_REVIEW_ATTESTATION_KEY", ""),
                os.environ.get("AMAURA_PROVIDER_RECEIPT_KEY", ""),
            }
            - {""}
        )
        == 4,
        "loopback_binding": host in {"127.0.0.1", "localhost", "::1"},
        "remote_api_auth": host in {"127.0.0.1", "localhost", "::1"}
        or len(jarvis_key) >= 24,
        "telegram_founder_bound": not telegram_token or bool(telegram_user),
        "experimental_langgraph_disabled": os.environ.get(
            "AMAURA_ENABLE_EXPERIMENTAL_LANGGRAPH", "0"
        ) != "1",
        "strict_evidence_mode": os.environ.get("AMAURA_STRICT_EVIDENCE", "0") == "1",
        "strict_review_mode": os.environ.get("AMAURA_STRICT_REVIEW", "0") == "1",
        "strict_git_mode": os.environ.get("AMAURA_STRICT_GIT", "0") == "1",
        "post_merge_validation": bool(os.environ.get("AMAURA_POST_MERGE_COMMAND", "").strip()),
        "outbox_attempt_policy": int(os.environ.get("AMAURA_OUTBOX_MAX_ATTEMPTS", "3")) >= 1,
        "gmail_adapter": (
            os.environ.get("AMAURA_ENABLE_GMAIL") != "1"
            or bool(os.environ.get("AMAURA_GMAIL_ACCESS_TOKEN", ""))
        ),
        "private_publication_adapter": (
            os.environ.get("AMAURA_ENABLE_PUBLICATION") != "1"
            or bool(
                os.environ.get("AMAURA_PUBLICATION_ENDPOINT", "")
                and os.environ.get("AMAURA_PUBLICATION_ACCESS_TOKEN", "")
            )
        ),
    }

    backup_dir = Path(
        os.environ.get(
            "AMAURA_BACKUP_DIR",
            str(control.store.db_path.parent / "backups"),
        )
    ).expanduser()
    backup_parent = backup_dir if backup_dir.exists() else backup_dir.parent
    configuration_checks["backup_destination_writable"] = (
        backup_parent.exists() and os.access(backup_parent, os.W_OK)
    )

    live_details: dict[str, Any]
    if live:
        ollama = _probe_ollama(
            os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
            worker_model=worker_model,
            reviewer_model=reviewer_model,
        )
        docker = _probe_docker(
            os.environ.get("AMAURA_SANDBOX_IMAGE", "amaura-sandbox:1.2.0")
        )
        live_checks = {
            "ollama_reachable": ollama["reachable"],
            "worker_model_installed": ollama["worker_model_installed"],
            "reviewer_model_installed": ollama["reviewer_model_installed"],
            "docker_healthy": docker["healthy"],
            "sandbox_image_available": docker["image_available"],
            "sandbox_image_smoke": docker["image_smoke"],
        }
        live_details = {"ollama": ollama, "docker": docker}
    else:
        live_checks = {}
        live_details = {"skipped": True}

    all_checks = {
        **source_checks,
        **configuration_checks,
        **live_checks,
    }
    blockers = [name for name, passed in all_checks.items() if not passed]
    source_blockers = [
        name for name, passed in source_checks.items() if not passed
    ]
    return {
        "ready": not blockers,
        "production_ready": not blockers,
        "source_certified": not source_blockers,
        "source_ready": not source_blockers,
        "core_operational": all(
            source_checks[name]
            for name in (
                "database_integrity",
                "tamper_evident_audit_chain",
                "workforce_registry",
                "workforce_tool_contract",
                "reviewer_contract",
                "workflow_catalogue",
                "founder_prompt_catalogue",
                "durable_supervisor_store",
                "leased_outbox_delivery",
            )
        ),
        "checks": all_checks,
        "source_checks": source_checks,
        "configuration_checks": configuration_checks,
        "live_checks": live_checks,
        "blockers": blockers,
        "source_blockers": source_blockers,
        "details": {
            "missing_employee_tools": missing_tools,
            "invalid_reviewers": invalid_reviewers,
            "live": live_details,
        },
        "optional_integrations": [
            _integration_status(item) for item in OPTIONAL_INTEGRATIONS
        ],
        "note": (
            "Optional adapters are reported separately. Production readiness "
            "passes only when source, configuration, models, and isolation are real."
        ),
    }


INTEGRATIONS = OPTIONAL_INTEGRATIONS

__all__ = ["INTEGRATIONS", "OPTIONAL_INTEGRATIONS", "production_readiness"]
