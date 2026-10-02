"""Deterministic onboarding response for every approved research agent."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

from agent_gateway.authority import AUTHORITY_NAMES, NEVER_PERMITTED
from agent_gateway.contracts import GatewayIdentity
from research_intake import build_research_context


_OPERATING_CONTEXT = "docs/AGENT_RESEARCH_OPERATING_CONTEXT.md"
_OPERATING_CONTEXT_PATH = Path(__file__).parents[1] / _OPERATING_CONTEXT


def build_bootstrap(
    identity: GatewayIdentity,
    *,
    operation_levels: Mapping[str, int],
    run_requests_enabled: bool,
) -> dict[str, object]:
    """Describe identity, context, authority, and boundaries without side effects."""

    context = build_research_context()
    operating_context = _OPERATING_CONTEXT_PATH.read_text()
    permitted = sorted(
        operation
        for operation, level in operation_levels.items()
        if level <= identity.authority_level
        and (operation != "run.request" or run_requests_enabled)
    )
    prohibited = list(NEVER_PERMITTED)
    prohibited.extend(
        sorted(
            operation
            for operation, level in operation_levels.items()
            if level > identity.authority_level
            or (operation == "run.request" and not run_requests_enabled)
        )
    )
    return {
        "schema": "qf_agent_bootstrap_v1",
        "identity": {
            "agent_id": identity.agent_id,
            "provider": identity.provider,
            "client": identity.client,
            "transport": identity.transport,
            "authority_level": identity.authority_level,
        },
        "operating_context": {
            "contract": "qf_agent_research_operating_context_v1",
            "reference": _OPERATING_CONTEXT,
            "sha256": hashlib.sha256(operating_context.encode("utf-8")).hexdigest(),
            "content": operating_context,
        },
        "research_context": context,
        "authority_level": {
            "level": identity.authority_level,
            "name": AUTHORITY_NAMES[identity.authority_level],
        },
        "owner_gates": [
            {
                "gate": "candidate_research",
                "state": context["mandate"]["current_research_state"],
                "requirement": "The owner must accept one bounded Candidate and its evidence contract before research begins.",
            },
            {
                "gate": "development_run",
                "state": "conditional",
                "requirement": "Level 2, an owner-approved Candidate, a linked immutable configuration, and an active Candidate strategy are all required.",
            },
            {
                "gate": "protected_validation_and_trading",
                "state": "not_authorized",
                "requirement": "Protected evidence, broker, paper/live, credential, order, capital, and risk authority require separate owner approval outside this gateway.",
            },
        ],
        "permitted_operations": permitted,
        "prohibited_operations": prohibited,
        "research_start": [
            "Read this bootstrap and the QF Research Context.",
            "Search prior work before external research.",
            "Preserve source provenance and formulate one bounded same-session intraday hypothesis.",
            "Validate and submit QF Candidate v1; submission does not grant research authority.",
            "Stop at every owner gate shown above.",
        ],
    }
