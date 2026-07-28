"""JARVIS tools for operating Amaura Studio's governed AI workforce."""

from __future__ import annotations

import json
import threading
from typing import Any

from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.executor import GovernedTaskRunner
from jarvis.amaura.supervisor import AmauraSupervisor


_CONTROL: AmauraControlPlane | None = None
_LOCK = threading.Lock()


def get_control_plane() -> AmauraControlPlane:
    global _CONTROL
    if _CONTROL is None:
        with _LOCK:
            if _CONTROL is None:
                _CONTROL = AmauraControlPlane()
    return _CONTROL


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


AMAURA_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "amaura_company_status",
            "description": "Read the Amaura executive dashboard. JARVIS is the master control plane for all listed employees.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_list_agents",
            "description": "List the governed Amaura v1 workforce with department, authority, tools, cost limit, risk ceiling, and reviewer.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_create_program",
            "description": "As JARVIS, turn a founder objective into a programme, project, milestone, and dependency-ordered employee tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "Concrete company outcome to achieve."},
                    "success_metric": {"type": "string", "description": "Measurable threshold proving the programme succeeded."},
                    "workflow_key": {"type": "string", "enum": ["client_acquisition", "content_factory", "lead_to_revenue", "software_delivery", "content_campaign", "research_experiment"]},
                    "title": {"type": "string"},
                    "priority": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                    "deadline": {"type": "string", "description": "Optional ISO-8601 deadline."},
                    "inputs": {"type": "object", "description": "Workflow inputs, including hypothesis for research."},
                },
                "required": ["objective", "success_metric", "workflow_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_revenue_dashboard",
            "description": "Read the ethical client-acquisition pipeline, campaign, lead, approval, and revenue dashboard.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_create_campaign",
            "description": "Create or update one bounded acquisition campaign with strict daily limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "campaign_id": {"type": "string"}, "name": {"type": "string"},
                    "target_segment": {"type": "string"}, "offer": {"type": "string"},
                    "minimum_score": {"type": "integer", "minimum": 70, "maximum": 100, "default": 70},
                    "daily_lead_limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                    "daily_outreach_limit": {"type": "integer", "minimum": 0, "maximum": 50, "default": 3},
                },
                "required": ["campaign_id", "name", "target_segment", "offer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_discover_lead",
            "description": "Add one unique, publicly sourced campaign lead; duplicate domains return the existing lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "campaign_id": {"type": "string"}, "company_name": {"type": "string"},
                    "domain": {"type": "string"}, "source_url": {"type": "string"},
                    "country": {"type": "string"}, "industry": {"type": "string"},
                },
                "required": ["campaign_id", "company_name", "domain", "source_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_score_lead",
            "description": "Apply the deterministic 100-point acquisition rubric to a researched lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "campaign_fit": {"type": "integer", "minimum": 0, "maximum": 25},
                    "visible_need": {"type": "integer", "minimum": 0, "maximum": 25},
                    "ability_to_pay": {"type": "integer", "minimum": 0, "maximum": 20},
                    "contactability": {"type": "integer", "minimum": 0, "maximum": 15},
                    "portfolio_match": {"type": "integer", "minimum": 0, "maximum": 15},
                },
                "required": ["lead_id", "campaign_fit", "visible_need", "ability_to_pay", "contactability", "portfolio_match"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_list_tasks",
            "description": "List company tasks, optionally filtered by workflow state or employee ID.",
            "parameters": {
                "type": "object",
                "properties": {"state": {"type": "string"}, "owner_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_task_packet",
            "description": "Have JARVIS issue the exact governed context, tools, data, budget, model route, dependencies, and criteria for one task.",
            "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_run_task",
            "description": "Have JARVIS dispatch one ready task to its assigned specialist employee inside the governed tool, cost, data, evidence, and review boundaries.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}, "max_iterations": {"type": "integer", "default": 12}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_supervisor_status",
            "description": "Read durable execution leases, queue depth, retries, reviews, and founder approval waits.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_supervisor_tick",
            "description": "Have JARVIS atomically advance one dependency-ready task or independent review with crash recovery.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string"},
                    "automatic_reviews": {"type": "boolean", "default": True},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_review_task",
            "description": "Record an independent reviewer decision. The reviewer must match the registry and cannot be the task owner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"}, "reviewer_id": {"type": "string"},
                    "approve": {"type": "boolean"}, "findings": {"type": "string"},
                },
                "required": ["task_id", "reviewer_id", "approve", "findings"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_pending_approvals",
            "description": "List founder approval requests for external, medium-, high-, or critical-risk company actions.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_pause_agent",
            "description": "Have JARVIS immediately pause a misbehaving employee and block its in-progress work while preserving evidence and audit history.",
            "parameters": {
                "type": "object",
                "properties": {"agent_id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["agent_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_record_decision",
            "description": "Write an institutional decision with context, options, rationale, owner, and review date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string"}, "context": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "chosen_option": {"type": "string"}, "reason": {"type": "string"},
                    "review_date": {"type": "string"},
                },
                "required": ["decision", "context", "options", "chosen_option", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amaura_daily_briefing",
            "description": "Generate the founder's daily company briefing with costs, blockers, results, risks, and top decisions.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def company_status() -> str:
    return _json(get_control_plane().dashboard())


def revenue_dashboard() -> str:
    return _json(get_control_plane().acquisition.dashboard())


def create_campaign(campaign_id: str, name: str, target_segment: str, offer: str,
                    minimum_score: int = 70, daily_lead_limit: int = 10,
                    daily_outreach_limit: int = 3) -> str:
    return _json(get_control_plane().acquisition.create_campaign(
        campaign_id=campaign_id, name=name, target_segment=target_segment, offer=offer,
        minimum_score=minimum_score, daily_lead_limit=daily_lead_limit,
        daily_outreach_limit=daily_outreach_limit,
    ))


def discover_lead(campaign_id: str, company_name: str, domain: str, source_url: str,
                  country: str = "", industry: str = "") -> str:
    return _json(get_control_plane().acquisition.discover_lead(
        campaign_id=campaign_id, company_name=company_name, domain=domain, source_url=source_url,
        country=country, industry=industry,
    ))


def score_lead(lead_id: str, campaign_fit: int, visible_need: int, ability_to_pay: int,
               contactability: int, portfolio_match: int) -> str:
    return _json(get_control_plane().acquisition.score_lead(lead_id, {
        "campaign_fit": campaign_fit, "visible_need": visible_need,
        "ability_to_pay": ability_to_pay, "contactability": contactability,
        "portfolio_match": portfolio_match,
    }))


def list_agents() -> str:
    return _json(get_control_plane().store.list_agents())


def create_program(objective: str, success_metric: str, workflow_key: str, title: str = "", priority: int = 3, deadline: str = "", inputs: dict | None = None) -> str:
    result = get_control_plane().create_program(
        objective=objective, success_metric=success_metric, workflow_key=workflow_key,
        title=title or None, priority=priority, deadline=deadline or None, inputs=inputs, actor="jarvis",
    )
    return _json(result)


def list_tasks(state: str = "", owner_id: str = "") -> str:
    return _json(get_control_plane().list_tasks(state or None, owner_id or None))


def task_packet(task_id: str) -> str:
    return _json(get_control_plane().task_packet(task_id, actor="jarvis"))


def run_task(task_id: str, max_iterations: int = 12) -> str:
    return _json(GovernedTaskRunner(get_control_plane()).run(task_id, max_iterations))

def supervisor_status() -> str:
    return _json(AmauraSupervisor(get_control_plane(), worker_id="jarvis-tool").status())


def supervisor_tick(workflow_id: str = "", automatic_reviews: bool = True) -> str:
    return _json(AmauraSupervisor(
        get_control_plane(),
        worker_id="jarvis-tool",
        automatic_reviews=automatic_reviews,
    ).tick(workflow_id=workflow_id or None))


def review_task(task_id: str, reviewer_id: str, approve: bool, findings: str) -> str:
    return _json(get_control_plane().review_task(task_id, reviewer_id, approve, findings))


def pending_approvals() -> str:
    return _json(get_control_plane().store.list_approvals("pending"))


def pause_agent(agent_id: str, reason: str) -> str:
    return _json(get_control_plane().pause_agent(agent_id, reason, actor="jarvis"))


def record_decision(decision: str, context: str, options: list[str], chosen_option: str, reason: str, review_date: str = "") -> str:
    control = get_control_plane()
    decision_id = control.record_decision(
        decision=decision, context=context, options=options, chosen_option=chosen_option,
        reason=reason, actor="jarvis", review_date=review_date or None,
    )
    return _json({"decision_id": decision_id})


def daily_briefing() -> str:
    return _json(get_control_plane().daily_briefing())


AMAURA_DISPATCH = {
    "amaura_company_status": company_status,
    "amaura_revenue_dashboard": revenue_dashboard,
    "amaura_create_campaign": create_campaign,
    "amaura_discover_lead": discover_lead,
    "amaura_score_lead": score_lead,
    "amaura_list_agents": list_agents,
    "amaura_create_program": create_program,
    "amaura_list_tasks": list_tasks,
    "amaura_task_packet": task_packet,
    "amaura_run_task": run_task,
    "amaura_supervisor_status": supervisor_status,
    "amaura_supervisor_tick": supervisor_tick,
    "amaura_review_task": review_task,
    "amaura_pending_approvals": pending_approvals,
    "amaura_pause_agent": pause_agent,
    "amaura_record_decision": record_decision,
    "amaura_daily_briefing": daily_briefing,
}
