# Runtime and validation evidence

This separates historical deployment records from current observation.

## Deployment record — verified record, not current-source proof

- Recorded deployed research revision:
  `79721a67f712c2b440aaeabcb57e7738f1c9fe08`.
- Deployment record verified on 2026-09-03.
- Recorded runtime: Python 3.12.14 and VectorBT Pro 2026.4.7.
- Current `main` pins Dash 4.3.0, Plotly 6.8.0, and dash-ag-grid 35.2.0. Those
  are source dependency requirements; their installed target versions were not
  directly verified. Python and VectorBT Pro versions above come from the
  deployment record.
- The record predates R07. R07 is not deployed and remains preserved outside
  production.
- A historical report records 807 collected tests, 805 passed, and 2 deliberate
  skips, but it spans revisions and is not current-revision proof.

## Current read-only observation — 2026-09-20

These are owner-requested sanitized summaries of a read-only health response
and local service/container inspection. Private coordinates and raw records are
omitted.

- Research health is currently healthy at the recorded deployed revision.
- No research containers were observed.
- A separate static prototype service is active.
- Container inspection was unavailable, so current container defaults and the
  complete installed-version set were not verified.

## Repository and local test evidence

- Current canonical `main` required GitHub checks passed on 2026-09-20. The
  required set contains no browser check.
- PR #65 passed all three required checks.
- A local Linux R07 JUnit report dated 2026-09-19 14:55:46 UTC records 631
  passes and 0 failures, but embeds no source revision. It therefore cannot
  independently bind that result to `31cf941`.
- Historical Linux browser evidence under Python 3.12.3 and pytest 9.1.1 is
  conflicting: one unbound report records 50 selected passes with 7 SPYM
  deselections, while evidence associated with revision `60686a…` records 9
  failures and 1 error in the same scope.
- Later focused 10/10 and Milestone 23D 1/1 rerun reports lack revision binding
  or current-target proof. There is no current-revision target browser proof.

## Claims not established

- No current-source target deployment.
- No current-revision licensed-target or browser acceptance.
- No operator acceptance.
- No qualified edge or profitability.
