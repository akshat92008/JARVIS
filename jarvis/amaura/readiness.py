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


def _probe_docker() -> dict[str, Any]:
    binary = shutil.which("docker")
    if not binary:
        return {"installed": False, "healthy": False, "error": "not_installed"}
    try:
        completed = subprocess.run(
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
            "error": type(exc).__name__,
        }
    return {
        "installed": True,
        "healthy": completed.returncode == 0,
        "error": "" if completed.returncode == 0 else "daemon_unavailable",
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
    prompts = load_prompt_catalogue()
    database = control.store.integrity_check()

    declared_tools = {tool for agent in ALL_AGENTS for tool in agent.tools}
    missing_tools = sorted(declared_tools - EXECUTABLE_EMPLOYEE_TOOLS)
    duplicate_agents = len(ALL_AGENTS) != len({agent.agent_id for agent in ALL_AGENTS})
    invalid_reviewers = sorted(
        agent.agent_id
        for agent in ALL_AGENTS
        if agent.agent_id != "jarvis"
        and agent.reviewer_id not in {"founder", *{item.agent_id for item in ALL_AGENTS}}
    )
    source_checks = {
        "database_integrity": bool(database["ok"]),
        "tamper_evident_audit_chain": bool(database["audit_chain"]["ok"]),
        "workforce_registry": len(ALL_AGENTS) == 43 and not duplicate_agents,
        "workforce_tool_contract": not missing_tools,
        "reviewer_contract": not invalid_reviewers,
        "workflow_catalogue": {
            "client_acquisition",
            "content_factory",
            "software_delivery",
        }.issubset(WORKFLOWS),
        "founder_prompt_catalogue": len(prompts) == 5
        and all(len(prompt) > 500 for prompt in prompts.values()),
        "durable_supervisor_store": isinstance(
            control.store.execution_status(),
            dict,
        ),
        "content_addressed_evidence": control.evidence.root.is_dir(),
        "durable_telemetry": isinstance(control.telemetry.snapshot(), dict),
        "sandbox_fail_closed": sandbox_mode == "docker"
        or (
            sandbox_mode == "host"
            and os.environ.get("AMAURA_ALLOW_HOST_EXECUTION") == "1"
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
        "telegram_founder_bound": bool(telegram_user),
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
        docker = _probe_docker()
        live_checks = {
            "ollama_reachable": ollama["reachable"],
            "worker_model_installed": ollama["worker_model_installed"],
            "reviewer_model_installed": ollama["reviewer_model_installed"],
            "docker_healthy": docker["healthy"],
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
