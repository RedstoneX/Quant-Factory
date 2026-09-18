"""Deterministic experiment-matrix planning without data access or simulation."""

from strategies.models import StrategySpecification
from strategies.parameter_governance import (
    ParameterPlanSummary,
    summarize_parameter_plan,
)

from backtesting.portability.models import (
    ExecutionProfile,
    ExperimentMatrixSummary,
    ExperimentVariant,
    InstrumentProfile,
    SessionProfile,
    TimeframeProfile,
    UnsupportedCombination,
)
from backtesting.portability.validation import (
    validate_execution_profile,
    validate_experiment_variant,
    validate_instrument_profile,
    validate_session_profile,
    validate_timeframe_profile,
)


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate experiment combinations: repeated {label}")


def summarize_experiment_matrix(
    *,
    instruments: tuple[InstrumentProfile, ...],
    timeframes: tuple[TimeframeProfile, ...],
    sessions: tuple[SessionProfile, ...],
    execution_profiles: tuple[ExecutionProfile, ...],
    strategy: StrategySpecification,
    parameter_plan: ParameterPlanSummary,
) -> ExperimentMatrixSummary:
    """Return runnable variants and unsupported combinations without simulation."""
    if not instruments or not timeframes or not sessions:
        raise ValueError("Instrument, timeframe, and session inputs must not be empty")

    approved_plan = summarize_parameter_plan(strategy, require_approved=True)
    if (
        parameter_plan.optimized_parameters != approved_plan.optimized_parameters
        or parameter_plan.total_combinations != approved_plan.total_combinations
        or parameter_plan.fixed_parameters != approved_plan.fixed_parameters
        or parameter_plan.structural_choice_parameters
        != approved_plan.structural_choice_parameters
    ):
        raise ValueError("Parameter-plan summary does not match strategy metadata")

    for profile in instruments:
        validate_instrument_profile(profile, require_approved=True)
    for profile in timeframes:
        validate_timeframe_profile(profile, require_approved=True)
    for profile in sessions:
        validate_session_profile(profile, require_approved=True)
    for profile in execution_profiles:
        validate_execution_profile(profile, require_approved=True)

    _require_unique(tuple(item.symbol for item in instruments), "instrument")
    _require_unique(tuple(item.interval for item in timeframes), "timeframe")
    _require_unique(tuple(item.session_id for item in sessions), "session")
    _require_unique(
        tuple(item.profile_id for item in execution_profiles), "execution profile"
    )

    session_map = {item.session_id: item for item in sessions}
    execution_map = {item.profile_id: item for item in execution_profiles}
    variants: list[ExperimentVariant] = []
    unsupported: list[UnsupportedCombination] = []

    for instrument in instruments:
        if instrument.session_profile_id not in session_map:
            raise ValueError(
                f"{instrument.symbol}: missing session profile "
                f"{instrument.session_profile_id}"
            )
        if instrument.execution_profile_id not in execution_map:
            raise ValueError(
                f"{instrument.symbol}: missing execution profile "
                f"{instrument.execution_profile_id}"
            )
        session = session_map[instrument.session_profile_id]
        execution = execution_map[instrument.execution_profile_id]
        for timeframe in timeframes:
            variant = ExperimentVariant(
                strategy_id=strategy.identity.strategy_id,
                instrument_symbol=instrument.symbol,
                provider_symbol=instrument.provider_symbol,
                timeframe_interval=timeframe.interval,
                session_id=session.session_id,
                execution_profile_id=execution.profile_id,
                adjusted_prices=instrument.adjusted_prices_required,
                approval_state="approved",
            )
            try:
                validate_experiment_variant(
                    variant,
                    instrument=instrument,
                    timeframe=timeframe,
                    session=session,
                    execution=execution,
                    strategy=strategy,
                    require_approved=True,
                )
            except ValueError as exc:
                unsupported.append(
                    UnsupportedCombination(
                        instrument_symbol=instrument.symbol,
                        timeframe_interval=timeframe.interval,
                        reason=str(exc),
                    )
                )
            else:
                variants.append(variant)

    identities = tuple(variant.identity for variant in variants)
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate experiment combinations are not allowed")

    warnings: list[str] = list(parameter_plan.warnings)
    if unsupported:
        warnings.append(
            f"{len(unsupported)} unsupported combination(s) excluded before simulation."
        )
    variant_count = len(variants)
    return ExperimentMatrixSummary(
        instrument_count=len(instruments),
        timeframe_count=len(timeframes),
        session_count=len(sessions),
        execution_profile_count=len(execution_profiles),
        experiment_variant_count=variant_count,
        parameter_combinations=parameter_plan.total_combinations,
        total_planned_simulations=variant_count * parameter_plan.total_combinations,
        variants=tuple(variants),
        unsupported_combinations=tuple(unsupported),
        warnings=tuple(warnings),
    )
