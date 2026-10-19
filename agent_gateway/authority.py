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
    "campaign.status": 0,
    "campaign.control_status": 0,
    "run.trades": 0,
    "data.files": 0,
    "data.download": 0,
    "campaign.requeue": 1,
    "campaign.pause": 1,
    "campaign.resume": 1,
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
