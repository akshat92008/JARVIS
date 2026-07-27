"""Governed worker execution: JARVIS dispatches, employees execute, reviewers verify."""

from __future__ import annotations

import os
import hashlib
import json
from typing import Any

from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.models import GovernanceError, TaskState
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
            raise GovernanceError(
                "Device-only inference failed; no cloud fallback was attempted. "
                "Start Ollama and configure AMAURA_LOCAL_MODEL."
            ) from exc


class GovernedTaskRunner:
    """Runs one company employee strictly inside a JARVIS-issued task packet."""

    def __init__(self, control_plane: AmauraControlPlane):
        self.control = control_plane

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
        from jarvis.api import NvidiaClient
        from jarvis.tools.registry import ALL_TOOL_DEFINITIONS, execute_tool

        employee = get_agent(task["owner_id"])
        local_only = route["provider"] == "local"
        model_cfg = (
            {"id": os.environ.get("AMAURA_LOCAL_MODEL", "qwen2.5-coder:1.5b"), "supports_tools": True}
            if local_only else (resolve_model(route["model_key"]) or MODELS[DEFAULT_MODEL])
        )
        approved_names = set(packet["approved_tools"])
        tools = [definition for definition in ALL_TOOL_DEFINITIONS if definition["function"]["name"] in approved_names]
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": employee.system_prompt
                + "\n\nReturn a concise completion summary. Do not claim success unless tool results support it.",
            },
            {"role": "user", "content": "JARVIS TASK PACKET:\n" + json.dumps(packet, indent=2)},
        ]
        agent_key = os.getenv(f"NVIDIA_API_KEY_{employee.agent_id.upper()}")
        client = _LocalOllamaClient() if local_only else NvidiaClient(api_key=agent_key)
        evidence: list[dict[str, Any]] = []
        final_response = ""
        iterations = 0

        for iterations in range(1, max_iterations + 1):
            response = client.chat_sync(
                model_id=model_cfg["id"],
                messages=messages,
                tools=tools if model_cfg.get("supports_tools") and tools else None,
            )
            choice = response.choices[0]
            content = choice.message.content or ""
            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                final_response = content.strip()
                break

            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                    for call in tool_calls
                ],
            })
            for call in tool_calls:
                try:
                    args = json.loads(call.function.arguments)
                except json.JSONDecodeError as exc:
                    raise GovernanceError(f"Employee produced invalid arguments for {call.function.name}") from exc
                if call.function.name == "run_command" and not args.get("cwd"):
                    args["cwd"] = packet["workspace"]
                self.control.authorize_tool(task_id, employee.agent_id, call.function.name, args)
                result = execute_tool(call.function.name, args)
                digest = hashlib.sha256(result.encode("utf-8", errors="replace")).hexdigest()[:16]
                evidence.append({
                    "type": "tool_result",
                    "reference": f"{call.function.name}:sha256:{digest}",
                    "success": not result.startswith("❌"),
                    "excerpt": result[:500],
                })
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
            self.control.record_cost(
                task_id, employee.agent_id, estimated_cost, "model_inference",
                metadata={"model": route["model_key"], "iterations": iterations},
            )
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
