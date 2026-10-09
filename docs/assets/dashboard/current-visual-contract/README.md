# Current Quant Factory visual contract

This directory contains the repository-owned visual contract approved by Terry
on October 8, 2026 after iterative trader-workflow review.

## Authoritative reference

- `quant-factory-reconciled-mockups.html` — authoritative interactive
  seven-surface reference and sole current visual target, in this order:
  Dashboard, Submit Strategies,
  Factory runs, Candidates, Results, Compare Selected, and Paper Trading.

The HTML source has SHA-256
`903554196439f3c7fa5cca4a48d8938fb7b9d212f5fae942a2bccc7ec34bb422`.

## How to use it

The reference controls visual language, composition, hierarchy, density,
spacing, affordances, and interaction intent. It does not authorize fabricated
runtime facts: the implementation must bind those surfaces to truthful
persisted and operational state.

The Dashboard reference is intentionally complete rather than summary-only. It
includes status summaries, Candidate universe, Latest finding, Factory now with
live operations, Top survivors, and Operational attention. Its representative
values demonstrate composition only; production renders must preserve the same
regions using truthful populated, empty, stale, inactive, failed, or unavailable
states.

For any frontend implementation, render the actual Dash surface at the same
desktop viewport and compare it directly with the matching reference surface.
Follow `.agents/skills/quant-factory-frontend/SKILL.md`.

No other mockup, preview, screenshot, page specification, CSS, browser test, or
deployed page is a visual or implementation target.
