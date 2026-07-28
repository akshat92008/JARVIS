"""Central policy enforcement for Amaura agent actions."""

from __future__ import annotations

import ipaddress
import json
import re
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jarvis.amaura.models import RISK_ORDER, GovernanceError, PolicyDecision, RiskLevel
from jarvis.amaura.registry import get_agent

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+-]{16,}", re.IGNORECASE),
)

EXTERNAL_ACTIONS = {
    "external_proposal",
    "client_commitment",
    "public_content",
    "public_publish",
    "production_deployment",
    "model_release",
    "payment",
    "refund",
    "contract_acceptance",
    "external_outreach",
}

TOOL_RISK_CLASSES = {
    "R0": {"read_file", "search_code", "find_files", "get_project_structure", "vector_search", "query_symbols"},
    "R1": {"web_search", "web_fetch", "read_pdf"},
    "R2": {"write_file", "edit_file", "create_document", "create_presentation", "run_command", "run_tests"},
    "R3": {"send_email", "send_message", "schedule_post", "publish_content", "create_gmail_draft"},
    "R4": {"payment", "refund", "delete_data", "production_deploy"},
}


def tool_risk_class(tool_name: str) -> str:
    for risk_class, names in TOOL_RISK_CLASSES.items():
        if tool_name in names:
            return risk_class
    return "R2"


PATH_ARGUMENTS = {"path", "file_path", "directory", "cwd", "repo_path", "project_path", "output_path"}
SHELL_METACHARACTERS = re.compile(r"[;&|><`\n\r]|\$")
SHELL_BACKED_ARGUMENTS = {"run_tests": {"framework", "filter"}, "lint_code": {"linter"}, "git_diff": {"target"}}
SAFE_COMMAND_PREFIXES = (
    ("pytest",),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("ruff",),
    ("mypy",),
    ("tsc",),
    ("rg",),
    ("ls",),
    ("git", "status"),
    ("git", "diff"),
    ("git", "log"),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "build"),
    ("npm", "run", "lint"),
    ("pnpm", "test"),
    ("pnpm", "build"),
    ("pnpm", "lint"),
    ("cargo", "test"),
    ("cargo", "check"),
    ("go", "test"),
)


def _public_http_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False, "Malformed URL"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "Only absolute HTTP(S) URLs are allowed"
    if parsed.username or parsed.password:
        return False, "URLs containing credentials are not allowed"
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")) or hostname in {"metadata.google.internal", "metadata.aws.internal"}:
        return False, "Local and metadata-service hosts are blocked"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True, ""
    if not address.is_global:
        return (False, "Private, loopback, link-local, and reserved network addresses are blocked")
    return True, ""


class PolicyEngine:
    """Evaluates authority, tool, data, cost, risk, and secret-handling rules."""

    @staticmethod
    def validate_assignment(task: dict[str, Any]) -> PolicyDecision:
        agent = get_agent(task["owner_id"])
        risk = RiskLevel(task["risk"])
        reasons: list[str] = []
        if RISK_ORDER[risk] > RISK_ORDER[agent.max_risk]:
            reasons.append(f"{agent.name} may not own {risk.value}-risk work")
        if task["budget_cents"] > agent.cost_limit_cents:
            reasons.append(f"Task budget {task['budget_cents']}c exceeds {agent.name}'s {agent.cost_limit_cents}c limit")
        if task.get("reviewer_id") == task["owner_id"]:
            reasons.append("No agent may review its own work")
        return PolicyDecision(allowed=not reasons, reasons=tuple(reasons))

    @staticmethod
    def validate_tool_action(task: dict[str, Any], agent_id: str, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
        agent = get_agent(agent_id)
        reasons: list[str] = []
        if task.get("state") != "in_progress":
            reasons.append("Employee tools may run only while the assigned task is in progress")
        if task["owner_id"] != agent_id:
            reasons.append("Only the assigned employee may execute this task")
        if tool_name not in agent.tools:
            reasons.append(f"Tool '{tool_name}' is outside {agent.name}'s approved tool set")
        risk_class = tool_risk_class(tool_name)
        if risk_class in {"R3", "R4"}:
            reasons.append(f"{risk_class} tool '{tool_name}' must execute through an authenticated founder approval adapter")
        serialized = json.dumps(args, default=str)
        if any(pattern.search(serialized) for pattern in SECRET_PATTERNS):
            reasons.append("Potential credential or secret detected in action payload")
        workspace = Path(task.get("metadata", {}).get("workspace", ".")).expanduser().resolve()
        for key, raw_value in args.items():
            if key not in PATH_ARGUMENTS or not isinstance(raw_value, str) or not raw_value:
                continue
            if SHELL_METACHARACTERS.search(raw_value):
                reasons.append(f"Path argument '{key}' contains unsafe shell characters")
                continue
            candidate = Path(raw_value).expanduser()
            if not candidate.is_absolute():
                candidate = workspace / candidate
            candidate = candidate.resolve()
            if candidate != workspace and workspace not in candidate.parents:
                reasons.append(f"Path argument '{key}' escapes the assigned workspace")
        if tool_name == "web_fetch":
            safe_url, url_reason = _public_http_url(str(args.get("url", "")))
            if not safe_url:
                reasons.append(f"Web fetch blocked: {url_reason}")
        for argument in SHELL_BACKED_ARGUMENTS.get(tool_name, set()):
            value = args.get(argument)
            if isinstance(value, str) and SHELL_METACHARACTERS.search(value):
                reasons.append(f"Shell-backed argument '{argument}' contains unsafe characters")
        if tool_name == "run_tests":
            framework = str(args.get("framework", "")).strip()
            if framework and framework not in {"pytest", "unittest", "jest", "vitest", "mocha", "go", "cargo", "rspec", "phpunit"}:
                reasons.append("Test framework is outside the governed allowlist")
        if tool_name == "git_diff":
            target = str(args.get("target", "")).strip()
            if target.startswith("-") or (target and not re.fullmatch(r"[A-Za-z0-9_./~^:@{}+-]+", target)):
                reasons.append("Git diff target is not a safe revision")
        if tool_name == "run_command":
            command = str(args.get("command", "")).strip()
            if SHELL_METACHARACTERS.search(command):
                reasons.append("Shell operators, substitutions, and redirections are not allowed for company employees")
            try:
                tokens = tuple(shlex.split(command))
            except ValueError:
                tokens = ()
                reasons.append("Command could not be parsed safely")
            if not tokens:
                reasons.append("Empty commands are not allowed")
            elif not any(tokens[: len(prefix)] == prefix for prefix in SAFE_COMMAND_PREFIXES):
                reasons.append("Command is outside the governed test/build/read-only allowlist")
        risk = RiskLevel(task["risk"])
        manual = risk is RiskLevel.CRITICAL or risk_class == "R4"
        requires_approval = manual or risk in {RiskLevel.MEDIUM, RiskLevel.HIGH} or task["action_type"] in EXTERNAL_ACTIONS
        return PolicyDecision(
            allowed=not reasons and not manual,
            requires_approval=requires_approval,
            manual_execution=manual,
            reasons=tuple(reasons or (["Critical actions require explicit manual execution"] if manual else [])),
        )

    @staticmethod
    def completion_gate(task: dict[str, Any]) -> PolicyDecision:
        risk = RiskLevel(task["risk"])
        evidence = task.get("evidence") or []
        reasons: list[str] = []
        if not evidence:
            reasons.append("Completion requires verifiable evidence")
        if task["action_type"] in EXTERNAL_ACTIONS and not evidence:
            reasons.append("No external claim or commitment may proceed without evidence")
        return PolicyDecision(
            allowed=not reasons,
            requires_approval=risk in {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL} or task["action_type"] in EXTERNAL_ACTIONS,
            manual_execution=risk is RiskLevel.CRITICAL,
            reasons=tuple(reasons),
        )

    @staticmethod
    def require_allowed(decision: PolicyDecision) -> None:
        if not decision.allowed:
            raise GovernanceError("; ".join(decision.reasons))
