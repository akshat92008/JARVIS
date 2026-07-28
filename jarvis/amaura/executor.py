"""Governed worker execution: JARVIS dispatches, employees execute, reviewers verify."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.models import GovernanceError, TaskState
from jarvis.amaura.policy import PATH_ARGUMENTS
from jarvis.amaura.registry import get_agent
from jarvis.models import DEFAULT_MODEL, MODELS, resolve_model


class _LocalOllamaClient:
    """Device-only OpenAI-compatible client with no cloud fallback."""

    def __init__(self):
        from openai import OpenAI

        base_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self._client = OpenAI(base_url=f"{base_url}/v1", api_key="ollama", timeout=120.0)

    def chat_sync(self, *, model_id: str, messages: list[dict], tools: list[dict] | None = None):
        kwargs: dict[str, Any] = {"model": model_id, "messages": messages, "temperature": 0.2}
        if tools:
            kwargs["tools"] = tools
        try:
            return self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise GovernanceError("Device-only inference failed; no cloud fallback was attempted. Start Ollama and configure AMAURA_LOCAL_MODEL.") from exc


class GovernedTaskRunner:
    """Runs one company employee strictly inside a JARVIS-issued task packet."""

    _WORKSPACE_DEFAULT_ARGUMENTS: ClassVar[dict[str, str]] = {
        "search_code": "directory",
        "find_files": "directory",
        "get_project_structure": "path",
        "run_command": "cwd",
        "run_tests": "cwd",
        "lint_code": "cwd",
        "analyze_code": "cwd",
        "git_status": "cwd",
        "git_diff": "cwd",
        "git_log": "cwd",
        "index_repository": "repo_path",
        "query_symbols": "repo_path",
    }

    def __init__(self, control_plane: AmauraControlPlane, client_factory=None):
        self.control = control_plane
        self.client_factory = client_factory

    def _client(self, route: dict[str, Any], employee):
        if self.client_factory is not None:
            return self.client_factory(route, employee)
        if route["provider"] == "local":
            return _LocalOllamaClient()
        from jarvis.api import NvidiaClient

        agent_key = os.getenv(f"NVIDIA_API_KEY_{employee.agent_id.upper()}")
        return NvidiaClient(api_key=agent_key)

    @classmethod
    def _scope_tool_args(cls, tool_name: str, args: dict[str, Any], workspace: str) -> dict[str, Any]:
        """Make policy validation and actual tool execution resolve the same paths."""
        scoped = dict(args)
        default_argument = cls._WORKSPACE_DEFAULT_ARGUMENTS.get(tool_name)
        if default_argument and not scoped.get(default_argument):
            scoped[default_argument] = workspace
        root = Path(workspace).expanduser().resolve()
        for key, raw_value in list(scoped.items()):
            if key not in PATH_ARGUMENTS or not isinstance(raw_value, str) or not raw_value:
                continue
            candidate = Path(raw_value).expanduser()
            if not candidate.is_absolute():
                candidate = root / candidate
            scoped[key] = str(candidate.resolve())
        return scoped

    @staticmethod
    def _execute_tool(tool_name: str, args: dict[str, Any], execute_tool) -> str:
        if tool_name != "run_command":
            return execute_tool(tool_name, args)
        command = shlex.split(str(args["command"]))
        timeout = max(1, min(int(args.get("timeout", 120)), 300))
        allowed_environment = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "PYTHONPATH", "VIRTUAL_ENV"}}
        allowed_environment.update({"PAGER": "cat", "GIT_PAGER": "cat", "CI": "1"})
        try:
            completed = subprocess.run(command, shell=False, cwd=args.get("cwd"), capture_output=True, text=True, timeout=timeout, env=allowed_environment, check=False)
        except subprocess.TimeoutExpired:
            return f"❌ Command timed out after {timeout}s: {args['command']}"
        except OSError as exc:
            return f"❌ Cannot execute command: {exc}"
        output = completed.stdout
        if completed.stderr:
            output += ("\n" if output else "") + completed.stderr
        output = output.strip() or "(no output)"
        if completed.returncode != 0:
            return f"❌ Command failed (exit code {completed.returncode}):\n{output}"
        return output

    def run(self, task_id: str, max_iterations: int = 12) -> dict[str, Any]:
        max_iterations = max(1, min(max_iterations, 30))
        task = self.control.store.get_work_item(task_id)
        if task["state"] in {TaskState.ASSIGNED.value, TaskState.BLOCKED.value}:
            task = self.control.start_task(task_id, actor="jarvis")
        if task["state"] == TaskState.BLOCKED.value:
            return {"status": "blocked", "task": task, "reason": "Dependencies are incomplete"}
        if task["state"] != TaskState.IN_PROGRESS.value:
            raise GovernanceError(f"Task runner cannot execute state '{task['state']}'")

        packet = self.control.task_packet(task_id, actor="jarvis")
        route = packet["model_route"]
        from jarvis.tools.registry import ALL_TOOL_DEFINITIONS, execute_tool

        employee = get_agent(task["owner_id"])
        local_only = route["provider"] == "local"
        model_cfg = {"id": os.environ.get("AMAURA_LOCAL_MODEL", "nova:3b"), "supports_tools": True} if local_only else (resolve_model(route["model_key"]) or MODELS[DEFAULT_MODEL])
        approved_names = set(packet["approved_tools"])
        tools = [definition for definition in ALL_TOOL_DEFINITIONS if definition["function"]["name"] in approved_names]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": employee.system_prompt + "\n\nReturn a concise completion summary. Do not claim success unless tool results support it."},
            {"role": "user", "content": "JARVIS TASK PACKET:\n" + json.dumps(packet, indent=2)},
        ]
        client = self._client(route, employee)
        evidence: list[dict[str, Any]] = []
        final_response = ""
        iterations = 0

        for iterations in range(1, max_iterations + 1):
            response = client.chat_sync(model_id=model_cfg["id"], messages=messages, tools=tools if model_cfg.get("supports_tools") and tools else None)
            choice = response.choices[0]
            content = choice.message.content or ""
            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                final_response = content.strip()
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [{"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}} for call in tool_calls],
                }
            )
            for call in tool_calls:
                try:
                    args = json.loads(call.function.arguments)
                except json.JSONDecodeError as exc:
                    raise GovernanceError(f"Employee produced invalid arguments for {call.function.name}") from exc
                if call.function.name == "run_command" and not args.get("cwd"):
                    args["cwd"] = packet["workspace"]
                scoped_args = self._scope_tool_args(call.function.name, args, packet["workspace"])
                self.control.authorize_tool(task_id, employee.agent_id, call.function.name, scoped_args)
                result = self._execute_tool(call.function.name, scoped_args, execute_tool)
                digest = hashlib.sha256(result.encode("utf-8", errors="replace")).hexdigest()[:16]
                evidence.append({"type": "tool_result", "reference": f"{call.function.name}:sha256:{digest}", "success": not result.startswith("❌"), "excerpt": result[:500]})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        else:
            raise GovernanceError(f"Employee exceeded the {max_iterations}-iteration execution limit")

        if not final_response:
            raise GovernanceError("Employee returned no completion summary")
        if not evidence:
            digest = hashlib.sha256(final_response.encode()).hexdigest()[:16]
            evidence.append({"type": "agent_output", "reference": f"response:sha256:{digest}", "success": True})

        estimated_cost = route["estimated_cost_cents"]
        if estimated_cost:
            self.control.record_cost(task_id, employee.agent_id, estimated_cost, "model_inference", metadata={"model": route["model_key"], "iterations": iterations})
        submitted = self.control.submit_task(task_id, employee.agent_id, final_response, evidence)
        return {
            "status": submitted["state"],
            "task_id": task_id,
            "employee": employee.name,
            "iterations": iterations,
            "summary": final_response,
            "evidence": evidence,
            "reviewer": submitted["reviewer_id"],
        }


def _extract_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, count=1, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate, count=1)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        raise GovernanceError("Reviewer returned no JSON decision")
    try:
        value = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GovernanceError("Reviewer returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise GovernanceError("Reviewer decision must be a JSON object")
    return value


class GovernedReviewRunner:
    """Run the registered independent reviewer without granting founder authority."""

    def __init__(self, control_plane: AmauraControlPlane, client_factory=None):
        self.control = control_plane
        self.client_factory = client_factory

    def _client(self, reviewer):
        route = {"provider": "local", "model_key": "ollama-local"}
        if self.client_factory is not None:
            return self.client_factory(route, reviewer)
        return _LocalOllamaClient()

    def run(self, task_id: str) -> dict[str, Any]:
        task = self.control.store.get_work_item(task_id)
        if task["state"] != TaskState.AWAITING_REVIEW.value:
            raise GovernanceError("Task is not awaiting independent review")
        reviewer_id = task["reviewer_id"]
        if not reviewer_id or reviewer_id == "founder":
            raise GovernanceError("Founder approval cannot be automated")
        if reviewer_id == task["owner_id"]:
            raise GovernanceError("No agent may certify its own work")
        self.control._ensure_agent_enabled(reviewer_id)
        reviewer = get_agent(reviewer_id)

        failed_evidence = [item for item in task["evidence"] if item.get("success") is False]
        review_packet = {
            "task_id": task["id"],
            "title": task["title"],
            "objective": task["description"],
            "acceptance_criteria": task["acceptance_criteria"],
            "submission_summary": task["summary"],
            "evidence": task["evidence"],
            "risk": task["risk"],
            "action_type": task["action_type"],
            "rules": ["Reject unsupported completion claims.", "Reject when any acceptance criterion lacks evidence.", "Never infer that a tool or test succeeded.", "Return JSON only."],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    reviewer.system_prompt + "\n\nAct as an independent verifier. Return exactly one JSON object with "
                    '"approve" (boolean), "findings" (non-empty string), and '
                    '"criteria" (array of objects with criterion, passed, evidence).'
                ),
            },
            {"role": "user", "content": "INDEPENDENT REVIEW PACKET:\n" + json.dumps(review_packet, indent=2)},
        ]
        model_id = os.environ.get("AMAURA_LOCAL_REVIEW_MODEL") or os.environ.get("AMAURA_LOCAL_MODEL", "nova:3b")
        response = self._client(reviewer).chat_sync(model_id=model_id, messages=messages, tools=None)
        content = response.choices[0].message.content or ""
        decision = _extract_json_object(content)
        approve = decision.get("approve")
        findings = decision.get("findings")
        if not isinstance(approve, bool) or not isinstance(findings, str) or not findings.strip():
            raise GovernanceError("Reviewer decision is missing approve/findings")
        if failed_evidence:
            approve = False
            findings = "Rejected deterministically because submitted evidence contains failed tool results. " + findings.strip()
        updated = self.control.review_task(task_id, actor=reviewer_id, approve=approve, findings=findings.strip())
        self.control.store.audit(
            reviewer_id,
            "automated_independent_review",
            "task",
            task_id,
            "approved" if approve else "rejected",
            {"model": model_id, "criteria": decision.get("criteria", []), "failed_evidence": len(failed_evidence)},
        )
        return {"task_id": task_id, "reviewer_id": reviewer_id, "approve": approve, "findings": findings.strip(), "state": updated["state"], "criteria": decision.get("criteria", [])}
