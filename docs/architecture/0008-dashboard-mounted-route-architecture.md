# ADR 0008: Mounted-route Dash dashboard architecture

- **Status:** Accepted
- **Date:** 2026-07-19
- **Scope:** Research dashboard application architecture, routing lifecycle, browser acceptance, and Milestone 23 dashboard refactor baseline
- **Supersedes:** ADR 0002 where it is less specific about routing structure; Decisions 211, 213, and 217 where they imply the current dashboard shell/routing implementation has already passed browser acceptance or that dynamic `page-content.children` routing is acceptable
- **Supplements:** ADR 0003 dashboard-first product direction and ADR 0007 post-Milestone-23 roadmap

## Context

Quant Factory's dashboard is the primary operator interface. Milestone 23 cannot pass until a non-programming operator can complete the equity research workflow through the browser without Python, terminal output, raw JSON/CSV, or SQLite inspection.

Recent Milestone 23 dashboard work exposed a structural problem in the Dash app. Dynamic replacement of `page-content.children` can unmount page-specific components while their callbacks remain registered in Dash's dependency graph. Browser refresh and hydration behavior can also diverge from callback-level tests when routing depends on replacing the active content tree. These failures are product-critical because navigation, direct deep links, refresh, selected states, and page identity must remain stable in the browser, not only in helper functions or server-side callback tests.

The project therefore needs a permanent dashboard architecture baseline before further dashboard feature implementation.

## Decision

### 1. Keep Plotly Dash and modularize the application

Quant Factory remains a Plotly Dash application. The dashboard must be modularized around clear page, routing, callback, service, adapter, and reusable-component boundaries rather than allowing one large file to accumulate unrelated layout and callback behavior indefinitely.

Modularization must preserve existing backend service, persistence, evidence, validation, orchestration, adapter, and accepted workflow behavior. It is an application-structure refactor, not a research-logic rewrite.

### 2. Use one persistent `dcc.Location`

The app has exactly one persistent `dcc.Location` component for browser location state. `dcc.Location.pathname` is the single route source of truth. No page-specific callback may write to `dcc.Location`, redirect, replace the active route, or control navigation without an explicit user action and a separately accepted routing design.

For Dash versions where URL changes are handled by a different callback from the component that owns `dcc.Location`, the `dcc.Location` configuration must follow the supported Dash lifecycle for that pattern.

### 3. Mount a permanent application shell

The dashboard shell is mounted once. It contains:

- the persistent `dcc.Location`;
- the persistent brand/home link;
- the persistent sidebar/navigation tree;
- the persistent main content area;
- the permanent route containers.

The sidebar/navigation tree must not be rebuilt during ordinary route changes.

### 4. Mount route containers once

Every registered route has one real, permanently mounted route container. Each route container owns the actual page components required by that page's callbacks, including controls, stores, selectors, buttons, and output regions.

Unknown-route handling uses a permanently mounted Page Not Found container. Unknown routes render Page Not Found without redirecting.

The dashboard must not use hidden compatibility text, invisible markers, legacy aliases, fake placeholder components, or test-only presentation behavior to satisfy callback or acceptance tests.

### 5. Route by pathname-driven visibility

Navigation changes update only:

- route-container visibility;
- active navigation styling;
- other explicitly route-derived presentation state that does not replace registered page components.

Route changes must not dynamically replace `page-content.children` as the active routing mechanism.

### 6. Keep page-owned callbacks within page boundaries

Page-specific callbacks own only their page's controls, stores, and outputs. They must not write the URL, rebuild navigation, or render another route. Expensive or mutating callbacks on inactive mounted pages must be gated so they do not launch runs, reproduce runs, cancel runs, recover stale runs, save reviews, compare runs, or otherwise mutate state without the route and user action that make the operation intentional.

Passive display callbacks may refresh mounted page content when that behavior is necessary to keep the UI consistent, but they must remain fail-closed and must not cause route changes.

### 7. Reuse components

Shared page headings, route containers, navigation links, metric cards, detail sections, charts, empty states, and action panels should become reusable components as the app is modularized. Reuse must reduce complexity and preserve trader-facing language. It must not introduce a competing dashboard framework or duplicate service logic in the UI layer.

### 8. Browser lifecycle acceptance is mandatory

Dashboard acceptance requires browser-lifecycle proof, not only Python unit tests or Dash callback helper tests. For routing or page-shell changes, acceptance must cover:

- direct deep link in a new browser tab;
- manual refresh on every registered route;
- back/forward navigation;
- sidebar navigation;
- brand/home link behavior;
- unknown-route rendering;
- selected/active navigation state;
- route identity after page-local callbacks mount;
- absence of unexpected client-side route changes;
- absence of Dash renderer missing-component errors.

Registered Dash callback or endpoint tests remain required, but they are supporting evidence. They do not replace manual browser acceptance.

## Consequences

- Milestone 23 is re-baselined around a controlled dashboard architecture refactor before additional dashboard feature work.
- Previously claimed browser acceptance for the dashboard shell/routing is not a current Milestone 23 pass condition.
- Future dashboard feature implementation must start from the mounted-route architecture and modular boundaries in this ADR.
- The refactor must preserve existing services, persistence, evidence, validation, orchestration, adapters, and accepted workflow behavior.
- Dynamic `page-content.children` routing is prohibited as the active routing mechanism.
- Browser diagnostics are acceptable during investigation when gated and bounded, but diagnostics are not acceptance by themselves.

For the approved Milestone 23C direction (Decision 273), Dash AG Grid is the
selected grid component and Dash Bootstrap Components is the selected source
for responsive layout and controls. These choices remain within Plotly Dash;
they do not authorize a framework rewrite. A concise page specification or
mockup must be approved before broad implementation.

## Acceptance criteria

The ADR 0008 dashboard refactor is accepted only when:

- all registered callback `Input`, `State`, and `Output` component IDs exist in the full mounted layout;
- no callback outputs `url.pathname`;
- no routing callback outputs `page-content.children`;
- exactly one route container is visible for each known pathname;
- the Page Not Found container is visible for unknown pathnames;
- navigation active state matches the pathname;
- direct deep links and manual refresh preserve the requested route in a browser;
- page-local callback initialization does not change the route;
- focused and full relevant dashboard tests pass;
- manual browser acceptance passes and is recorded before Milestone 23 can close.

## Non-goals

This ADR does not authorize:

- Dash Pages migration;
- framework replacement;
- paper trading;
- live trading;
- broker integration;
- strategy discovery;
- validation or evidence logic rewrites;
- persistence schema changes unrelated to the dashboard shell;
- Milestone 24 work.
