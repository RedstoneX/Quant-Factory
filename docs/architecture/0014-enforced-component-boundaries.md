# ADR 0014: Enforced Component Boundaries

- **Status:** Accepted
- **Date:** 2026-10-01
- **Authority:** Decision 319

## Context

At canonical revision `fe7564eac1f5838dd35ec0acd85fa943aa5a063e`, a
reproducible AST measurement found three runtime strongly connected components,
90 runtime edges inside those cycles, and 21 forbidden runtime dependency
directions. The cycles joined validation to persistence, dashboard pages and
callbacks to the application composition root, and the candidate runtime to
its Prefect adapter. File length was not the cause or the remediation target.

## Decision

Quant Factory uses the one-way component rules in
`config/architecture.json`. `tools/check_architecture.py` enforces them in CI,
separates runtime from `TYPE_CHECKING` imports, rejects new or renamed
violations, and requires the exact violation baseline to stay current and only
shrink. The accepted direction is:

| Owner | Owns | Explicit boundary | May depend on | Must not depend on |
|---|---|---|---|---|
| Strategies | Signal definitions and parameter governance | Strategy inputs and signal results | Licensed engine where required | Persistence, orchestration, dashboard |
| Market data | Provider access, cache and data audit | Audited market frames and provenance inputs | Strategies and licensed engine | Persistence orchestration or UI |
| Persistence | SQLite transactions, repositories, durable records and artifact contracts | Record/value objects and storage operations | Stable strategy identities | Backtesting, validation, orchestration, Prefect or dashboard behavior |
| Backtesting and validation | Experiments, gates and evidence coordination | Experiment results, validation results and the `ValidationPersistence` protocol | Market data, strategies, licensed engine and persistence contracts | Orchestration, Prefect or dashboard |
| Orchestration | Durable claims and candidate/fixture sequencing | Injected pipeline and fixture launcher contracts | Backtesting, market data, persistence and strategies | Prefect implementation details or dashboard composition |
| Prefect adapter | External scheduling and flow entry points | Implements orchestration launcher contracts | Orchestration and lower-level research components | Ownership of core candidate behavior |
| Dashboard components/pages/callbacks | Operator presentation and interaction units | Explicit renderer and `ResultsViewServices` collaborators | Stable models and lower-level services allowed by policy | Back-imports to `dashboard.application` |
| Dashboard composition | Construction and wiring of the one private UI | Injects page renderers, callback collaborators and runtime adapters | Dashboard units and lower-level services | Ownership of domain or persistence semantics |
| Deployment and tools | Outermost operational entry points and checks | Process/configuration inputs and observable operational results | Inward components allowed by policy | New domain authority |

State remains with its owning component: persistence owns durable database and
artifact state; orchestration owns durable launch/claim transitions through
persistence; dashboard session state remains in the established dashboard
stores; Prefect owns only adapter scheduling state. No compatibility bridge or
global mutation may transfer ownership across these boundaries.

Independent construction is part of the boundary definition. The candidate
runtime accepts a pipeline launcher, the fixture service accepts a fixture
launcher, validation evidence coordination accepts `ValidationPersistence`,
and Results callbacks/pages accept explicit presentation collaborators. Their
contract tests construct and exercise those units without constructing the
whole application or importing the outer adapter/composition module.

## Enforcement and secondary size backstop

The architecture guard runs before dependency installation in portable CI.
Its accepted baseline is empty: new runtime SCCs and forbidden directions fail.
The same policy contains a secondary 1,000-physical-line growth backstop. Eight
already-large modules are recorded at their current exact size; they may shrink
but may not grow, the recorded limits may not increase, and no new exception
may be added through an ordinary PR. This is only accumulation protection. It
does not require a file split, prove component quality, or replace the
independent-construction test.

## Result and compatibility

At completion the graph contains zero runtime SCCs, zero cyclic runtime edges,
and zero forbidden runtime directions. Routes, component IDs, database schema,
deployment behavior, evidence/provenance rules, and trading/research semantics
were intentionally preserved. This decision creates no strategy, execution,
broker, paper/live, credential, protected-data, or capital authority.
