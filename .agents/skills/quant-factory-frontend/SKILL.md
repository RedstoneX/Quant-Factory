---
name: quant-factory-frontend
description: Implement or review any Quant Factory operator-facing frontend, UI, UX, styling, interaction, or visual-conformance change. Use before editing dashboard pages or assets and before claiming frontend completion. Do not use for backend-only work.
---

# Quant Factory Frontend

Treat the rendered interface as a product contract, not as decoration around
working callbacks.

## Establish the contract

1. Read `AGENTS.md`, the current `docs/MILESTONES.md`, the current decision
   index, and only the decisions relevant to the requested surface.
2. Read
   `docs/assets/dashboard/current-visual-contract/README.md` and open the
   repository-owned interactive reference it identifies.
3. Name the exact surface, approved reference state, representative persisted
   state, viewport, data/state owner, and permitted change before editing.
4. Preserve Dash, Dash Core Components, Plotly, Dash AG Grid, VectorBT,
   persistence, lineage, state semantics, and authority boundaries; use
   Mantine as the default polished UI layer. Reuse data and behavior
   contracts. Presentation composition comes only from the current visual
   contract.

The approved reference controls visual language, composition, hierarchy,
density, spacing, affordances, and interaction intent. Product facts must still
come from real application state. If a reference fact cannot be supported,
show the truthful unavailable, empty, loading, failure, or inactive state in
the same design language; never fabricate data to make the page resemble the
reference.

Do not generate another creative direction, use Figma, consult an earlier
visual artifact, or let a generic design skill reinterpret an approved surface.
No competing visual reference may be added to the active tree.

## Implement in bounded slices

The first production slice is Dashboard only. Do not implement another surface
until the actual Dashboard render has passed the four gates and Terry has
explicitly approved continuing. Later work remains one coherent surface or
shared visual primitive at a time.

Build the approved composition as a clean Dash UI under `dashboard.ui`.
Working backend contracts may be retained. Do not replace working backend
contracts or create a second frontend.

Dash Mantine Components is the default production UI layer for the approved
shell and commodity components. The first real Dashboard implementation is its
integration proof; do not build a separate hand-crafted Dashboard first.
Combine Mantine with Dash Core Components for appropriate analytical controls,
Plotly and VectorBT for charts/evidence, and Dash AG Grid for dense sortable and
filterable records. Confirm visual fit, callback compatibility, and payload/load
cost while implementing the slice. If a demonstrated blocker appears, stop for
an owner decision before selecting a fallback. Do not begin a standalone React
frontend without a separate owner decision.

Preserve the approved information behavior: Dashboard exposes current factory
operations and survivors; Candidates defaults to sortable/filterable survivors;
one selected survivor opens exact Results; Compare Selected is secondary.
Every interactive-looking summary, chart mark, status, alert, row, link, or
button must perform its promised exact drill-down or action. Remove interactive
styling when no action exists.

After implementation and self-review, use `web-interface-audit` as the
secondary accessibility and interaction audit and resolve its blocking
findings before the independent adversary review. When a generic guideline
conflicts with the approved Quant Factory contract or trader workflow, report
the conflict and follow Tier 1 plus the approved contract.

## Prove the rendered result

For each implemented surface, follow
[references/visual-acceptance.md](references/visual-acceptance.md). Functional
tests, HTTP success, expected text, callback success, and clean console output
do not prove visual conformance. A material mismatch means the surface is
incomplete.

Before requesting merge or deployment, the local actual Dash render must pass
technical, control, and visual-conformance checks plus a separate read-only
Quant Factory adversary review. Resolve every material trader-workflow,
visual-contract, truthful-state, component-use, or affordance finding, then show
Terry the actual/reference pair. Only his explicit approval authorizes a
private interactive deployment. Do not claim comprehension or begin another
surface until Terry has used that deployed Dashboard unaided and accepted it.
