"""Single provider-neutral authority map for gateway dispatch and bootstrap."""

OPERATION_LEVELS = {
    "bootstrap": 0,
    "context.get": 0,
    "prior.search": 0,
    "candidate.list": 0,
    "candidate.get": 0,
    "run.status": 0,
    "run.results": 0,
    "run.evidence": 0,
    "lineage.get": 0,
    "candidate.validate": 1,
    "candidate.submit": 1,
    "research.note.add": 1,
    "run.request": 2,
}

AUTHORITY_NAMES = {0: "context_read", 1: "draft_intake", 2: "development_research"}

NEVER_PERMITTED = (
    "candidate.approve",
    "strategy.implement",
    "protected_evidence.read",
    "data.purchase",
    "credential.read",
    "broker.order",
    "paper.activate",
    "live.activate",
    "capital.allocate",
    "source.modify",
)
