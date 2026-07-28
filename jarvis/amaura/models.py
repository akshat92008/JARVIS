"""Domain types shared by the Amaura company control plane."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskState(StrEnum):
    DRAFT = "draft"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    POSTPONED = "postponed"
    EXPIRED = "expired"


RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}


@dataclass(frozen=True, slots=True)
class CompanyAgent:
    """An AI employee's enforceable operating envelope."""

    agent_id: str
    name: str
    department: str
    objective: str
    tools: tuple[str, ...]
    permissions: tuple[str, ...]
    data_access: tuple[str, ...]
    cost_limit_cents: int
    max_risk: RiskLevel
    reviewer_id: str | None
    escalation_destination: str = "jarvis"
    model_policy: str = "balanced"
    performance_objectives: tuple[str, ...] = ()
    system_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["max_risk"] = self.max_risk.value
        for key in ("tools", "permissions", "data_access", "performance_objectives"):
            result[key] = list(result[key])
        return result


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    key: str
    title: str
    description: str
    owner_id: str
    reviewer_id: str
    acceptance_criteria: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    risk: RiskLevel = RiskLevel.LOW
    budget_cents: int = 100
    action_type: str = "internal_work"
    prompt_profile: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowTemplate:
    key: str
    name: str
    department: str
    steps: tuple[WorkflowStep, ...]
    required_inputs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool = False
    manual_execution: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GovernanceError(ValueError):
    """Raised when an action violates the Amaura operating doctrine."""
