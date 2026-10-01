"""Provider-neutral research intake contracts for Quant Factory."""

from research_intake.qf_candidate import (
    QF_CANDIDATE_SCHEMA,
    CandidateIssue,
    CandidateImportResult,
    CandidatePacketError,
    CandidateValidation,
    attach_candidate_to_idea,
    export_candidate_packet,
    import_candidate_as_idea,
    parse_candidate_packet,
    validate_candidate_packet,
)

__all__ = [
    "QF_CANDIDATE_SCHEMA",
    "CandidateIssue",
    "CandidateImportResult",
    "CandidatePacketError",
    "CandidateValidation",
    "attach_candidate_to_idea",
    "export_candidate_packet",
    "import_candidate_as_idea",
    "parse_candidate_packet",
    "validate_candidate_packet",
]


from research_intake.qf_research_context import (
    QF_RESEARCH_CONTEXT_SCHEMA,
    build_research_context,
    export_research_context,
)

__all__ += [
    "QF_RESEARCH_CONTEXT_SCHEMA",
    "build_research_context",
    "export_research_context",
]
