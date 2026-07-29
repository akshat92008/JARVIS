"""Content-addressed evidence and signed independent-review attestations."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.amaura.models import GovernanceError


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    sha256: str
    reference: str
    media_type: str
    byte_length: int
    source: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceVault:
    """Write-once evidence vault with deterministic integrity verification."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        if not (
            len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
        ):
            raise GovernanceError("Invalid evidence digest")
        return self.root / "sha256" / digest[:2] / digest[2:]

    def put_text(
        self,
        text: str,
        *,
        source: str,
        media_type: str = "text/plain; charset=utf-8",
    ) -> EvidenceRecord:
        return self.put_bytes(
            text.encode("utf-8", errors="replace"),
            source=source,
            media_type=media_type,
        )

    def put_json(self, value: Any, *, source: str) -> EvidenceRecord:
        return self.put_bytes(
            _canonical_bytes(value),
            source=source,
            media_type="application/json",
        )

    def put_bytes(
        self,
        payload: bytes,
        *,
        source: str,
        media_type: str,
    ) -> EvidenceRecord:
        digest = hashlib.sha256(payload).hexdigest()
        target = self._path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise GovernanceError("Evidence vault collision or tampering detected")
        else:
            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                prefix=".evidence-",
                delete=False,
            ) as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            try:
                temporary_path.replace(target)
            finally:
                temporary_path.unlink(missing_ok=True)
        return EvidenceRecord(
            sha256=digest,
            reference=f"evidence://sha256/{digest}",
            media_type=media_type,
            byte_length=len(payload),
            source=source,
            created_at=datetime.now(UTC).isoformat(),
        )

    def verify(self, reference: str, *, expected_sha256: str = "") -> dict[str, Any]:
        prefix = "evidence://sha256/"
        if not reference.startswith(prefix):
            return {
                "ok": False,
                "reference": reference,
                "reason": "not_content_addressed",
            }
        digest = reference.removeprefix(prefix)
        if expected_sha256 and not hmac.compare_digest(digest, expected_sha256):
            return {
                "ok": False,
                "reference": reference,
                "reason": "declared_digest_mismatch",
            }
        try:
            target = self._path(digest)
        except GovernanceError:
            return {"ok": False, "reference": reference, "reason": "invalid_digest"}
        if not target.is_file():
            return {"ok": False, "reference": reference, "reason": "missing"}
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        return {
            "ok": hmac.compare_digest(actual, digest),
            "reference": reference,
            "sha256": actual,
            "byte_length": target.stat().st_size,
            "reason": "" if hmac.compare_digest(actual, digest) else "tampered",
        }


def deterministic_evidence_review(
    task: dict[str, Any],
    vault: EvidenceVault,
) -> dict[str, Any]:
    """Reject missing, failed, or tampered completion evidence before model review."""

    evidence = task.get("evidence") or []
    findings: list[str] = []
    verified: list[dict[str, Any]] = []
    if not str(task.get("summary", "")).strip():
        findings.append("Submission has no completion summary")
    if not evidence:
        findings.append("Submission has no evidence")
    for index, item in enumerate(evidence):
        if item.get("success") is False:
            findings.append(f"Evidence {index + 1} records a failed operation")
        reference = str(item.get("reference", ""))
        if reference.startswith("evidence://"):
            result = vault.verify(
                reference,
                expected_sha256=str(item.get("sha256", "")),
            )
            verified.append(result)
            if not result["ok"]:
                findings.append(
                    f"Evidence {index + 1} failed integrity verification: "
                    f"{result['reason']}"
                )
        elif item.get("type") == "tool_result":
            findings.append(
                f"Tool evidence {index + 1} is not stored in the evidence vault"
            )
    criteria = task.get("acceptance_criteria") or []
    if criteria and not evidence:
        findings.append("Acceptance criteria have no supporting evidence")
    return {
        "approve": not findings,
        "findings": findings,
        "verified_evidence": verified,
        "criteria_count": len(criteria),
        "evidence_count": len(evidence),
        "submission_sha256": hashlib.sha256(
            _canonical_bytes(
                {
                    "task_id": task.get("id"),
                    "summary": task.get("summary"),
                    "evidence": evidence,
                    "acceptance_criteria": criteria,
                }
            )
        ).hexdigest(),
    }


def create_review_attestation(
    *,
    task_id: str,
    reviewer_id: str,
    reviewer_model: str,
    decision: dict[str, Any],
    deterministic_review: dict[str, Any],
    key: str | None = None,
) -> dict[str, Any]:
    secret = (key if key is not None else os.environ.get(
        "AMAURA_REVIEW_ATTESTATION_KEY", ""
    )).encode()
    if len(secret) < 32:
        raise GovernanceError(
            "AMAURA_REVIEW_ATTESTATION_KEY must contain at least 32 bytes"
        )
    payload = {
        "task_id": task_id,
        "reviewer_id": reviewer_id,
        "reviewer_model": reviewer_model,
        "decision": decision,
        "deterministic_review": deterministic_review,
        "created_at": datetime.now(UTC).isoformat(),
    }
    signature = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return {
        **payload,
        "algorithm": "hmac-sha256",
        "signature": signature,
    }


def verify_review_attestation(
    attestation: dict[str, Any],
    *,
    key: str | None = None,
) -> bool:
    secret = (key if key is not None else os.environ.get(
        "AMAURA_REVIEW_ATTESTATION_KEY", ""
    )).encode()
    if len(secret) < 32:
        return False
    payload = {
        name: attestation[name]
        for name in (
            "task_id",
            "reviewer_id",
            "reviewer_model",
            "decision",
            "deterministic_review",
            "created_at",
        )
        if name in attestation
    }
    expected = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(attestation.get("signature", "")), expected)


__all__ = [
    "EvidenceRecord",
    "EvidenceVault",
    "create_review_attestation",
    "deterministic_evidence_review",
    "verify_review_attestation",
]
