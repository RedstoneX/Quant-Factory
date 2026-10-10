# Rendered visual acceptance

Use this procedure only for an owner-authorized frontend implementation or
frontend review. It is a read-only proof procedure; it does not authorize a
deployment, Candidate run, research mutation, broker connection, or trading.

## Gate A: visual shell

For the first implementation slice, perform only this procedure for Dashboard
and stop for Terry's decision:

1. Render the real Dash/Mantine shell at 1440 by 980 using only the exact
   reference's representative state. Mark the render as local visual proof; it
   is not operational truth and may not read persistence or be deployed.
2. Capture it after fonts and visible components settle. Preserve the revision,
   viewport, and capture time.
3. Place the approved reference and actual render side by side.
4. Inspect: global shell, above-the-fold priority, grid and panel
   geometry, typography, spacing, color and contrast, information density,
   chart proportions, table treatment, controls, and primary emphasis.
5. Correct every material difference. Backend behavior, callbacks, tests,
   accessibility audits, or scale evidence cannot excuse a visual mismatch.
6. Show Terry the actual/reference pair and stop. Do not wire state, continue to
   controls, request merge, deploy, or begin another surface.

## Gate B: truthful working Dashboard

Only after Terry explicitly approves Gate A:

1. Replace representative values with an identified read-only persisted-state
   projection. Never fabricate a Candidate, survivor, run, chart, or trade.
2. Exercise every included safe control and exact identity transition.
3. Capture the truthful actual page at 1440 by 980 and compare it with the same
   visual contract, allowing only necessary compact empty/stale/unavailable
   state differences.
4. Run the Dashboard as a persistent private service at the established
   tailnet URL with the external canonical database configured read-only.
5. Show Terry the URL, truthful render, and state identity for unaided use. A
   screenshot or temporary local process does not close this gate.
6. After Terry's walkthrough, run the secondary `web-interface-audit` and the
   independent read-only Quant Factory adversary before merge.

The approved HTML file must have SHA-256
`266336fb5d62caa844cae6c67d4ed36df63a14bc4de7ad72919375d9318e74c1`
before it is used as a reference. A mismatch stops the comparison until the
owner approves a replacement contract and checksum.

## Later workflow surfaces

For Candidates, Results, Factory runs, Submit Strategies, Compare Selected,
and the Paper Trading destination, verify
`docs/assets/workspaces/current-workflow-contract/workspaces.html` has SHA-256
`313b098fa43ca0e25e6c92dad55b2d508faca94765c3cd8fe9c7005837f71b31`.
Use the named surface in that file for exact regions, controls, hierarchy, and
workflow. Use the accepted Dashboard contract for the shared modern visual
language.

Implement one complete surface, connect truthful state, publish it at the
existing private application, and show Terry the working route. A screenshot or
new mockup is not the deliverable. Keep proof lean: targeted technical checks,
one exercise of each visible safe control, direct visual inspection, and the
required secondary review only after the owner walkthrough.

When `docs/MILESTONES.md` records an owner-authorized continuous completion
batch, the working route and lean proof remain required for every surface, but
the owner walkthrough occurs once after the entire named batch. Do not wait for
intermediate approval, repeat broad audits, or stop merely because one surface
has been published successfully.

## Gate vocabulary

- **Technical:** the application loads and the data/state contracts are true.
- **Controls:** intended safe interactions work with the selected identity.
- **Visual:** the actual render materially conforms to the approved contract.
- **Comprehension:** Terry can use and understand it without developer help.

Report each gate separately. Never summarize them as “all good.” If visual
evidence was not captured and inspected, the visual gate is **not run**. If the
reference and actual render materially disagree, the visual gate **fails** even
when all functional tests pass.
