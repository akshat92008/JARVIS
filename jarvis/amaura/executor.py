"""Governed worker execution: JARVIS dispatches, employees execute, reviewers verify."""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, ClassVar

from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.evidence import (
    create_review_attestation,
    deterministic_evidence_review,
)
from jarvis.amaura.models import GovernanceError, TaskState
from jarvis.amaura.network import fetch_public_text
from jarvis.amaura.policy import PATH_ARGUMENTS
from jarvis.amaura.registry import get_agent
from jarvis.amaura.sandbox import run_governed_command, StatefulDockerSandbox
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
        "index_codebase_ast": "root_dir",
        "search_symbol": "root_dir",
    }

    def __init__(self, control_plane: AmauraControlPlane, client_factory=None):
        self.control = control_plane
        self.client_factory = client_factory

    def _client(self, route: dict[str, Any], employee):
        if self.client_factory is not None:
            return self.client_factory(route, employee)
        if route["provider"] == "local":
            return _LocalOllamaClient()
        if os.environ.get("AMAURA_DISABLE_CLOUD") == "1":
            raise GovernanceError(
                "Cloud model access is disabled for this execution"
            )
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

    def _execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        execute_tool,
        sandbox: StatefulDockerSandbox | None = None,
    ) -> str:
        if tool_name == "web_fetch":
            result = fetch_public_text(
                str(args["url"]),
                max_length=int(args.get("max_length", 10_000)),
            )
            if result.startswith("❌"):
                return json.dumps({"ok": False, "data": {}, "error": result, "external_id": "", "retryable": False})
            return json.dumps({"ok": True, "data": {"output": result}, "error": None, "external_id": "", "retryable": False})
        if tool_name not in {"run_command", "run_tests", "lint_code"}:
            return execute_tool(tool_name, args)
        if tool_name == "run_tests":
            framework = str(args.get("framework", "") or "pytest")
            path = str(args.get("path", "."))
            test_filter = str(args.get("filter", ""))
            verbose = bool(args.get("verbose", True))
            commands: dict[str, list[str]] = {
                "pytest": ["python", "-m", "pytest", path],
                "unittest": ["python", "-m", "unittest", "discover", path],
                "jest": ["npx", "jest", path],
                "vitest": ["npx", "vitest", "run", path],
                "mocha": ["npx", "mocha", path],
                "go": ["go", "test", "./..." if path == "." else path],
                "cargo": ["cargo", "test"],
                "rspec": ["bundle", "exec", "rspec", path],
                "phpunit": ["./vendor/bin/phpunit", path],
            }
            tokens = commands[framework]
            if verbose and framework in {"pytest", "unittest", "jest", "go"}:
                tokens.append("-v" if framework != "jest" else "--verbose")
            if test_filter:
                if framework == "pytest":
                    tokens.extend(("-k", test_filter))
                elif framework == "go":
                    tokens.extend(("-run", test_filter))
                elif framework == "cargo":
                    tokens.append(test_filter)
            command = shlex.join(tokens)
        elif tool_name == "lint_code":
            linter = str(args.get("linter", "") or "ruff")
            path = str(args.get("path", "."))
            fix = bool(args.get("fix", False))
            commands = {
                "ruff": ["python", "-m", "ruff", "check", path],
                "flake8": ["python", "-m", "flake8", path],
                "eslint": ["npx", "eslint", path],
                "golangci-lint": ["golangci-lint", "run", path],
                "clippy": ["cargo", "clippy"],
            }
            tokens = commands[linter]
            if fix and linter in {"ruff", "eslint"}:
                tokens.append("--fix")
            command = shlex.join(tokens)
        else:
            command = str(args["command"])
        timeout = max(1, min(int(args.get("timeout", 120)), 300))
        try:
            if sandbox:
                completed = sandbox.run(command, timeout=timeout)
            else:
                completed = run_governed_command(
                    command,
                    workspace=str(args["cwd"]),
                    timeout=timeout,
                )
        except GovernanceError as exc:
            return json.dumps({"ok": False, "data": {}, "error": f"Cannot execute command: {exc}", "external_id": "", "retryable": False})
        output = completed.stdout
        if completed.stderr:
            output += ("\n" if output else "") + completed.stderr
        output = output.strip() or "(no output)"
        if completed.returncode != 0:
            return json.dumps({"ok": False, "data": {}, "error": f"Command failed (exit code {completed.returncode}):\n{output}", "external_id": "", "retryable": False})
        return json.dumps({"ok": True, "data": {"output": output}, "error": None, "external_id": "", "retryable": False})

    def run(self, task_id: str, max_iterations: int = 12) -> dict[str, Any]:
        max_iterations = max(1, min(max_iterations, 30))
        task = self.control.store.get_work_item(task_id)
        if task["state"] in {TaskState.ASSIGNED.value, TaskState.BLOCKED.value}:
            task = self.control.start_task(task_id, actor="jarvis")
        if task["state"] == TaskState.BLOCKED.value:
            return {"status": "blocked", "task": task, "reason": "Dependencies are incomplete"}
        if task["state"] != TaskState.IN_PROGRESS.value:
            raise GovernanceError(f"Task runner cannot execute state '{task['state']}'")

        packet_dict = self.control.task_packet(task_id, actor="jarvis")
        # P0-2: include repository_write (used by builder/patch_engineer in workflows.py)
        # in addition to software_delivery/engineering so worktrees are created correctly.
        if task["action_type"] in {"software_delivery", "engineering", "repository_write"} and packet_dict.get("_workspace"):
            workspace = packet_dict["_workspace"]
            if os.path.isdir(os.path.join(workspace, ".git")):
                wt_path = f"/tmp/amaura-worktrees/{task_id}"
                os.makedirs("/tmp/amaura-worktrees", exist_ok=True)
                if not os.path.exists(wt_path):
                    res = subprocess.run(["git", "worktree", "add", "-B", f"amaura-{task_id}", wt_path, "HEAD"], cwd=workspace, capture_output=True)
                    if res.returncode != 0:
                        raise GovernanceError(f"Failed to create git worktree: {res.stderr.decode()}")
                packet_dict["_workspace"] = wt_path
                packet_dict["repository_context"]["workspace_dir"] = wt_path

        route = packet_dict.pop("_model_route")
        workspace = packet_dict.pop("_workspace")
        approved_names = set(packet_dict.pop("_approved_tools"))

        from jarvis.amaura.models import CanonicalTaskPacket
        packet_model = CanonicalTaskPacket.model_validate(packet_dict)
        clean_packet = packet_model.model_dump(mode="json")

        from jarvis.tools.registry import ALL_TOOL_DEFINITIONS, execute_tool

        employee = get_agent(task["owner_id"])
        local_only = route["provider"] == "local"
        model_cfg = {"id": os.environ.get("AMAURA_LOCAL_MODEL", "nova:3b"), "supports_tools": True} if local_only else (resolve_model(route["model_key"]) or MODELS[DEFAULT_MODEL])
        tools = [definition for definition in ALL_TOOL_DEFINITIONS if definition["function"]["name"] in approved_names]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": employee.system_prompt + "\n\nReturn a concise completion summary. Do not claim success unless tool results support it."},
            {"role": "user", "content": "JARVIS TASK PACKET:\n" + json.dumps(clean_packet, indent=2)},
        ]
        client = self._client(route, employee)
        evidence: list[dict[str, Any]] = []
        final_response = ""
        iterations = 0
        response = None  # holds last LLM response for model_execution_receipt (P0-8)

        sandbox = None
        sandbox_mode = os.environ.get("AMAURA_SANDBOX_MODE", "docker").strip().lower()
        if sandbox_mode == "docker":
            try:
                sandbox = StatefulDockerSandbox(workspace=workspace)
            except GovernanceError as exc:
                sandbox_error = str(exc)
                record = self.control.evidence.put_text(sandbox_error, source=f"task:{task_id}:sandbox_init_failure")
                evidence.append({
                    "type": "sandbox_init_failure",
                    "reference": record.reference,
                    "sha256": record.sha256,
                    "byte_length": record.byte_length,
                    "success": False,
                    "excerpt": sandbox_error[:500],
                })
        
        try:
            for iteration in range(1, max_iterations + 1):
                iterations = iteration
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
                        args["cwd"] = workspace
                    scoped_args = self._scope_tool_args(call.function.name, args, workspace)
                    self.control.authorize_tool(task_id, employee.agent_id, call.function.name, scoped_args)
                    result = self._execute_tool(
                        call.function.name,
                        scoped_args,
                        execute_tool,
                        sandbox=sandbox,
                    )
                    record = self.control.evidence.put_text(
                        result,
                        source=f"task:{task_id}:tool:{call.function.name}",
                    )
                    try:
                        parsed_result = json.loads(result)
                        success = parsed_result.get("ok", False)
                        excerpt_str = str(parsed_result.get("data", {}).get("output", result))
                        if parsed_result.get("error"):
                            excerpt_str += "\nError: " + str(parsed_result["error"])
                    except Exception:
                        success = not result.startswith("❌")
                        excerpt_str = result

                    evidence.append(
                        {
                            "type": "tool_result",
                            "reference": record.reference,
                            "sha256": record.sha256,
                            "byte_length": record.byte_length,
                            "tool": call.function.name,
                            "success": success,
                            "excerpt": excerpt_str[:500],
                        }
                    )
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            else:
                raise GovernanceError(f"Employee exceeded the {max_iterations}-iteration execution limit")
        finally:
            if sandbox:
                sandbox.close()

        if not final_response:
            raise GovernanceError("Employee returned no completion summary")
        if not evidence:
            if task.get("acceptance_criteria"):
                raise GovernanceError("Employee submitted no verifiable evidence to satisfy acceptance criteria. Agent prose is insufficient.")
            record = self.control.evidence.put_text(
                final_response,
                source=f"task:{task_id}:agent_output",
            )
            evidence.append(
                {
                    "type": "agent_output",
                    "reference": record.reference,
                    "sha256": record.sha256,
                    "byte_length": record.byte_length,
                    "success": True,
                    "excerpt": final_response[:500],
                }
            )

        estimated_cost = route["estimated_cost_cents"]
        # P0-8: record the actual model and provider for every inference, not just the route name.
        # The provider may have remapped the requested model to a fallback.
        last_usage = getattr(response, "usage", None) if response is not None else None
        model_execution_receipt = {
            "requested_route": route["model_key"],
            "actual_model": getattr(response, "model", route["model_key"]) if response is not None else route["model_key"],
            "provider": route["provider"],
            "fallback_model_key": route.get("fallback_model_key"),
            "sandbox_mode": sandbox_mode,
            "container_id": getattr(sandbox, "container_id", None) if sandbox else None,
            "input_tokens": getattr(last_usage, "prompt_tokens", 0) if last_usage else 0,
            "output_tokens": getattr(last_usage, "completion_tokens", 0) if last_usage else 0,
            "estimated_cost_cents": estimated_cost,
            "iterations": iterations,
        }
        receipt_record = self.control.evidence.put_json(
            model_execution_receipt,
            source=f"task:{task_id}:model_execution_receipt",
        )
        evidence.append(
            {
                "type": "model_execution_receipt",
                "reference": receipt_record.reference,
                "sha256": receipt_record.sha256,
                "byte_length": receipt_record.byte_length,
                "success": True,
                "excerpt": f"model={model_execution_receipt['actual_model']} provider={model_execution_receipt['provider']} tokens={model_execution_receipt['input_tokens']}+{model_execution_receipt['output_tokens']}",
            }
        )
        if estimated_cost:
            self.control.record_cost(task_id, employee.agent_id, estimated_cost, "model_inference", metadata=model_execution_receipt)
        submitted = self.control.submit_task(task_id, employee.agent_id, final_response, evidence)
        return {
            "status": submitted["state"],
            "task_id": task_id,
            "employee": employee.name,
            "iterations": iterations,
            "summary": final_response,
            "evidence": evidence,
            "model_execution_receipt": model_execution_receipt,
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

        worker_model = os.environ.get("AMAURA_LOCAL_MODEL", "nova:3b").strip()
        model_id = (
            os.environ.get("AMAURA_LOCAL_REVIEW_MODEL", "").strip()
            or worker_model
        )
        if model_id == worker_model:
            raise GovernanceError(
                "Independent automated review requires a model distinct from "
                "AMAURA_LOCAL_MODEL"
            )
        deterministic = deterministic_evidence_review(task, self.control.evidence)
        failed_evidence = [
            item for item in task["evidence"] if item.get("success") is False
        ]
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
        response = self._client(reviewer).chat_sync(model_id=model_id, messages=messages, tools=None)
        content = response.choices[0].message.content or ""
        decision = _extract_json_object(content)
        approve = decision.get("approve")
        findings = decision.get("findings")
        if not isinstance(approve, bool) or not isinstance(findings, str) or not findings.strip():
            raise GovernanceError("Reviewer decision is missing approve/findings")
        if not deterministic["approve"]:
            approve = False
            deterministic_findings = "; ".join(deterministic["findings"])
            findings = (
                "Rejected by deterministic evidence verification: "
                f"{deterministic_findings}. {findings.strip()}"
            )
        decision = {
            "approve": approve,
            "findings": findings.strip(),
            "criteria": decision.get("criteria", []),
        }
        attestation = create_review_attestation(
            task_id=task_id,
            reviewer_id=reviewer_id,
            reviewer_model=model_id,
            decision=decision,
            deterministic_review=deterministic,
        )
        self.control.store.record_review_attestation(attestation)
        updated = self.control.review_task(task_id, actor=reviewer_id, approve=approve, findings=findings.strip(), attestation=attestation)
        self.control.store.audit(
            reviewer_id,
            "automated_independent_review",
            "task",
            task_id,
            "approved" if approve else "rejected",
            {
                "model": model_id,
                "criteria": decision.get("criteria", []),
                "failed_evidence": len(failed_evidence),
                "submission_sha256": deterministic["submission_sha256"],
                "attestation_signature": attestation["signature"],
            },
        )
        return {
            "task_id": task_id,
            "reviewer_id": reviewer_id,
            "reviewer_model": model_id,
            "approve": approve,
            "findings": findings.strip(),
            "state": updated["state"],
            "criteria": decision.get("criteria", []),
            "deterministic_review": deterministic,
            "attestation": attestation,
        }
