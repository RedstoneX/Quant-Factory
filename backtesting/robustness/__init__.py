"""Public parameter and regime robustness interface."""

from backtesting.robustness.artifact_loader import find_valid_lock, load_lock_artifact
from backtesting.robustness.evaluation import evaluate_neighborhood
from backtesting.robustness.models import (
    CandidateDerivation,
    DimensionStability,
    EvaluatedParameterPoint,
    NeighborhoodCandidate,
    NeighborhoodConfig,
    NeighborhoodConstructionResult,
    NeighborhoodEvaluation,
    NeighborhoodSummary,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
    RegimeEvaluationResult,
    RegimeLabels,
    RobustnessConfig,
    RobustnessResult,
    SourceLockEvidence,
    ThresholdResult,
)
from backtesting.robustness.parameter_neighborhood import build_neighborhood
from backtesting.robustness.regimes import (
    attribute_returns_to_regimes,
    evaluate_regimes,
    label_regimes,
)
from backtesting.robustness.reporting import (
    read_robustness_report,
    validate_robustness_report,
    write_robustness_report,
)
from backtesting.robustness.runner import (
    build_robustness_result,
    combine_statuses,
    insufficient_result,
    run_robustness_pipeline,
    summarize_neighborhood,
)

__all__ = [
    "CandidateDerivation",
    "DimensionStability",
    "EvaluatedParameterPoint",
    "NeighborhoodCandidate",
    "NeighborhoodConfig",
    "NeighborhoodConstructionResult",
    "NeighborhoodEvaluation",
    "NeighborhoodSummary",
    "ParameterNeighborhoodDefinition",
    "RegimeConfig",
    "RegimeEvaluationResult",
    "RegimeLabels",
    "RobustnessConfig",
    "RobustnessResult",
    "SourceLockEvidence",
    "ThresholdResult",
    "attribute_returns_to_regimes",
    "build_neighborhood",
    "build_robustness_result",
    "combine_statuses",
    "evaluate_neighborhood",
    "evaluate_regimes",
    "find_valid_lock",
    "insufficient_result",
    "label_regimes",
    "load_lock_artifact",
    "read_robustness_report",
    "run_robustness_pipeline",
    "summarize_neighborhood",
    "validate_robustness_report",
    "write_robustness_report",
]
