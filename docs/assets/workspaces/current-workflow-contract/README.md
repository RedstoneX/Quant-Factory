# Current Quant Factory workspace contract

This directory contains the owner-approved interactive structure for the six
workflow surfaces that follow Dashboard:

- Candidates
- Results
- Factory runs
- Submit Strategies
- Compare Selected
- the external Paper Trading destination

## Authoritative reference

- `workspaces.html` — exact page composition, information hierarchy, controls,
  drill-down intent, and cross-page workflow for the six surfaces above.

The HTML source has SHA-256
`d87f311127c513cefb50e75472a49aeb27d3031ac76c84e26a9940b73b23264a`.

The file also contains an older Dashboard slide because it was created as one
interactive carousel. That slide is explicitly **not authoritative** and must
not be used, copied, restyled, or implemented. Dashboard is controlled only by
`docs/assets/dashboard/current-visual-contract/dashboard.html`.

## Implementation rule

For the six named workflow surfaces, preserve the reference's page structure,
regions, prioritization, controls, drill-downs, and navigation consequences.
Apply the modern visual language, component treatment, spacing, and shared
shell established by the accepted Dashboard contract. This is a translation
into the accepted Mantine/Dash component system, not a greenfield redesign and
not permission to omit panels or invent a different workflow.

Representative values demonstrate composition only. Production pages bind to
truthful persisted or operational state and use compact truthful empty,
unavailable, loading, and error states where necessary.
