# Public safety and omissions

This package is deliberately limited to review-safe material.

## Explicitly omitted

- Private SPYM preview evidence, provenance, and all screenshots rendered from
  it.
- The exact approved HTML because its visible labels include private fixture
  identity and time. Its SHA-256 is retained in the source manifest.
- The private evidence-pack build script.
- Raw browser-validation JSON and the path-bearing browser script.
- R07 raw market data, generated artifacts, database, manifests, run IDs,
  filesystem paths, logs, container metadata, and metric records.
- Credentials, environment files, hostnames, IP addresses, private network
  details, account data, and infrastructure coordinates.
- VectorBT Pro or any other separately licensed source or package.
- Initial, intermediate, and final private-fixture screenshots.
- Production state, backups, deployment bundles, and secrets.

## Included with limits

- Sanitized aggregate R07 facts already verified and safe selected summary
  metrics.
- A textual patch for an unpushed local commit; it is not merged application
  state.
- Exact uncommitted drafts, clearly separated from canonical code.
- A deterministic synthetic generator. Its output is invented visual-review
  data and is not included.
- A sanitized HTML/JavaScript derivative for local synthetic reproduction. It
  is not the exact approved artifact or application code.
- A path-free summary of historical prototype browser observations, clearly
  separated from current application and R07 proof.
- Historical deployment facts without private coordinates.

No material in this package grants deployment, paper/live, credential, or
capital authority.
