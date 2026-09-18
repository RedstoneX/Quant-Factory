"""Typed results and errors for pre-simulation hygiene gates."""

from dataclasses import dataclass, field
from typing import Any, Literal

GateStatus = Literal["passed", "failed"]
GateSeverity = Literal["info", "warning", "blocking"]


@dataclass(frozen=True)
class ValidationResult:
    gate_id: str
    status: GateStatus
    severity: GateSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocking_failure(self) -> bool:
        return self.status == "failed" and self.severity == "blocking"


class ExperimentValidationError(ValueError):
    """Aggregate every blocking gate failure into one readable error."""

    def __init__(self, results: tuple[ValidationResult, ...]) -> None:
        self.results = results
        self.failures = tuple(result for result in results if result.is_blocking_failure)
        lines = [
            f"Experiment validation failed ({len(self.failures)} blocking gate(s)):"
        ]
        lines.extend(
            f"- {failure.gate_id}: {failure.message}" for failure in self.failures
        )
        super().__init__("\n".join(lines))


def raise_for_blocking_failures(results: tuple[ValidationResult, ...]) -> None:
    if any(result.is_blocking_failure for result in results):
        raise ExperimentValidationError(results)
