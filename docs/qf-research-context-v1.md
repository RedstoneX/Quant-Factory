# QF Research Context v1

QF Research Context v1 is the portable companion to QF Candidate v1 for work
performed outside Quant Factory.

Its purpose is simple: an external researcher or LLM should not have to know
Quant Factory's history from memory. Give it the exported context before asking
it to discover or normalize strategy ideas.

The context contains:

- the current same-session intraday mandate;
- the current first-stage MES/MNQ focus;
- prior Quant Factory tested hypotheses and their scoped dispositions;
- a compact snapshot of relevant catalogued data;
- deduplication and research boundaries;
- the QF Candidate v1 output contract; and
- an instruction to preserve uncertainty and avoid unauthorized backtesting,
  optimization, implementation, protected evidence, or trading.

## Portable artifact

The checked-in snapshot is:

`docs/qf-research-context-v1.yaml`

The Ideas workbench also exposes YAML/JSON downloads generated from the same
code contract.

This is a **supporting snapshot, not Tier-1 authority**. Quant Factory still
re-checks `AGENTS.md`, `docs/MILESTONES.md`, `docs/DECISIONS.md`, prior
work, local data availability/checksums, and Candidate validity before any
research is authorized.

## External workflow

Use:

```text
QF Research Context v1
        +
your research directive / source universe
        ↓
external LLM or human researcher
        ↓
QF Candidate v1 packet(s)
        ↓
Quant Factory Ideas workbench
        ↓
owner review
```

An external model may research broadly, but it must not claim a Candidate is
approved merely because it generated the packet.

A prior test does not automatically close a strategy family. The context must
distinguish the exact rule/parameter space that was tested from the broader
family. For example, the shallow historical MES ORB baseline matrix screened
out, but materially different ORB hypotheses remain eligible. Only an explicit
Tier-1 owner decision can mark a whole family exhausted.

## Maintenance

When the active research mandate, prior-work dispositions, relevant data
inventory, or Candidate contract changes materially, update
`research_intake/qf_research_context.py` and the checked-in YAML snapshot in
the same pull request. Tests require the snapshot to parse to the same document
as the exported context.
