"""Authenticated, idempotent provider adapters for approved external actions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

from jarvis.amaura.models import GovernanceError
from jarvis.amaura.network import request_json, validate_public_url
from jarvis.amaura.n8n import get_n8n_client

Transport = Callable[..., tuple[int, dict[str, Any], dict[str, str]]]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()


def _receipt_key(value: str | None = None) -> bytes:
    raw = value if value is not None else os.environ.get(
        "AMAURA_PROVIDER_RECEIPT_KEY",
        "",
    )
    encoded = raw.encode()
    if len(encoded) < 32:
        raise GovernanceError(
            "AMAURA_PROVIDER_RECEIPT_KEY must contain at least 32 bytes"
        )
    return encoded


@dataclass(frozen=True, slots=True)
class ProviderReceipt:
    provider: str
    operation: str
    external_id: str
    idempotency_key: str
    payload_sha256: str
    status: str
    created_at: str
    signature: str
    thread_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def verify(self, *, key: str | None = None) -> bool:
        unsigned = {
            name: getattr(self, name)
            for name in (
                "provider",
                "operation",
                "external_id",
                "idempotency_key",
                "payload_sha256",
                "status",
                "created_at",
                "thread_id",
            )
        }
        expected = hmac.new(
            _receipt_key(key),
            _canonical_bytes(unsigned),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    @classmethod
    def issue(
        cls,
        *,
        provider: str,
        operation: str,
        external_id: str,
        idempotency_key: str,
        payload: Any,
        status: str,
        thread_id: str = "",
        key: str | None = None,
    ) -> ProviderReceipt:
        if not all(
            value.strip()
            for value in (
                provider,
                operation,
                external_id,
                idempotency_key,
                status,
            )
        ):
            raise GovernanceError("Provider receipt fields may not be empty")
        unsigned = {
            "provider": provider,
            "operation": operation,
            "external_id": external_id,
            "idempotency_key": idempotency_key,
            "payload_sha256": hashlib.sha256(
                _canonical_bytes(payload)
            ).hexdigest(),
            "status": status,
            "created_at": datetime.now(UTC).isoformat(),
            "thread_id": thread_id,
        }
        signature = hmac.new(
            _receipt_key(key),
            _canonical_bytes(unsigned),
            hashlib.sha256,
        ).hexdigest()
        return cls(**unsigned, signature=signature)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ProviderReceipt:
        try:
            return cls(
                provider=str(value["provider"]),
                operation=str(value["operation"]),
                external_id=str(value["external_id"]),
                idempotency_key=str(value["idempotency_key"]),
                payload_sha256=str(value["payload_sha256"]),
                status=str(value["status"]),
                created_at=str(value["created_at"]),
                signature=str(value["signature"]),
                thread_id=str(value.get("thread_id", "")),
            )
        except KeyError as exc:
            raise GovernanceError("Provider receipt is incomplete") from exc


class GmailAdapter:
    """Send one founder-approved message and return a signed Gmail receipt."""

    endpoint = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        transport: Transport = request_json,
        receipt_key: str | None = None,
    ):
        self.access_token = (
            access_token
            if access_token is not None
            else os.environ.get("AMAURA_GMAIL_ACCESS_TOKEN", "")
        )
        self.transport = transport
        self.receipt_key = receipt_key

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    def send(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
        sender: str = "",
    ) -> ProviderReceipt:
        if not self.access_token:
            raise GovernanceError("Gmail access token is not configured")
        if "@" not in recipient or not body.strip() or not idempotency_key.strip():
            raise GovernanceError(
                "Gmail delivery requires recipient, body, and idempotency key"
            )
        message = EmailMessage()
        message["To"] = recipient
        if sender:
            message["From"] = sender
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
        payload = {"raw": raw}
        status, response, _ = self.transport(
            self.endpoint,
            method="POST",
            payload=payload,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "X-Amaura-Idempotency-Key": idempotency_key,
            },
        )
        if status not in {200, 201}:
            raise GovernanceError(f"Gmail delivery failed with HTTP {status}")
        external_id = str(response.get("id", "")).strip()
        thread_id = str(response.get("threadId", "")).strip()
        if not external_id:
            raise GovernanceError("Gmail returned no message identifier")
        return ProviderReceipt.issue(
            provider="gmail",
            operation="send_email",
            external_id=external_id,
            thread_id=thread_id,
            idempotency_key=idempotency_key,
            payload={
                "recipient": recipient,
                "subject": subject,
                "body": body,
            },
            status="sent",
            key=self.receipt_key,
        )


class N8nEmailAdapter:
    """Send one founder-approved message via n8n webhook and return a receipt."""
    
    def __init__(self, receipt_key: str | None = None):
        self.client = get_n8n_client()
        self.receipt_key = receipt_key
        
    @property
    def configured(self) -> bool:
        return os.environ.get("USE_N8N") == "1"
        
    def send(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
        sender: str = "",
    ) -> ProviderReceipt:
        if not self.configured:
            raise GovernanceError("n8n is not configured")
        
        result = self.client.trigger_webhook(
            os.environ.get("N8N_WEBHOOK_EMAIL", "amaura-email"),
            {
                "to": recipient,
                "from": sender,
                "subject": subject,
                "body": body,
                "idempotency_key": idempotency_key
            }
        )
        if result.get("status") == "error":
            raise GovernanceError(f"n8n email delivery failed: {result.get('error')}")
            
        external_id = str(result.get("id", idempotency_key)).strip()
        thread_id = str(result.get("threadId", "")).strip()
        
        return ProviderReceipt.issue(
            provider="n8n",
            operation="send_email",
            external_id=external_id,
            thread_id=thread_id,
            idempotency_key=idempotency_key,
            payload={
                "recipient": recipient,
                "subject": subject,
                "body": body,
            },
            status="sent",
            key=self.receipt_key,
        )


class PrivatePublicationAdapter:
    """Create a private provider draft; it never performs a public publish."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_token: str | None = None,
        transport: Transport = request_json,
        receipt_key: str | None = None,
    ):
        self.endpoint = (
            endpoint
            if endpoint is not None
            else os.environ.get("AMAURA_PUBLICATION_ENDPOINT", "")
        )
        self.access_token = (
            access_token
            if access_token is not None
            else os.environ.get("AMAURA_PUBLICATION_ACCESS_TOKEN", "")
        )
        self.transport = transport
        self.receipt_key = receipt_key

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.access_token)

    def create_private_draft(
        self,
        *,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> ProviderReceipt:
        if not self.configured:
            raise GovernanceError("Private publication adapter is not configured")
        validate_public_url(self.endpoint, resolve=True)
        if payload.get("visibility") not in {"private", "draft"}:
            raise GovernanceError(
                "Publication adapter accepts only private or draft visibility"
            )
        if not idempotency_key.strip():
            raise GovernanceError("Publication idempotency key is required")
        status, response, _ = self.transport(
            self.endpoint,
            method="POST",
            payload=payload,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "X-Amaura-Idempotency-Key": idempotency_key,
            },
        )
        if status not in {200, 201, 202}:
            raise GovernanceError(
                f"Private publication draft failed with HTTP {status}"
            )
        external_id = str(response.get("id", "")).strip()
        visibility = str(response.get("visibility", "")).strip().lower()
        if not external_id or visibility not in {"private", "draft"}:
            raise GovernanceError(
                "Provider did not confirm a private publication draft"
            )
        return ProviderReceipt.issue(
            provider=str(response.get("provider", "private-publication")),
            operation="create_private_draft",
            external_id=external_id,
            idempotency_key=idempotency_key,
            payload=payload,
            status=visibility,
            key=self.receipt_key,
        )


def verify_provider_receipt(
    value: ProviderReceipt | dict[str, Any],
    *,
    expected_operation: str,
    expected_idempotency_key: str = "",
    expected_payload: Any | None = None,
    key: str | None = None,
) -> ProviderReceipt:
    receipt = value if isinstance(value, ProviderReceipt) else ProviderReceipt.from_dict(value)
    if not receipt.verify(key=key):
        raise GovernanceError("Provider receipt signature is invalid")
    if receipt.operation != expected_operation:
        raise GovernanceError("Provider receipt operation does not match")
    if expected_idempotency_key and not hmac.compare_digest(
        receipt.idempotency_key,
        expected_idempotency_key,
    ):
        raise GovernanceError("Provider receipt idempotency key does not match")
    if expected_payload is not None:
        expected_hash = hashlib.sha256(_canonical_bytes(expected_payload)).hexdigest()
        if not hmac.compare_digest(receipt.payload_sha256, expected_hash):
            raise GovernanceError("Provider receipt payload does not match")
    return receipt


__all__ = [
    "GmailAdapter",
    "PrivatePublicationAdapter",
    "N8nEmailAdapter",
    "ProviderReceipt",
    "verify_provider_receipt",
]
