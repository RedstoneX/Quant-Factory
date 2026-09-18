"""Immutable, read-only view models for comparing persisted research runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode

from dashboard.callbacks.review_state import load_durable_review
from dashboard.formatting import format_metric
from dashboard.run_detail_adapter import RunDetailDashboardAdapter, SelectedRunDetailView
from persistence import PersistenceService
from persistence.database import database_path


HEADLINE_METRICS = (
    ("total_return", "Total return"),
    ("annualized_return", "Annualized return"),
    ("sharpe_ratio", "Sharpe ratio"),
    ("max_drawdown", "Maximum drawdown"),
    ("number_of_trades", "Number of trades"),
    ("win_rate", "Win rate"),
)


@dataclass(frozen=True, slots=True)
class CompareRunIdentity:
    """Stable operator identity retained for every requested run."""

    position: int
    run_id: str
    available: bool
    results_href: str
    strategy: str
    instrument: str
    timeframe: str
    requested_period: str
    actual_period: str
    run_status: str
    evidence_outcome: str
    human_review: str
    omissions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompareMetricValue:
    run_id: str
    raw_value: float | int | None
    display_value: str
    basis: str
    omission: str | None = None


@dataclass(frozen=True, slots=True)
class CompareMetricRow:
    key: str
    label: str
    state: str
    values: tuple[CompareMetricValue, ...]
    basis_warning: str | None = None


@dataclass(frozen=True, slots=True)
class CompareSeriesPoint:
    timestamp: str
    value: float


@dataclass(frozen=True, slots=True)
class CompareSeries:
    run_id: str
    label: str
    basis: str
    points: tuple[CompareSeriesPoint, ...]
    omission: str | None = None


@dataclass(frozen=True, slots=True)
class CompareDifferenceValue:
    run_id: str
    value: str
    available: bool
    omission: str | None = None


@dataclass(frozen=True, slots=True)
class CompareDifferenceField:
    key: str
    label: str
    state: str
    values: tuple[CompareDifferenceValue, ...]


@dataclass(frozen=True, slots=True)
class CompareDifferenceGroup:
    key: str
    label: str
    fields: tuple[CompareDifferenceField, ...]


@dataclass(frozen=True, slots=True)
class ComparabilityFinding:
    code: str
    severity: str
    message: str
    run_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompareViewModel:
    """Complete read model; all members are immutable and persistence-derived."""

    requested_run_ids: tuple[str, ...]
    runs: tuple[CompareRunIdentity, ...]
    metric_rows: tuple[CompareMetricRow, ...]
    equity_series: tuple[CompareSeries, ...]
    drawdown_series: tuple[CompareSeries, ...]
    difference_groups: tuple[CompareDifferenceGroup, ...]
    findings: tuple[ComparabilityFinding, ...]
    directly_comparable: bool


@dataclass(slots=True)
class _RunSnapshot:
    position: int
    run_id: str
    results_href: str
    available: bool = False
    strategy: str = "Unavailable"
    instrument: str = "Unavailable"
    timeframe: str = "Unavailable"
    requested_period: str = "Unavailable"
    actual_period: str = "Unavailable"
    timezone: str = "Unavailable"
    adjusted: str = "Unavailable"
    provider: str = "Unavailable"
    provider_implementation: str = "Unavailable"
    dataset_identity: str = "Unavailable"
    manifest_reference: str = "Unavailable"
    row_count: str = "Unavailable"
    run_status: str = "Unavailable"
    stage: str = "Unavailable"
    evidence_outcome: str = "Not run"
    evidence_reasons: str = "Unavailable"
    protected_data_state: str = "Unavailable"
    human_review: str = "Unavailable"
    review_note: str = "Unavailable"
    review_operator: str = "Unavailable"
    review_updated_at: str = "Unavailable"
    metric_basis: str = "No persisted ranked result"
    metrics: dict[str, float | int] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    detail: SelectedRunDetailView | None = None
    omissions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class CompareDashboardAdapter:
    """Build Compare data without mutating runs, evidence, reviews, or artifacts."""

    def __init__(
        self,
        database: str | Path | None = None,
        *,
        artifact_root: str | Path | None = None,
        detail_adapter: RunDetailDashboardAdapter | None = None,
    ) -> None:
        self.database = database_path(database)
        self.artifact_root = Path(artifact_root or Path.cwd())
        self.detail_adapter = detail_adapter or RunDetailDashboardAdapter(
            database=self.database,
            artifact_root=self.artifact_root,
        )

    def compare(self, run_ids: Sequence[str]) -> CompareViewModel:
        """Read each requested run independently and retain the requested order."""

        requested = tuple(str(run_id) for run_id in run_ids)
        service = PersistenceService(self.database)
        try:
            snapshots = tuple(
                self._snapshot(service, run_id, position)
                for position, run_id in enumerate(requested, start=1)
            )
        finally:
            service.close()

        equity_series: list[CompareSeries] = []
        drawdown_series: list[CompareSeries] = []
        for snapshot in snapshots:
            equity, drawdown = _normalized_series(snapshot)
            equity_series.append(equity)
            drawdown_series.append(drawdown)

        metric_rows = _metric_rows(snapshots)
        difference_groups = _difference_groups(snapshots)
        findings = _comparability_findings(
            snapshots,
            metric_rows,
            tuple(equity_series),
            difference_groups,
        )
        identities = tuple(_identity(snapshot) for snapshot in snapshots)
        return CompareViewModel(
            requested_run_ids=requested,
            runs=identities,
            metric_rows=metric_rows,
            equity_series=tuple(equity_series),
            drawdown_series=tuple(drawdown_series),
            difference_groups=difference_groups,
            findings=findings,
            directly_comparable=not any(
                finding.severity == "blocking" for finding in findings
            ),
        )

    def _snapshot(
        self,
        service: PersistenceService,
        run_id: str,
        position: int,
    ) -> _RunSnapshot:
        snapshot = _RunSnapshot(
            position=position,
            run_id=run_id,
            results_href=(
                "/research/backtest-results?" + urlencode({"run_id": run_id})
            ),
        )
        run = service.runs.get(run_id)
        if run is None:
            snapshot.errors.append(f"Persisted run {run_id or '(empty identity)'} is unavailable.")
            return snapshot

        snapshot.available = True
        snapshot.strategy = f"{run.strategy_id}@{run.strategy_version}"
        snapshot.run_status = run.status.value.replace("_", " ").title()
        snapshot.stage = run.stage.value.replace("_", " ").title()

        configuration = service.configurations.get(run.configuration_id)
        configuration_document: dict[str, Any] = {}
        if configuration is None:
            snapshot.omissions.append("Saved configuration is unavailable.")
        else:
            try:
                configuration_document = _json_object(
                    configuration.canonical_config_json,
                    label="saved configuration",
                )
            except ValueError as exc:
                snapshot.errors.append(str(exc))
        snapshot.parameters = _mapping(configuration_document.get("parameters"))
        configured_execution = _mapping(configuration_document.get("execution"))
        configured_market_data = _mapping(configuration_document.get("market_data"))

        provenance = service.results.get_data_provenance(run_id)
        if provenance is None:
            snapshot.omissions.append("Data provenance is unavailable.")
        else:
            snapshot.provider = _present(provenance.provider)
            snapshot.provider_implementation = _present(
                provenance.provider_implementation
            )
            snapshot.instrument = _present(provenance.symbol)
            snapshot.timeframe = _present(provenance.interval)
            snapshot.requested_period = _present(provenance.requested_coverage)
            snapshot.actual_period = _present(provenance.actual_coverage)
            snapshot.timezone = _present(provenance.timezone)
            snapshot.adjusted = "Adjusted" if provenance.adjusted else "Unadjusted"
            snapshot.dataset_identity = _present(provenance.checksum)
            snapshot.manifest_reference = _present(provenance.manifest_reference)
            snapshot.row_count = str(provenance.row_count)
        snapshot.provider = _fallback(
            snapshot.provider,
            configured_market_data.get("provider"),
        )
        snapshot.instrument = _fallback(
            snapshot.instrument,
            configured_market_data.get("symbol"),
        )
        snapshot.timeframe = _fallback(
            snapshot.timeframe,
            configured_market_data.get("interval"),
        )

        persisted_execution: dict[str, Any] = {}
        execution = service.results.get_execution_assumptions(run_id)
        if execution is None:
            snapshot.omissions.append("Persisted execution assumptions are unavailable.")
        else:
            try:
                persisted_execution = _json_object(
                    execution.assumptions_json,
                    label="persisted execution assumptions",
                )
            except ValueError as exc:
                snapshot.errors.append(str(exc))
        snapshot.execution = {
            "configured": configured_execution,
            "persisted": persisted_execution,
        }

        rows = service.results.list_parameter_results(run_id)
        if not rows:
            snapshot.omissions.append("No persisted ranked metric result is available.")
        else:
            selected = rows[0]
            snapshot.metric_basis = (
                f"Rank {selected.ranking_position} persisted parameter result"
                + (
                    f"; screening {selected.screening_status}"
                    if selected.screening_status
                    else ""
                )
            )
            try:
                metric_document = _json_object(
                    selected.metrics_json,
                    label="persisted headline metrics",
                )
                snapshot.metrics = {
                    key: value
                    for key, value in metric_document.items()
                    if _finite_number(value)
                }
            except ValueError as exc:
                snapshot.errors.append(str(exc))

        try:
            detail = self.detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            snapshot.errors.append(f"Persisted evidence is unavailable: {exc}")
            detail = None
        snapshot.detail = detail
        if detail is not None:
            for warning in detail.warnings:
                target = (
                    snapshot.errors
                    if _looks_like_error(warning)
                    else snapshot.omissions
                )
                target.append(warning)
            outcome = _detail_fields(detail.evidence.validation_outcome)
            snapshot.evidence_outcome = _present(
                outcome.get("Normalized status"),
                default="Not run",
            ).replace("_", " ").capitalize()
            snapshot.evidence_reasons = _present(outcome.get("Reasons"))
            snapshot.protected_data_state = _present(
                outcome.get("Protected-data state")
            )

        try:
            review = load_durable_review(
                self.database,
                self.artifact_root,
                run_id,
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            snapshot.errors.append(f"Durable human review is unavailable: {exc}")
        else:
            snapshot.human_review = review.display_state
            snapshot.review_note = _present(review.note)
            snapshot.review_operator = _present(review.operator)
            snapshot.review_updated_at = _present(review.updated_at)
        return snapshot


def _identity(snapshot: _RunSnapshot) -> CompareRunIdentity:
    return CompareRunIdentity(
        position=snapshot.position,
        run_id=snapshot.run_id,
        available=snapshot.available,
        results_href=snapshot.results_href,
        strategy=snapshot.strategy,
        instrument=snapshot.instrument,
        timeframe=snapshot.timeframe,
        requested_period=snapshot.requested_period,
        actual_period=snapshot.actual_period,
        run_status=snapshot.run_status,
        evidence_outcome=snapshot.evidence_outcome,
        human_review=snapshot.human_review,
        omissions=_unique(snapshot.omissions),
        errors=_unique(snapshot.errors),
    )


def _metric_rows(snapshots: tuple[_RunSnapshot, ...]) -> tuple[CompareMetricRow, ...]:
    rows: list[CompareMetricRow] = []
    for key, label in HEADLINE_METRICS:
        values = []
        for snapshot in snapshots:
            raw = snapshot.metrics.get(key)
            if raw is None:
                values.append(
                    CompareMetricValue(
                        run_id=snapshot.run_id,
                        raw_value=None,
                        display_value="Unavailable",
                        basis=snapshot.metric_basis,
                        omission="Metric is absent from the persisted ranked result.",
                    )
                )
            else:
                values.append(
                    CompareMetricValue(
                        run_id=snapshot.run_id,
                        raw_value=raw,
                        display_value=format_metric(key, raw),
                        basis=snapshot.metric_basis,
                    )
                )
        state = _state(
            tuple(value.raw_value for value in values),
            available=tuple(value.omission is None for value in values),
        )
        bases = {value.basis for value in values}
        basis_warning = (
            None
            if len(bases) == 1 and "No persisted ranked result" not in bases
            else "Headline metric bases differ or are unavailable; interpret values separately."
        )
        rows.append(
            CompareMetricRow(
                key=key,
                label=label,
                state=state,
                values=tuple(values),
                basis_warning=basis_warning,
            )
        )
    return tuple(rows)


def _normalized_series(snapshot: _RunSnapshot) -> tuple[CompareSeries, CompareSeries]:
    label = " · ".join(
        value
        for value in (snapshot.strategy, snapshot.instrument, snapshot.timeframe)
        if value != "Unavailable"
    ) or snapshot.run_id
    if snapshot.detail is None:
        omission = "Persisted equity evidence is unavailable."
        snapshot.omissions.append(omission)
        return (
            CompareSeries(snapshot.run_id, label, "Start = 100", (), omission),
            CompareSeries(snapshot.run_id, label, "Peak-relative drawdown", (), omission),
        )

    raw_rows = snapshot.detail.evidence.equity_curve
    if not raw_rows:
        omission = "No validated persisted equity curve is available."
        snapshot.omissions.append(omission)
        return (
            CompareSeries(snapshot.run_id, label, "Start = 100", (), omission),
            CompareSeries(snapshot.run_id, label, "Peak-relative drawdown", (), omission),
        )

    validated: list[tuple[str, float]] = []
    for index, row in enumerate(raw_rows):
        timestamp = row.get("timestamp")
        value = row.get("value")
        if not _valid_timestamp(timestamp) or not _finite_number(value):
            message = (
                f"Equity curve for {snapshot.run_id} contains invalid point {index}; "
                "the complete series was omitted."
            )
            snapshot.errors.append(message)
            return (
                CompareSeries(snapshot.run_id, label, "Start = 100", (), message),
                CompareSeries(snapshot.run_id, label, "Peak-relative drawdown", (), message),
            )
        validated.append((str(timestamp), float(value)))

    baseline = validated[0][1]
    if baseline == 0.0:
        message = (
            f"Equity curve for {snapshot.run_id} has a zero starting value and "
            "cannot be normalized safely."
        )
        snapshot.errors.append(message)
        return (
            CompareSeries(snapshot.run_id, label, "Start = 100", (), message),
            CompareSeries(snapshot.run_id, label, "Peak-relative drawdown", (), message),
        )

    equity = tuple(
        CompareSeriesPoint(timestamp, value / baseline * 100.0)
        for timestamp, value in validated
    )
    peak: float | None = None
    drawdown_points = []
    for timestamp, value in validated:
        peak = value if peak is None else max(peak, value)
        if peak == 0.0:
            message = (
                f"Equity curve for {snapshot.run_id} has a zero running peak and "
                "cannot produce drawdown safely."
            )
            snapshot.errors.append(message)
            return (
                CompareSeries(snapshot.run_id, label, "Start = 100", equity),
                CompareSeries(
                    snapshot.run_id,
                    label,
                    "Peak-relative drawdown",
                    (),
                    message,
                ),
            )
        drawdown_points.append(
            CompareSeriesPoint(timestamp, (value / peak) - 1.0)
        )
    return (
        CompareSeries(snapshot.run_id, label, "Start = 100", equity),
        CompareSeries(
            snapshot.run_id,
            label,
            "Peak-relative drawdown",
            tuple(drawdown_points),
        ),
    )


def _difference_groups(
    snapshots: tuple[_RunSnapshot, ...],
) -> tuple[CompareDifferenceGroup, ...]:
    documents = {
        "parameters": [snapshot.parameters for snapshot in snapshots],
        "data": [
            {
                "provider": snapshot.provider,
                "provider_implementation": snapshot.provider_implementation,
                "dataset_identity": snapshot.dataset_identity,
                "manifest_reference": snapshot.manifest_reference,
                "row_count": snapshot.row_count,
                "instrument": snapshot.instrument,
                "timeframe": snapshot.timeframe,
                "requested_period": snapshot.requested_period,
                "actual_period": snapshot.actual_period,
                "timezone": snapshot.timezone,
                "adjustment": snapshot.adjusted,
            }
            for snapshot in snapshots
        ],
        "execution": [snapshot.execution for snapshot in snapshots],
        "evidence": [
            {
                "stage": snapshot.stage,
                "outcome": snapshot.evidence_outcome,
                "reasons": snapshot.evidence_reasons,
                "protected_data_state": snapshot.protected_data_state,
            }
            for snapshot in snapshots
        ],
        "review": [
            {
                "state": snapshot.human_review,
                "note": snapshot.review_note,
                "operator": snapshot.review_operator,
                "updated_at": snapshot.review_updated_at,
            }
            for snapshot in snapshots
        ],
    }
    labels = {
        "parameters": "Parameters",
        "data": "Data, provider and period",
        "execution": "Execution and costs",
        "evidence": "Evidence",
        "review": "Human review",
    }
    return tuple(
        CompareDifferenceGroup(
            key=key,
            label=labels[key],
            fields=_difference_fields(snapshots, documents[key]),
        )
        for key in ("parameters", "data", "execution", "evidence", "review")
    )


def _difference_fields(
    snapshots: tuple[_RunSnapshot, ...],
    documents: list[Mapping[str, Any]],
) -> tuple[CompareDifferenceField, ...]:
    flattened = [_flatten(document) for document in documents]
    keys = sorted({key for document in flattened for key in document})
    fields = []
    for key in keys:
        values = []
        for snapshot, document in zip(snapshots, flattened, strict=True):
            raw = document.get(key)
            available = not _missing(raw)
            values.append(
                CompareDifferenceValue(
                    run_id=snapshot.run_id,
                    value=_display(raw) if available else "Unavailable",
                    available=available,
                    omission=None if available else "Persisted value is unavailable.",
                )
            )
        fields.append(
            CompareDifferenceField(
                key=key,
                label=_human_label(key),
                state=_state(
                    tuple(value.value for value in values),
                    available=tuple(value.available for value in values),
                ),
                values=tuple(values),
            )
        )
    return tuple(fields)


def _comparability_findings(
    snapshots: tuple[_RunSnapshot, ...],
    metric_rows: tuple[CompareMetricRow, ...],
    equity_series: tuple[CompareSeries, ...],
    difference_groups: tuple[CompareDifferenceGroup, ...],
) -> tuple[ComparabilityFinding, ...]:
    findings: list[ComparabilityFinding] = []
    run_ids = tuple(snapshot.run_id for snapshot in snapshots)
    if len(snapshots) < 2:
        findings.append(
            ComparabilityFinding(
                "fewer_than_two_runs",
                "blocking",
                "Select at least two persisted runs before comparing.",
                run_ids,
            )
        )
    if len(set(run_ids)) != len(run_ids):
        findings.append(
            ComparabilityFinding(
                "duplicate_run_selection",
                "blocking",
                "Choose at least two distinct persisted runs before comparing.",
                run_ids,
            )
        )
    unavailable = tuple(
        snapshot.run_id for snapshot in snapshots if not snapshot.available
    )
    if unavailable:
        findings.append(
            ComparabilityFinding(
                "run_unavailable",
                "blocking",
                "One or more requested persisted runs are unavailable.",
                unavailable,
            )
        )
    errored = tuple(snapshot.run_id for snapshot in snapshots if snapshot.errors)
    if errored:
        findings.append(
            ComparabilityFinding(
                "persisted_evidence_error",
                "blocking",
                (
                    "One or more requested runs contain invalid persisted evidence; "
                    "supported sections remain visible but direct comparison is unsafe."
                ),
                errored,
            )
        )

    checks = (
        (
            "dataset_identity",
            "dataset_identity",
            "Selected runs use different persisted dataset identities.",
        ),
        ("instrument", "instrument", "Selected runs use different instruments."),
        ("timeframe", "timeframe", "Selected runs use different timeframes."),
        ("actual_period", "actual_period", "Selected runs use different data windows."),
        ("timezone", "timezone", "Selected runs use different data timezones."),
        ("adjustment", "adjusted", "Selected runs use different adjustment policies."),
    )
    for code, attribute, message in checks:
        values = [
            getattr(snapshot, attribute)
            for snapshot in snapshots
            if snapshot.available
        ]
        if any(value == "Unavailable" for value in values):
            findings.append(
                ComparabilityFinding(
                    f"{code}_unavailable",
                    "blocking",
                    f"{message[:-1]} or are missing that comparison basis.",
                    run_ids,
                )
            )
        elif len(set(values)) > 1:
            findings.append(
                ComparabilityFinding(code, "blocking", message, run_ids)
            )

    providers = {
        snapshot.provider for snapshot in snapshots if snapshot.available
    }
    if len(providers) > 1:
        findings.append(
            ComparabilityFinding(
                "provider",
                "warning",
                (
                    "Selected runs use different data providers; inspect "
                    "provenance before interpreting differences."
                ),
                run_ids,
            )
        )

    bases = {snapshot.metric_basis for snapshot in snapshots if snapshot.available}
    if (
        "No persisted ranked result" in bases
        or len(bases) > 1
        or any(row.basis_warning for row in metric_rows)
    ):
        findings.append(
            ComparabilityFinding(
                "metric_basis",
                "blocking",
                "Headline metric bases differ or are unavailable.",
                run_ids,
            )
        )

    missing_curves = tuple(
        series.run_id for series in equity_series if not series.points
    )
    if missing_curves:
        findings.append(
            ComparabilityFinding(
                "equity_unavailable",
                "blocking",
                "Normalized equity and drawdown cannot be compared for every selected run.",
                missing_curves,
            )
        )
    timestamps = {
        tuple(point.timestamp for point in series.points)
        for series in equity_series
        if series.points
    }
    if len(timestamps) > 1:
        findings.append(
            ComparabilityFinding(
                "curve_alignment",
                "warning",
                (
                    "Persisted curve timestamps differ; labelled series must be "
                    "interpreted on their own observations."
                ),
                run_ids,
            )
        )

    for group in difference_groups:
        if group.key in {"execution", "evidence", "review"} and any(
            field.state == "changed" for field in group.fields
        ):
            findings.append(
                ComparabilityFinding(
                    f"{group.key}_differences",
                    "warning",
                    f"Selected runs have different {group.label.lower()} values.",
                    run_ids,
                )
            )
    return _deduplicate_findings(findings)


def _json_object(value: str, *, label: str) -> dict[str, Any]:
    try:
        document = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"The {label} is invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"The {label} is not a JSON object.")
    return document


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _detail_fields(fields: Iterable[Any]) -> dict[str, str]:
    return {str(field.label): str(field.value) for field in fields}


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _present(value: Any, *, default: str = "Unavailable") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _fallback(current: str, candidate: Any) -> str:
    return _present(candidate) if current == "Unavailable" else current


def _flatten(document: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_key in sorted(document):
        key = f"{prefix}.{raw_key}" if prefix else str(raw_key)
        value = document[raw_key]
        if isinstance(value, Mapping):
            result.update(_flatten(value, key))
        else:
            result[key] = value
    return result


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == "Unavailable"


def _display(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(_display(item) for item in value) or "Unavailable"
    return str(value)


def _human_label(key: str) -> str:
    return " · ".join(
        part.replace("_", " ").strip().title() for part in key.split(".")
    )


def _state(values: tuple[Any, ...], *, available: tuple[bool, ...]) -> str:
    if not values or not all(available):
        return "missing"
    canonical = tuple(json.dumps(value, sort_keys=True) for value in values)
    return "equal" if len(set(canonical)) == 1 else "changed"


def _looks_like_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in ("invalid", "corrupt", "failed", "mismatch", "unsafe")
    )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _deduplicate_findings(
    findings: Iterable[ComparabilityFinding],
) -> tuple[ComparabilityFinding, ...]:
    unique: dict[tuple[str, tuple[str, ...]], ComparabilityFinding] = {}
    for finding in findings:
        unique[(finding.code, finding.run_ids)] = finding
    return tuple(unique.values())


__all__ = [
    "CompareDashboardAdapter",
    "CompareDifferenceField",
    "CompareDifferenceGroup",
    "CompareDifferenceValue",
    "CompareMetricRow",
    "CompareMetricValue",
    "CompareRunIdentity",
    "CompareSeries",
    "CompareSeriesPoint",
    "CompareViewModel",
    "ComparabilityFinding",
]
