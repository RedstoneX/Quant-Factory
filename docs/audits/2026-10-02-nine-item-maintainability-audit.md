# Nine-item maintainability audit evidence

> **Status authority:** this is a supporting evidence report only. It cannot set
> project priority, phase, blocker, milestone status, or authorization.
> `docs/MILESTONES.md` alone governs current status and sequencing.

## Scope and interpretation

The measured revision is
`fea37c2243e10f0b935a6ae5231fdac5eeb3fb97`. Measurements cover Git-tracked
files at that revision. Environments, caches, generated files, untracked files,
protected evidence, network services, broker state, and paid-provider state are
excluded. This audit did not authorize research, trading, deployment, broad
cleanup, or automatic remediation.

The report separates four states:

- **proved at the measured revision** — direct measurement or a fault test
  closed the question;
- **defect found** — a concrete failure was reproduced;
- **fixed separately** — a narrow fix exists outside the measured revision and
  needs normal integration;
- **debt** — an identified gap remains, but this audit did not authorize a mass
  rewrite.

The exact positive-claim and governing-setting rows are preserved in
[`2026-10-02-completion-claims.tsv`](2026-10-02-completion-claims.tsv) and
[`2026-10-02-decision-source-registry.tsv`](2026-10-02-decision-source-registry.tsv).
The validated 20-component construction matrix and every cited pytest node ID
are preserved in
[`2026-10-02-component-construction-matrix.json`](2026-10-02-component-construction-matrix.json).
The structural guard owns the exact over-limit file, function, and broad-handler
identities in `config/structural-maintainability-baseline.json`; this report does
not duplicate those large lists.

| Frozen artifact | Data rows | SHA-256 |
| --- | ---: | --- |
| Completion claims | 30 | `11f6389a019d79bdcc793de86052a5a0090389141e3eae3dcb222589559c9f96` |
| Decision-source registry | 340 | `0d51c140d966973dc8a510419b59433f6c5d56db6bcdb26345dfcd60d9d82ed3` |
| Component construction matrix | 20 | `35cec8896046ab7435b9bb169551ffc3555fa9bc717582e0511fb41d9063a9bb` |

## Executive result

The project is not a repeat of the reference failure, but it is not debt-free.
It has enforceable architecture boundaries, explicit construction seams, strong
order/research idempotency, and mostly discriminated failure states. It also has
large-file/function debt, 52 runtime broad handlers with no syntactic re-raise,
11 unproved CLI save/record claims, many unsourced decision settings, one
reproduced gateway note idempotency defect, and retained provisioning scripts
without crash-convergence proof. Those debts are recorded rather than silently
converted into new scope.

| Finding | State at `fea37c2` | Disposition at report authoring |
| --- | --- | --- |
| Results lookup rendered an unproved `Created` status | Reproduced defect | Fixed in the preceding narrow branch commit; 9 focused tests pass |
| Stored Results identity could be replaced after lookup error | Reproduced defect | Fixed with the same narrow patch; transient error now preserves identity |
| Review mutation could survive artifact failure | Reproduced defect | Atomic fix and fault matrix are being reviewed separately; not counted fixed here |
| Browser-local settings claimed “saved” before storage acknowledgement | Truthfulness defect | Wording-only fix is being reviewed separately; not counted fixed here |
| Oversized files/functions and existing broad handlers | Measured debt | Ratchet safeguard committed separately at `f9cd6c7`; no mass rewrite authorized |
| Gateway note retry duplication and provisioning crash convergence | Reproduced/identified debt | Deferred by explicit scope; still open |
| Unverified CLI completion claims and unsupported decision settings | Measured debt | Inventoried; still open |
| Browser outbound-network proof | Insufficient evidence | Pending; no pass claimed |

## 1. File and function size

At the measured revision:

- 356 tracked Python files: 218 runtime and 138 test files;
- 44 Python files exceed 600 physical lines: 24 runtime and 20 tests;
- 45 tracked source-like files exceed 600 lines when CSS, JavaScript, shell,
  TOML, YAML, Dockerfile, and Makefile are included;
- 47 Python functions or methods exceed 150 AST lines: 35 runtime and 12 tests;
- the largest identities and every exact location/checksum are in the structural
  baseline, not inferred from impressions.

**Assessment:** debt. Existing files are grandfathered by exact identity and
content bounds; the guard is a no-growth ratchet, not permission for additional
large code. The structural safeguard adds a 600-line source limit and 150-line
function limit while remaining green on the frozen baseline. Its separate
commit `f9cd6c7bdd2dbe158a09b566e602db78af815599` passes 8 focused tests,
reports the exact 45/47/52 ratchets, reports zero constructor bypasses and
licensed-test doubles, and leaves the architecture guard at 0 runtime SCCs,
0 cyclic runtime edges, and 0 forbidden runtime directions.

## 2. Independent construction

This is a component-level result. It does not claim that every page, callback,
or helper has an independent constructor.

| Architecture component | Independent? | Representative validated node ID |
| --- | --- | --- |
| `licensed_engine` | Yes | `tests/test_ci_portable_imports.py::test_vectorbt_loader_reports_the_licensed_engine_boundary` |
| `strategies` | Yes | `tests/test_rsi_mean_reversion.py::test_common_interface_signal_result_matches_preserved_rsi_rules` |
| `market_data` | Yes | `tests/test_market_data_cache.py::test_compatible_cache_reused_offline` |
| `persistence` | Yes | `tests/test_persistence.py::test_fresh_database_initialization_schema_version_and_restart` |
| `backtesting` | Yes | `tests/test_experiment_runner.py::test_strategy_lookup_and_grid_execution` |
| `orchestration` | Yes | `tests/test_run_service.py::test_successful_launch_records_separate_prefect_identity` |
| `prefect_adapter` | Yes | `tests/test_prefect_spike.py::test_server_independent_persistence_adapter_writes_deterministic_result` |
| `research_entrypoints` | Yes | `tests/test_mes_orb_durable_screening.py::test_durable_pair_persists_ranked_evidence_and_opens_in_existing_results` |
| `research_intake` | Yes | `tests/test_qf_candidate_v1.py::test_candidate_yaml_parses_and_distinguishes_sweep_from_review_readiness` |
| `agent_gateway` | Yes | `tests/test_agent_gateway.py::test_context_prior_and_candidate_read_contracts` |
| `execution` | Yes | `tests/test_execution_contracts.py::test_intent_serializes_to_json_without_float_or_sdk_values` |
| `dashboard_public` | Facade | `tests/test_dashboard_startup.py::test_dashboard_starts_without_loading_or_running_legacy_research` |
| `dashboard_composition` | No, intentional root | `tests/test_dashboard.py::test_dash_route_callback_endpoint_keeps_workflow_pages_separate` |
| `dashboard_pages` | Yes | `tests/test_dashboard_component_boundaries.py::test_backtest_results_page_uses_an_explicit_renderer_contract` |
| `dashboard_callbacks` | Yes | `tests/test_dashboard_component_boundaries.py::test_results_callbacks_construct_with_an_independent_view_contract` |
| `dashboard_components` | Yes | `tests/test_trade_explorer.py::test_trade_rows_normalize_vectorbt_readable_fields_without_fabrication` |
| `dashboard_models` | Yes | `tests/test_results_model.py::test_aggregation_uses_epoch_left_ohlc_rules_and_does_not_fill_gaps` |
| `dashboard_support` | Yes | `tests/test_dashboard_responsive_shell.py::test_responsive_shell_mounts_one_location_and_accessible_drawer_controls` |
| `deployment` | Yes | `tests/test_deployment_packaging.py::test_entrypoint_fails_closed_when_required_mount_configuration_is_missing` |
| `tools` | Yes | `tests/test_architecture_boundaries.py::test_guard_rejects_then_accepts_a_temporary_forbidden_dependency` |

**Result:** 18 of 20 components own behavior that can be independently
constructed or exercised. The two exceptions are deliberate: one composition
root and one behavior-free public facade.

## 3. Broad exception handlers

The AST definition was: bare `except`, `Exception`, `BaseException`, an
attribute ending in either name, or a tuple containing one. “Non-reraising”
means the handler subtree contains no `raise`; a later fail-closed conversion is
still counted.

| Scope | Broad handlers | No syntactic re-raise | Contains re-raise |
| --- | ---: | ---: | ---: |
| Runtime | 73 | 52 | 21 |
| Tests | 36 | 9 | 27 |
| Total | 109 | 61 | 48 |

Of the 52 runtime non-reraising handlers, 42 are on money, integrity, or
irreversible/retry-sensitive paths: 37 current and 5 historical. “Non-reraising”
does not mean “silent”: several create explicit fail-closed state, transfer an
exception across a thread boundary, or call a helper that raises. The baseline
records exact locations and classifications so the count cannot grow unnoticed.

**Assessment:** measured debt, not a finding that all 52 handlers are defective.
No broad rewrite was authorized.

## 4. Positive completion claims

The source scan found 30 stable source claims using “saved”, “recorded”, or
equivalent positive completion language. No email “sent” or alert-dispatch claim
exists in the measured production source.

- 13 are CLI save/record claims;
- 11 of those 13 lack a main-boundary readback or injected persistence-failure
  proof;
- RSI robustness performs write/read validation before its positive claims;
- durable draft, Candidate, Setup, and review paths have successful persistence
  evidence, but several lacked write/commit fault injection at the measured
  revision;
- the browser-local settings message claimed “saved” without a local-storage
  acknowledgement;
- a direct fault test proved a real review defect: the database review mutation
  could commit before artifact write/registration failed, leaving partial state.

Every claim, its mechanism, current evidence, missing fault, and smallest proof
is in the completion-claim TSV. The settings wording and atomic review boundary
have narrow fixes prepared separately; they are **not** evidence that the
measured revision was already correct. The remaining unverified CLI claims are
debt.

## 5. Real construction versus test substitution

Pytest collected 1,801 cases. The AST inventory contained 1,207 test functions
across 138 files.

- a deliberately broad “assisted test” upper bound found 236 test definitions,
  418 collected instances, and 47 files;
- exact constructor bypasses using `__new__`, `object.__new__`, or equivalent
  construction avoidance: **0**;
- constructor/factory substitution: 5 tests in 4 files; all are legitimate
  boundary substitutions with real-construction counterparts;
- core-calculation substitution: 15 tests in 7 files; 14 have a real-engine or
  lower-level counterpart;
- one gap remains: the Donchian baseline wrapper does not have an exact
  real-engine wrapper counterpart.

**Assessment:** no constructor-bypass pattern comparable to the reference
failure. The Donchian wrapper counterpart is bounded debt; “uses a fake” alone
is not counted as a defect when the test is explicitly proving an adapter or
failure boundary.

## 6. Network reachability from tests

A compiled `connect`/`connect64` interposer allowed loopback and blocked outbound
IPv4 and IPv6 connections. Its SHA-256 was
`687789a5aa1f4cf5b2faf6528e4f5935373e8605303fa75b31e7c5338b09a57f`.
With the blocker preloaded, the full non-browser test set completed:

- 1,727 passed;
- 0 failed, 0 errors, 0 skipped in the JUnit report;
- 405.866 seconds;
- 3 unrelated pytest temporary-directory cleanup warnings;
- the run included 17 licensed-VectorBT, 2 external-Prefect, and 1
  controlled-market-data marked cases.

This proves those non-browser tests did not require an outbound socket. A
browser attempt was interrupted and produced no terminal report; browser
network isolation is therefore **pending**, not passed. A repository-owned
blocker/proof tool and CI invocation are being prepared separately.

## 7. Decision-governing numbers

The frozen Python setting universe contains 340 rows in 60 files: module/class
settings, numeric function defaults, and numeric keyword overrides. A broader
AST candidate scan found 608 numeric decision candidates in 108 Python files.
The 340 stable settings are classified without treating approval or a prior
backtest as a source:

| Source class | Rows |
| --- | ---: |
| Derived internal contract | 15 |
| Externally sourced MES contract | 10 |
| Historical/fixture | 40 |
| Mathematical invariant | 10 |
| Operational policy | 76 |
| Presentation/layout | 38 |
| Provisional policy | 65 |
| Published Gao/SPYM source | 1 |
| Schema invariant | 26 |
| Unsupported | 59 |
| **Total** | **340** |

Exactly 200 assessments begin with `unsupported:` and 213 rows explicitly say
that no defensible source was found. The MES contract/fee rows cite CME,
IBKR, and NFA evidence and retain the revalidation-before-live warning. The one
Gao/SPYM row is only a source-derived input cardinality, not profitability
evidence. Provisional evidence thresholds remain labeled unsupported.

This is “every” row in the stated 340-setting universe, not every incidental
numeric literal, date fragment, status code, array index, fixture datum, shell
constant, or YAML value. That boundary is intentional and prevents an AST
heuristic from being misrepresented as semantic omniscience. Operational shell,
Compose, and CI timeouts found during manual review are summarized as unsourced
operational policy; they do not become justified merely because they are
documented.

**Assessment:** substantial source debt. The smallest enforceable follow-up is a
registry-backed guard for new semantic settings, not a blanket ban on literals.

## 8. Non-repeat-safe effects

Seven effect boundaries were inspected:

1. broker order POST;
2. Prefect/research invocation;
3. gateway `candidate.submit`;
4. gateway `research.note.add`;
5. gateway `run.request`;
6. retained OneCLI resource provisioning;
7. retained agent-gateway host provisioning.

Four current operations have retry/idempotency proof: broker order submission,
durable research launch, Candidate submission, and run request through the
durable launch boundary. The broker path writes a durable claim before one POST,
uses a deterministic client order ID, records ambiguous outcome as
`SUBMISSION_UNKNOWN`, and never automatically reposts. Research launch uses a
durable key plus compare-and-set invocation marker and likewise stops at an
unknown outcome.

A fault injected after gateway note insertion but before audit insertion proved
one defect: retrying the same request produced two notes and one audit row. The
note table has no request identity. That gateway change was outside the current
no-gateway implementation scope and remains debt. The two retained provisioning
workflows lack hard-kill/crash-convergence proof; they are also debt. No payment
or email-sending boundary was found.

## 9. “Unknown” versus “no”

Eleven owner/safety/progression failure families were inspected:

- 8 use an explicit discriminated state: reconciliation, broker submission,
  research launch, validation evidence, gateway responses, system health, Git
  lineage, and compare-query parsing;
- 2 collapsed lookup error into absence/false in Results run lookup and stored
  selection validity;
- 1 review-load path maps a read error to `UNREVIEWED`, but also shows a warning
  and independently disables save, so it is a visible fail-closed ambiguity
  rather than a silent promotion.

The Results defect was reproduced: an injected `RunServiceError` became `None`,
and the UI rendered `Run status: Created`. A narrow fix now renders
`Run status: Unavailable` for missing/failed lookup and preserves the selected
identity on transient lookup error. Focused proof is 9 passing tests in
`tests/test_results_deep_link.py`; the production callback remains at its
2,000-line ratchet. That fix is separate from the measured revision.

## Reproduction and integrity commands

Run from a clean checkout of the measured revision unless a command explicitly
references a later guard:

```bash
git rev-parse HEAD
git ls-files '*.py' | wc -l
python3 tools/check_structural_maintainability.py --base-ref fea37c2243e10f0b935a6ae5231fdac5eeb3fb97
python3 -m pytest -q tests/test_structural_maintainability.py
python3 -m pytest --collect-only -q tests
wc -l docs/audits/2026-10-02-completion-claims.tsv docs/audits/2026-10-02-decision-source-registry.tsv
awk -F '\t' 'NF != 8 { print FNR ":" NF }' docs/audits/2026-10-02-completion-claims.tsv docs/audits/2026-10-02-decision-source-registry.tsv
sha256sum docs/audits/2026-10-02-completion-claims.tsv docs/audits/2026-10-02-decision-source-registry.tsv
python3 -m json.tool docs/audits/2026-10-02-component-construction-matrix.json >/dev/null
sha256sum docs/audits/2026-10-02-component-construction-matrix.json
```

Network proof procedure:

```bash
cc -shared -fPIC -ldl -o /tmp/qf-audit-block-outbound.so tools/block_outbound_connect.c
sha256sum /tmp/qf-audit-block-outbound.so
LD_PRELOAD=/tmp/qf-audit-block-outbound.so \
  python3 -m pytest -q tests --ignore=tests/browser \
  --junitxml=/tmp/qf-audit-nonbrowser.xml
```

The inventory row counts include one header each: 31 lines for 30 completion
claims and 341 lines for 340 governing settings. Stable IDs/locations must be
unique. The decision registry's `(path, kind, value)` projection must remain an
exact ordered projection of the frozen numeric-setting inventory used for this
audit.

## Explicit exclusions and stop condition

- No claim is made that all broad handlers are wrong or that every test double
  is a bypass.
- No browser network-blocked pass is claimed.
- No strategy threshold is justified by owner approval or a prior backtest.
- No gateway, provisioning, CLI persistence, architecture, framework, or mass
  decomposition project is authorized by this report.
- Fixed-separately items do not change the truth of the measured-revision
  findings until integrated and retested normally.
- This evidence report stops at answering the nine audit questions and naming
  the smallest safeguards; `docs/MILESTONES.md` remains the only status and
  sequencing authority.
