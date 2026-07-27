"""Budget- and privacy-aware model routing for company employees."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from jarvis.amaura.models import GovernanceError, RiskLevel
from jarvis.amaura.registry import get_agent


@dataclass(frozen=True, slots=True)
class ModelRoute:
    model_key: str
    provider: str
    privacy: str
    estimated_cost_cents: int
    fallback_model_key: str | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class ModelGateway:
    """Selects an approved model without exposing restricted data or exceeding budget."""

    def route(
        self,
        agent_id: str,
        *,
        risk: str = "low",
        sensitivity: str = "internal",
        estimated_tokens: int = 4000,
        remaining_budget_cents: int,
        needs_vision: bool = False,
    ) -> ModelRoute:
        agent = get_agent(agent_id)
        estimated_tokens = max(1, estimated_tokens)
        if sensitivity in {"client_confidential", "secret", "restricted"}:
            route = ModelRoute(
                model_key="ollama-local",
                provider="local",
                privacy="device_only",
                estimated_cost_cents=0,
                fallback_model_key=None,
                reason="Restricted data is routed to a local model with no cloud fallback.",
            )
        elif needs_vision:
            route = ModelRoute(
                model_key="llama-vision",
                provider="nvidia",
                privacy="cloud_approved",
                estimated_cost_cents=max(1, estimated_tokens // 2500),
                fallback_model_key="llama-3.3-70b",
                reason="The task requires visual understanding.",
            )
        elif agent.model_policy == "balanced" or RiskLevel(risk) in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            route = ModelRoute(
                model_key="fable-5-reasoning",
                provider="hybrid",
                privacy="cloud_approved",
                estimated_cost_cents=max(1, estimated_tokens // 3000),
                fallback_model_key="llama-3.3-70b",
                reason="Complex governed work uses the reasoning route with a recorded fallback.",
            )
        else:
            route = ModelRoute(
                model_key="llama-3.3-70b",
                provider="nvidia",
                privacy="cloud_approved",
                estimated_cost_cents=max(1, estimated_tokens // 4000),
                fallback_model_key="ollama-local",
                reason="Routine work uses the lower-cost general model.",
            )
        if route.estimated_cost_cents > remaining_budget_cents:
            raise GovernanceError(
                f"Estimated model cost {route.estimated_cost_cents}c exceeds remaining task budget {remaining_budget_cents}c"
            )
        return route
