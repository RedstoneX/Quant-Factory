# ADR 0011: Durable research-launch claims

- **Status:** PROPOSED / NOT ACCEPTED / NOT AUTHORIZED FOR IMPLEMENTATION
- **Date proposed:** 2026-09-18
- **Decision owner:** Terry, the Quant Factory project owner
- **Scope if accepted:** Milestone 23 research-fixture submission identity,
  persistence, orchestration handoff, recovery and dashboard observation
- **Would supplement:** [ADR 0004](0004-adopt-before-build.md),
  [ADR 0007](0007-portable-deployment-and-alpaca-first-roadmap.md) and
  [ADR 0008](0008-dashboard-mounted-route-architecture.md)
- **Implementation status:** None. This proposal changes no code, schema,
  runtime, deployment or accepted authority.

> **Proposal boundary:** Only Terry can accept, revise or reject this
> architecture. A commit, pull request, review or merge of this document does
> not accept it and does not authorize implementation. Decision 277 accepts the
> current dashboard/operator experience; it does not authorize the persistence
> and orchestration redesign described here.

## Context

The accepted
[dashboard direction](../QUANT_FACTORY_DASHBOARD_UI_DIRECTION.md#run-test-researchrun-test)
requires the Run test page to launch an approved saved configuration once,
show **Starting test...** while submission is unresolved, preserve the same
run identity across refresh, distinguish an unknown submission outcome from
run status and avoid a duplicate retry. The same specification explicitly
excludes backend, persistence and orchestration redesign. The required
server-side behavior therefore has no accepted implementation authority yet.

At public repository revision
`f3b15d65948938dbcbdba854575e6c57f52c062e`, the verified implementation has
these relevant properties:

- `FixtureRunService` validates a configuration and checks for an existing run
  before calling the fixture launcher, but it does not atomically claim a
  submission;
- the Prefect fixture creates the Quant Factory run after its Prefect flow-run
  identity exists;
- a repeated run identity is rejected rather than treated as a replay of one
  durable request;
- the dashboard callback waits synchronously for the launcher and has no
  persisted submission state; and
- the research deployment runs Prefect in the dashboard request process. It
  has a Prefect server but no research worker or deployment execution service.

This leaves a crash and concurrency window between validation and durable run
creation. It also prevents the browser from knowing whether an interrupted
submission created work elsewhere. Treating that ambiguity as an ordinary
Failed run or automatically retrying it could duplicate work or misstate what
happened.

The paper-order journal is not a suitable shortcut. It belongs to a separate
execution and security domain and carries broker-order, account and venue
semantics. Research launch identity needs a research-specific record. Paper
journal algorithms and tests may inform adversarial review, but the paper
journal must not be imported, shared or repurposed.

## Proposed decision

If Terry accepts this option, Quant Factory will add a bounded, research-only
durable submission claim in front of the existing in-request Prefect fixture
invocation. It will not add a worker, background thread, scheduler, broker
connection or production deployment change.

The guarantee is deliberately precise:

- one idempotency key identifies exactly one Quant Factory research run and
  one launch request;
- Quant Factory initiates the existing launcher at most once for that claim;
- an acknowledged Prefect identity is reconciled to the same Quant Factory
  run; and
- when the external outcome cannot be proved, the system records
  **submission unknown**, disables another launch and requires reconciliation.

This is not a claim that arbitrary external execution can be made
mathematically exactly once across every process or network failure. The
unknown state is the explicit fail-closed boundary.

### 1. Authority remains separated

Quant Factory remains authoritative for:

- the immutable saved configuration;
- the idempotency key and canonical launch request;
- the Quant Factory run identity;
- submission state and operator events;
- research results, evidence, lineage and human review; and
- whether another submission is safe.

Prefect remains authoritative for:

- the technical flow-run identity and state;
- execution inside one acknowledged flow;
- technical retries, cancellation and logs; and
- the technical failure or crash of that flow.

Submission state is not run status. In particular,
`SUBMISSION_UNKNOWN` must not be added to `RunStatus`, rendered as a normal
orchestration status or interpreted as evidence failure.

### 2. Add a research-specific schema-version-5 submission record

The proposed additive table is `research_run_submissions`:

| Field | Contract |
|---|---|
| `idempotency_key` | Opaque, bounded text primary key prepared before the server mutation |
| `run_id` | Unique foreign key to exactly one `experiment_runs` row |
| `configuration_id` | Foreign key to the immutable saved configuration |
| `canonical_request_json` | Secret-free canonical request document |
| `request_fingerprint` | SHA-256 of the canonical request document |
| `state` | One of the submission states below |
| `dispatcher_instance_id` | Ephemeral identity of the in-request service instance that began invocation |
| `prefect_flow_run_id` | Nullable unique technical Prefect identity |
| `prefect_api_url` | Nullable, non-secret technical reference |
| `claimed_at` | Durable claim time |
| `invocation_started_at` | Time the write-ahead invocation marker was committed |
| `acknowledged_at` | Time the Prefect identity was durably bound |
| `unknown_at` | Time ambiguity was recorded |
| `updated_at` | Latest submission-state update time |
| `error_summary` | Nullable, sanitized operator-safe failure summary |

The canonical request contains only inputs that define the meaning of this
launch, including a protocol version, configuration identity, fixture stage
and accepted launch policy. It contains no credentials, private coordinates,
raw market data, results or arbitrary browser text.

The submission state machine is:

```text
CLAIMED -> INVOKING -> ACKNOWLEDGED
                    \-> SUBMISSION_UNKNOWN
CLAIMED ------------> FAILED_BEFORE_SUBMISSION
SUBMISSION_UNKNOWN --> ACKNOWLEDGED       # reconciliation proved one flow
SUBMISSION_UNKNOWN --> ABANDONED          # explicit evidenced resolution
```

`ACKNOWLEDGED`, `FAILED_BEFORE_SUBMISSION` and `ABANDONED` are terminal for
the submission claim. The associated experiment run continues through its
existing Created, Running and terminal run-status lifecycle where applicable.
No automatic transition from `SUBMISSION_UNKNOWN` to `INVOKING` is allowed.

### 3. Claim the run atomically before invocation

The claim operation uses a short SQLite `BEGIN IMMEDIATE` transaction. Inside
that one transaction it will:

1. validate that the saved configuration exists, is immutable and is
   launchable as an approved infrastructure fixture;
2. canonicalize and fingerprint the request;
3. derive or allocate the stable Quant Factory run identity;
4. create the experiment run in `CREATED` state;
5. append its initial `run_created` operator event; and
6. insert the `CLAIMED` submission row.

If any step fails, the whole transaction rolls back. The transaction remains
short and performs no Prefect, network, market-data or licensed-engine work.

SQLite write contention will be bounded explicitly. This proposal does not
authorize WAL mode; changing SQLite journal mode requires separate target
filesystem evidence.

### 4. Make replay and conflict behavior deterministic

The browser prepares an opaque launch key before enabling the Run test button.
An explicit click submits that prepared key. A lost response, refresh or
duplicate callback therefore reuses the same key rather than creating a new
intent.

The server applies these rules:

- same key plus the same canonical request returns the existing submission and
  run without another mutation or invocation;
- same key plus a different configuration or request fingerprint fails with a
  typed conflict and creates nothing;
- a concurrent claim loser reads and returns the committed winner only when
  the complete request identity matches; and
- a new deliberate test after a terminal result uses a new key and a distinct
  run, preserving any required parent/reproduction lineage.

The key is an idempotency identity, not an authentication credential. It must
be length- and format-validated and must not contain a secret.

### 5. Commit the invocation marker before calling Prefect

The service uses an atomic compare-and-set from `CLAIMED` to `INVOKING` and
records its injected per-process dispatcher identity before it calls the
existing fixture launcher.

Only the compare-and-set winner may invoke. A concurrent callback or replay
returns the existing submission snapshot. If preparation fails before the
external call is possible, the service may record
`FAILED_BEFORE_SUBMISSION` and fail the Created run with a sanitized reason.

Once `INVOKING` is committed, a generic exception cannot prove that no Prefect
flow was created. Unless the database already proves acknowledgement or a
terminal run, the service records `SUBMISSION_UNKNOWN`. It does not invoke the
launcher again.

### 6. Bind the Prefect identity inside the flow

The idempotency key, Quant Factory run ID and configuration ID are passed into
the existing fixture flow. Its first Quant Factory database operation will
atomically:

1. load the submission by idempotency key;
2. verify the request, run, configuration, strategy and fixture stage;
3. bind exactly one Prefect flow-run ID;
4. move the submission to `ACKNOWLEDGED` or reconcile Unknown to
   Acknowledged; and
5. move the run from Created to Running with its existing `run_started`
   operator event.

An exact repeated binding is a no-op. A different run, configuration,
fingerprint or Prefect identity fails closed and records a sanitized service
integrity event. The current behavior that silently returns any existing run
without binding or verifying the Prefect identity must not remain in this
path.

### 7. Preserve the following crash-window behavior

| Crash or loss window | Required result |
|---|---|
| Before claim commit | No submission, run or event exists |
| During claim transaction | Complete rollback |
| After `CLAIMED`, before `INVOKING` | The same explicit intent may safely resume |
| After `INVOKING`, before Prefect binding | `SUBMISSION_UNKNOWN`; no automatic reinvocation |
| After Prefect binding, before callback response | Reopen and reconcile the same acknowledged run |
| After terminal persistence, before response | Replay returns the terminal run without invocation |
| Dashboard-process restart with old `INVOKING` owner | Convert to Unknown; never assume no work was created |

Reconciliation is read-only with respect to starting work. If an exact Prefect
identity or other authoritative Prefect record proves that one matching flow
exists, it may bind that flow and reconcile normal run state. Zero visible
matches after an ambiguous call is not by itself proof that it is safe to
submit again. Multiple or mismatched matches are integrity failures.

### 8. Keep retry, cancellation and stale recovery state-valid

- The durable dashboard path does not repeat the outer launcher call as a
  retry. Technical retry stays within the one acknowledged Prefect flow and
  appends an idempotent `run_retry_scheduled` event to the same Quant Factory
  run.
- An explicit retry after a terminal run is a new launch key and a new run,
  with lineage where required.
- `SUBMISSION_UNKNOWN` disables launch, retry and cancellation until
  reconciliation establishes a real flow or an explicit evidenced resolution
  abandons the claim.
- Cooperative cancellation remains available only for a known active run and
  retains the existing Prefect acknowledgement boundary.
- A stale `CLAIMED` record is known not to have crossed the invocation marker
  and may fail safely as not submitted.
- A stale `INVOKING` record whose dispatcher process no longer exists becomes
  Unknown, not Failed.
- A stale acknowledged run reconciles its known Prefect identity before any
  terminal recovery. Missing or unavailable reconciliation evidence must not
  be presented as proof of success or failure.

Operator events remain concise and append-only. Full Prefect logs are not
copied into the Quant Factory database.

### 9. Make the browser observe persisted state

Run test remains a page-owned, route-gated mutation under ADR 0008. A session
store keeps the prepared key and selected immutable configuration. The button
is disabled and labelled **Starting test...** as soon as the explicit request
is pending.

Button state, run identity, the persistent quartet and the event timeline are
derived from the durable claim, run and event records. Dash callback
`running` state is not authoritative because request completion, refresh and
process restart can reset it. An inactive mounted route may read no more than
needed for passive presentation and must never claim, invoke, retry, cancel or
recover a run.

Refresh reopens the same key and run. A browser without that session identity
must not guess that the newest run belongs to it; the run remains discoverable
through Results.

## Current in-request limitation

This bounded option deliberately preserves the current synchronous,
in-request fixture invocation. It adds durable intent and truthful recovery;
it does not make computation survive loss of the dashboard process.

The durable outcomes after process loss are therefore:

- the same acknowledged run can be reopened and reconciled from persisted
  Quant Factory and Prefect state;
- an unacknowledged invocation becomes Submission unknown; and
- no replacement request silently duplicates it.

This option must not be described as a durable execution worker. Existing
request timeout, process lifetime and cooperative-cancellation limits remain
visible constraints.

## Migration, backup and rollback

If this proposal is accepted and later implemented:

1. schema version 5 is additive; existing runs remain valid and are not
   fabricated into submission records;
2. old run reads retain their current Prefect-metadata compatibility path;
3. migration runs once, before concurrent dashboard writers start;
4. the target SQLite database is backed up and its restore is verified before
   the first schema-5 startup;
5. the candidate database and artifacts are preserved if validation fails;
6. rollback stops the candidate, restores the verified schema-4 backup and
   prior image, then repeats health, identity and browser checks; and
7. an older binary is not pointed at schema 5, and rollback never drops the
   new table in place.

Any production rollout remains a separate owner-authorized, backed-up,
validated deployment slice. Accepting this architecture would not itself
authorize that rollout.

## Required validation before implementation can be accepted

### Persistence and concurrency

- fresh schema-5 initialization and v4-to-v5 migration;
- injected failure after each claim write proves total rollback;
- two independent connections claiming the same key concurrently create one
  submission, one run and one initial event;
- same-key replay returns that run;
- same-key request/configuration mismatch creates nothing and fails clearly;
- concurrent dispatch compare-and-set invokes the launcher once; and
- restart preserves submission, run and event identity.

### Fault and recovery

- deterministic faults at every crash window in this proposal;
- old dispatcher identity converts Invoking to Unknown after process restart;
- exact Prefect binding replay is idempotent;
- mismatched binding fails closed;
- Unknown never triggers an automatic launch retry;
- retry events remain on one run;
- cancellation remains cooperative and state-valid; and
- stale recovery distinguishes Claimed, Invoking, Unknown and Acknowledged.

### Registered callbacks and browser lifecycle

- one callback owner for the launch button and each launch store/output;
- route and explicit-action guards on every mutation;
- immediate disabled **Starting test...** state;
- one visible stable run identity through Created, Running and terminal state;
- event/timeline monitoring without invented progress;
- rapid duplicate click and duplicate request cause one invocation;
- refresh during launch reopens the same identity;
- application restart reopens the same identity and shows Unknown where
  acknowledgement cannot be proved;
- inactive mounted pages do not mutate; and
- the relevant Milestone 18, Milestone 23, dashboard and browser suites pass.

The successful integrated Milestone 23 proof still uses the real SPYM VectorBT
Pro fixture in the licensed target environment. Deterministic fixtures remain
appropriate for concurrency and failure injection. Portable CI does not
replace licensed-target or browser evidence.

## Consequences if accepted

- Run test gains one durable identity before external invocation.
- Duplicate callback delivery and browser refresh become replay-safe.
- Ambiguity becomes visible instead of being rounded to Failed or retried.
- Quant Factory gains a small research-specific persistence contract and must
  maintain its migration and recovery tests.
- The existing in-request execution limit remains; process loss may terminate
  computation even though identity and recovery remain durable.
- Milestone 23 remains pending until implementation and all required evidence
  pass. Acceptance of this ADR would not accept the milestone.

## Explicit exclusions

This proposal does not authorize:

- implementation before Terry accepts an architecture choice;
- reuse of the paper-order journal or paper execution state;
- a Prefect deployment, runner, worker, background thread or custom scheduler;
- a production or OVH runtime change;
- credentials, accounts, broker APIs, orders, positions or capital;
- strategy discovery, optimization or protected-test evaluation;
- a new dashboard framework;
- automatic retry of an unresolved submission; or
- any paper or live activation.

## Owner decision required

Terry must choose one of these paths before implementation:

1. **Accept the bounded in-request design.** Implement and validate the
   research-specific durable claim exactly within the boundaries above.
2. **Revise the proposal.** Record the required changes and keep implementation
   blocked until the revised architecture is explicitly accepted.
3. **Choose a separate worker/deployment architecture.** Design a larger
   follow-up in which submission creates an idempotent Prefect deployment run
   and an independently managed research worker executes it. That option
   changes deployment topology, worker lifecycle, database concurrency,
   packaging, recovery and target acceptance. It is not silently included in
   this proposal and requires its own architecture and deployment evidence.

No default is inferred from silence. Decision 277 is not acceptance of any of
these persistence/orchestration choices.

## Documentation-impact assessment for this proposal

- `AGENTS.md`: not applicable — no permanent behavior or allocation is
  accepted by a proposal.
- `docs/MILESTONES.md`: not applicable — scope, order, status and acceptance do
  not change.
- `docs/DECISIONS.md`: not applicable — Terry has not accepted a decision.
- ADR: updated — this file records the non-authoritative architecture proposal.
- `docs/CHAT_HANDOFF.md`: not applicable — no accepted fact requires startup
  visibility.
- `README.md`: not applicable — public orientation is unchanged.
- Runbook/specification: not applicable — no operating or implementation
  procedure is authorized.

If Terry later accepts or revises the design, documentation governance requires
the accepted decision, authoritative milestone status, affected specification
and any operational procedure to be synchronized in that later change.
