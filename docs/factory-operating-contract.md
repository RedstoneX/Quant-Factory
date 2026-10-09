# Quant Factory operating contract

This document defines product behavior and state. It contains no page layout,
visual direction, active queue, or implementation authority.

## Purpose

Quant Factory is a high-throughput, mostly automated filtration system for
finding rare, durable trading edges. Owner- and LLM-authored QF Candidate
packets enter the same provider-neutral conveyor. Weak, invalid, duplicated, or
unsupported work is closed automatically; genuine survivors and exceptions are
made visible without turning the owner into a routine approval bottleneck.

## Canonical state

One read-only presentation projection derives from existing authoritative
Candidate, run, evidence, policy, artifact, and lineage records. No dashboard
surface creates a second database, evidence source, or lifecycle truth.

Keep these dimensions independent:

- Candidate lifecycle: received, validating, repairing, study planning,
  implementation check, eligible, queued, screening, OOS, walk-forward,
  robustness, Monte Carlo, qualified survivor, screened out, invalid,
  duplicate closed, implementation blocked, budget blocked, or exception hold.
- Run status: not run, queued, running, succeeded, failed, or cancelled.
- Evidence outcome: not run, passed, screened out, insufficient, or invalid.
- Authority: in-policy automation, exception hold, paper eligible, or paper
  lane inactive.
- Current eligibility: the exact action permitted now.
- Current attention: none, unresolved meaning, prior-work judgment, cost/data
  authority, paper authority, or system intervention.

Never collapse these dimensions into generic labels such as Accepted, Ready,
or Failed. Every aggregate must reconcile with its exact underlying records.

## Operator projections

Dashboard is aggregate-first oversight of the complete filtered population. It
reports current operations, queue and worker capacity, bottlenecks, evidence
survival, newly qualified survivors, genuine owner exceptions, system failures,
closed failure history, data readiness, and observation freshness without
loading every Candidate into the browser. Its plots and survivor shortlist are
bounded views whose counts still reconcile to the full population.

Candidates is the complete high-density survivor and Candidate workspace. It
owns full ranking, sorting, filtering, saved views, and selection across large
populations. Dashboard drill-downs either open one exact record, provide real
server-paged record access, or transfer the current filter context to
Candidates. Results owns one selected Candidate's charts, trades, drawdown,
evidence, and lineage. These projections never create lifecycle state.

## Automated conveyor

For every imported Candidate, one idempotent coordinator:

1. preserves source bytes and immutable identity;
2. validates schema, provenance, intraday mandate, safety, and semantics;
3. performs only deterministic normalization or at most two bounded repair
   attempts, each as a child version with a field-level diff and provenance;
4. checks exact identity and economic meaning against prior work;
5. compiles fixed rules, bounded variables, conditional relationships, and
   structural variants into an immutable StudyPlan;
6. precommits data, splits, costs, execution assumptions, objective, evidence
   gates, multiplicity rules, budgets, and stop conditions;
7. resolves a versioned strategy adapter and matches its checksum;
8. admits work only inside an active campaign policy and creates one durable
   launch claim;
9. reuses `CandidatePipelineRuntime` and `FactoryFilterChainService` for
   screening, OOS, walk-forward, robustness/regime, and Monte Carlo; and
10. materializes full portfolios, charts, trades, and evidence only for the
    declared finalists, then creates an immutable survivor package when every
    gate passes.

Every gate persists input identity, policy version, outcome, reason codes,
observation time, and next eligibility. Replay reopens or safely resumes the
same work; it never creates a duplicate run.

## Repair and search boundaries

Repair may clarify already-supported meaning. It may not invent source facts,
alter the hypothesis, add indicators or variants, widen a range, change the
objective/data split/costs after results, weaken a gate, refine a failed region,
inspect protected evidence, or promote an edge.

VectorBT Pro evaluates the declared space efficiently; it does not choose a new
hypothesis or silently expand the search. Ranking favors stable neighboring
regions and downstream evidence, not the single best historical return. Any
refinement is a new precommitted study version.

## Campaign authority

Unattended research remains disabled until an owner-approved, versioned policy
sets instruments, sessions, strategy families, data, horizons, concurrency,
Candidate/study/variant/sample/finalist limits, compute/storage/cost ceilings,
retry/circuit-breaker rules, objectives, costs, data splits, multiplicity
controls, evidence gates, and expiry. Missing values fail closed. A policy
change never retroactively edits work already begun.

Ordinary validation rejection, duplication, screening failure, and downstream
evidence failure close automatically. Owner attention is limited to unresolved
meaning, uncertain economic equivalence, mandate or paid/protected-data
expansion, hypothesis-changing adapter choices, paper-policy expansion, and
paper/live/broker/capital activation. Infrastructure failures use a separate
system-intervention queue.

## Survivor and paper boundary

A qualified survivor is still research evidence, not an approved edge or a
trading instruction. Quant Factory may create a content-addressed paper package
and record handoff status only inside a separately activated paper lane. The
Alpaca paper-trading application is a separate project, runtime, database,
credential domain, and operator interface. Quant Factory shows no paper P&L and
owns no broker controls.

## Truth and safety

- Candidate, StudyPlan, run, evidence, chart, trade, and paper-package identity
  remain exact and traceable.
- The two screened-out MES proof Candidates may not be tuned or rerun.
- No fixture or fabricated owner-facing record may stand in for a Candidate,
  run, survivor, chart, or trade.
- Research, protected evidence, paper, live, broker, and capital authority do
  not follow from UI work.
