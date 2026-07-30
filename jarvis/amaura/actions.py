from typing import Any
from jarvis.amaura.control_plane import AmauraControlPlane

class AmauraActions:
    """Action layer mapping LangGraph nodes to the Amaura control plane."""

    def __init__(self, control: AmauraControlPlane, worker_id: str = "langgraph-worker"):
        self.control = control
        self.worker_id = worker_id

    def discover_lead(self, campaign_id: str, company_name: str, domain_name: str, source_url: str) -> str:
        res = self.control.execute(
            {
                "domain": "acquisition",
                "handler": "discover_lead",
                "campaign_id": campaign_id,
                "company_name": company_name,
                "domain": domain_name,
                "source_url": source_url,
            }
        )
        return res["lead_id"]

    def add_evidence(self, lead_id: str, claim_type: str, claim: str, source_url: str, source_excerpt: str, confidence: float) -> dict[str, Any]:
        return self.control.execute(
            {
                "domain": "acquisition",
                "handler": "add_evidence",
                "lead_id": lead_id,
                "claim_type": claim_type,
                "claim": claim,
                "source_url": source_url,
                "source_excerpt": source_excerpt,
                "confidence": confidence,
            }
        )

    def score_lead(self, lead_id: str, components: dict[str, int]) -> dict[str, Any]:
        return self.control.execute(
            {
                "domain": "acquisition",
                "handler": "score_lead",
                "lead_id": lead_id,
                "components": components,
            }
        )

    def transition_lead(self, lead_id: str, to_stage: str, reason: str) -> dict[str, Any]:
        return self.control.execute(
            {
                "domain": "acquisition",
                "handler": "transition",
                "lead_id": lead_id,
                "to_stage": to_stage,
                "actor": self.worker_id,
                "reason": reason,
            }
        )

    def stage_message(self, lead_id: str, recipient: str, channel: str, message_type: str, subject: str, body: str) -> str:
        res = self.control.execute(
            {
                "domain": "acquisition",
                "handler": "stage_message",
                "lead_id": lead_id,
                "recipient": recipient,
                "channel": channel,
                "message_type": message_type,
                "subject": subject,
                "body": body,
            }
        )
        return res["message_id"]

    def decide_message(self, message_id: str, approve: bool, reason: str) -> dict[str, Any]:
        return self.control.execute(
            {
                "domain": "acquisition",
                "handler": "decide_message",
                "message_id": message_id,
                "actor": self.worker_id,
                "approve": approve,
                "reason": reason,
            }
        )

    def send_message(self, message_id: str, recipient: str) -> dict[str, Any]:
        return self.control.execute(
            {
                "domain": "acquisition",
                "handler": "deliver_approved_message",
                "message_id": message_id,
                "recipient": recipient,
                "actor": self.worker_id,
            }
        )

    def update_crm(self, lead_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        from jarvis.amaura.n8n import get_n8n_client
        n8n = get_n8n_client()
        result = n8n.sync_crm(lead_id, fields)
        return result
