"""Immutable research-to-paper handoff records with no execution capability.

The research product may construct this manifest only after a configured,
fail-closed eligibility decision.  A separately authorized paper system may
later verify and consume it.  The record contains references and checksums,
never strategy code, credentials, broker account identity, or orders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re


PAPER_HANDOFF_SCHEMA = "qf.paper-handoff.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.]{0,14}\Z", re.ASCII)


class PaperHandoffError(ValueError):
    """Raised when a paper handoff is incomplete or ambiguous."""


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise PaperHandoffError(f"{field} must be a bounded non-empty string")
    return value


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PaperHandoffError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _bounded_unique(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values or len(values) > 64:
        raise PaperHandoffError(f"{field} must be a non-empty bounded tuple")
    checked = tuple(_identifier(value, field) for value in values)
    if len(set(checked)) != len(checked):
        raise PaperHandoffError(f"{field} must not contain duplicates")
    return checked


@dataclass(frozen=True)
class PaperHandoffPackage:
    """One content-addressed survivor package offered to the paper boundary.

    This package is neither an order nor deployment approval.  ``lane_policy_id``
    identifies the separately owner-activated paper lane under which automatic
    admission may later occur; the paper system must independently re-check
    eligibility, capacity, broker support, risk policy, and duplicate state.
    """

    handoff_id: str
    candidate_id: str
    strategy_id: str
    strategy_version: str
    source_run_id: str
    evidence_bundle_ref: str
    evidence_bundle_sha256: str
    strategy_package_ref: str
    strategy_package_sha256: str
    execution_vehicle_id: str
    instrument_symbols: tuple[str, ...]
    eligibility_decision_id: str
    eligibility_gate_ids: tuple[str, ...]
    lane_policy_id: str
    paper_risk_policy_id: str
    source_revision: str
    created_at: datetime
    schema: str = PAPER_HANDOFF_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PAPER_HANDOFF_SCHEMA:
            raise PaperHandoffError("schema is not supported")
        for field in (
            "handoff_id",
            "candidate_id",
            "strategy_id",
            "strategy_version",
            "source_run_id",
            "evidence_bundle_ref",
            "strategy_package_ref",
            "execution_vehicle_id",
            "eligibility_decision_id",
            "lane_policy_id",
            "paper_risk_policy_id",
            "source_revision",
        ):
            _identifier(getattr(self, field), field)
        _sha256(self.evidence_bundle_sha256, "evidence_bundle_sha256")
        _sha256(self.strategy_package_sha256, "strategy_package_sha256")
        symbols = _bounded_unique(self.instrument_symbols, "instrument_symbols")
        if any(_SYMBOL.fullmatch(symbol) is None for symbol in symbols):
            raise PaperHandoffError("instrument_symbols contain an unsupported spelling")
        _bounded_unique(self.eligibility_gate_ids, "eligibility_gate_ids")
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
        ):
            raise PaperHandoffError("created_at must be timezone-aware")
        object.__setattr__(self, "created_at", self.created_at.astimezone(timezone.utc))


def paper_handoff_manifest(package: PaperHandoffPackage) -> dict[str, object]:
    """Return a deterministic JSON-native manifest for a verified package."""

    if not isinstance(package, PaperHandoffPackage):
        raise PaperHandoffError("package must be PaperHandoffPackage")
    value = asdict(package)
    value["instrument_symbols"] = list(package.instrument_symbols)
    value["eligibility_gate_ids"] = list(package.eligibility_gate_ids)
    value["created_at"] = package.created_at.isoformat().replace("+00:00", "Z")
    return value


__all__ = [
    "PAPER_HANDOFF_SCHEMA",
    "PaperHandoffError",
    "PaperHandoffPackage",
    "paper_handoff_manifest",
]
