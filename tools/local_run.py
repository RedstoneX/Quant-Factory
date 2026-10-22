"""Run one idea through the full test pipeline in this process: no Prefect, no gateway.

    python -m tools.local_run --packet idea.yaml
    python -m tools.local_run --configuration-id CONFIG_ID
    python -m tools.local_run --run-id RUN_ID        # test that run's saved setup again
    python -m tools.local_run --rerun RUN_ID         # reproduce a run and report every metric difference

Storage comes from QUANT_FACTORY_DB_PATH, QUANT_FACTORY_ARTIFACT_ROOT and QUANT_FACTORY_DATA_LOCATIONS.
Everything below is a thin translator onto the gateway's own path: the same packet validation,
``run_auto_test`` and ``CandidatePipelineRuntime``, so a local run records the same provenance (data
checksum, git sha, package fingerprint). Only the Prefect wrapper is replaced, by a direct call to
``CandidatePipelineRuntime.execute_flow``. Backtesting only; nothing here approves or trades.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from orchestration import CandidatePipelineRuntime, FactoryFilterChainService, FilterChainOutcome, new_research_launch_key
from orchestration.auto_campaign import (
    AutoTestOutcome,
    AutoTestRequest,
    GeneratedRuleStrategyAdapter,
    dataset_profile,
    outcome_from_chain,
    packet_market,
    packet_requested_start,
    run_auto_test,
    runtime_launch,
)
from persistence import PersistenceService
from persistence.models import ResearchLaunchOperation, ResearchRunSubmissionRecord
from research_intake import candidate_rule_spec, import_candidate_as_idea

REQUIRED_ENVIRONMENT = ("QUANT_FACTORY_DB_PATH", "QUANT_FACTORY_ARTIFACT_ROOT", "QUANT_FACTORY_DATA_LOCATIONS")
LOCAL_FLOW_PREFIX = "local-"  # stored where Prefect's flow-run id would be, so a local run is recognisable


def local_pipeline_launcher(*, runtime: Any, submission: ResearchRunSubmissionRecord) -> FilterChainOutcome:
    """The Prefect flow body without Prefect: the same runtime call under a local flow identity."""
    return runtime.execute_flow(submission=submission, prefect_flow_run_id=f"{LOCAL_FLOW_PREFIX}{submission.run_id}")


def storage_from_environment(environ: Mapping[str, str] = os.environ) -> tuple[Path, Path]:
    missing = [name for name in REQUIRED_ENVIRONMENT if not environ.get(name)]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} before running")
    return Path(environ["QUANT_FACTORY_DB_PATH"]), Path(environ["QUANT_FACTORY_ARTIFACT_ROOT"])


def run_packet(path: Path, *, database: Path, artifact_root: Path, adapter: Any = None, launch: Any = None) -> AutoTestOutcome:
    """Import the packet as an idea, then hand it to run_auto_test exactly as the campaign does."""
    adapter = adapter or GeneratedRuleStrategyAdapter()
    imported = import_candidate_as_idea(
        path.read_text(encoding="utf-8"), database=database,
        format_hint="json" if path.suffix.lower() == ".json" else "yaml",
    )
    packet = dict(imported.validation.document)
    draft = imported.draft
    try:
        rule_spec = candidate_rule_spec(packet)
        if rule_spec is None:
            return AutoTestOutcome("implementation_blocked", "rules_missing", "The idea has no rule_spec.")
        definition = adapter.definition(
            candidate_id=draft.draft_id, title=draft.title, rule_spec=rule_spec, variables=packet.get("variables") or {},
        )
        requested_start = packet_requested_start(packet)
    except ValueError as exc:
        return AutoTestOutcome("implementation_blocked", "rules_invalid", str(exc))
    symbol, timeframe = packet_market(packet)
    profile = dataset_profile(symbol, timeframe, requested_start)
    if profile is None:
        return AutoTestOutcome(
            "implementation_blocked", "data_unavailable",
            f"No verified local dataset with recorded trading costs for {symbol or '?'} at {timeframe or '?'}.",
        )
    request = AutoTestRequest(
        candidate_id=draft.draft_id, definition=definition, profile=profile,
        database=str(database), artifact_root=str(artifact_root),
    )
    return run_auto_test(
        request, adapter=adapter,
        launch=launch or runtime_launch(database=database, artifact_root=artifact_root, pipeline_launcher=local_pipeline_launcher),
    )


def _runtime(database: Path, artifact_root: Path, configuration_id: str) -> CandidatePipelineRuntime:
    return CandidatePipelineRuntime.from_saved_configuration(
        database=database, artifact_root=artifact_root, configuration_id=configuration_id,
        pipeline_launcher=local_pipeline_launcher, cache_only=True,
    )


def _source_run(database: Path, run_id: str) -> Any:
    service = PersistenceService(database)
    try:
        run = service.runs.get(run_id)
    finally:
        service.close()
    if run is None:
        raise SystemExit(f"unknown run {run_id}")
    return run


def run_configuration(configuration_id: str, *, database: Path, artifact_root: Path) -> AutoTestOutcome:
    result = _runtime(database, artifact_root, configuration_id).launch(idempotency_key=new_research_launch_key())
    return outcome_from_chain(result.chain, result.launch.claim.run.run_id)


def run_saved_run(run_id: str, *, database: Path, artifact_root: Path) -> AutoTestOutcome:
    """Test a saved run's setup again on today's data, recorded as a relaunch of that run."""
    source = _source_run(database, run_id)
    result = _runtime(database, artifact_root, source.configuration_id).launch(
        idempotency_key=new_research_launch_key(),
        operation=ResearchLaunchOperation.HISTORICAL_RELAUNCH, source_run_id=run_id,
    )
    return outcome_from_chain(result.chain, result.launch.claim.run.run_id)


def chain_metrics(service: PersistenceService, chain: FilterChainOutcome) -> pd.DataFrame:
    """One row per (stage, parameters, metric): every stage's recorded metrics, verdicts and data checksum."""
    rows: list[dict[str, Any]] = [
        {"stage": "chain", "parameters": "", "metric": "status", "value": chain.status},
        {"stage": "chain", "parameters": "", "metric": "stopped_at", "value": chain.stopped_at},
    ]
    runs = [("screening", chain.screening_run_id)] + [(str(getattr(h.stage, "value", h.stage)), h.run_id) for h in chain.completed]
    for handoff in chain.completed:
        stage = str(getattr(handoff.stage, "value", handoff.stage))
        rows.append({"stage": stage, "parameters": "", "metric": "status", "value": handoff.status})
        rows.append({"stage": stage, "parameters": "", "metric": "eligible_to_progress", "value": handoff.eligible_to_progress})
    for stage, run_id in runs:
        provenance = service.results.get_data_provenance(run_id)
        if provenance is not None:
            rows.append({"stage": stage, "parameters": "", "metric": "data_checksum", "value": provenance.checksum})
        for result in service.results.list_parameter_results(run_id):
            flat = pd.json_normalize(json.loads(result.metrics_json)).iloc[0].to_dict()
            rows.extend({"stage": stage, "parameters": result.normalized_parameters_json, "metric": key, "value": value}
                        for key, value in flat.items())
    return pd.DataFrame(rows, columns=["stage", "parameters", "metric", "value"])


def metric_differences(old: pd.DataFrame, new: pd.DataFrame, *, rtol: float = 1e-9, atol: float = 1e-12) -> pd.DataFrame:
    """Rows whose value differs (numbers within float tolerance count as equal) or exist on one side only."""
    merged = old.merge(new, on=["stage", "parameters", "metric"], how="outer", suffixes=("_old", "_new"), indicator=True)
    old_numbers = pd.to_numeric(merged["value_old"], errors="coerce")
    new_numbers = pd.to_numeric(merged["value_new"], errors="coerce")
    numeric = old_numbers.notna() & new_numbers.notna() & ~merged["value_old"].map(lambda v: isinstance(v, bool))
    close = pd.Series(np.isclose(old_numbers.fillna(0), new_numbers.fillna(0), rtol=rtol, atol=atol), index=merged.index)
    same_text = merged["value_old"].astype(str) == merged["value_new"].astype(str)
    both_missing = merged["value_old"].isna() & merged["value_new"].isna()
    same = (merged["_merge"] == "both") & ((numeric & close) | (~numeric & (same_text | both_missing)))
    return merged.loc[~same, ["stage", "parameters", "metric", "value_old", "value_new"]].reset_index(drop=True)


def rerun(run_id: str, *, database: Path, artifact_root: Path) -> tuple[AutoTestOutcome, pd.DataFrame]:
    """Reproduce a saved run on its pinned data cut-off (the saved setup's data_as_of) and diff every metric."""
    source = _source_run(database, run_id)
    runtime = _runtime(database, artifact_root, source.configuration_id)
    result = runtime.launch(
        idempotency_key=new_research_launch_key(), operation=ResearchLaunchOperation.REPRODUCTION, source_run_id=run_id,
    )
    service = PersistenceService(database)
    try:
        original = FactoryFilterChainService(service, artifact_root=artifact_root).reopen(screening_run_id=run_id)
        differences = metric_differences(chain_metrics(service, original), chain_metrics(service, result.chain))
    finally:
        service.close()
    return outcome_from_chain(result.chain, result.launch.claim.run.run_id), differences


def _print_outcome(outcome: AutoTestOutcome) -> None:
    print(f"result: {outcome.state} ({outcome.reason_code})")
    if outcome.run_id:
        print(f"run: {outcome.run_id}")
    if outcome.reason_detail:
        print(f"detail: {outcome.reason_detail}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.local_run", description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--packet", type=Path, help="qf_candidate_v1 packet (.json, .yaml or .yml)")
    mode.add_argument("--configuration-id", help="run a saved configuration")
    mode.add_argument("--run-id", help="test a saved run's configuration again on current data")
    mode.add_argument("--rerun", metavar="RUN_ID", help="reproduce a saved run on its pinned data and report metric differences")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database, artifact_root = storage_from_environment()
    if args.rerun:
        outcome, differences = rerun(args.rerun, database=database, artifact_root=artifact_root)
        _print_outcome(outcome)
        if differences.empty:
            print("reproduction matches: no metric differences")
            return 0
        print(f"reproduction differs in {len(differences)} value(s):")
        print(differences.to_string(index=False))
        return 3
    if args.packet:
        outcome = run_packet(args.packet, database=database, artifact_root=artifact_root)
    elif args.configuration_id:
        outcome = run_configuration(args.configuration_id, database=database, artifact_root=artifact_root)
    else:
        outcome = run_saved_run(args.run_id, database=database, artifact_root=artifact_root)
    _print_outcome(outcome)
    return 0 if outcome.state in {"survivor", "screened_out"} else 2


if __name__ == "__main__":
    sys.exit(main())
