"""Durable SQLite ledger for Amaura work, evidence, approvals, and audit history."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from jarvis.paths import get_data_dir


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class CompanyStore:
    """Thread-safe, append-audited company state store."""

    JSON_COLUMNS: ClassVar[set[str]] = {
        "acceptance_criteria",
        "dependencies",
        "evidence",
        "metadata",
        "payload",
        "details",
        "config",
        "score_components",
        "output",
        "metrics",
        "lesson",
        "asset_metadata",
        "evidence_snapshot",
        "result",
        "labels",
        "attributes",
    }
    MUTABLE_WORK_FIELDS: ClassVar[set[str]] = {
        "owner_id",
        "reviewer_id",
        "state",
        "priority",
        "deadline",
        "budget_cents",
        "spent_cents",
        "risk",
        "success_metric",
        "acceptance_criteria",
        "dependencies",
        "evidence",
        "summary",
        "action_type",
        "metadata",
    }

    def __init__(self, db_path: str | Path | None = None):
        default_dir = Path(os.environ.get("AMAURA_DATA_DIR", get_data_dir() / "amaura"))
        self.db_path = Path(db_path) if db_path else default_dir / "amaura.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._autocommit = True  # set False inside atomic_block to batch commits
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextlib.contextmanager
    def atomic_block(self) -> Any:
        """Context manager that wraps multiple operations in a single transaction (P1).

        Within the block, individual operations skip their per-row commits.
        On exit the transaction is committed; on exception it is rolled back.
        This ensures compound operations (e.g. programme creation) are all-or-nothing.
        """
        with self._lock:
            nested = self._connection.in_transaction
            if not nested:
                self._connection.execute("BEGIN IMMEDIATE")
                self._autocommit = False
            try:
                yield
                if not nested:
                    self._connection.commit()
            except Exception:
                if not nested:
                    self._connection.rollback()
                raise
            finally:
                if not nested:
                    self._autocommit = True

    def _commit_if_needed(self) -> None:
        if self._autocommit:
            self._connection.commit()


    def integrity_check(self) -> dict[str, Any]:
        """Run SQLite structural and referential integrity checks."""
        with self._lock:
            integrity = [row[0] for row in self._connection.execute("PRAGMA integrity_check").fetchall()]
            foreign_keys = [dict(row) for row in self._connection.execute("PRAGMA foreign_key_check").fetchall()]
            journal_mode = self._connection.execute("PRAGMA journal_mode").fetchone()[0]
        audit_chain = self.audit_chain_check()
        return {
            "ok": integrity == ["ok"] and not foreign_keys and audit_chain["ok"],
            "integrity": integrity,
            "foreign_key_violations": foreign_keys,
            "journal_mode": journal_mode,
            "audit_chain": audit_chain,
        }

    def backup(self, destination: str | Path) -> Path:
        """Create a transactionally consistent SQLite backup."""
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(target) as backup_connection:
            self._connection.backup(backup_connection)
        return target

    def _migrate(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            definition TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            parent_id TEXT REFERENCES work_items(id),
            item_type TEXT NOT NULL,
            workflow_id TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            owner_id TEXT NOT NULL,
            reviewer_id TEXT,
            state TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 3,
            deadline TEXT,
            budget_cents INTEGER NOT NULL DEFAULT 0 CHECK (budget_cents >= 0),
            spent_cents INTEGER NOT NULL DEFAULT 0 CHECK (spent_cents >= 0),
            risk TEXT NOT NULL DEFAULT 'low',
            action_type TEXT NOT NULL DEFAULT 'internal_work',
            success_metric TEXT NOT NULL DEFAULT '',
            acceptance_criteria TEXT NOT NULL DEFAULT '[]',
            dependencies TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_work_parent ON work_items(parent_id);
        CREATE INDEX IF NOT EXISTS idx_work_state ON work_items(state);
        CREATE INDEX IF NOT EXISTS idx_work_owner ON work_items(owner_id);

        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES work_items(id),
            action_type TEXT NOT NULL,
            risk TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            decided_by TEXT,
            reason TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            payload_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT,
            resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pending_approval_per_task
            ON approvals(task_id) WHERE status = 'pending';

        CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

        CREATE TABLE IF NOT EXISTS audit_logs (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            prev_hash TEXT NOT NULL DEFAULT '',
            entry_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS knowledge (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            evidence_refs TEXT NOT NULL DEFAULT '[]',
            sensitivity TEXT NOT NULL DEFAULT 'internal',
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(namespace, key)
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            decision TEXT NOT NULL,
            context TEXT NOT NULL,
            options TEXT NOT NULL,
            chosen_option TEXT NOT NULL,
            reason TEXT NOT NULL,
            owner TEXT NOT NULL,
            review_date TEXT,
            outcome TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS costs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES work_items(id),
            agent_id TEXT NOT NULL,
            category TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
            units REAL NOT NULL DEFAULT 0,
            unit_name TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cost_task ON costs(task_id);

        CREATE TABLE IF NOT EXISTS execution_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES work_items(id),
            worker_id TEXT NOT NULL,
            attempt INTEGER NOT NULL CHECK(attempt > 0),
            state TEXT NOT NULL,
            lease_until TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_execution_runs_task ON execution_runs(task_id, attempt);
        CREATE INDEX IF NOT EXISTS idx_execution_runs_state_lease ON execution_runs(state, lease_until);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_execution_per_task
            ON execution_runs(task_id) WHERE state IN ('leased', 'running');

        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            target_segment TEXT NOT NULL,
            offer TEXT NOT NULL,
            minimum_score INTEGER NOT NULL DEFAULT 70 CHECK(minimum_score BETWEEN 0 AND 100),
            active INTEGER NOT NULL DEFAULT 1,
            daily_lead_limit INTEGER NOT NULL DEFAULT 10 CHECK(daily_lead_limit BETWEEN 1 AND 100),
            daily_outreach_limit INTEGER NOT NULL DEFAULT 3 CHECK(daily_outreach_limit BETWEEN 0 AND 50),
            daily_followup_limit INTEGER NOT NULL DEFAULT 5 CHECK(daily_followup_limit BETWEEN 0 AND 100),
            maximum_followups INTEGER NOT NULL DEFAULT 2 CHECK(maximum_followups BETWEEN 0 AND 5),
            config TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id),
            company_name TEXT NOT NULL,
            domain TEXT NOT NULL,
            contact_name TEXT NOT NULL DEFAULT '',
            public_contact TEXT NOT NULL DEFAULT '',
            contact_source_url TEXT NOT NULL DEFAULT '',
            linkedin_url TEXT NOT NULL DEFAULT '',
            country TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT 'discovered',
            total_score INTEGER NOT NULL DEFAULT 0 CHECK(total_score BETWEEN 0 AND 100),
            score_components TEXT NOT NULL DEFAULT '{}',
            do_not_contact INTEGER NOT NULL DEFAULT 0,
            opt_out_reason TEXT NOT NULL DEFAULT '',
            estimated_value_cents INTEGER NOT NULL DEFAULT 0 CHECK(estimated_value_cents >= 0),
            next_action TEXT NOT NULL DEFAULT '',
            next_action_at TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(domain)
        );
        CREATE INDEX IF NOT EXISTS idx_leads_campaign_stage ON leads(campaign_id, stage);
        CREATE INDEX IF NOT EXISTS idx_leads_next_action ON leads(next_action_at);

        CREATE TABLE IF NOT EXISTS lead_evidence (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL REFERENCES leads(id),
            claim_type TEXT NOT NULL,
            claim TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_excerpt TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(lead_id, claim_type, source_url, content_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_lead ON lead_evidence(lead_id);

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL REFERENCES leads(id),
            channel TEXT NOT NULL,
            message_type TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            recipient TEXT NOT NULL DEFAULT '',
            approved_payload_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            approved_by TEXT,
            approved_at TEXT,
            sent_at TEXT,
            external_message_id TEXT,
            thread_id TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            evidence_snapshot TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_lead ON messages(lead_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_external_id ON messages(external_message_id)
            WHERE external_message_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS pipeline_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT REFERENCES leads(id),
            campaign_id TEXT REFERENCES campaigns(id),
            event_type TEXT NOT NULL,
            agent TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            output TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pipeline_events_lead ON pipeline_events(lead_id, sequence);

        CREATE TABLE IF NOT EXISTS idempotency_records (
            idempotency_key TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            result_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_controls (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS content_campaigns (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            audience TEXT NOT NULL,
            business_objective TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            config TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS content_assets (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES content_campaigns(id),
            asset_type TEXT NOT NULL,
            uri TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            source_url TEXT NOT NULL DEFAULT '',
            creator TEXT NOT NULL DEFAULT '',
            licence TEXT NOT NULL DEFAULT '',
            asset_metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(campaign_id, asset_type, sha256)
        );
        CREATE INDEX IF NOT EXISTS idx_content_assets_campaign ON content_assets(campaign_id);

        CREATE TABLE IF NOT EXISTS content_metrics (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES content_campaigns(id),
            platform TEXT NOT NULL,
            window TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            metrics TEXT NOT NULL,
            UNIQUE(campaign_id, platform, window)
        );

        CREATE TABLE IF NOT EXISTS content_lessons (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES content_campaigns(id),
            lesson TEXT NOT NULL,
            evidence_refs TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS review_attestations (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES work_items(id),
            reviewer_id TEXT NOT NULL,
            reviewer_model TEXT NOT NULL,
            submission_sha256 TEXT NOT NULL,
            decision TEXT NOT NULL,
            signature TEXT NOT NULL,
            attestation TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_review_attestations_task
            ON review_attestations(task_id, created_at);

        CREATE TABLE IF NOT EXISTS operational_metrics (
            name TEXT NOT NULL,
            labels_key TEXT NOT NULL,
            labels TEXT NOT NULL DEFAULT '{}',
            value REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(name, labels_key)
        );

        CREATE TABLE IF NOT EXISTS operational_traces (
            id TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            outcome TEXT NOT NULL,
            duration_ms REAL NOT NULL CHECK(duration_ms >= 0),
            attributes TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_operational_traces_created
            ON operational_traces(created_at);

        CREATE TABLE IF NOT EXISTS operational_alerts (
            id TEXT PRIMARY KEY,
            severity TEXT NOT NULL,
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            resource_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_operational_alerts_status
            ON operational_alerts(status, created_at);
        """
        with self._lock:
            self._connection.executescript(schema)
            self._ensure_column("approvals", "payload_hash", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("approvals", "expires_at", "TEXT")
            self._ensure_column("audit_logs", "prev_hash", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("audit_logs", "entry_hash", "TEXT NOT NULL DEFAULT ''")
            # P0-6: bind recipient and payload hash to message at staging time
            self._ensure_column("messages", "recipient", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("messages", "approved_payload_hash", "TEXT NOT NULL DEFAULT ''")
            self._backfill_approval_integrity()
            self._backfill_audit_hash_chain()
            self._commit_if_needed()

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        columns = {row["name"] for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def canonical_hash(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _backfill_approval_integrity(self) -> None:
        rows = self._connection.execute("SELECT id,payload,payload_hash,created_at,expires_at FROM approvals").fetchall()
        for row in rows:
            changes: dict[str, str] = {}
            if not row["payload_hash"]:
                try:
                    payload = json.loads(row["payload"])
                except json.JSONDecodeError:
                    payload = row["payload"]
                changes["payload_hash"] = self.canonical_hash(payload)
            if not row["expires_at"]:
                created_at = datetime.fromisoformat(row["created_at"])
                changes["expires_at"] = (created_at + timedelta(hours=48)).isoformat()
            if changes:
                self._connection.execute(f"UPDATE approvals SET {', '.join(f'{key}=?' for key in changes)} WHERE id=?", [*changes.values(), row["id"]])

    @staticmethod
    def _audit_digest(*, previous: str, actor: str, action: str, resource_type: str, resource_id: str, outcome: str, details_json: str, created_at: str) -> str:
        entry = {"actor": actor, "action": action, "resource_type": resource_type, "resource_id": resource_id, "outcome": outcome, "details": details_json, "created_at": created_at}
        payload = previous + json.dumps(entry, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def _backfill_audit_hash_chain(self) -> None:
        previous = ""
        rows = self._connection.execute("SELECT * FROM audit_logs ORDER BY sequence").fetchall()
        for row in rows:
            expected = self._audit_digest(
                previous=previous,
                actor=row["actor"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                outcome=row["outcome"],
                details_json=row["details"],
                created_at=row["created_at"],
            )
            if not row["entry_hash"]:
                self._connection.execute("UPDATE audit_logs SET prev_hash=?,entry_hash=? WHERE sequence=?", (previous, expected, row["sequence"]))
                previous = expected
            else:
                previous = row["entry_hash"]

    def audit_chain_check(self) -> dict[str, Any]:
        previous = ""
        with self._lock:
            rows = self._connection.execute("SELECT * FROM audit_logs ORDER BY sequence").fetchall()
        for row in rows:
            expected = self._audit_digest(
                previous=previous,
                actor=row["actor"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                outcome=row["outcome"],
                details_json=row["details"],
                created_at=row["created_at"],
            )
            if row["prev_hash"] != previous or row["entry_hash"] != expected:
                return {"ok": False, "broken_at_sequence": row["sequence"], "entries": len(rows)}
            previous = row["entry_hash"]
        return {"ok": True, "broken_at_sequence": None, "entries": len(rows), "head": previous}

    @staticmethod
    def _decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for key in CompanyStore.JSON_COLUMNS | {"definition", "evidence_refs", "options"}:
            if key in result and isinstance(result[key], str):
                try:
                    result[key] = json.loads(result[key])
                except json.JSONDecodeError:
                    pass
        if "enabled" in result:
            result["enabled"] = bool(result["enabled"])
        for key in ("active", "do_not_contact"):
            if key in result:
                result[key] = bool(result[key])
        return result

    def upsert_agent(self, definition: dict[str, Any]) -> None:
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """INSERT INTO agents(agent_id, name, department, definition, enabled, updated_at)
                VALUES(?, ?, ?, ?, 1, ?)
                ON CONFLICT(agent_id) DO UPDATE SET name=excluded.name,
                department=excluded.department, definition=excluded.definition, updated_at=excluded.updated_at""",
                (definition["agent_id"], definition["name"], definition["department"], json.dumps(definition), now),
            )
            self._commit_if_needed()

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM agents ORDER BY department, name").fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        decoded = self._decode_row(row)
        if decoded is None:
            raise KeyError(f"Unknown Amaura agent: {agent_id}")
        return decoded

    def set_agent_enabled(self, agent_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            cursor = self._connection.execute("UPDATE agents SET enabled = ?, updated_at = ? WHERE agent_id = ?", (int(enabled), utc_now(), agent_id))
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown Amaura agent: {agent_id}")
            self._commit_if_needed()
        return self.get_agent(agent_id)

    def insert_work_item(self, item: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        values = {
            "parent_id": None,
            "workflow_id": None,
            "description": "",
            "reviewer_id": None,
            "state": "assigned",
            "priority": 3,
            "deadline": None,
            "budget_cents": 0,
            "spent_cents": 0,
            "risk": "low",
            "action_type": "internal_work",
            "success_metric": "",
            "acceptance_criteria": [],
            "dependencies": [],
            "evidence": [],
            "summary": "",
            "metadata": {},
            **item,
        }
        columns = (
            "id",
            "parent_id",
            "item_type",
            "workflow_id",
            "title",
            "description",
            "owner_id",
            "reviewer_id",
            "state",
            "priority",
            "deadline",
            "budget_cents",
            "spent_cents",
            "risk",
            "action_type",
            "success_metric",
            "acceptance_criteria",
            "dependencies",
            "evidence",
            "summary",
            "metadata",
            "created_at",
            "updated_at",
        )
        values["created_at"] = now
        values["updated_at"] = now
        encoded = [json.dumps(values[c]) if c in self.JSON_COLUMNS else values[c] for c in columns]
        placeholders = ", ".join("?" for _ in columns)
        with self._lock:
            self._connection.execute(f"INSERT INTO work_items({', '.join(columns)}) VALUES({placeholders})", encoded)
            if self._autocommit:
                self._commit_if_needed()
        return self.get_work_item(values["id"])

    def get_work_item(self, item_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
        decoded = self._decode_row(row)
        if decoded is None:
            raise KeyError(f"Unknown work item: {item_id}")
        return decoded

    def list_work_items(self, *, item_type: str | None = None, state: str | None = None, owner_id: str | None = None, parent_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("item_type", item_type), ("state", state), ("owner_id", owner_id), ("parent_id", parent_id)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(limit, 1000)))
        with self._lock:
            rows = self._connection.execute(f"SELECT * FROM work_items{where} ORDER BY priority ASC, created_at ASC LIMIT ?", params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def update_work_item(self, item_id: str, **fields: Any) -> dict[str, Any]:
        invalid = set(fields) - self.MUTABLE_WORK_FIELDS
        if invalid:
            raise ValueError(f"Invalid work-item fields: {', '.join(sorted(invalid))}")
        if not fields:
            return self.get_work_item(item_id)
        fields["updated_at"] = utc_now()
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            params.append(json.dumps(value) if key in self.JSON_COLUMNS else value)
        params.append(item_id)
        with self._lock:
            cursor = self._connection.execute(f"UPDATE work_items SET {', '.join(assignments)} WHERE id = ?", params)
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown work item: {item_id}")
            self._commit_if_needed()
        return self.get_work_item(item_id)

    def create_approval(self, approval: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        values = {"status": "pending", "decided_by": None, "reason": "", "payload": {}, "expires_at": (datetime.now(UTC) + timedelta(hours=48)).isoformat(), **approval}
        payload_json = json.dumps(values["payload"], sort_keys=True, separators=(",", ":"), default=str)
        payload_hash = self.canonical_hash(values["payload"])
        with self._lock:
            try:
                self._connection.execute(
                    """INSERT INTO approvals(id, task_id, action_type, risk, status, requested_by,
                    decided_by, reason, payload, payload_hash, created_at, expires_at, resolved_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
                    (
                        values["id"],
                        values["task_id"],
                        values["action_type"],
                        values["risk"],
                        values["status"],
                        values["requested_by"],
                        values["decided_by"],
                        values["reason"],
                        payload_json,
                        payload_hash,
                        now,
                        values["expires_at"],
                    ),
                )
                self._commit_if_needed()
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                if "approvals.task_id" in str(exc):
                    existing = self._connection.execute("SELECT id FROM approvals WHERE task_id=? AND status='pending'", (values["task_id"],)).fetchone()
                    if existing:
                        return self.get_approval(existing["id"])
                raise
        return self.get_approval(values["id"])

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        decoded = self._decode_row(row)
        if decoded is None:
            raise KeyError(f"Unknown approval: {approval_id}")
        return decoded

    def list_approvals(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM approvals"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def expire_stale_approvals(self) -> int:
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE approvals SET status='expired',resolved_at=?
                WHERE status='pending' AND expires_at IS NOT NULL AND expires_at<=?""",
                (utc_now(), utc_now()),
            )
            self._commit_if_needed()
        return cursor.rowcount

    def resolve_approval(self, approval_id: str, status: str, decided_by: str, reason: str) -> dict[str, Any]:
        with self._lock:
            current = self._connection.execute("SELECT status,expires_at FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if current is None:
                raise KeyError(f"Unknown approval: {approval_id}")
            if current["status"] != "pending":
                raise ValueError(f"Approval is already {current['status']}")
            if current["expires_at"] and datetime.fromisoformat(current["expires_at"]) <= datetime.now(UTC):
                self._connection.execute("UPDATE approvals SET status='expired',resolved_at=? WHERE id=? AND status='pending'", (utc_now(), approval_id))
                self._commit_if_needed()
                raise ValueError("Approval has expired and must be requested again")
            cursor = self._connection.execute(
                """UPDATE approvals SET status = ?, decided_by = ?, reason = ?, resolved_at = ?
                WHERE id = ? AND status = 'pending'""",
                (status, decided_by, reason, utc_now(), approval_id),
            )
            if cursor.rowcount != 1:
                latest = self.get_approval(approval_id)
                raise ValueError(f"Approval is already {latest['status']}")
            self._commit_if_needed()
        return self.get_approval(approval_id)

    def publish_event(self, event_type: str, aggregate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        created_at = utc_now()
        with self._lock:
            cursor = self._connection.execute("INSERT INTO events(event_type, aggregate_id, payload, created_at) VALUES(?, ?, ?, ?)", (event_type, aggregate_id, json.dumps(payload), created_at))
            self._commit_if_needed()
        return {"sequence": cursor.lastrowid, "event_type": event_type, "aggregate_id": aggregate_id, "payload": payload, "created_at": created_at}

    def list_events(self, event_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM events"
        params: list[Any] = []
        if event_type:
            query += " WHERE event_type = ?"
            params.append(event_type)
        query += " ORDER BY sequence DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def audit(self, actor: str, action: str, resource_type: str, resource_id: str, outcome: str, details: dict[str, Any] | None = None) -> None:
        created_at = utc_now()
        details_json = json.dumps(details or {}, sort_keys=True, separators=(",", ":"), default=str)
        with self._lock:
            row = self._connection.execute("SELECT entry_hash FROM audit_logs ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = row["entry_hash"] if row else ""
            entry_hash = self._audit_digest(
                previous=previous, actor=actor, action=action, resource_type=resource_type, resource_id=resource_id, outcome=outcome, details_json=details_json, created_at=created_at
            )
            self._connection.execute(
                """INSERT INTO audit_logs(actor, action, resource_type, resource_id, outcome, details,
                prev_hash,entry_hash,created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (actor, action, resource_type, resource_id, outcome, details_json, previous, entry_hash, created_at),
            )
            self._commit_if_needed()

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM audit_logs ORDER BY sequence DESC LIMIT ?", (max(1, min(limit, 1000)),)).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def record_cost(self, entry: dict[str, Any]) -> None:
        metadata = entry.get("metadata", {})
        with self._lock:
            self._connection.execute(
                """INSERT INTO costs(id, task_id, agent_id, category, amount_cents, units, unit_name, metadata, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry["id"], entry["task_id"], entry["agent_id"], entry["category"], entry["amount_cents"], entry.get("units", 0), entry.get("unit_name", ""), json.dumps(metadata), utc_now()),
            )
            self._connection.execute("UPDATE work_items SET spent_cents = spent_cents + ?, updated_at = ? WHERE id = ?", (entry["amount_cents"], utc_now(), entry["task_id"]))
            self._commit_if_needed()

    def upsert_knowledge(self, namespace: str, key: str, value: Any, evidence_refs: list[str], sensitivity: str, actor: str) -> None:
        with self._lock:
            self._connection.execute(
                """INSERT INTO knowledge(namespace, key, value, evidence_refs, sensitivity, updated_by, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET value=excluded.value,
                evidence_refs=excluded.evidence_refs, sensitivity=excluded.sensitivity,
                updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                (namespace, key, json.dumps(value), json.dumps(evidence_refs), sensitivity, actor, utc_now()),
            )
            self._commit_if_needed()

    def record_decision(self, decision: dict[str, Any]) -> None:
        with self._lock:
            self._connection.execute(
                """INSERT INTO decisions(id, decision, context, options, chosen_option, reason, owner,
                review_date, outcome, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision["id"],
                    decision["decision"],
                    decision["context"],
                    json.dumps(decision["options"]),
                    decision["chosen_option"],
                    decision["reason"],
                    decision["owner"],
                    decision.get("review_date"),
                    decision.get("outcome", ""),
                    utc_now(),
                ),
            )
            self._commit_if_needed()

    # -- Revenue pipeline -------------------------------------------------

    def upsert_campaign(self, campaign: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        values = {"minimum_score": 70, "active": True, "daily_lead_limit": 10, "daily_outreach_limit": 3, "daily_followup_limit": 5, "maximum_followups": 2, "config": {}, **campaign}
        with self._lock:
            self._connection.execute(
                """INSERT INTO campaigns(id,name,target_segment,offer,minimum_score,active,
                daily_lead_limit,daily_outreach_limit,daily_followup_limit,maximum_followups,
                config,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,target_segment=excluded.target_segment,
                offer=excluded.offer,minimum_score=excluded.minimum_score,active=excluded.active,
                daily_lead_limit=excluded.daily_lead_limit,daily_outreach_limit=excluded.daily_outreach_limit,
                daily_followup_limit=excluded.daily_followup_limit,maximum_followups=excluded.maximum_followups,
                config=excluded.config,updated_at=excluded.updated_at""",
                (
                    values["id"],
                    values["name"],
                    values["target_segment"],
                    values["offer"],
                    values["minimum_score"],
                    int(values["active"]),
                    values["daily_lead_limit"],
                    values["daily_outreach_limit"],
                    values["daily_followup_limit"],
                    values["maximum_followups"],
                    json.dumps(values["config"]),
                    now,
                    now,
                ),
            )
            self._commit_if_needed()
        return self.get_campaign(values["id"])

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        result = self._decode_row(row)
        if result is None:
            raise KeyError(f"Unknown campaign: {campaign_id}")
        return result

    def list_campaigns(self, active: bool | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM campaigns", []
        if active is not None:
            query, params = query + " WHERE active=?", [int(active)]
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def insert_lead(self, lead: dict[str, Any], *, daily_limit: int | None = None, day_prefix: str = "") -> dict[str, Any]:
        now = utc_now()
        values = {
            "contact_name": "",
            "public_contact": "",
            "contact_source_url": "",
            "linkedin_url": "",
            "country": "",
            "industry": "",
            "stage": "discovered",
            "total_score": 0,
            "score_components": {},
            "do_not_contact": False,
            "opt_out_reason": "",
            "estimated_value_cents": 0,
            "next_action": "",
            "next_action_at": None,
            "metadata": {},
            **lead,
        }
        with self.atomic_block():
                if daily_limit is not None:
                    count = self._connection.execute("SELECT COUNT(*) FROM leads WHERE campaign_id=? AND created_at LIKE ?", (values["campaign_id"], f"{day_prefix}%")).fetchone()[0]
                    if count >= daily_limit:
                        raise ValueError("Daily lead discovery limit reached")
                self._connection.execute(
                    """INSERT INTO leads(id,campaign_id,company_name,domain,contact_name,public_contact,
                    contact_source_url,linkedin_url,country,industry,stage,total_score,score_components,
                    do_not_contact,opt_out_reason,estimated_value_cents,next_action,next_action_at,metadata,
                    created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        values["id"],
                        values["campaign_id"],
                        values["company_name"],
                        values["domain"],
                        values["contact_name"],
                        values["public_contact"],
                        values["contact_source_url"],
                        values["linkedin_url"],
                        values["country"],
                        values["industry"],
                        values["stage"],
                        values["total_score"],
                        json.dumps(values["score_components"]),
                        int(values["do_not_contact"]),
                        values["opt_out_reason"],
                        values["estimated_value_cents"],
                        values["next_action"],
                        values["next_action_at"],
                        json.dumps(values["metadata"]),
                        now,
                        now,
                    ),
                )
        return self.get_lead(values["id"])

    def get_lead(self, lead_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        result = self._decode_row(row)
        if result is None:
            raise KeyError(f"Unknown lead: {lead_id}")
        return result

    def get_lead_by_domain(self, domain: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM leads WHERE domain=?", (domain,)).fetchone()
        return self._decode_row(row)

    def list_leads(self, campaign_id: str | None = None, stage: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if campaign_id:
            clauses.append("campaign_id=?")
            params.append(campaign_id)
        if stage:
            clauses.append("stage=?")
            params.append(stage)
        query = "SELECT * FROM leads" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        query += " ORDER BY total_score DESC, created_at ASC LIMIT ?"
        params.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def update_lead(self, lead_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "stage",
            "total_score",
            "score_components",
            "do_not_contact",
            "opt_out_reason",
            "estimated_value_cents",
            "next_action",
            "next_action_at",
            "metadata",
            "contact_name",
            "public_contact",
            "contact_source_url",
            "linkedin_url",
            "country",
            "industry",
        }
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Invalid lead fields: {', '.join(sorted(invalid))}")
        if not fields:
            return self.get_lead(lead_id)
        fields["updated_at"] = utc_now()
        assignments, params = [], []
        for key, value in fields.items():
            assignments.append(f"{key}=?")
            if key in {"score_components", "metadata"}:
                value = json.dumps(value)
            elif key == "do_not_contact":
                value = int(value)
            params.append(value)
        params.append(lead_id)
        with self._lock:
            cursor = self._connection.execute(f"UPDATE leads SET {', '.join(assignments)} WHERE id=?", params)
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown lead: {lead_id}")
            self._commit_if_needed()
        return self.get_lead(lead_id)

    def add_lead_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        values = {"retrieved_at": utc_now(), **evidence}
        with self._lock:
            self._connection.execute(
                """INSERT INTO lead_evidence(id,lead_id,claim_type,claim,source_url,source_excerpt,
                retrieved_at,confidence,content_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    values["id"],
                    values["lead_id"],
                    values["claim_type"],
                    values["claim"],
                    values["source_url"],
                    values["source_excerpt"],
                    values["retrieved_at"],
                    values["confidence"],
                    values["content_hash"],
                    utc_now(),
                ),
            )
            self._commit_if_needed()
        with self._lock:
            row = self._connection.execute("SELECT * FROM lead_evidence WHERE id=?", (values["id"],)).fetchone()
        return self._decode_row(row)  # type: ignore[return-value]

    def list_lead_evidence(self, lead_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM lead_evidence WHERE lead_id=? ORDER BY created_at", (lead_id,)).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def insert_message(self, message: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        values = {
            "subject": "", "recipient": "", "approved_payload_hash": "",
            "status": "draft", "approved_by": None, "approved_at": None,
            "sent_at": None, "external_message_id": None, "thread_id": None,
            "evidence_snapshot": [],
            **message,
        }
        with self._lock:
            self._connection.execute(
                """INSERT INTO messages(id,lead_id,channel,message_type,subject,body,
                recipient,approved_payload_hash,status,approved_by,
                approved_at,sent_at,external_message_id,thread_id,idempotency_key,evidence_snapshot,
                created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    values["id"],
                    values["lead_id"],
                    values["channel"],
                    values["message_type"],
                    values["subject"],
                    values["body"],
                    values["recipient"],
                    values["approved_payload_hash"],
                    values["status"],
                    values["approved_by"],
                    values["approved_at"],
                    values["sent_at"],
                    values["external_message_id"],
                    values["thread_id"],
                    values["idempotency_key"],
                    json.dumps(values["evidence_snapshot"]),
                    now,
                    now,
                ),
            )
            self._commit_if_needed()
        return self.get_message(values["id"])

    def get_message(self, message_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        result = self._decode_row(row)
        if result is None:
            raise KeyError(f"Unknown message: {message_id}")
        return result

    def update_message(self, message_id: str, **fields: Any) -> dict[str, Any]:
        # subject and body are write-once: they are set at staging time and locked
        # from that point forward to enforce exact-payload approval (P0-6).
        # approved_payload_hash is written once at approval time by decide_message.
        allowed = {"status", "approved_by", "approved_at", "sent_at",
                   "external_message_id", "thread_id", "approved_payload_hash"}
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Invalid message fields: {', '.join(sorted(invalid))}")
        fields["updated_at"] = utc_now()
        with self._lock:
            cursor = self._connection.execute(f"UPDATE messages SET {', '.join(f'{key}=?' for key in fields)} WHERE id=?", [*fields.values(), message_id])
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown message: {message_id}")
            self._commit_if_needed()
        return self.get_message(message_id)

    def mark_message_sending(self, message_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE messages SET status='sending',updated_at=?
                WHERE id=? AND status='approved'""",
                (now, message_id),
            )
            if cursor.rowcount != 1:
                message = self.get_message(message_id)
                if message["status"] == "sent":
                    return message
                raise ValueError(
                    f"Message is {message['status']} and cannot start a new provider send"
                )
            self._commit_if_needed()
        return self.get_message(message_id)

    def mark_message_reconciliation_required(self, message_id: str, reason: str) -> dict[str, Any]:
        now = utc_now()
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE messages SET status='reconciliation_required',updated_at=?
                WHERE id=? AND status='sending'""",
                (now, message_id),
            )
            if cursor.rowcount != 1:
                return self.get_message(message_id)
            self._commit_if_needed()
        self.publish_event("message.reconciliation_required", message_id, {"reason": reason})
        return self.get_message(message_id)

    def confirm_message_sent_atomic(self, message_id: str, *, campaign_id: str, is_followup: bool, daily_limit: int, since: str, external_message_id: str, thread_id: str | None) -> dict[str, Any]:
        """Atomically enforce a campaign cap and record provider-confirmed delivery."""
        with self.atomic_block():
                message = self._connection.execute("SELECT status FROM messages WHERE id=?", (message_id,)).fetchone()
                if message is None:
                    raise KeyError(f"Unknown message: {message_id}")
                if message["status"] == "sent":
                    self._connection.rollback()
                    return self.get_message(message_id)
                if message["status"] not in {"approved", "sending"}:
                    raise ValueError("Only an approved or sending message can be marked sent")
                comparator = "='followup'" if is_followup else "!='followup'"
                count = self._connection.execute(
                    f"""SELECT COUNT(*) FROM messages m JOIN leads l ON l.id=m.lead_id
                    WHERE l.campaign_id=? AND m.status='sent' AND m.message_type{comparator}
                    AND m.sent_at>=?""",
                    (campaign_id, since),
                ).fetchone()[0]
                if count >= daily_limit:
                    raise ValueError("Campaign daily outbound limit reached")
                now = utc_now()
                self._connection.execute(
                    """UPDATE messages SET status='sent',sent_at=?,external_message_id=?,thread_id=?,updated_at=?
                    WHERE id=?""",
                    (now, external_message_id, thread_id, now, message_id),
                )
        return self.get_message(message_id)

    def list_messages(self, lead_id: str | None = None, status: str | None = None, since: str | None = None) -> list[dict[str, Any]]:
        clauses, params = [], []
        for column, value in (("lead_id", lead_id), ("status", status)):
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        if since:
            clauses.append("created_at>=?")
            params.append(since)
        query = "SELECT * FROM messages" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY created_at DESC"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def publish_pipeline_event(self, *, lead_id: str | None, campaign_id: str | None, event_type: str, agent: str, input_hash: str, output: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO pipeline_events(lead_id,campaign_id,event_type,agent,input_hash,output,created_at) VALUES(?,?,?,?,?,?,?)",
                (lead_id, campaign_id, event_type, agent, input_hash, json.dumps(output), now),
            )
            self._commit_if_needed()
        return {"sequence": cursor.lastrowid, "lead_id": lead_id, "campaign_id": campaign_id, "event_type": event_type, "agent": agent, "input_hash": input_hash, "output": output, "created_at": now}

    def list_pipeline_events(self, lead_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        query = "SELECT * FROM pipeline_events"
        params: list[Any] = []
        if lead_id:
            query += " WHERE lead_id=?"
            params.append(lead_id)
        query += " ORDER BY sequence DESC LIMIT ?"
        params.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def record_idempotency(self, key: str, operation: str, resource_id: str, result_hash: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO idempotency_records(idempotency_key,operation,resource_id,result_hash,created_at) VALUES(?,?,?,?,?)", (key, operation, resource_id, result_hash, utc_now())
            )
            self._commit_if_needed()
        return cursor.rowcount == 1

    def get_idempotency(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM idempotency_records WHERE idempotency_key=?", (key,)).fetchone()
        return self._decode_row(row)

    def set_control(self, key: str, value: str, actor: str) -> None:
        with self._lock:
            self._connection.execute(
                """INSERT INTO system_controls(key,value,updated_by,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (key, value, actor, utc_now()),
            )
            self._commit_if_needed()

    def get_control(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._connection.execute("SELECT value FROM system_controls WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    # -- Durable worker leases -------------------------------------------

    def _get_execution(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM execution_runs WHERE id=?", (run_id,)).fetchone()
        decoded = self._decode_row(row)
        if decoded is None:
            raise KeyError(f"Unknown execution run: {run_id}")
        return decoded

    def list_executions(self, *, state: str | None = None, task_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if state:
            clauses.append("state=?")
            params.append(state)
        if task_id:
            clauses.append("task_id=?")
            params.append(task_id)
        query = "SELECT * FROM execution_runs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def recover_expired_executions(self, *, max_attempts: int = 3) -> list[dict[str, Any]]:
        """Expire abandoned leases and make retryable tasks available again."""
        now = utc_now()
        recovered: list[dict[str, Any]] = []
        with self.atomic_block():
                rows = self._connection.execute(
                    """SELECT * FROM execution_runs
                    WHERE state IN ('leased','running') AND lease_until<=?
                    ORDER BY started_at""",
                    (now,),
                ).fetchall()
                for row in rows:
                    self._connection.execute(
                        """UPDATE execution_runs
                        SET state='expired',finished_at=?,error=?
                        WHERE id=? AND state IN ('leased','running')""",
                        (now, "Worker lease expired before completion", row["id"]),
                    )
                    retry = row["attempt"] < max(1, max_attempts)
                    task_state = "assigned" if retry else "failed"
                    self._connection.execute(
                        """UPDATE work_items SET state=?,updated_at=?,
                        summary=CASE WHEN summary='' THEN ? ELSE ? || '\n\n' || summary END
                        WHERE id=? AND state='in_progress'""",
                        (task_state, now, "Execution lease expired; JARVIS recovered the task.", "Execution lease expired; JARVIS recovered the task.", row["task_id"]),
                    )
                    recovered.append({"run_id": row["id"], "task_id": row["task_id"], "attempt": row["attempt"], "retry_scheduled": retry})
        return recovered

    def claim_next_task(self, *, worker_id: str, lease_seconds: int = 900, max_attempts: int = 3, workflow_id: str | None = None) -> dict[str, Any] | None:
        """Atomically lease one dependency-ready task to one worker."""
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        lease_seconds = max(30, min(int(lease_seconds), 86_400))
        max_attempts = max(1, min(int(max_attempts), 20))
        self.recover_expired_executions(max_attempts=max_attempts)
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        lease_until = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        with self.atomic_block():
                params: list[Any] = []
                workflow_clause = ""
                if workflow_id:
                    workflow_clause = " AND w.workflow_id=?"
                    params.append(workflow_id)
                candidates = self._connection.execute(
                    f"""SELECT w.* FROM work_items w
                    JOIN agents a ON a.agent_id=w.owner_id AND a.enabled=1
                    WHERE w.item_type='task' AND w.state IN ('assigned','blocked')
                    {workflow_clause}
                    AND NOT EXISTS (
                        SELECT 1 FROM execution_runs r
                        WHERE r.task_id=w.id AND r.state IN ('leased','running')
                    )
                    ORDER BY w.priority ASC,w.created_at ASC LIMIT 200""",
                    params,
                ).fetchall()
                selected: sqlite3.Row | None = None
                attempt = 0
                for candidate in candidates:
                    try:
                        dependencies = json.loads(candidate["dependencies"])
                    except json.JSONDecodeError:
                        dependencies = []
                    if dependencies:
                        placeholders = ",".join("?" for _ in dependencies)
                        incomplete = self._connection.execute(
                            f"""SELECT COUNT(*) FROM work_items
                            WHERE id IN ({placeholders}) AND state!='completed'""",
                            dependencies,
                        ).fetchone()[0]
                        if incomplete:
                            if candidate["state"] != "blocked":
                                self._connection.execute("UPDATE work_items SET state='blocked',updated_at=? WHERE id=?", (now, candidate["id"]))
                            continue
                    prior = self._connection.execute("SELECT COALESCE(MAX(attempt),0) FROM execution_runs WHERE task_id=?", (candidate["id"],)).fetchone()[0]
                    if prior >= max_attempts:
                        self._connection.execute("UPDATE work_items SET state='failed',updated_at=? WHERE id=?", (now, candidate["id"]))
                        continue
                    selected = candidate
                    attempt = prior + 1
                    break
                if selected is None:
                    self._commit_if_needed()
                    return None
                cursor = self._connection.execute(
                    """UPDATE work_items SET state='in_progress',updated_at=?
                    WHERE id=? AND state IN ('assigned','blocked')""",
                    (now, selected["id"]),
                )
                if cursor.rowcount != 1:
                    self._connection.rollback()
                    return None
                self._connection.execute(
                    """INSERT INTO execution_runs(
                    id,task_id,worker_id,attempt,state,lease_until,heartbeat_at,started_at,result
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (run_id, selected["id"], worker_id.strip(), attempt, "running", lease_until, now, now, "{}"),
                )
        return {"run": self._get_execution(run_id), "task": self.get_work_item(selected["id"])}

    def heartbeat_execution(self, run_id: str, *, worker_id: str, lease_seconds: int = 900) -> dict[str, Any]:
        now_dt = datetime.now(UTC)
        lease_until = (now_dt + timedelta(seconds=max(30, min(int(lease_seconds), 86_400)))).isoformat()
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE execution_runs SET heartbeat_at=?,lease_until=?
                WHERE id=? AND worker_id=? AND state='running'""",
                (now_dt.isoformat(), lease_until, run_id, worker_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Execution lease is no longer active or belongs to another worker")
            self._commit_if_needed()
        return self._get_execution(run_id)

    def finish_execution(self, run_id: str, *, worker_id: str, succeeded: bool, result: dict[str, Any] | None = None, error: str = "", retryable: bool = True, max_attempts: int = 3) -> dict[str, Any]:
        """Close a lease and deterministically retry or fail an interrupted task."""
        now = utc_now()
        with self.atomic_block():
                run = self._connection.execute("SELECT * FROM execution_runs WHERE id=?", (run_id,)).fetchone()
                if run is None:
                    raise KeyError(f"Unknown execution run: {run_id}")
                if run["worker_id"] != worker_id:
                    raise ValueError("Execution lease belongs to another worker")
                if run["state"] != "running":
                    raise ValueError(f"Execution run is already {run['state']}")
                state = "succeeded" if succeeded else "failed"
                self._connection.execute(
                    """UPDATE execution_runs SET state=?,finished_at=?,heartbeat_at=?,
                    error=?,result=? WHERE id=?""",
                    (state, now, now, error[:4000], json.dumps(result or {}, sort_keys=True, default=str), run_id),
                )
                if not succeeded:
                    retry = retryable and run["attempt"] < max(1, max_attempts)
                    task_state = "assigned" if retry else "failed"
                    summary = f"EXECUTION ATTEMPT {run['attempt']} FAILED: {error[:2000]}" if error else f"EXECUTION ATTEMPT {run['attempt']} FAILED"
                    self._connection.execute(
                        """UPDATE work_items SET state=?,updated_at=?,
                        summary=CASE WHEN summary='' THEN ? ELSE ? || '\n\n' || summary END
                        WHERE id=? AND state='in_progress'""",
                        (task_state, now, summary, summary, run["task_id"]),
                    )
        return self._get_execution(run_id)

    def execution_status(self) -> dict[str, Any]:
        with self._lock:
            counts = {row["state"]: row["count"] for row in self._connection.execute("SELECT state,COUNT(*) AS count FROM execution_runs GROUP BY state").fetchall()}
            active = [
                self._decode_row(row)
                for row in self._connection.execute(
                    """SELECT * FROM execution_runs WHERE state IN ('leased','running')
                    ORDER BY started_at"""
                ).fetchall()
            ]
        return {"counts": counts, "active": active}

    # -- Content factory --------------------------------------------------

    def create_content_campaign(self, campaign: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        values = {"status": "draft", "config": {}, **campaign}
        with self._lock:
            self._connection.execute(
                "INSERT INTO content_campaigns(id,title,audience,business_objective,status,config,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (values["id"], values["title"], values["audience"], values["business_objective"], values["status"], json.dumps(values["config"]), now, now),
            )
            self._commit_if_needed()
        return self.get_content_campaign(values["id"])

    def get_content_campaign(self, campaign_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM content_campaigns WHERE id=?", (campaign_id,)).fetchone()
        result = self._decode_row(row)
        if result is None:
            raise KeyError(f"Unknown content campaign: {campaign_id}")
        return result

    def add_content_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        values = {"status": "draft", "source_url": "", "creator": "", "licence": "", "asset_metadata": {}, **asset}
        with self._lock:
            self._connection.execute(
                """INSERT INTO content_assets(id,campaign_id,asset_type,uri,sha256,status,source_url,
                creator,licence,asset_metadata,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    values["id"],
                    values["campaign_id"],
                    values["asset_type"],
                    values["uri"],
                    values["sha256"],
                    values["status"],
                    values["source_url"],
                    values["creator"],
                    values["licence"],
                    json.dumps(values["asset_metadata"]),
                    now,
                    now,
                ),
            )
            self._commit_if_needed()
        with self._lock:
            row = self._connection.execute("SELECT * FROM content_assets WHERE id=?", (values["id"],)).fetchone()
        return self._decode_row(row)  # type: ignore[return-value]

    def list_content_assets(self, campaign_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM content_assets WHERE campaign_id=? ORDER BY created_at", (campaign_id,)).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def record_content_metrics(self, entry: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._connection.execute(
                """INSERT INTO content_metrics(id,campaign_id,platform,window,captured_at,metrics)
                VALUES(?,?,?,?,?,?) ON CONFLICT(campaign_id,platform,window) DO UPDATE SET
                captured_at=excluded.captured_at,metrics=excluded.metrics""",
                (entry["id"], entry["campaign_id"], entry["platform"], entry["window"], entry.get("captured_at", utc_now()), json.dumps(entry["metrics"])),
            )
            self._commit_if_needed()
        with self._lock:
            row = self._connection.execute("SELECT * FROM content_metrics WHERE campaign_id=? AND platform=? AND window=?", (entry["campaign_id"], entry["platform"], entry["window"])).fetchone()
        return self._decode_row(row)  # type: ignore[return-value]

    # -- Review attestations and operational telemetry -----------------

    def record_review_attestation(
        self,
        attestation: dict[str, Any],
    ) -> dict[str, Any]:
        identifier = str(attestation.get("id") or f"review_{uuid.uuid4().hex[:16]}")
        decision = attestation.get("decision") or {}
        deterministic = attestation.get("deterministic_review") or {}
        submission_sha256 = str(deterministic.get("submission_sha256", ""))
        if not submission_sha256:
            raise ValueError("Review attestation requires a submission digest")
        with self._lock:
            self._connection.execute(
                """INSERT INTO review_attestations(
                id,task_id,reviewer_id,reviewer_model,submission_sha256,
                decision,signature,attestation,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    attestation["task_id"],
                    attestation["reviewer_id"],
                    attestation["reviewer_model"],
                    submission_sha256,
                    json.dumps(decision, sort_keys=True, default=str),
                    attestation["signature"],
                    json.dumps(attestation, sort_keys=True, default=str),
                    attestation["created_at"],
                ),
            )
            self._commit_if_needed()
            row = self._connection.execute(
                "SELECT * FROM review_attestations WHERE id=?",
                (identifier,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Review attestation insert did not persist")
        result = dict(row)
        result["decision"] = json.loads(result["decision"])
        result["attestation"] = json.loads(result["attestation"])
        return result

    def list_review_attestations(
        self,
        *,
        task_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM review_attestations"
        params: list[Any] = []
        if task_id:
            query += " WHERE task_id=?"
            params.append(task_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["decision"] = json.loads(item["decision"])
            item["attestation"] = json.loads(item["attestation"])
            results.append(item)
        return results

    @staticmethod
    def _metric_labels_key(labels: dict[str, str]) -> str:
        return json.dumps(labels, sort_keys=True, separators=(",", ":"))

    def record_metric(
        self,
        *,
        name: str,
        labels: dict[str, str],
        value: float,
    ) -> dict[str, Any]:
        labels_key = self._metric_labels_key(labels)
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """INSERT INTO operational_metrics(name,labels_key,labels,value,updated_at)
                VALUES(?,?,?,?,?) ON CONFLICT(name,labels_key) DO UPDATE SET
                value=operational_metrics.value+excluded.value,
                updated_at=excluded.updated_at""",
                (
                    name,
                    labels_key,
                    json.dumps(labels, sort_keys=True),
                    value,
                    now,
                ),
            )
            self._commit_if_needed()
            row = self._connection.execute(
                "SELECT * FROM operational_metrics WHERE name=? AND labels_key=?",
                (name, labels_key),
            ).fetchone()
        decoded = self._decode_row(row)
        if decoded is None:
            raise RuntimeError("Metric update did not persist")
        return decoded

    def list_metrics(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT name,labels,value,updated_at FROM operational_metrics "
                "ORDER BY name,labels_key"
            ).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def record_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """INSERT INTO operational_traces(
                id,operation,outcome,duration_ms,attributes,error,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    trace["id"],
                    trace["operation"],
                    trace["outcome"],
                    float(trace["duration_ms"]),
                    json.dumps(trace.get("attributes") or {}, sort_keys=True, default=str),
                    str(trace.get("error", ""))[:1000],
                    now,
                ),
            )
            self._commit_if_needed()
            row = self._connection.execute(
                "SELECT * FROM operational_traces WHERE id=?",
                (trace["id"],),
            ).fetchone()
        decoded = self._decode_row(row)
        if decoded is None:
            raise RuntimeError("Trace insert did not persist")
        return decoded

    def list_traces(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM operational_traces ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [self._decode_row(row) for row in rows]  # type: ignore[misc]

    def create_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        severity = str(alert["severity"]).lower()
        if severity not in {"info", "warning", "critical"}:
            raise ValueError("Alert severity must be info, warning, or critical")
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """INSERT INTO operational_alerts(
                id,severity,code,message,resource_id,status,details,created_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    alert["id"],
                    severity,
                    alert["code"],
                    alert["message"],
                    alert.get("resource_id", ""),
                    "open",
                    json.dumps(alert.get("details") or {}, sort_keys=True, default=str),
                    now,
                ),
            )
            self._commit_if_needed()
            row = self._connection.execute(
                "SELECT * FROM operational_alerts WHERE id=?",
                (alert["id"],),
            ).fetchone()
        result = dict(row) if row is not None else None
        if result is None:
            raise RuntimeError("Alert insert did not persist")
        result["details"] = json.loads(result["details"])
        return result

    def list_alerts(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM operational_alerts"
        params: list[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item["details"])
            results.append(item)
        return results

    def resolve_alert(self, alert_id: str) -> dict[str, Any]:
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE operational_alerts
                SET status='resolved',resolved_at=?
                WHERE id=? AND status='open'""",
                (utc_now(), alert_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown or resolved alert: {alert_id}")
            self._commit_if_needed()
            row = self._connection.execute(
                "SELECT * FROM operational_alerts WHERE id=?",
                (alert_id,),
            ).fetchone()
        result = dict(row) if row is not None else None
        if result is None:
            raise RuntimeError("Resolved alert is missing")
        result["details"] = json.loads(result["details"])
        return result

    def dashboard(self) -> dict[str, Any]:
        with self._lock:
            states = {row["state"]: row["count"] for row in self._connection.execute("SELECT state, COUNT(*) AS count FROM work_items WHERE item_type = 'task' GROUP BY state").fetchall()}
            departments = {row["department"]: row["count"] for row in self._connection.execute("SELECT department, COUNT(*) AS count FROM agents WHERE enabled = 1 GROUP BY department").fetchall()}
            pending = self._connection.execute("SELECT COUNT(*) FROM approvals WHERE status = 'pending'").fetchone()[0]
            total_cost = self._connection.execute("SELECT COALESCE(SUM(amount_cents), 0) FROM costs").fetchone()[0]
            active_programmes = self._connection.execute("SELECT COUNT(*) FROM work_items WHERE item_type = 'programme' AND state NOT IN ('completed','cancelled','failed')").fetchone()[0]
            violations = self._connection.execute("SELECT COUNT(*) FROM audit_logs WHERE outcome = 'denied'").fetchone()[0]
            open_alerts = self._connection.execute(
                "SELECT COUNT(*) FROM operational_alerts WHERE status='open'"
            ).fetchone()[0]
        return {
            "control_plane": "jarvis",
            "active_programmes": active_programmes,
            "task_states": states,
            "pending_approvals": pending,
            "total_cost_cents": total_cost,
            "policy_violations": violations,
            "open_alerts": open_alerts,
            "agents": {"total": sum(departments.values()), "departments": departments},
        }
