"""Deterministic admission for the owner-authorized R15 validation campaign."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from agent_gateway.contracts import GatewayError
from agent_gateway.store import GatewayStore
from persistence import PersistenceService
from research_intake import validate_candidate_packet


R15_POLICY_ID = "r15-product-validation-v1"
R15_DATASET_ID = "futures_MES_5m_databento"
R15_MAX_CANDIDATES = 12
R15_MAX_PARAMETERS_PER_STUDY = 100
R15_MAX_PARAMETERS = 1_200
TERMINAL_STATES = {
    "duplicate_closed",
    "invalid",
    "prior_work_conflict",
    "implementation_blocked",
    "budget_blocked",
    "deterministic_failure",
    "screened_out",
    "insufficient",
    "failed",
    "qualified_survivor",
}

# These implementations are real and registered, but their exact hypotheses are
# already closed by retained prior work. A nearby title or packet may not reopen
# them or stand in for a new implementation.
PROHIBITED_IMPLEMENTATIONS = {
    "mes_opening_range_breakout_long": "plain_orb_matrix_closed",
    "mes_opening_range_breakout_short": "plain_orb_matrix_closed",
    "mes_overnight_gap_reversal": "fixed_gap_rule_closed",
    "mes_15m_orb_vwap_quality_candidate": "fixed_proof_candidate_closed",
    "mes_intraday_sma_10_30_candidate": "fixed_proof_candidate_closed",
}


@dataclass(frozen=True)
class CampaignDecision:
    policy_id: str
    candidate_id: str
    state: str
    reason_code: str
    reason_detail: str
    parameter_combinations: int
    configuration_id: str | None = None
    run_id: str | None = None

    def document(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "candidate_id": self.candidate_id,
            "state": self.state,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "parameter_combinations": self.parameter_combinations,
            "configuration_id": self.configuration_id,
            "run_id": self.run_id,
        }


def evaluate_r15_candidate(
    *, candidate_id: str, database: str | Path, store: GatewayStore,
) -> CampaignDecision:
    existing = store.campaign_state(R15_POLICY_ID, candidate_id)
    if existing is not None:
        return _decision(existing)

    service = PersistenceService(database)
    try:
        draft = service.idea_drafts.get(candidate_id)
        if draft is None:
            raise GatewayError("not_found", "Candidate was not found")
        try:
            document = json.loads(draft.candidate_json)
        except json.JSONDecodeError as exc:
            return _record(store, candidate_id, "invalid", "candidate_invalid", "Candidate content is not valid canonical JSON.", 0)
    finally:
        service.close()

    validation = validate_candidate_packet(document)
    combinations = int(validation.parameter_combinations or 0)
    if not validation.valid or not validation.review_ready:
        return _record(store, candidate_id, "invalid", "candidate_invalid", "Candidate did not pass the complete QF Candidate v1 admission contract.", combinations)

    prior_states = store.campaign_states(R15_POLICY_ID)
    if len(prior_states) >= R15_MAX_CANDIDATES:
        return _record(store, candidate_id, "budget_blocked", "candidate_ceiling", "The R15 twelve-Candidate admission ceiling is closed.", combinations)
    if combinations < 1 or combinations > R15_MAX_PARAMETERS_PER_STUDY:
        return _record(store, candidate_id, "budget_blocked", "study_parameter_ceiling", "The immutable study must contain 1 to 100 parameter combinations.", combinations)
    used = sum(int(row["parameter_combinations"]) for row in prior_states if row["state"] not in {"invalid", "duplicate_closed"})
    if used + combinations > R15_MAX_PARAMETERS:
        return _record(store, candidate_id, "budget_blocked", "campaign_parameter_ceiling", "The R15 1,200-combination campaign ceiling would be exceeded.", combinations)

    candidate = _mapping(document.get("candidate"))
    status = str(candidate.get("status") or "draft").strip().lower()
    if status in {"owner_approved", "implemented"}:
        return _record(store, candidate_id, "invalid", "authority_assertion", "Candidate packets cannot grant their own research authority.", combinations)
    market = _mapping(document.get("market"))
    instruments = _mapping(market.get("instruments"))
    preferred = instruments.get("preferred")
    if preferred != ["MES"]:
        return _record(store, candidate_id, "invalid", "instrument_out_of_policy", "R15 permits MES as the only preferred instrument.", combinations)
    if R15_DATASET_ID not in json.dumps(document, sort_keys=True):
        return _record(store, candidate_id, "invalid", "dataset_not_precommitted", "The fixed R15 MES dataset identity is missing.", combinations)
    fixed = _mapping(document.get("fixed"))
    if fixed.get("flat_by_close") is not True:
        return _record(store, candidate_id, "invalid", "session_boundary_missing", "The Candidate must explicitly precommit flat_by_close: true.", combinations)
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources or not any(_source_attributed(row) for row in sources):
        return _record(store, candidate_id, "invalid", "source_attribution_missing", "At least one attributable source is required.", combinations)

    implementation = _mapping(document.get("implementation"))
    strategy_id = str(implementation.get("strategy_id") or "").strip()
    if not strategy_id:
        return _record(store, candidate_id, "implementation_blocked", "adapter_unspecified", "No exact registered MES strategy adapter was identified.", combinations)
    if strategy_id in PROHIBITED_IMPLEMENTATIONS:
        return _record(store, candidate_id, "prior_work_conflict", PROHIBITED_IMPLEMENTATIONS[strategy_id], "The exact implemented hypothesis is closed retained prior work and may not be rerun or tuned.", combinations)
    return _record(store, candidate_id, "implementation_blocked", "adapter_unavailable", "No exact policy-approved registered MES adapter and immutable StudyPlan compiler exists for this hypothesis.", combinations)


def executable_campaign_configuration(
    candidate_id: str, database: str | Path, store: GatewayStore, policy_id: str,
) -> str:
    if policy_id != R15_POLICY_ID:
        raise GatewayError("campaign_inactive", "requested campaign policy is not active")
    decision = store.campaign_state(policy_id, candidate_id)
    if decision is None:
        decision = evaluate_r15_candidate(candidate_id=candidate_id, database=database, store=store).document()
    if decision["state"] != "admitted" or not decision.get("configuration_id"):
        raise GatewayError(str(decision["reason_code"]), str(decision["reason_detail"]))
    return str(decision["configuration_id"])


def attach_campaign_decision(
    result: dict[str, Any], *, policy_id: str | None, database: str | Path,
    store: GatewayStore,
) -> dict[str, Any]:
    if policy_id == R15_POLICY_ID:
        result["campaign"] = evaluate_r15_candidate(
            candidate_id=str(result["candidate_id"]), database=database, store=store,
        ).document()
    return result


def _record(store: GatewayStore, candidate_id: str, state: str, code: str, detail: str, combinations: int) -> CampaignDecision:
    row = store.record_campaign_event(
        policy_id=R15_POLICY_ID,
        candidate_id=candidate_id,
        state=state,
        reason_code=code,
        reason_detail=detail,
        parameter_combinations=combinations,
    )
    return _decision(row)


def _decision(row: Mapping[str, Any]) -> CampaignDecision:
    return CampaignDecision(
        policy_id=str(row["policy_id"]), candidate_id=str(row["candidate_id"]),
        state=str(row["state"]), reason_code=str(row["reason_code"]),
        reason_detail=str(row["reason_detail"]), parameter_combinations=int(row["parameter_combinations"]),
        configuration_id=str(row["configuration_id"]) if row.get("configuration_id") else None,
        run_id=str(row["run_id"]) if row.get("run_id") else None,
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _source_attributed(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return bool(str(value.get("url") or value.get("title") or value.get("claim") or "").strip())


__all__ = [
    "CampaignDecision", "R15_POLICY_ID", "TERMINAL_STATES",
    "attach_campaign_decision", "evaluate_r15_candidate",
    "executable_campaign_configuration",
]
