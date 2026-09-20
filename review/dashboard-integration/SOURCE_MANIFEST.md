# Source manifest

All hashes are full SHA-256 values. Copied files are review inputs, not
canonical application state.

## Approved standalone prototype and sanitized reproduction

The exact approved HTML is deliberately omitted because it exposes the private
fixture identity and time. Its preserved source hash is
`c25d9a7de214800c3e04f700699b766efc71835bcdcc7a8f6910fc4b03dec770`.
The private evidence, provenance, screenshots, build script, raw browser JSON,
and path-bearing browser script are also omitted.

The exact approved CSS and JavaScript remain as source references. The original
JavaScript requests an omitted private file and is not used by the synthetic
reproduction. The sanitized HTML and JavaScript are review-only derivatives
with explicit synthetic labels and a synthetic instrument contract.

| Included file | Status | SHA-256 |
|---|---|---|
| `prototype/chart-first-private/staging-chart-first-preview.css` | Exact approved source reference | `2d93f8d97ee50e9eb519242efafe4f00e6e0098d7693b6e29ca6c6d87795d2b6` |
| `prototype/chart-first-private/staging-chart-first-preview.js` | Exact approved source reference; not used for reproduction | `b5ea3e9cfbb4c9ab4d74d85fae0e6bbc17db4b50922449fa6da5bdd631760d85` |
| `prototype/synthetic-review-preview.html` | Sanitized derivative | `88abb13581651f3dfd1817d3bb9957fd974dc8b65f2def101a70155108bac168` |
| `prototype/chart-first-private/synthetic-review-preview.js` | Sanitized derivative | `d7c1d16b6091c8dd163fdba5523b0a0ae742162650c5d328601f283d05b6cc37` |
| `prototype/chart-first-private/generate-synthetic-evidence.py` | New review-only generator | `3ad5501ef26018bd0d6f7e13e80badd1c249b6140256946eb9388acfd9bc3c16` |

No private-fixture screenshot is included. The single bounded recapture attempt
failed its safety assertion after the final label correction, so all generated
screenshots were omitted. Browser rendering of the final derivative is
unverified.

## Local R07 integration patch

- Commit: `31cf941e84d849f77d8fe4fdac617890bd408049`
- Exact base/parent: `44d85db1e0b26bf3701b3c9c621135666b5f354b`
- Predecessor repair: `f2c443afb970b9518147c5823de4e0ae03c6ebe1`
- State: local only, unpushed, unmerged, undeployed, and not operator-accepted
- Patch: `patches/0001-fix-integrate-R07-durable-evidence-rendering.patch`
- Patch SHA-256: `45fe63f48a36cf5fc1a2f25ee5dcc963660324422847382c84d77cd16f9e9987`

The patch includes application, test, and documentation changes. Canonical
files are referenced from `main`; they are not duplicated separately.

## Uncommitted standalone drafts

These are exact copies of untracked files. Both origin branches were at base
`4b3cd9d39a2e571d8e3eb3a14c14d3df100fb568`. They were not committed,
integrated, deployed, or proved against current `main`.

| Copied file | Origin branch and source-relative name | SHA-256 |
|---|---|---|
| `drafts/qf-m23-results-chart-component/dashboard/components/results_workspace.py` | `codex/m23-results-chart-component`: `dashboard/components/results_workspace.py` | `d62ff6690fb9af555a88b41388f14976f5e428643c696053dd811455d3daabef` |
| `drafts/qf-results-workspace-assets/dashboard/assets/zz-results-workspace.css` | `codex/results-workspace-assets`: `dashboard/assets/zz-results-workspace.css` | `09c8bc0f4ed4c69ff0cde42e9b1a45d69b68f6ef19af71c5fc15fee776749e17` |
| `drafts/qf-results-workspace-assets/dashboard/assets/zz-results-workspace.js` | `codex/results-workspace-assets`: `dashboard/assets/zz-results-workspace.js` | `8011239098568f07aee6eb9fce52985586d60c3731a494d7eef1ef7498e4a655` |
| `drafts/qf-results-workspace-assets/tests/test_results_workspace_assets.py` | `codex/results-workspace-assets`: `tests/test_results_workspace_assets.py` | `ba489c17bb122ce418bde18c659a9434f0871897520867f33e907eed9fdc9122` |

The Python draft and the CSS/JavaScript draft implement different component
contracts. The Python draft hardcodes dollar formatting for the price axis and
hover text (`results_workspace.py` lines 140 and 447), which is incorrect for
MES index-point prices.
