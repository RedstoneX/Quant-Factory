"""Removable gateway-only audit, note, deduplication, and lineage storage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

# Reason code an operator writes when requeueing an idea after a server fix; it restarts the interruption budget.
REQUEUED_AFTER_FIX = "requeued_after_fix"


SCHEMA_VERSION = 4
_CAMPAIGN_FIELDS = ("event_id", "candidate_id", "policy_id", "state", "reason_code", "reason_detail", "packet_sha256", "run_id", "created_at")


class GatewayStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        self._archive_foreign_campaign_events()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS gateway_schema (
                version INTEGER NOT NULL PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS candidate_identities (
                candidate_id TEXT NOT NULL PRIMARY KEY,
                content_hash TEXT NOT NULL UNIQUE,
                qf_draft_id TEXT NOT NULL UNIQUE,
                canonical_json TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS candidate_lineage (
                candidate_id TEXT NOT NULL PRIMARY KEY,
                parent_candidate_id TEXT,
                parent_run_id TEXT,
                change_reason TEXT NOT NULL,
                evidence_cited TEXT NOT NULL,
                rule_changed TEXT NOT NULL,
                material_difference TEXT NOT NULL,
                falsification TEXT NOT NULL,
                bounded_search_space TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                FOREIGN KEY (candidate_id) REFERENCES candidate_identities(candidate_id)
            );
            CREATE TABLE IF NOT EXISTS research_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS gateway_audit (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                agent_id TEXT NOT NULL,
                transport TEXT NOT NULL,
                peer_uid INTEGER,
                operation TEXT NOT NULL,
                candidate_id TEXT,
                run_id TEXT,
                authority_level INTEGER NOT NULL,
                accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
                reason_code TEXT NOT NULL,
                parent_lineage_json TEXT NOT NULL,
                response_json TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS gateway_audit_no_update
            BEFORE UPDATE ON gateway_audit BEGIN
                SELECT RAISE(ABORT, 'gateway audit is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS gateway_audit_no_delete
            BEFORE DELETE ON gateway_audit BEGIN
                SELECT RAISE(ABORT, 'gateway audit is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS research_notes_no_update
            BEFORE UPDATE ON research_notes BEGIN
                SELECT RAISE(ABORT, 'research notes are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS research_notes_no_delete
            BEFORE DELETE ON research_notes BEGIN
                SELECT RAISE(ABORT, 'research notes are append-only');
            END;
            CREATE TABLE IF NOT EXISTS campaign_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                state TEXT NOT NULL,
                reason_code TEXT,
                reason_detail TEXT,
                packet_sha256 TEXT,
                run_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_campaign_events_candidate
            ON campaign_events(candidate_id, event_id);
            CREATE TRIGGER IF NOT EXISTS campaign_events_no_update
            BEFORE UPDATE ON campaign_events BEGIN
                SELECT RAISE(ABORT, 'campaign events are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS campaign_events_no_delete
            BEFORE DELETE ON campaign_events BEGIN
                SELECT RAISE(ABORT, 'campaign events are append-only');
            END;
            CREATE TABLE IF NOT EXISTS campaign_control (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                paused INTEGER NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS campaign_control_no_update
            BEFORE UPDATE ON campaign_control BEGIN
                SELECT RAISE(ABORT, 'campaign control events are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS campaign_control_no_delete
            BEFORE DELETE ON campaign_control BEGIN
                SELECT RAISE(ABORT, 'campaign control events are append-only');
            END;
            """
        )
        row = self.connection.execute("SELECT version FROM gateway_schema").fetchone()
        if row is None:
            self.connection.execute("INSERT INTO gateway_schema(version) VALUES (?)", (SCHEMA_VERSION,))
        elif row["version"] in (1, 2, 3):
            self.connection.execute("UPDATE gateway_schema SET version=?", (SCHEMA_VERSION,))
        elif row["version"] != SCHEMA_VERSION:
            raise RuntimeError("unsupported agent gateway state schema")
        self.connection.commit()

    def _archive_foreign_campaign_events(self) -> None:
        """Keep an older campaign_events layout as a read-only archive.

        An earlier campaign (R15, Oct 2026) created campaign_events with other
        columns; CREATE TABLE IF NOT EXISTS would keep that layout and every
        write of the current campaign would fail. Its rows are history, so the
        table is renamed, never rewritten or deleted.
        """
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(campaign_events)")}
        if not columns or "packet_sha256" in columns:
            return
        with self.connection:
            self.connection.execute("ALTER TABLE campaign_events RENAME TO campaign_events_archive_r15")
            attached = self.connection.execute(
                "SELECT type, name FROM sqlite_master WHERE tbl_name='campaign_events_archive_r15' "
                "AND type IN ('trigger','index') AND sql IS NOT NULL"
            ).fetchall()
            for kind, name in attached:
                self.connection.execute(f'DROP {kind.upper()} "{name}"')
            for event in ("UPDATE", "DELETE"):
                self.connection.execute(
                    f"CREATE TRIGGER campaign_events_archive_r15_no_{event.lower()} "
                    f"BEFORE {event} ON campaign_events_archive_r15 BEGIN "
                    "SELECT RAISE(ABORT, 'archived campaign events are read-only'); END"
                )

    @contextmanager
    def immediate(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
        except Exception:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def candidate_for_hash(self, content_hash: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM candidate_identities WHERE content_hash=?", (content_hash,)
        ).fetchone()
        return dict(row) if row is not None else None

    def candidate_ids_created_by(self, agent_id: str) -> list[str]:
        rows = self.connection.execute(
            "SELECT candidate_id FROM candidate_identities WHERE created_by=? ORDER BY created_at, candidate_id",
            (agent_id,),
        ).fetchall()
        return [str(row["candidate_id"]) for row in rows]

    def record_candidate(
        self,
        *,
        candidate_id: str,
        content_hash: str,
        canonical_json: str,
        created_by: str,
        lineage: dict[str, str] | None,
    ) -> bool:
        with self.immediate():
            existing = self.candidate_for_hash(content_hash)
            if existing is not None:
                return False
            self.connection.execute(
                """INSERT INTO candidate_identities
                (candidate_id, content_hash, qf_draft_id, canonical_json, created_by)
                VALUES (?, ?, ?, ?, ?)""",
                (candidate_id, content_hash, candidate_id, canonical_json, created_by),
            )
            if lineage:
                self.connection.execute(
                    """INSERT INTO candidate_lineage
                    (candidate_id, parent_candidate_id, parent_run_id, change_reason,
                     evidence_cited, rule_changed, material_difference, falsification,
                     bounded_search_space)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        candidate_id,
                        lineage.get("parent_candidate_id") or None,
                        lineage.get("parent_run_id") or None,
                        lineage["change_reason"],
                        lineage["evidence_cited"],
                        lineage["rule_changed"],
                        lineage["material_difference"],
                        lineage["falsification"],
                        lineage["bounded_search_space"],
                    ),
                )
        return True

    def add_note(self, *, candidate_id: str, agent_id: str, note: str) -> int:
        with self.immediate():
            cursor = self.connection.execute(
                "INSERT INTO research_notes(candidate_id, agent_id, note) VALUES (?, ?, ?)",
                (candidate_id, agent_id, note),
            )
            return int(cursor.lastrowid)

    def lineage(self, candidate_id: str) -> dict[str, Any] | None:
        identity = self.connection.execute(
            "SELECT * FROM candidate_identities WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        if identity is None:
            return None
        lineage = self.connection.execute(
            "SELECT * FROM candidate_lineage WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        notes = self.connection.execute(
            "SELECT note_id, agent_id, note, created_at FROM research_notes WHERE candidate_id=? ORDER BY note_id",
            (candidate_id,),
        ).fetchall()
        children = self.connection.execute(
            "SELECT candidate_id FROM candidate_lineage WHERE parent_candidate_id=? ORDER BY candidate_id",
            (candidate_id,),
        ).fetchall()
        return {
            "candidate_id": candidate_id,
            "content_hash": identity["content_hash"],
            "created_by": identity["created_by"],
            "created_at": identity["created_at"],
            "lineage": dict(lineage) if lineage is not None else None,
            "notes": [dict(row) for row in notes],
            "children": [row["candidate_id"] for row in children],
        }

    def audit(
        self,
        *,
        request_id: str,
        agent_id: str,
        transport: str,
        peer_uid: int | None,
        operation: str,
        candidate_id: str | None,
        run_id: str | None,
        authority_level: int,
        accepted: bool,
        reason_code: str,
        parent_lineage: dict[str, Any] | None = None,
        response: dict[str, Any],
    ) -> None:
        with self.immediate():
            self.connection.execute(
                """INSERT OR IGNORE INTO gateway_audit
                (request_id, agent_id, transport, peer_uid, operation, candidate_id,
                 run_id, authority_level, accepted, reason_code,
                 parent_lineage_json, response_json)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request_id,
                    agent_id,
                    transport,
                    peer_uid,
                    operation,
                    candidate_id,
                    run_id,
                    authority_level,
                    int(accepted),
                    reason_code,
                    json.dumps(parent_lineage or {}, sort_keys=True, separators=(",", ":")),
                    json.dumps(response, sort_keys=True, separators=(",", ":")),
                ),
            )

    def audited_request(self, request_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT agent_id, transport, operation, response_json FROM gateway_audit WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        document = json.loads(result.pop("response_json"))
        if not isinstance(document, dict):
            raise RuntimeError("stored gateway response is invalid")
        result["response"] = document
        return result

    def append_campaign_event(
        self,
        *,
        candidate_id: str,
        policy_id: str,
        state: str,
        reason_code: str | None,
        reason_detail: str | None = None,
        packet_sha256: str | None = None,
        run_id: str | None = None,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self.immediate() as connection:
            cursor = connection.execute(
                """
                INSERT INTO campaign_events(candidate_id, policy_id, state, reason_code,
                    reason_detail, packet_sha256, run_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, policy_id, state, reason_code, reason_detail, packet_sha256, run_id, created_at),
            )
            return int(cursor.lastrowid)

    def append_campaign_control(self, paused: bool, actor: str, reason: str | None = None) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self.immediate() as connection:
            cursor = connection.execute(
                "INSERT INTO campaign_control(paused, actor, reason, created_at) VALUES (?, ?, ?, ?)",
                (1 if paused else 0, actor, reason, created_at),
            )
            return int(cursor.lastrowid)

    def campaign_control_state(self) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT paused, actor, reason, created_at FROM campaign_control ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {"paused": False, "actor": None, "reason": None, "created_at": None}
        return {"paused": bool(row["paused"]), "actor": row["actor"], "reason": row["reason"], "created_at": row["created_at"]}

    def latest_campaign_events(self) -> dict[str, dict[str, Any]]:
        rows = self.connection.execute(
            f"""
            SELECT {", ".join("event." + name for name in _CAMPAIGN_FIELDS)}
            FROM campaign_events event JOIN (
                SELECT candidate_id, MAX(event_id) event_id FROM campaign_events GROUP BY candidate_id
            ) latest ON latest.event_id = event.event_id
            """
        ).fetchall()
        return {str(row["candidate_id"]): dict(row) for row in rows}

    def campaign_attempts(self, candidate_id: str, packet_sha256: str) -> int:
        """How many test runs were started for this exact packet."""
        row = self.connection.execute(
            "SELECT COUNT(*) FROM campaign_events WHERE candidate_id=? AND packet_sha256=? AND state='running'",
            (candidate_id, packet_sha256),
        ).fetchone()
        return int(row[0])

    def campaign_attempts_since_requeue(self, candidate_id: str, packet_sha256: str) -> int:
        """Starts since the operator last requeued this packet after a fix; earlier starts hit the old bug."""
        row = self.connection.execute(
            "SELECT COUNT(*) FROM campaign_events WHERE candidate_id=? AND packet_sha256=? AND state='running' "
            "AND event_id > COALESCE((SELECT MAX(event_id) FROM campaign_events WHERE candidate_id=? "
            "AND packet_sha256=? AND reason_code=?), 0)",
            (candidate_id, packet_sha256, candidate_id, packet_sha256, REQUEUED_AFTER_FIX),
        ).fetchone()
        return int(row[0])

    def latest_campaign_event(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {', '.join(_CAMPAIGN_FIELDS)} FROM campaign_events "
            "WHERE candidate_id=? ORDER BY event_id DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        return dict(row) if row is not None else None
