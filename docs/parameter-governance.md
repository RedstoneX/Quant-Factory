# Parameter Governance and Hypothesis-Control Policy

## Philosophy

Quant Factory is hypothesis-driven. A strategy begins with a source or written
hypothesis supplied by the user, or with an AI-translated specification that the
user explicitly approves. The factory may explore bounded variations that have
an explicit source and rationale; it must not assemble arbitrary indicators,
timeframes, filters, exits, and position rules until historical winners appear.

> VectorBT Pro is used for fast, bounded, reproducible exploration of approved hypotheses. Its speed is not permission to search arbitrary strategy space until a historical winner appears.

Every strategy specification records its hypothesis, source, approval state,
and one independently testable reference configuration. The reference normally
comes from original source material, established literature, explicit user
instruction, or a documented economic or market rationale.

## Parameter classifications

Every fixed or tunable strategy field uses exactly one classification:

- `fixed`: not optimized, such as long-only direction or one-position-at-a-time.
- `source_defined`: taken directly from an approved source or hypothesis.
- `bounded_discrete`: a short, reasoned list of meaningfully different values.
- `local_sensitivity`: nearby values around a reference value.
- `structural_choice`: a materially different rule or mechanism.

Each parameter records its name, description, classification, reference value,
candidate values, source, rationale, optimization flag, structural flag,
expected grid contribution, and approval state. The source says where the field
or value came from; the rationale explains why it belongs in the approved plan.
An optimized parameter must have both, and its reference value must be among its
unique candidate values.

Structural choices—such as an RSI-recovery exit versus a moving-average exit,
or a fixed stop versus an ATR stop—are separate strategy variants or separately
approved experiment definitions. They are excluded from an ordinary Cartesian
parameter grid and cannot be disguised as local sensitivity.

## Reference-first exploration

Exploration has three ordered stages:

1. **Reference reproduction.** Run the approved reference configuration exactly
   to verify interpretation, implementation, and baseline behavior.
2. **Coarse bounded exploration.** Test a small set of defensible alternatives
   to identify broad viable or non-viable regions without fine-tuning noise.
3. **Local refinement.** Refine only around a region that survived prior gates.
   This requires a newly approved parameter plan or an explicitly pre-approved
   refinement policy.

Passing one stage does not authorize silent changes in the next. Codex, AI,
strategy code, and experiment runners may not add values, widen ranges, change
spacing or units, optimize fixed fields, add structural choices, or introduce
new indicators and filters without a reviewed specification.

## Grid summary and warning policy

Before execution, `summarize_parameter_plan` validates the plan and reports:

- every optimized parameter and its candidate count;
- the total Cartesian combination count;
- the number of fixed fields excluded from the grid;
- structural choices excluded from the grid;
- threshold and structural-choice warnings.

The initial warning threshold is 100 combinations. It is provisional and
configurable, not a universal maximum: it creates a deliberate review point
while the project has few archetypes and human review remains practical. A
different threshold requires an explicit, documented choice. Exceeding the
threshold warns rather than silently truncating or changing the grid.

## Selection and stable regions

Quant Factory does not automatically promote the single highest-return
historical row. Review favors stable neighboring parameters, gradual metric
changes, consistent drawdowns, sufficient trades, realistic execution,
repeatable out-of-sample behavior, and robustness across regimes. An isolated
optimum surrounded by weak or failing values is flagged as potential
overfitting, not treated as a discovery victory.

## Approval boundary

Before implementation or grid execution, the human-readable specification must
expose the strategy source and hypothesis, reference rules and parameters,
candidate values and rationales, parameter classifications, structural
variants, total grid size, warnings, and approval state. The user approves both
the strategy interpretation and parameter plan.

Under the current agent policy, approval is either an explicit approved
specification committed to this repository or a clearly identified approval in
the bounded implementation-agent request. The typed experiment runner requires an
approved strategy and approved parameter definitions before simulation. A
future dashboard and Strategy Idea Inbox may provide the interface, but do not
change this boundary.

## Examples

Local sensitivity around a source reference:

```yaml
rsi_length:
  classification: local_sensitivity
  reference: 14
  values: [10, 12, 14, 16, 18]
  source: original_strategy
  rationale: evaluate stability around the source-defined RSI length
  optimized: true
  structural: false
```

A structural alternative:

```yaml
exit_rule:
  classification: structural_choice
  reference: rsi_recovery
  values:
    - rsi_recovery
    - moving_average_exit
  source: human_approved_extension
  rationale: compare materially different exit mechanisms as separate variants
  optimized: false
  structural: true
```

The second example must be represented as separately approved variants and must
not be mixed into an ordinary parameter grid without explicit approval.

## Prohibited behavior

The project must not autonomously mine arbitrary strategy space, silently alter
approved plans, treat a fast engine as permission for indiscriminate search,
mix structural variants into ordinary grids, refine around failed regions, or
prefer isolated peaks without robustness evidence. VectorBT Pro remains the
simulation and analytics engine; Quant Factory owns hypothesis approval,
parameter governance, validation, evidence progression, and auditability.
