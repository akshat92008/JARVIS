"""Durability, approval-integrity, and security tests for the workforce supervisor."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.evidence import deterministic_evidence_review
from jarvis.amaura.executor import GovernedTaskRunner
from jarvis.amaura.models import GovernanceError, TaskState
from jarvis.amaura.policy import PolicyEngine
from jarvis.amaura.supervisor import AmauraSupervisor


class _SuccessfulRunner:
    def __init__(self, control: AmauraControlPlane):
        self.control = control

    def run(self, task_id: str) -> dict:
        task = self.control.store.get_work_item(task_id)
        submitted = self.control.submit_task(
            task_id,
            actor=task["owner_id"],
            summary="The bounded task completed with verifiable evidence.",
            evidence=[
                {
                    "type": "test_report",
                    "reference": f"artifact://{task_id}/report",
                    "success": True,
                }
            ],
        )
        return {"status": submitted["state"], "task_id": task_id}


class _SuccessfulReviewer:
    def __init__(self, control: AmauraControlPlane):
        self.control = control

    def run(self, task_id: str) -> dict:
        task = self.control.store.get_work_item(task_id)
        deterministic = deterministic_evidence_review(task, self.control.evidence)
        updated = self.control.review_task(
            task_id,
            actor=task["reviewer_id"],
            approve=True,
            findings="Every acceptance criterion is supported by the submitted report.",
            attestation={
                "signature": "mock",
                "decision": {"approve": True, "criteria": []},
                "deterministic_review": deterministic,
                "task_id": task_id,
                "reviewer_id": task["reviewer_id"],
            },
        )
        return {"task_id": task_id, "approve": True, "state": updated["state"]}


class _TransientFailureRunner:
    def __init__(self, control: AmauraControlPlane):
        self.control = control

    def run(self, task_id: str) -> dict:
        raise ConnectionError("Local inference connection temporarily unavailable")


class TestAmauraSupervisor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.control = AmauraControlPlane(Path(self.temp_dir.name) / "amaura.db")
        self._attestation_patcher = patch("jarvis.amaura.evidence.verify_review_attestation", return_value=True)
        self._attestation_patcher.start()

    def tearDown(self):
        self._attestation_patcher.stop()
        self.control.close()
        self.temp_dir.cleanup()

    def _programme(self):
        return self.control.create_program(
            objective="Deliver a verified internal feature",
            success_metric="Every acceptance criterion passes independent review",
            workflow_key="software_delivery",
            inputs={"repository_path": self.temp_dir.name},
        )

    def _attestation(self, task_id: str, reviewer_id: str) -> dict:
        task = self.control.store.get_work_item(task_id)
        return {
            "signature": "mock",
            "decision": {"approve": True, "criteria": []},
            "deterministic_review": deterministic_evidence_review(task, self.control.evidence),
            "task_id": task_id,
            "reviewer_id": reviewer_id,
        }

    def test_supervisor_leases_executes_and_reviews_independently(self):
        programme = self._programme()
        first = programme["tasks"][0]
        supervisor = AmauraSupervisor(
            self.control,
            worker_id="test-worker",
            runner_factory=_SuccessfulRunner,
            reviewer_factory=_SuccessfulReviewer,
        )

        executed = supervisor.tick()
        self.assertEqual(executed["status"], "executed")
        self.assertEqual(executed["execution"]["state"], "succeeded")
        self.assertEqual(
            self.control.store.get_work_item(first["id"])["state"],
            TaskState.AWAITING_REVIEW.value,
        )

        reviewed = supervisor.tick()
        self.assertEqual(reviewed["status"], "reviewed")
        self.assertEqual(
            self.control.store.get_work_item(first["id"])["state"],
            TaskState.COMPLETED.value,
        )
        self.assertEqual(
            self.control.store.execution_status()["counts"]["succeeded"], 1
        )

    def test_transient_failures_retry_once_then_fail_closed(self):
        first = self._programme()["tasks"][0]
        supervisor = AmauraSupervisor(
            self.control,
            worker_id="retry-worker",
            max_attempts=2,
            runner_factory=_TransientFailureRunner,
            automatic_reviews=False,
        )

        retry = supervisor.tick()
        self.assertEqual(retry["status"], "retry_scheduled")
        self.assertEqual(
            self.control.store.get_work_item(first["id"])["state"],
            TaskState.ASSIGNED.value,
        )

        failed = supervisor.tick()
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(
            self.control.store.get_work_item(first["id"])["state"],
            TaskState.FAILED.value,
        )
        self.assertEqual(
            len(self.control.store.list_executions(task_id=first["id"])), 2
        )

    def test_expired_worker_lease_is_recovered(self):
        first = self._programme()["tasks"][0]
        claim = self.control.store.claim_next_task(
            worker_id="crashed-worker",
            lease_seconds=30,
            max_attempts=2,
        )
        self.assertIsNotNone(claim)
        with self.control.store._lock:
            self.control.store._connection.execute(
                "UPDATE execution_runs SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
                (claim["run"]["id"],),
            )
            self.control.store._connection.commit()

        recovered = self.control.store.recover_expired_executions(max_attempts=2)
        self.assertEqual(recovered[0]["task_id"], first["id"])
        self.assertTrue(recovered[0]["retry_scheduled"])
        self.assertEqual(
            self.control.store.get_work_item(first["id"])["state"],
            TaskState.ASSIGNED.value,
        )

    def test_approval_is_bound_to_exact_payload(self):
        programme = self.control.create_program(
            objective="Publish a verified update",
            success_metric="Every public claim is independently evidenced",
            workflow_key="content_campaign",
        )
        evidence_task, content_task, _ = programme["tasks"]
        for task in (evidence_task,):
            self.control.start_task(task["id"])
            self.control.submit_task(
                task["id"],
                task["owner_id"],
                "Evidence register is complete.",
                [{"type": "evidence", "reference": "artifact://evidence/v1"}],
            )
            self.control.review_task(
                task["id"],
                task["reviewer_id"],
                True,
                "Evidence sources verified.",
                attestation=self._attestation(task["id"], task["reviewer_id"]),
            )
        self.control.start_task(content_task["id"])
        self.control.submit_task(
            content_task["id"],
            content_task["owner_id"],
            "Approved draft v1.",
            [{"type": "content", "reference": "artifact://content/v1"}],
        )
        self.control.review_task(
            content_task["id"],
            content_task["reviewer_id"],
            True,
            "Claims verified.",
            attestation=self._attestation(content_task["id"], content_task["reviewer_id"]),
        )
        approval = self.control.store.list_approvals("pending")[0]
        self.control.store.update_work_item(
            content_task["id"], summary="Tampered draft v2"
        )

        with self.assertRaisesRegex(GovernanceError, "payload changed"):
            self.control.decide_approval(
                approval["id"],
                self.control.founder_id,
                "approved",
                "Approve the reviewed version.",
            )

    def test_audit_chain_detects_database_tampering(self):
        self._programme()
        self.assertTrue(self.control.store.audit_chain_check()["ok"])
        with self.control.store._lock:
            first = self.control.store._connection.execute(
                "SELECT sequence FROM audit_logs ORDER BY sequence LIMIT 1"
            ).fetchone()
            self.control.store._connection.execute(
                "UPDATE audit_logs SET details='{\"tampered\":true}' WHERE sequence=?",
                (first["sequence"],),
            )
            self.control.store._connection.commit()
        self.assertFalse(self.control.store.integrity_check()["ok"])

    def test_policy_blocks_ssrf_shell_injection_and_workspace_escape(self):
        task = self._programme()["tasks"][0]
        started = self.control.start_task(task["id"])
        decision = PolicyEngine.validate_tool_action(
            started,
            task["owner_id"],
            "get_project_structure",
            {"path": str(Path(self.temp_dir.name) / "safe")},
        )
        self.assertTrue(decision.allowed)

        lead_programme = self.control.create_program(
            objective="Research public opportunities",
            success_metric="One sourced opportunity",
            workflow_key="lead_to_revenue",
            inputs={"workspace": self.temp_dir.name},
        )
        lead_task = self.control.start_task(lead_programme["tasks"][0]["id"])
        blocked = PolicyEngine.validate_tool_action(
            lead_task,
            lead_task["owner_id"],
            "web_fetch",
            {"url": "http://127.0.0.1:8000/private"},
        )
        self.assertFalse(blocked.allowed)
        self.assertIn("blocked", " ".join(blocked.reasons).lower())

        scoped = GovernedTaskRunner._scope_tool_args(
            "read_file",
            {"path": "README.md"},
            self.temp_dir.name,
        )
        self.assertEqual(
            scoped["path"],
            str((Path(self.temp_dir.name) / "README.md").resolve()),
        )

    def test_explicit_local_mode_is_zero_cost_and_has_no_cloud_fallback(self):
        with patch.dict(
            "os.environ",
            {"AMAURA_MODEL_MODE": "local", "AMAURA_LOCAL_MODEL": "nova:3b"},
            clear=False,
        ):
            route = self.control.models.route(
                "builder",
                remaining_budget_cents=0,
                estimated_tokens=50_000,
            )
        self.assertEqual(route.provider, "local")
        self.assertEqual(route.estimated_cost_cents, 0)
        self.assertIsNone(route.fallback_model_key)


if __name__ == "__main__":
    unittest.main()
