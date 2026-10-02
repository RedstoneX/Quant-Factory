"""Removable gateway-only audit, note, deduplication, and lineage storage."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


SCHEMA_VERSION = 1


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
            """
        )
        row = self.connection.execute("SELECT version FROM gateway_schema").fetchone()
        if row is None:
            self.connection.execute("INSERT INTO gateway_schema(version) VALUES (?)", (SCHEMA_VERSION,))
        elif row["version"] != SCHEMA_VERSION:
            raise RuntimeError("unsupported agent gateway state schema")
        self.connection.commit()

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
