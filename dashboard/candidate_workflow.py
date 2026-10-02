"""Truthful Candidate identity and executable-configuration bindings."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

from dashboard.run_adapter import (
    IdeaDraftView,
    SavedConfigurationView,
    list_idea_drafts,
    list_saved_configurations,
)
from persistence import StrategyLifecycle
from research_intake import parse_candidate_packet, validate_candidate_packet


@dataclass(frozen=True)
class CandidateIdentityView:
    """One immutable Candidate version as shown throughout the owner workflow."""

    candidate_id: str
    version_fingerprint: str
    title: str
    family: str
    status: str
    attribution: str
    rationale: str
    fixed_definition: str
    evidence_contract: str

    @property
    def short_version(self) -> str:
        return self.version_fingerprint[:12]


@dataclass(frozen=True)
class CandidateConfigurationBinding:
    """Authoritative Candidate-to-configuration link used by owner pages."""

    draft: IdeaDraftView | None
    identity: CandidateIdentityView | None
    configuration: SavedConfigurationView | None
    blocker_code: str | None
    blocker_reason: str | None

    @property
    def candidate_status(self) -> str:
        return self.identity.status if self.identity is not None else "missing"

    @property
    def bound(self) -> bool:
        return self.configuration is not None and self.blocker_code is None


def candidate_identity(draft: IdeaDraftView) -> CandidateIdentityView | None:
    """Return the exact validated version identity persisted on one idea."""

    if not draft.candidate_json:
        return None
    try:
        validation = validate_candidate_packet(
            parse_candidate_packet(draft.candidate_json, format_hint="json")
        )
    except (TypeError, ValueError):
        return None
    if not validation.valid:
        return None
    candidate = validation.document.get("candidate")
    if not isinstance(candidate, Mapping):
        return None
    hypothesis = validation.document.get("hypothesis")
    rationale = str(hypothesis.get("behavior") or "Not specified") if isinstance(hypothesis, Mapping) else "Not specified"
    definition = {
        key: validation.document.get(key)
        for key in ("rules", "fixed", "variables", "variants")
        if validation.document.get(key) not in (None, {}, [])
    }
    return CandidateIdentityView(
        candidate_id=draft.draft_id,
        version_fingerprint=hashlib.sha256(
            validation.canonical_json.encode("utf-8")
        ).hexdigest(),
        title=str(candidate.get("title") or draft.title).strip(),
        family=str(candidate.get("family") or "Not specified").strip(),
        status=str(candidate.get("status") or "draft").strip(),
        attribution=draft.attribution.strip() or "Owner import",
        rationale=rationale,
        fixed_definition=_compact(definition),
        evidence_contract=_compact(validation.document.get("evaluation") or {}),
    )


def candidate_review_state(draft: IdeaDraftView | None) -> tuple[str, bool]:
    """Return durable decision state and whether Setup may be entered."""

    identity = candidate_identity(draft) if draft is not None else None
    status = identity.status if identity is not None else ""
    return status, status == "owner_approved"


def candidate_identity_for_configuration(
    configuration_id: str,
    *,
    database: str | Path,
) -> CandidateIdentityView | None:
    """Resolve a run configuration back to exactly one persisted Candidate."""

    matches = tuple(
        draft
        for draft in list_idea_drafts(database)
        if draft.configuration_id == configuration_id
    )
    if len(matches) != 1:
        return None
    return candidate_identity(matches[0])


def candidate_compare_identity(
    configuration_id: str,
    implementation: str,
    *,
    database: str | Path,
) -> tuple[str, dict[str, str]]:
    """Return the owner label and trace fields used by Compare."""

    identity = candidate_identity_for_configuration(configuration_id, database=database)
    unavailable = {
        "candidate_id": "Unavailable",
        "candidate_version": "Unavailable",
        "candidate_status": "Unavailable",
        "candidate_source": "Unavailable",
        "candidate_rationale": "Unavailable",
        "candidate_fixed_definition": "Unavailable",
        "candidate_evidence_contract": "Unavailable",
        "implementation_strategy": implementation,
    }
    if identity is None:
        return implementation, unavailable
    return f"{identity.title} · {identity.short_version}", {
        "candidate_id": identity.candidate_id,
        "candidate_version": identity.version_fingerprint,
        "candidate_status": identity.status.replace("_", " ").title(),
        "candidate_source": identity.attribution,
        "candidate_rationale": identity.rationale,
        "candidate_fixed_definition": identity.fixed_definition,
        "candidate_evidence_contract": identity.evidence_contract,
        "implementation_strategy": implementation,
    }


def candidate_selection_blocker(
    draft_id: str | None,
    configuration_id: str | None,
    *,
    database: str | Path,
) -> str | None:
    """Explain why a browser-selected setup is not this exact Candidate."""

    binding = candidate_configuration_binding(draft_id, database=database)
    if not binding.bound:
        return binding.blocker_reason or "The Candidate is not ready to run."
    if binding.configuration.configuration_id != configuration_id:
        return "The selected setup does not match this exact Candidate."
    return None


def candidate_detail_fields(
    identity: CandidateIdentityView | None,
) -> tuple[tuple[str, str], ...]:
    if identity is None:
        return ()
    return (
        ("Candidate", identity.title),
        ("Candidate ID", identity.candidate_id),
        ("Candidate version", identity.version_fingerprint),
        ("Candidate family", identity.family),
        ("Candidate source", identity.attribution),
        ("Candidate rationale", identity.rationale),
        ("Candidate fixed definition", identity.fixed_definition),
        ("Candidate evidence contract", identity.evidence_contract),
        ("Candidate status", identity.status.replace("_", " ").title()),
    )


def displayed_candidate_identity(fields: object) -> tuple[str | None, str | None, str | None]:
    values = {
        getattr(field, "label", ""): getattr(field, "value", None)
        for field in fields or ()
    }
    version = values.get("Candidate version")
    return values.get("Candidate"), values.get("Candidate ID"), version[:12] if version else None


def candidate_configuration_binding(
    draft_id: str | None,
    *,
    database: str | Path,
) -> CandidateConfigurationBinding:
    """Resolve browser selection without ever falling back to another setup."""

    drafts = list_idea_drafts(database)
    draft = next((item for item in drafts if item.draft_id == draft_id), None)
    if not draft_id:
        return _blocked(None, None, "candidate_required", "Choose a saved QF Candidate first.")
    if draft is None:
        return _blocked(None, None, "candidate_missing", "The selected Candidate is no longer available.")
    if not draft.candidate_json:
        return _blocked(
            draft,
            None,
            "candidate_packet_required",
            "Add and save a QF Candidate file before preparing a test.",
        )
    identity = candidate_identity(draft)
    if identity is None:
        return _blocked(
            draft,
            None,
            "candidate_packet_invalid",
            "The saved Candidate file is invalid and must be corrected on Ideas.",
        )
    if identity.status != "owner_approved":
        return _blocked(
            draft,
            identity,
            "owner_approval_required",
            "Accept the exact Candidate on Ideas before implementation or testing.",
        )
    if not draft.configuration_id:
        return _blocked(
            draft,
            identity,
            "implementation_required",
            "This Candidate is accepted but has no matching implementation yet.",
        )
    linked_drafts = tuple(
        item for item in drafts if item.configuration_id == draft.configuration_id
    )
    if len(linked_drafts) != 1:
        return _blocked(
            draft,
            identity,
            "configuration_link_ambiguous",
            "The linked setup does not identify exactly one Candidate and has been blocked.",
        )
    configuration = next(
        (
            item
            for item in list_saved_configurations(database)
            if item.configuration_id == draft.configuration_id
        ),
        None,
    )
    if configuration is None:
        return _blocked(
            draft,
            identity,
            "linked_configuration_missing",
            "The Candidate's linked implementation is unavailable.",
        )
    if configuration.lifecycle != StrategyLifecycle.CANDIDATE.value:
        return _blocked(
            draft,
            identity,
            "fixture_substitution_forbidden",
            "The linked setup is an infrastructure fixture, not this Candidate.",
        )
    return CandidateConfigurationBinding(draft, identity, configuration, None, None)


def _blocked(
    draft: IdeaDraftView | None,
    identity: CandidateIdentityView | None,
    code: str,
    reason: str,
) -> CandidateConfigurationBinding:
    return CandidateConfigurationBinding(draft, identity, None, code, reason)


def _compact(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
