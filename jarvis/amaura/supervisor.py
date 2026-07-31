"""Crash-resumable supervisor for Amaura's governed internal workforce."""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import uuid
from collections.abc import Callable
from typing import Any

from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.executor import GovernedReviewRunner, GovernedTaskRunner
from jarvis.amaura.integrations import dispatch_outbox_event
from jarvis.amaura.models import GovernanceError, TaskState

RunnerFactory = Callable[[AmauraControlPlane], GovernedTaskRunner]
ReviewerFactory = Callable[[AmauraControlPlane], GovernedReviewRunner]


class AmauraSupervisor:
    """Lease, execute, recover, and independently review one safe unit at a time."""

    def __init__(
        self,
        control_plane: AmauraControlPlane,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 900,
        max_attempts: int = 2,
        runner_factory: RunnerFactory = GovernedTaskRunner,
        reviewer_factory: ReviewerFactory = GovernedReviewRunner,
        automatic_reviews: bool = True,
    ):
        self.control = control_plane
        self.worker_id = worker_id or (
            f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        )
        self.lease_seconds = max(30, min(int(lease_seconds), 86_400))
        self.max_attempts = max(1, min(int(max_attempts), 20))
        self.runner_factory = runner_factory
        self.reviewer_factory = reviewer_factory
        self.automatic_reviews = automatic_reviews

    def status(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "lease_seconds": self.lease_seconds,
            "max_attempts": self.max_attempts,
            "automatic_reviews": self.automatic_reviews,
            "executions": self.control.store.execution_status(),
            "ready_tasks": len(self.control.list_tasks(TaskState.ASSIGNED.value)),
            "awaiting_review": len(
                self.control.list_tasks(TaskState.AWAITING_REVIEW.value)
            ),
            "awaiting_approval": len(
                self.control.list_tasks(TaskState.AWAITING_APPROVAL.value)
            ),
            "open_alerts": len(self.control.store.list_alerts(status="open")),
        }

    def tick(self, *, workflow_id: str | None = None) -> dict[str, Any]:
        """Advance exactly one review or execution and return an auditable outcome."""
        with self.control.telemetry.trace(
            "supervisor.tick",
            worker_id=self.worker_id,
            workflow_id=workflow_id or "",
        ):
            return self._tick(workflow_id=workflow_id)

    def _tick(self, *, workflow_id: str | None = None) -> dict[str, Any]:
        # Process pending outbox events first
        outbox_events = self.control.store.fetch_pending_outbox_events(limit=10)
        dispatched_events = []
        for event in outbox_events:
            try:
                receipt = dispatch_outbox_event(event)
                
                # If this was an email, we need to confirm the pipeline message
                if event["operation"] == "send_email":
                    payload = event["payload"]
                    self.control.acquisition.confirm_external_send(
                        message_id=payload["message_id"],
                        actor=payload.get("actor", "jarvis"),
                        provider_receipt=receipt,
                    )
                    
                self.control.store.complete_outbox_event(event["id"])
                dispatched_events.append({"id": event["id"], "status": "success", "receipt": receipt})
            except Exception as exc:
                self.control.store.complete_outbox_event(event["id"], error=str(exc))
                dispatched_events.append({"id": event["id"], "status": "failed", "error": str(exc)})
                self.control.telemetry.alert(
                    severity="warning",
                    code="outbox_dispatch_failed",
                    message="Failed to dispatch outbox event.",
                    resource_id=event["id"],
                    details={"provider": event["provider"], "operation": event["operation"], "error": str(exc)}
                )

        recovered = self.control.store.recover_expired_executions(
            max_attempts=self.max_attempts
        )
        for item in recovered:
            self.control.store.publish_event(
                "execution.recovered",
                item["run_id"],
                item,
            )
            self.control.telemetry.alert(
                severity="warning",
                code="execution_lease_recovered",
                message="An abandoned employee execution lease was recovered.",
                resource_id=item["run_id"],
                details=item,
            )
            self.control.store.audit(
                "jarvis",
                "recover_execution",
                "execution",
                item["run_id"],
                "retry_scheduled" if item["retry_scheduled"] else "failed",
                item,
            )

        if self.automatic_reviews:
            reviewable = self.control.list_tasks(TaskState.AWAITING_REVIEW.value)
            if workflow_id:
                reviewable = [
                    task for task in reviewable if task["workflow_id"] == workflow_id
                ]
            if reviewable:
                task = reviewable[0]
                try:
                    review = self.reviewer_factory(self.control).run(task["id"])
                    return {
                        "status": "reviewed",
                        "recovered": recovered,
                        "review": review,
                    }
                except Exception as exc:  # noqa: BLE001 - defer any unsafe reviewer failure
                    self.control.store.audit(
                        "jarvis",
                        "automatic_review",
                        "task",
                        task["id"],
                        "deferred",
                        {"error": str(exc)[:2000]},
                    )
                    self.control.telemetry.alert(
                        severity="critical",
                        code="automatic_review_deferred",
                        message="Independent automated review failed closed.",
                        resource_id=task["id"],
                        details={"error_type": type(exc).__name__},
                    )
                    return {
                        "status": "review_deferred",
                        "recovered": recovered,
                        "task_id": task["id"],
                        "error": str(exc),
                    }

        claim = self.control.store.claim_next_task(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            max_attempts=self.max_attempts,
            workflow_id=workflow_id,
        )
        if claim is None:
            return {"status": "idle", "recovered": recovered, "outbox_dispatched": dispatched_events}

        run = claim["run"]
        task = claim["task"]
        self.control.store.publish_event(
            "execution.started",
            run["id"],
            {
                "task_id": task["id"],
                "worker_id": self.worker_id,
                "attempt": run["attempt"],
            },
        )
        self.control.store.audit(
            "jarvis",
            "lease_task",
            "execution",
            run["id"],
            "allowed",
            {"task_id": task["id"], "worker_id": self.worker_id},
        )

        stop_heartbeat = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(run["id"], stop_heartbeat),
            name=f"amaura-heartbeat-{run['id']}",
            daemon=True,
        )
        heartbeat.start()
        try:
            result = self.runner_factory(self.control).run(task["id"])
            execution = self.control.store.finish_execution(
                run["id"],
                worker_id=self.worker_id,
                succeeded=True,
                result=result,
                max_attempts=self.max_attempts,
            )
            self.control.store.publish_event(
                "execution.succeeded",
                run["id"],
                {"task_id": task["id"], "state": result["status"]},
            )
            self.control.telemetry.increment(
                "amaura_execution_total",
                labels={"outcome": "succeeded"},
            )
            return {
                "status": "executed",
                "recovered": recovered,
                "outbox_dispatched": dispatched_events,
                "execution": execution,
                "result": result,
            }
        except Exception as exc:  # noqa: BLE001 - every worker failure must close its lease
            retryable = self._is_retryable(exc)
            execution = self.control.store.finish_execution(
                run["id"],
                worker_id=self.worker_id,
                succeeded=False,
                error=str(exc),
                retryable=retryable,
                max_attempts=self.max_attempts,
            )
            self.control.store.publish_event(
                "execution.failed",
                run["id"],
                {
                    "task_id": task["id"],
                    "attempt": run["attempt"],
                    "retryable": retryable,
                    "error": str(exc)[:2000],
                },
            )
            self.control.store.audit(
                "jarvis",
                "execute_task",
                "execution",
                run["id"],
                "failed",
                {"retryable": retryable, "error": str(exc)[:2000]},
            )
            outcome = (
                "retry_scheduled"
                if self.control.store.get_work_item(task["id"])["state"]
                == TaskState.ASSIGNED.value
                else "failed"
            )
            self.control.telemetry.increment(
                "amaura_execution_total",
                labels={"outcome": outcome},
            )
            self.control.telemetry.alert(
                severity="warning" if retryable else "critical",
                code="employee_execution_failed",
                message="An employee execution failed inside the governed supervisor.",
                resource_id=task["id"],
                details={
                    "run_id": run["id"],
                    "attempt": run["attempt"],
                    "retryable": retryable,
                    "error_type": type(exc).__name__,
                },
            )
            return {
                "status": outcome,
                "recovered": recovered,
                "outbox_dispatched": dispatched_events,
                "execution": execution,
                "task_id": task["id"],
                "error": str(exc),
            }
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=2)

    def drain(
        self,
        *,
        workflow_id: str | None = None,
        max_ticks: int = 100,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for _ in range(max(1, min(max_ticks, 10_000))):
            result = self.tick(workflow_id=workflow_id)
            results.append(result)
            if result["status"] in {"idle", "review_deferred"}:
                break
        return results

    def run_forever(
        self,
        *,
        workflow_id: str | None = None,
        poll_seconds: float = 5.0,
        stop_event: threading.Event | None = None,
    ) -> None:
        stop = stop_event or threading.Event()
        poll_seconds = max(0.25, min(float(poll_seconds), 60.0))
        while not stop.is_set():
            result = self.tick(workflow_id=workflow_id)
            if result["status"] in {"idle", "review_deferred"}:
                stop.wait(poll_seconds)

    def _heartbeat_loop(self, run_id: str, stop: threading.Event) -> None:
        interval = max(10, min(self.lease_seconds // 3, 60))
        while not stop.wait(interval):
            try:
                self.control.store.heartbeat_execution(
                    run_id,
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
            except (KeyError, ValueError):
                return

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return True
        if isinstance(exc, OSError):
            return True
        if isinstance(exc, GovernanceError):
            message = str(exc).lower()
            return any(
                marker in message
                for marker in (
                    "inference failed",
                    "temporarily unavailable",
                    "timed out",
                    "timeout",
                    "connection",
                    "rate limit",
                )
            )
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Amaura durable workforce supervisor"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--once", action="store_true", help="Advance one execution or review"
    )
    mode.add_argument(
        "--drain", action="store_true", help="Run until no safe work is ready"
    )
    parser.add_argument(
        "--workflow", default="", help="Restrict work to one workflow key"
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-ticks", type=int, default=100)
    parser.add_argument("--no-auto-review", action="store_true")
    args = parser.parse_args()

    control = AmauraControlPlane()
    supervisor = AmauraSupervisor(
        control,
        lease_seconds=int(os.environ.get("AMAURA_LEASE_SECONDS", "900")),
        max_attempts=int(os.environ.get("AMAURA_MAX_ATTEMPTS", "2")),
        automatic_reviews=not args.no_auto_review,
    )
    try:
        if args.drain:
            print(
                json.dumps(
                    supervisor.drain(
                        workflow_id=args.workflow or None,
                        max_ticks=args.max_ticks,
                    ),
                    indent=2,
                    default=str,
                )
            )
        elif args.once:
            print(
                json.dumps(
                    supervisor.tick(workflow_id=args.workflow or None),
                    indent=2,
                    default=str,
                )
            )
        else:
            supervisor.run_forever(
                workflow_id=args.workflow or None,
                poll_seconds=args.poll_seconds,
            )
    except KeyboardInterrupt:
        return 0
    finally:
        control.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
