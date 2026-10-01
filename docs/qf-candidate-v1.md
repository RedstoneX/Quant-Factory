# QF Candidate v1 — Research Intake Contract

> **Status:** Accepted portable intake contract for the standardized intake
> milestone. The contract is provider-neutral and non-executable.
>
> Importing or generating a Candidate packet does **not** authorize source
> retrieval, strategy execution, paid data, protected testing, paper/live
> trading, broker orders, or capital exposure. A future built-in LLM analyzer
> is optional; no model/provider is required by this contract.

## Purpose

QF Candidate v1 is a portable research-intake format that separates messy,
probabilistic idea generation from deterministic Quant Factory research.

The intended boundary is:

```text
public source / owner idea / external LLM / optional built-in analyzer
                            |
                            v
                     QF Candidate v1
                            |
                            v
                  owner review / clarification
                            |
                            v
                  approved candidate contract
                            |
                            v
           candidate-specific deterministic implementation
                            |
                            v
               Python / VectorBT Pro research pipeline
```

The same Candidate packet should be usable whether it was created by:

- Terry directly;
- ChatGPT, Claude, Grok, Gemini, or another external LLM;
- a future optional Quant Factory source-analysis button;
- a human researcher;
- analysis of a YouTube video, Reddit post/community, paper, article, web page,
  or Python/VectorBT/TA-Lib strategy archetype.

The format is a **research brief first** and a machine interchange format
second. A knowledgeable trader should be able to understand it without knowing
Quant Factory internals.

## Core design principles

1. **Readable by a human.** Raw YAML/JSON is available, but the dashboard should
   render the same content as a concise research card.
2. **Provider-neutral.** No LLM vendor or model is part of the contract.
3. **Not executable code.** Candidate packets contain research intent and
   bounded rules, never Python, VectorBT expressions, broker instructions, or
   live-trading configuration.
4. **Source facts are separated from interpretation.** The packet distinguishes
   what a source explicitly said from what an LLM, owner, or Quant Factory
   inferred or proposed.
5. **Ambiguity is preserved, not silently resolved.** Important unresolved
   questions remain visible until explicitly answered.
6. **Structural variants and parameter sweeps are different things.** VectorBT
   can efficiently sweep bounded parameter values, but it does not invent new
   strategy logic.
7. **Quant Factory owns deterministic defaults.** Fees, slippage, evidence
   gates, data availability, and runtime identities should normally remain QF
   concerns rather than being invented by an external LLM.
8. **No automatic approval.** Importing or generating a packet never authorizes
   a backtest.
9. **Prior work matters.** The packet should make it easy for Quant Factory to
   identify duplicates or near-duplicates before research is repeated.
10. **Minimum viable boundary.** QF Candidate v1 should not become a universal
    strategy DSL or agent framework.

## Candidate lifecycle

Recommended states:

- `draft` — incomplete idea or imported packet;
- `needs_clarification` — one or more high-importance questions remain;
- `ready_for_review` — sufficiently specified for owner review;
- `owner_approved` — owner accepted the research contract;
- `implemented` — deterministic strategy adapter exists and matches the
  approved contract;
- `rejected` — candidate was rejected before or after testing;
- `retired` — retained for history but no longer active.

A packet should never advance automatically because an LLM claims confidence.

## Recommended top-level structure

```yaml
schema: qf_candidate_v1

candidate: {}
sources: []
source_assessment: {}
hypothesis: {}
source_rules: {}
qf_interpretation: {}
market: {}
rules: {}
fixed: {}
variables: {}
variants: []
open_questions: []
data_needs: {}
execution: {}
exclusions: []
prior_work: {}
evaluation: {}
implementation_notes: {}
```

Only `schema`, `candidate`, `hypothesis`, `market`, `rules`, and either
`sources` or an explicit owner-observation source are expected for a useful
draft. Other sections may be added as the idea becomes more precise.

---

## 1. Candidate summary

The first screen should answer, in seconds, what the idea is.

```yaml
candidate:
  title: "15-minute ORB with VWAP confirmation"
  one_line: >
    Trade breakouts of the first 15-minute range only when price confirms
    on the correct side of VWAP.
  family: "opening_range_breakout"
  status: draft
```

`family` is optional but useful for duplicate detection and candidate-family
grouping.

## 2. Sources

Keep original attribution. Do not collapse several sources into one synthetic
citation.

```yaml
sources:
  - id: source_1
    type: youtube
    title: "ORB Strategy Explained"
    url: "https://..."
    creator: "Example Trader"
    role: primary

  - id: source_2
    type: reddit
    url: "https://reddit.com/..."
    community: "r/Daytrading"
    role: supporting
```

Suggested `type` values:

- `youtube`
- `reddit`
- `paper`
- `article`
- `web`
- `library`
- `code`
- `owner_observation`
- `other`

For a library archetype, record package/project and symbol/class/function when
available.

## 3. Source assessment

This is not a performance score. It summarizes source quality and agreement.

```yaml
source_assessment:
  agreement: >
    Sources agree on the breakout concept but disagree on range length and
    stop placement.
  evidence_quality: anecdotal
  confidence: medium
  unsupported_claims:
    - "No source supplied independently audited performance."
```

Useful `evidence_quality` values may include:

- `owner_observation`
- `anecdotal`
- `community_consensus`
- `backtest_claim`
- `published_empirical`
- `replicated_empirical`
- `unknown`

This field describes the source, not whether Quant Factory believes the edge
exists.

## 4. Hypothesis

A strategy is more than entry rules. State why the behavior might exist and
why it might fail.

```yaml
hypothesis:
  behavior: >
    Strong opening directional pressure may persist after the initial
    15-minute range when price is accepted on the same side of VWAP.

  edge_reasoning:
    - "Opening imbalance may produce short-lived continuation."
    - "VWAP location may filter breakouts against intraday order flow."

  failure_theory:
    - "The opening range may already contain most of the move."
    - "VWAP confirmation may delay entry enough to eliminate the edge."
```

`failure_theory` is strongly recommended. It creates a falsifiable research
question rather than a promotional strategy description.

## 5. Source rules vs QF interpretation

Never silently turn vague source language into precise rules.

```yaml
source_rules:
  entry: "Break the first 15-minute high or low."
  confirmation: "Trade with VWAP."
  stop: "Opposite side of the range."
  target: "Examples mention 1R and 2R."

qf_interpretation:
  entry: >
    Candidate interpretation: first completed 5-minute bar closing beyond the
    15-minute opening-range boundary.
  confirmation: >
    Candidate interpretation: close must be above VWAP for long and below VWAP
    for short.
```

An imported packet may leave `qf_interpretation` empty and instead list open
questions.

## 6. Market and session

Keep this trader-readable.

```yaml
market:
  instruments:
    preferred: ["MES", "MNQ"]
    transferable_to: ["SPY", "QQQ", "SPX"]
  timeframe: "5m"
  session: "US regular trading hours"
  holding_style: intraday
  overnight_positions: false
```

Quant Factory may normalize this later into exact calendars, symbols, and
datasets. The packet should not require internal catalog IDs.

## 7. Exact testable rules

Rules are structured English, not code.

```yaml
rules:
  setup:
    - "Build opening-range high and low from 09:30 through 09:45 ET."

  long_entry:
    - "Price closes above opening-range high."
    - "Price is above VWAP."

  short_entry:
    - "Price closes below opening-range low."
    - "Price is below VWAP."

  exits:
    stop: "Opposite side of opening range."
    target: "R-multiple variable."
    time_exit: "Flat by 15:55 ET."

  max_trades_per_session: 1
```

A rule that cannot yet be made precise belongs in `open_questions`, not hidden
inside prose.

## 8. Fixed rules

Fixed rules are deliberately **not** swept.

```yaml
fixed:
  session: "09:30-16:00 ET"
  overnight_positions: false
  max_trades_per_session: 1
  vwap_confirmation: true
```

This protects the candidate identity from accidental optimization.

## 9. Variables — VectorBT sweep dimensions

Variables define the bounded search space VectorBT may evaluate efficiently.

```yaml
variables:
  opening_range_minutes:
    values: [5, 15, 30]
    rationale: "Common ORB definitions found across the cited sources."

  target_r:
    values: [1.0, 1.5, 2.0]
    rationale: "Bounded to values explicitly discussed in the sources."
```

### Important distinction

VectorBT can generate and test the combinatorial parameter grid after the
dimensions are defined.

For example:

- 3 opening-range lengths
- x 3 entry cutoffs
- x 2 VWAP states
- x 4 target values

produces 72 combinations without writing 72 separate strategies.

VectorBT does **not** independently invent a new filter, entry style, market
microstructure hypothesis, or structural strategy variation. Those must be
defined before the sweep.

## 10. Structural variants

Variants are genuinely different logical forms of the same candidate family.

```yaml
variants:
  - id: plain_orb
    name: "Plain ORB"
    difference: "No VWAP filter."

  - id: vwap_location
    name: "VWAP location"
    difference: "Require price on the correct side of VWAP."

  - id: vwap_slope
    name: "VWAP slope"
    difference: >
      Require both price location and VWAP slope in the trade direction.
```

A structural variant can be tested without new code only when the existing
strategy archetype already supports that logic. Otherwise it requires a small
candidate-specific implementation change before execution.

### Candidate families

An LLM researching a broad topic such as ORB may return one candidate family
with several structural variants rather than many nearly identical packets.

```text
Opening Range Breakout
  ├─ plain breakout
  ├─ VWAP confirmation
  ├─ volume confirmation
  └─ retest entry
```

Quant Factory should preserve the family relationship while treating each
meaningfully different logic path truthfully.

## 11. Open questions

Ambiguity should be visible and actionable.

```yaml
open_questions:
  - id: breakout_definition
    question: "Does touching the range boundary count as a breakout?"
    importance: high
    suggested_default: "Require a completed bar close beyond the boundary."
    origin: llm_proposed

  - id: vwap_slope
    question: "If VWAP slope is used, how is it defined?"
    importance: medium
    suggested_default: "Five-bar linear slope in the trade direction."
    origin: llm_proposed
```

A candidate should normally remain `needs_clarification` while any
high-importance question is unresolved.

## 12. Data needs

The packet describes requirements. Quant Factory determines actual
availability.

```yaml
data_needs:
  minimum_resolution: "5m"
  fields: ["OHLCV"]
  requires_volume: true
  requires_session_boundaries: true
```

Quant Factory may separately enrich the imported packet with a non-portable
status view such as:

```yaml
qf_data_status:
  MES: available
  MNQ: available
  QQQ: missing
```

That status is local Quant Factory evidence and should not be expected from an
external LLM.

## 13. Execution assumptions

Prefer Quant Factory defaults unless strategy mechanics require otherwise.

```yaml
execution:
  use_qf_defaults: true
  special_assumptions:
    entry_fill: "Next bar open after confirmed breakout."
```

External LLMs should not invent commissions, slippage, account size, margin, or
broker behavior unless the source itself makes those assumptions part of the
hypothesis.

## 14. Explicit exclusions

This is a first-class guardrail.

```yaml
exclusions:
  - "No overnight holding."
  - "Do not optimize arbitrary VWAP slope periods."
  - "Do not add volume filters unless separately proposed."
  - "Do not change exit timing after observing results."
```

Exclusions define what is **not** part of the candidate.

## 15. Prior-work relationship

External producers may suggest possible duplicates; Quant Factory verifies them.

```yaml
prior_work:
  possible_duplicates:
    - "MES ORB"
  claimed_difference:
    - "Adds VWAP confirmation."
    - "Tests a different opening-range definition."
```

The imported claim is not authoritative. Quant Factory's own prior-work check
decides whether the candidate is actually new enough to justify research.

## 16. Evaluation contract

Do not ask every external LLM to invent profitability thresholds.

```yaml
evaluation:
  use_qf_standard_screen: true
  candidate_specific_checks:
    - "Require adequate eligible sessions for both directions."
```

The standard Quant Factory evidence contract owns general screening and
validation rules unless the candidate has a justified source-specific
requirement.

## 17. Implementation notes

Optional hints for Codex or a future implementation assistant.

```yaml
implementation_notes:
  likely_archetype: "opening_range_breakout"
  reusable_components:
    - "session range calculation"
    - "VWAP"
  expected_custom_logic: "minimal"
```

These notes are advisory and may be wrong. They do not change the approved
candidate definition.

---

## Field-level provenance

For important inferred fields, v1 should allow optional provenance.

Example:

```yaml
entry_rule:
  value: "Close above opening-range high."
  origin: qf_interpretation
  source_ids: ["source_1"]
```

Recommended origins:

- `source_explicit`
- `source_inferred`
- `llm_proposed`
- `owner_supplied`
- `owner_approved`
- `qf_default`
- `qf_interpretation`

The dashboard need not display provenance beside every ordinary field, but it
should be available when resolving ambiguity or reviewing how a rule arose.

## Human-readable dashboard rendering

The normal operator view should not be raw YAML.

Example:

```text
15-Minute ORB + VWAP

IDEA
Breakouts from the first 15 minutes may continue when price is already
accepted on the correct side of VWAP.

SOURCE
YouTube + two Reddit discussions
Evidence quality: anecdotal / community

TEST
• MES / MNQ
• 5-minute bars
• Opening range: 5 / 15 / 30 minutes
• Plain ORB vs VWAP confirmation
• Targets: 1R / 1.5R / 2R
• Flat by session close

UNRESOLVED
• Breakout on touch or bar close?
• Exact VWAP-slope definition if slope variant is retained.

PRIOR WORK
Plain MES ORB was previously rejected.
This candidate must establish that the proposed filter constitutes a genuinely
different hypothesis rather than a relabelled rerun.

NEXT STEP
Resolve 2 high-importance questions → review candidate
```

Raw YAML/JSON remains available for import/export and technical inspection.

## Intake methods

QF Candidate v1 should support multiple producers without changing the factory.

### A. Paste Candidate packet

An external LLM returns YAML or JSON and Terry pastes it into Quant Factory.

### B. Upload Candidate file

Import a `.yaml`, `.yml`, or `.json` file.

### C. Owner-authored workbench

Terry fills the human-readable fields directly; Quant Factory serializes them
to the same Candidate contract.

### D. Optional future built-in analyzer

A future thin source-analysis action may use a provider such as Google Gemini
to fetch/read permitted public content and return exactly the same Candidate
contract.

The built-in analyzer is only one producer. It is not required for the Candidate
format and must not create a second research path.

### External LLM research context

Before asking an external LLM to discover strategies, give it QF Research
Context v1 (`docs/qf-research-context-v1.yaml`). That context carries the
current intraday mandate, scoped prior-work evidence, relevant data snapshot,
and deduplication rule.

Prior work is compared at the exact/economically-equivalent hypothesis level.
A shallow or failed implementation must not cause an external researcher to
discard the entire ORB, momentum, mean-reversion, channel-breakout, gap-reversal,
or other family unless Tier 1 explicitly closes that family.

The portable flow is:

```text
QF Research Context v1 + research directive -> external LLM -> QF Candidate v1
```

The Ideas workbench can download the context as YAML or JSON.

### External LLM prompt pattern

A generic prompt can be:

```text
Research the supplied source(s) for a concrete same-session intraday trading
strategy. Produce one QF Candidate v1 packet per genuinely distinct candidate
family. Separate explicit source rules from your interpretation. Do not invent
missing rules silently; put them in open_questions. Distinguish structural
variants from parameter values VectorBT can sweep. Preserve source attribution,
state why the edge might work and fail, list exclusions, and do not claim
profitability from community anecdotes.
```

## Optional future Gemini integration

If separately accepted, Quant Factory may add a small built-in analyzer using a
provider-neutral adapter and the same Candidate output contract.

A proportionate first implementation would:

1. accept pasted text or an allowed public URL;
2. retrieve only the minimum source content required;
3. treat source content as untrusted data;
4. call one configured analyst model;
5. require structured QF Candidate v1 output;
6. store the source reference and generated packet;
7. require owner review before any candidate implementation or run.

The provider is replaceable. Google Gemini direct may be attractive because
another RedstoneX project already uses a Google AI Studio direct provider on a
free tier, but Quant Factory should not copy that project's multi-agent routing,
fallback ladder, benchmarking framework, or unrelated model-policy machinery.

No provider choice is part of QF Candidate v1 itself.

## Import validation

A Candidate importer should validate structure, not decide whether the strategy
is profitable.

Examples of deterministic validation:

- supported schema version;
- required title and hypothesis;
- valid source URLs where present;
- no embedded executable code;
- intraday/session fields consistent with active mandate;
- bounded variable lists rather than open-ended optimization instructions;
- no duplicate variable IDs;
- high-importance questions visible;
- explicit overnight policy;
- valid variant identifiers;
- no broker/order/live-capital instructions;
- no automatic launch flag.

Validation errors should be plain-language and editable.

Examples:

- "Entry timing is still ambiguous."
- "Parameter `vwap_period` has no bounded allowed values."
- "This packet allows overnight holding, which conflicts with the current QF mandate."
- "Variant `retest_entry` refers to logic not defined in the candidate."

## What v1 deliberately does not contain

Do not put the following into the portable Candidate contract:

- Python code;
- VectorBT expressions;
- internal strategy registry IDs;
- database IDs;
- run IDs;
- local file paths;
- market-data manifest hashes;
- Bitwarden/credential references;
- broker account information;
- paper/live controls;
- capital allocation;
- full validation-engine configuration;
- protected-test identities;
- hundreds of optimized parameters.

These belong to implementation, evidence, or runtime layers.

## Relationship to Quant Factory implementation

QF Candidate v1 is the boundary between probabilistic research and deterministic
research.

It does **not** eliminate candidate-specific code.

For a new strategy family:

1. Candidate packet is reviewed and approved.
2. Codex (or another implementation assistant) creates the smallest deterministic
   strategy adapter that implements the approved logic.
3. Focused tests prove the implementation matches the packet.
4. Quant Factory binds approved data/execution assumptions.
5. VectorBT performs the bounded parameter sweep.
6. The existing screening/validation pipeline evaluates evidence.

As reusable archetypes accumulate, more future Candidate packets can map onto
existing logic and require only configuration rather than new code.

## Deferred design questions after v1 backend acceptance

The following should be resolved during a future intake milestone rather than
silently decided by implementation:

1. Exact minimum required fields for `ready_for_review`.
2. Whether YAML, JSON, or both are canonical on disk.
3. Whether one packet may contain multiple structural variants or whether each
   approved variant becomes its own immutable child candidate.
4. Exact field-level provenance representation.
5. How Candidate family identity and duplicate detection are represented.
6. Whether the dashboard can edit imported packets directly or creates a new
   revision on every material change.
7. How source snapshots/transcripts are referenced without copying copyrighted
   material unnecessarily.
8. Whether a built-in source analyzer is introduced at all and, if so, which
   provider is configured first.
9. Whether public-source retrieval is handled by the model provider, a small
   Quant Factory retriever, or an external research tool.
10. How approved Candidate packets map to immutable strategy specifications
    without creating a generic arbitrary-strategy DSL.

## Suggested acceptance criteria for a future intake milestone

A future implementation can be considered minimally useful when Terry can:

1. paste or upload a QF Candidate v1 packet;
2. read it as a normal research brief;
3. see source attribution, structural variants, parameter sweep dimensions,
   ambiguities, exclusions, and prior-work warnings;
4. edit/clarify the packet without raw-file manipulation;
5. receive deterministic validation errors;
6. explicitly approve a finalized candidate;
7. hand that approved candidate to the existing candidate-specific
   implementation path;
8. export the packet again for use with any external LLM;
9. optionally use one built-in analyzer that produces the exact same contract,
   without making that provider mandatory.

That is enough to make Candidate v1 useful while preserving Quant Factory's
single-user, reuse-first, deterministic-research architecture.
