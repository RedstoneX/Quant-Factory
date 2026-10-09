---
name: web-interface-audit
description: Audit an implemented Quant Factory web surface for accessibility, interaction clarity, and resilient interface behavior after it has been built from the approved visual contract. Use only as a secondary review; do not use it to generate or reinterpret the product design.
---

# Web Interface Audit

Review the real rendered surface and the code that produces it. This audit is
secondary to `AGENTS.md`, the current visual contract, and
`quant-factory-frontend`; it cannot replace visual comparison or owner
acceptance.

Check only material issues:

- controls are semantic, keyboard reachable, visibly focused, and accurately
  labelled;
- links, buttons, filters, selections, drawers, tabs, grids, and chart
  drill-downs look interactive only when they work;
- loading, empty, unavailable, failed, selected, disabled, and stale states are
  distinguishable without relying on colour alone;
- focus, selection, filter, and exact Candidate/run identity survive the
  intended interaction;
- dense grids remain scannable and expose the same action by keyboard;
- responsive behavior preserves the primary task without hiding required
  evidence; and
- motion, tooltips, icons, and progressive disclosure improve comprehension
  rather than decorating the page.

When current external guidance is needed and network use is authorized, consult
the MIT-licensed Vercel Web Interface Guidelines at
`https://github.com/vercel-labs/web-interface-guidelines`. Do not copy its
skill wrapper into this repository, make it a source of product direction, or
let generic advice override the Quant Factory contract.

Return concise findings tied to the exact surface and observable behavior.
Classify each as blocking or non-blocking. Do not redesign the surface, edit
files, or claim that this audit closes the visual or comprehension gate unless
the task separately authorizes those actions.
