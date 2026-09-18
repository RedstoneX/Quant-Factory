"""Public pre-simulation and normalized research-evidence interfaces."""

from backtesting.validation.models import (
    ExperimentValidationError,
    ValidationResult,
    raise_for_blocking_failures,
)
from backtesting.validation.gates import (
    normalize_signals,
    validate_execution,
    validate_market_data,
    validate_signals,
)
from backtesting.validation.evidence_adapters import (
    map_native_status,
    normalize_evidence,
    normalize_low_frequency_walk_forward_evidence,
    normalize_monte_carlo_evidence,
    normalize_out_of_sample_evidence,
    normalize_robustness_evidence,
    normalize_walk_forward_evidence,
)
from backtesting.validation.evidence_models import (
    EvidenceStatus,
    ExecutionCostAssumptions,
    NormalizedEvidenceRecord,
    NormalizedThresholdResult,
    ProtectedDataState,
    StageAcceptanceThreshold,
    ValidationPeriod,
    ValidationSpecification,
    WalkForwardWindowRules,
)
from backtesting.validation.walk_forward_artifacts import (
    PersistedWalkForwardEvidence,
    build_walk_forward_evidence_document,
    persist_walk_forward_evidence_artifact,
    retrieve_walk_forward_evidence_artifact,
    validate_walk_forward_evidence_document,
)
from backtesting.validation.monte_carlo_artifacts import (
    PersistedMonteCarloEvidence,
    build_monte_carlo_evidence_document,
    persist_monte_carlo_evidence_artifact,
    retrieve_monte_carlo_evidence_artifact,
    validate_monte_carlo_evidence_document,
)
from backtesting.validation.robustness_artifacts import (
    PersistedRobustnessEvidence,
    build_robustness_evidence_document,
    persist_robustness_evidence_artifact,
    retrieve_robustness_evidence_artifact,
    validate_robustness_evidence_document,
)
from backtesting.validation.evidence_decision_artifacts import (
    PersistedEvidenceDecisionRecord,
    build_evidence_decision_document,
    persist_evidence_decision_artifact,
    retrieve_evidence_decision_artifact,
    validate_evidence_decision_document,
)
from backtesting.validation.lockbox_gate import (
    LockboxArtifactReference,
    LockboxGateResult,
    evaluate_lockbox_prerequisites,
)

__all__ = [
    "ExperimentValidationError",
    "EvidenceStatus",
    "ExecutionCostAssumptions",
    "NormalizedEvidenceRecord",
    "NormalizedThresholdResult",
    "ProtectedDataState",
    "PersistedWalkForwardEvidence",
    "PersistedMonteCarloEvidence",
    "PersistedRobustnessEvidence",
    "PersistedEvidenceDecisionRecord",
    "LockboxArtifactReference",
    "LockboxGateResult",
    "StageAcceptanceThreshold",
    "ValidationResult",
    "ValidationPeriod",
    "ValidationSpecification",
    "WalkForwardWindowRules",
    "build_walk_forward_evidence_document",
    "build_monte_carlo_evidence_document",
    "build_robustness_evidence_document",
    "build_evidence_decision_document",
    "evaluate_lockbox_prerequisites",
    "map_native_status",
    "normalize_evidence",
    "normalize_low_frequency_walk_forward_evidence",
    "normalize_monte_carlo_evidence",
    "normalize_out_of_sample_evidence",
    "normalize_robustness_evidence",
    "normalize_walk_forward_evidence",
    "persist_walk_forward_evidence_artifact",
    "persist_monte_carlo_evidence_artifact",
    "persist_robustness_evidence_artifact",
    "persist_evidence_decision_artifact",
    "retrieve_walk_forward_evidence_artifact",
    "retrieve_monte_carlo_evidence_artifact",
    "retrieve_robustness_evidence_artifact",
    "retrieve_evidence_decision_artifact",
    "normalize_signals",
    "raise_for_blocking_failures",
    "validate_execution",
    "validate_walk_forward_evidence_document",
    "validate_monte_carlo_evidence_document",
    "validate_robustness_evidence_document",
    "validate_evidence_decision_document",
    "validate_market_data",
    "validate_signals",
]
