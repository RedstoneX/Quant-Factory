"""Background campaign that automatically tests every valid idea with rules.

Events are appended to the gateway's ``campaign_events`` log; the research
database is written only by the existing persistence and pipeline APIs inside
the per-run child process. Nothing here sets an approval or promotes anything.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
from typing import Any, Callable, Mapping

from agent_gateway.store import GatewayStore
from orchestration.auto_campaign import (
    POLICY_ID,
    AutoTestOutcome,
    AutoTestRequest,
    RuleStrategyAdapter,
    dataset_profile,
    earlier_owner_of_strategy,
    packet_market,
    packet_requested_start,
    safe_detail,
)
from persistence import PersistenceService
from research_intake import validate_candidate_packet

RuleSpecReader = Callable[[Mapping[str, Any]], "dict[str, Any] | None"]
Executor = Callable[[AutoTestRequest], AutoTestOutcome]
OPEN_STATES = frozenset({"queued", "running"})
RESULT_STATES = frozenset({"survivor", "screened_out"})  # finished with numbers: owns its strategy
# A test cut short by a restart (usually a deploy) is rerun under a fresh launch key;
# an idea that is interrupted this many times is reported instead of rerun forever.
MAX_ATTEMPTS = 3


class AutoTestCampaign:
    def __init__(
        self,
        *,
        database: str | Path,
        gateway_database: str | Path,
        artifact_root: str | Path,
        adapter: RuleStrategyAdapter,
        executor: Executor,
        rule_spec_reader: RuleSpecReader,
        poll_seconds: float = 60.0,
    ) -> None:
        self.database = Path(database)
        self.gateway_database = Path(gateway_database)
        self.artifact_root = Path(artifact_root)
        self.adapter = adapter
        self.executor = executor
        self.rule_spec_reader = rule_spec_reader
        self.poll_seconds = poll_seconds
        self._run_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------
    def start(self) -> threading.Thread:
        self.requeue_after_restart()
        self._thread = threading.Thread(target=self._loop, name="qf-auto-test-campaign", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except (OSError, sqlite3.Error, KeyError, ValueError, RuntimeError) as exc:
                # The gateway keeps serving; the next pass retries.
                print(f"automatic testing pass failed: {safe_detail(exc)}", file=sys.stderr, flush=True)
            self._stop.wait(self.poll_seconds)

    def requeue_after_restart(self) -> list[str]:
        store = GatewayStore(self.gateway_database)
        try:
            interrupted = [row for row in store.latest_campaign_events().values() if row["state"] in OPEN_STATES]
            for row in sorted(interrupted, key=lambda item: item["event_id"]):
                store.append_campaign_event(
                    candidate_id=row["candidate_id"], policy_id=POLICY_ID, state="queued",
                    reason_code="requeued_after_restart", packet_sha256=row["packet_sha256"],
                )
            return [row["candidate_id"] for row in interrupted]
        finally:
            store.close()

    # -- one pass --------------------------------------------------------
    def run_once(self) -> int:
        """Queue new or changed ideas, then test queued ideas one at a time."""
        if not self._run_lock.acquire(blocking=False):
            return 0
        try:
            store = GatewayStore(self.gateway_database)
            try:
                queued = self._queue(store)
                for draft, packet, invalid, digest in queued:
                    if self._stop.is_set():
                        break
                    try:
                        self._process(store, draft, packet, invalid, digest)
                    except (OSError, sqlite3.Error, KeyError, ValueError, RuntimeError) as exc:
                        # Record the real cause for THIS idea so it is not silently re-started each pass.
                        print(f"automatic test of {draft.draft_id} failed: {safe_detail(exc)}", file=sys.stderr, flush=True)
                        store.append_campaign_event(
                            candidate_id=draft.draft_id, policy_id=POLICY_ID, state="failed", reason_code="run_error",
                            reason_detail=safe_detail(f"{type(exc).__name__}: {exc}"), packet_sha256=digest,
                        )
                return len(queued)
            finally:
                store.close()
        finally:
            self._run_lock.release()

    def _queue(self, store: GatewayStore) -> list[tuple[Any, dict[str, Any], str | None, str]]:
        latest = store.latest_campaign_events()
        service = PersistenceService(self.database)
        try:
            # A setup-linked idea cannot change its packet, so once it has a terminal event it is never revisited.
            settled = {
                candidate for candidate, event in latest.items()
                if event["state"] not in OPEN_STATES | {"duplicate_closed"}
            }
            drafts = sorted(service.idea_drafts.list(skip_linked_ids=settled), key=lambda draft: (draft.created_at, draft.draft_id))
        finally:
            service.close()
        queued = []
        for draft in drafts:
            event = latest.get(draft.draft_id)
            if not draft.candidate_json or (draft.configuration_id and event is None):
                continue  # no packet, or a hand-built setup: never touched
            digest = hashlib.sha256(draft.candidate_json.encode("utf-8")).hexdigest()
            if event is not None and event["state"] not in OPEN_STATES and event["packet_sha256"] == digest:
                owner = latest.get(str(event["reason_detail"])) if event["state"] == "duplicate_closed" else None
                if owner is None or owner["state"] in OPEN_STATES | RESULT_STATES:
                    continue  # decided already; re-evaluated when the packet changes or its owner proved to have no result
            eligible = _eligible_packet(draft.candidate_json)
            if eligible is None:
                continue
            if event is None or event["state"] not in OPEN_STATES:
                store.append_campaign_event(
                    candidate_id=draft.draft_id, policy_id=POLICY_ID, state="queued",
                    reason_code="waiting", packet_sha256=digest,
                )
            queued.append((draft, *eligible, digest))
        return queued

    def _process(
        self, store: GatewayStore, draft: Any, packet: dict[str, Any], invalid: str | None, digest: str
    ) -> None:
        def record(state: str, code: str, detail: str | None = None, run_id: str | None = None) -> None:
            store.append_campaign_event(
                candidate_id=draft.draft_id, policy_id=POLICY_ID, state=state, reason_code=code,
                reason_detail=detail, packet_sha256=digest, run_id=run_id,
            )

        try:
            if invalid is not None:
                raise ValueError(invalid)
            rule_spec = self.rule_spec_reader(packet)
            if rule_spec is None:
                return record(
                    "implementation_blocked", "rules_missing",
                    "The idea has no rule_spec, so no strategy can be generated from it.",
                )
            definition = self.adapter.definition(
                candidate_id=draft.draft_id, title=draft.title, rule_spec=rule_spec,
                variables=packet.get("variables") or {},
            )
        except ValueError as exc:
            return record("implementation_blocked", "rules_invalid", f"The rule_spec is invalid: {safe_detail(exc)}")
        strategy_id = str(definition["strategy_id"])
        symbol, timeframe = packet_market(packet)
        without_result = {
            candidate for candidate, event in store.latest_campaign_events().items()
            if event["state"] not in OPEN_STATES | RESULT_STATES
        }
        earlier = earlier_owner_of_strategy(
            database=self.database, strategy_id=strategy_id, candidate_id=draft.draft_id,
            symbol=symbol, timeframe=timeframe, without_result=without_result,
        )
        if earlier is not None:
            return record("duplicate_closed", "same_rules", earlier)
        profile = dataset_profile(symbol, timeframe, packet_requested_start(packet))
        if profile is None:
            return record(
                "implementation_blocked", "data_unavailable",
                f"No verified local dataset with recorded trading costs exists for {symbol or 'an unnamed market'} "
                f"at {timeframe or 'an unstated timeframe'}.",
            )
        attempt = store.campaign_attempts(draft.draft_id, digest)
        recent = store.campaign_attempts_since_requeue(draft.draft_id, digest)
        if recent >= MAX_ATTEMPTS:
            return record(
                "failed", "run_error",
                f"The test was interrupted {recent} times before finishing and was not started again.",
            )
        record("running", "started")
        outcome = self.executor(
            AutoTestRequest(
                candidate_id=draft.draft_id, definition=definition, profile=profile,
                database=str(self.database), artifact_root=str(self.artifact_root), attempt=attempt,
            )
        )
        record(outcome.state, outcome.reason_code, outcome.reason_detail, outcome.run_id)


def _eligible_packet(candidate_json: str) -> tuple[dict[str, Any], str | None] | None:
    """Return a packet passing intake validation, or failing it only on its rule_spec."""
    try:
        document = json.loads(candidate_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(document, dict):
        return None
    validation = validate_candidate_packet(document)
    if validation.valid:
        return dict(validation.document), None
    if all(issue.code == "rule_spec" for issue in validation.errors):
        return dict(validation.document), "; ".join(issue.message for issue in validation.errors)
    return None
