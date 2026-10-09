# Rendered visual acceptance

Use this procedure only for an owner-authorized frontend implementation or
frontend review. It is a read-only proof procedure; it does not authorize a
deployment, Candidate run, research mutation, broker connection, or trading.

## Required evidence

For the first reconstruction slice, perform this procedure for Dashboard only
and stop for Terry's decision. Do not use Dashboard acceptance as authority to
implement the remaining surfaces.

1. Render the real Dash route with deterministic representative state at the
   approved desktop viewport. Use 1440 by 980 unless the visual-contract README
   records a more specific viewport for that surface. Use a read-only identified
   snapshot of canonical persisted inputs; do not create a Candidate, survivor,
   run, or owner-facing fake record to populate the reference.
2. Capture the actual page after fonts, callbacks, Plotly figures, and AG Grid
   content have settled. Preserve the exact route, revision, state identity,
   viewport, and capture time.
3. Place the approved reference and actual render side by side. Also create an
   overlay or image difference when the available tooling supports it.
4. Inspect at minimum: global shell, above-the-fold priority, grid and panel
   geometry, typography, spacing, color and contrast, information density,
   charts, tables, controls, affordances, selected/hover/focus states, empty or
   unavailable states, and primary drill-down behavior.
5. Record every material difference. Correct it or identify the exact truthful
   state constraint that requires a deliberate deviation.
6. Exercise safe read-only controls separately. Do not treat working controls
   as evidence that the page looks correct.
7. Run the secondary `web-interface-audit` and resolve blocking accessibility,
   semantics, keyboard, responsive, state, and affordance findings.
8. Give the approved reference, actual render, and representative-state identity
   to an independent read-only Quant Factory adversary. Resolve every material
   workflow, visual, truthfulness, component-use, and affordance finding.
9. Show the approved reference and actual render to Terry for the pre-deployment
   visual checkpoint. Only his explicit approval authorizes a private
   interactive deployment.
10. After that separately authorized deployment, Terry uses the Dashboard
   unaided. His hands-on acceptance closes comprehension. Do not begin another
   surface before this checkpoint.

The approved HTML file must have SHA-256
`d87f311127c513cefb50e75472a49aeb27d3031ac76c84e26a9940b73b23264a`
before it is used as a reference. A mismatch stops the comparison until the
owner approves a replacement contract and checksum.

## Gate vocabulary

- **Technical:** the application loads and the data/state contracts are true.
- **Controls:** intended safe interactions work with the selected identity.
- **Visual:** the actual render materially conforms to the approved contract.
- **Comprehension:** Terry can use and understand it without developer help.

Report each gate separately. Never summarize them as “all good.” If visual
evidence was not captured and inspected, the visual gate is **not run**. If the
reference and actual render materially disagree, the visual gate **fails** even
when all functional tests pass.
