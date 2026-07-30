"""n8n Webhook Client for executing external actions."""

from __future__ import annotations

import os
import json
from typing import Any
import urllib.request
import urllib.error

class N8nClient:
    """Client to trigger n8n webhooks for external actions."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("N8N_BASE_URL", "http://localhost:5678")).rstrip("/")
        self.api_key = api_key or os.environ.get("N8N_API_KEY")

    def trigger_webhook(self, webhook_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Trigger a specific n8n webhook ID with JSON payload."""
        url = f"{self.base_url}/webhook/{webhook_id}"
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = response.read().decode("utf-8")
                try:
                    return json.loads(result)
                except json.JSONDecodeError:
                    return {"status": "success", "raw": result}
        except urllib.error.URLError as e:
            return {"status": "error", "error": str(e)}

    def stage_outreach(self, lead_id: str, channel: str, message_type: str, subject: str, body: str) -> dict[str, Any]:
        """Trigger the n8n webhook for staging outreach."""
        # Typically the webhook_id would be configured in env, here using a standard convention
        webhook_id = os.environ.get("N8N_WEBHOOK_OUTREACH", "amaura-outreach")
        return self.trigger_webhook(webhook_id, {
            "lead_id": lead_id,
            "channel": channel,
            "message_type": message_type,
            "subject": subject,
            "body": body
        })

    def send_message(self, to: str, message: str) -> dict[str, Any]:
        """Trigger the n8n webhook for sending an immediate message (e.g. telegram/imessage)."""
        webhook_id = os.environ.get("N8N_WEBHOOK_MESSAGE", "amaura-message")
        return self.trigger_webhook(webhook_id, {
            "to": to,
            "message": message
        })

    def sync_crm(self, lead_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Trigger the n8n webhook to sync lead state externally."""
        webhook_id = os.environ.get("N8N_WEBHOOK_CRM", "amaura-crm-sync")
        return self.trigger_webhook(webhook_id, {
            "lead_id": lead_id,
            "data": data
        })

# Global instance
def get_n8n_client() -> N8nClient:
    return N8nClient()
