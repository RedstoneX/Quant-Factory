"""Broker-neutral execution evidence contracts; no broker connectivity."""

from execution.contracts import (
    AccountSnapshot,
    Cancellation,
    ExecutionContractError,
    ExecutionDomain,
    ExecutionScope,
    Fill,
    Instrument,
    OrderAcknowledgement,
    OrderIntent,
    OrderSide,
    OrderType,
    PositionSnapshot,
    QuantityUnit,
    ReconciliationResult,
    ReconciliationStatus,
    Rejection,
    RiskMetadata,
    TimeInForce,
    to_primitive,
)
from execution.reconciliation import reconcile_snapshots
from execution.paper_journal import JournalConflictError, JournalEntry, JournalState, PaperJournalError, PaperOrderJournal
from execution.paper_binding import PaperDeploymentBinding, PaperDeploymentBindingError
from execution.paper_handoff import (
    PAPER_HANDOFF_SCHEMA,
    PaperHandoffError,
    PaperHandoffPackage,
    paper_handoff_manifest,
)

__all__ = [
    "AccountSnapshot", "Cancellation", "ExecutionContractError", "ExecutionDomain",
    "ExecutionScope", "Fill", "Instrument", "OrderAcknowledgement", "OrderIntent",
    "OrderSide", "OrderType", "PositionSnapshot", "QuantityUnit", "ReconciliationResult",
    "ReconciliationStatus", "Rejection", "RiskMetadata", "TimeInForce", "reconcile_snapshots",
    "to_primitive",
    "JournalConflictError", "JournalEntry", "JournalState", "PaperJournalError", "PaperOrderJournal",
    "PaperDeploymentBinding", "PaperDeploymentBindingError",
    "PAPER_HANDOFF_SCHEMA", "PaperHandoffError", "PaperHandoffPackage",
    "paper_handoff_manifest",
]
