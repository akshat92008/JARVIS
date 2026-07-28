"""Production-readiness checks for the local Amaura operating kernel."""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    required_for_core: bool = False


INTEGRATIONS = (
    Integration("PydanticAI", "python", "pydantic_ai"),
    Integration("LangGraph", "python", "langgraph"),
    Integration("DBOS", "python", "dbos"),
    Integration("LiteLLM", "python", "litellm"),
    Integration("OpenTelemetry", "python", "opentelemetry"),
    Integration("FFmpeg", "binary", "ffmpeg"),
    Integration("Ollama", "binary", "ollama"),
    Integration("Crawl4AI", "python", "crawl4ai"),
    Integration("OBS", "binary", "obs"),
    Integration("Promptfoo", "binary", "promptfoo"),
    Integration("Docker/OpenSandbox host", "binary", "docker"),
)


def _integration_status(integration: Integration) -> dict[str, object]:
    if integration.kind == "python":
        available = importlib.util.find_spec(integration.probe) is not None
    else:
        available = shutil.which(integration.probe) is not None
    return {"name": integration.name, "available": available, "required_for_core": integration.required_for_core, "probe": integration.probe}


def production_readiness(control: AmauraControlPlane) -> dict[str, object]:
    operator_key = os.environ.get("AMAURA_OPERATOR_KEY", "")
    approval_key = os.environ.get("AMAURA_APPROVAL_KEY", "")
    host = os.environ.get("JARVIS_HOST", "127.0.0.1")
    jarvis_key = os.environ.get("JARVIS_API_KEY", "")
    model_mode = os.environ.get("AMAURA_MODEL_MODE", "balanced").strip().lower()
    local_model = os.environ.get("AMAURA_LOCAL_MODEL", "").strip()
    telegram_user = os.environ.get("TELEGRAM_USER_ID", "").strip()
    prompts = load_prompt_catalogue()
    database = control.store.integrity_check()
    checks = {
        "database_integrity": database["ok"],
        "tamper_evident_audit_chain": database["audit_chain"]["ok"],
        "workforce_registry": len(ALL_AGENTS) >= 40 and len({a.agent_id for a in ALL_AGENTS}) == len(ALL_AGENTS),
        "workflow_catalogue": {"client_acquisition", "content_factory", "software_delivery"}.issubset(WORKFLOWS),
        "founder_prompt_catalogue": len(prompts) == 5 and all(len(prompt) > 500 for prompt in prompts.values()),
        "durable_supervisor_store": isinstance(control.store.execution_status(), dict),
        "zero_cost_local_routing": model_mode == "local" and bool(local_model),
        "telegram_founder_bound": bool(telegram_user),
        "operator_key": len(operator_key) >= 24,
        "approval_key": len(approval_key) >= 24,
        "keys_are_separate": bool(operator_key and approval_key and operator_key != approval_key),
        "loopback_binding": host in {"127.0.0.1", "localhost", "::1"},
        "remote_api_auth": host in {"127.0.0.1", "localhost", "::1"} or len(jarvis_key) >= 24,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    integrations = [_integration_status(item) for item in INTEGRATIONS]
    return {
        "ready": not blockers,
        "core_operational": all(
            checks[name] for name in ("database_integrity", "tamper_evident_audit_chain", "workforce_registry", "workflow_catalogue", "founder_prompt_catalogue", "durable_supervisor_store")
        ),
        "checks": checks,
        "blockers": blockers,
        "optional_integrations": integrations,
        "note": "Optional adapters extend the kernel; they are not silently treated as configured.",
    }


__all__ = ["INTEGRATIONS", "production_readiness"]
