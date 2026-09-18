# Execution-contract mechanism

**Status:** Implemented offline contract slice; not execution-ready.

Milestone 24C now has a small broker-neutral record boundary in `execution/`.
It defines immutable order intent, acknowledgement, fill, cancellation,
rejection, account and position snapshots, and a reconciliation result. An
order intent carries paper/live record identity, strategy, run, deployment,
account, idempotency, and risk-decision identity; later lifecycle records carry
the same execution scope and reference that intent for their risk-metadata join.
Paper and live are labels
in immutable records only; they do not select an endpoint, reveal a credential,
authorize an order, or change process behavior.

The contract rejects naive timestamps, float or boolean monetary and quantity
values, non-finite `Decimal` values, missing identifiers, ambiguous whole-share
quantities, and inconsistent order-price combinations. Serialization produces
JSON-native primitives while retaining `Decimal` as a string and normalizing
timestamps to UTC. `to_primitive` is outbound JSON preparation for these
in-memory records only; it is not a versioned wire envelope, deserializer, or
persistence/migration format.

Observed fill fees are explicit: `None` preserves an unknown fee, while a
finite signed `Decimal` preserves either a charge or a venue rebate. The
contract does not turn an absent fee into zero-cost accounting.

`reconcile_snapshots` is a deterministic evidence comparison, not a trading or
risk engine. It reports `matched` only after both snapshots explicitly confirm
their position lists are complete and all account balances and position values
match. Different account/domain/currency identity or stale timestamps are
`indeterminate`, never `matched`; concrete balance or position disagreements
are `mismatched`.

The in-memory contract slice alone does not add a research persistence layer,
database migration, adapter interface,
broker SDKs, credentials, networking, order submission, deployment eligibility,
authorization, tolerance policies, currency conversion, P&L calculation, or
dashboard behavior. Those require later separately accepted Milestone 24 work
and paper/live isolation controls under ADR 0006.

## Offline paper account/deployment binding preflight

`PaperDeploymentBinding` is the one reusable configuration boundary for a
paper account, deployment identity, and `owner-attestation:` reference. The
observer configuration requires one binding. The paper journal persists it and
the Alpaca order boundary compares its binding exactly with the journal's.
The pure snapshot mapper requires a format-validated binding and compares the
observed broker account identity with it; it cannot establish deployment or
attestation consistency with another component. The caller and future runtime
must establish cross-component binding consistency. Tests and the configuration
example use synthetic identifiers; UUID validation cannot determine whether an
identifier is real. Public health and failure text keep identifiers out of
output.

The attestation reference must identify a durable, operator-supplied external
record that authorizes this account/deployment pairing. It is not a boolean or
string proof of account ownership: this offline code neither retrieves nor
verifies the external record. The dedicated-account boundary is recorded in
the private archive, but the runtime still must bind that confirmation to the
deployment record. Observer health therefore distinguishes a valid account
observation from deployment readiness and always reports deployment readiness
as false. A future credentialed deployment must independently verify the
attestation, account ownership, endpoint, credential isolation, and target
environment before it may report itself deployment-ready.

`execution/paper_observer_bootstrap.py` adds an offline orchestration contract
for that future target proof. It binds only Decision 272's attestation reference,
the protected expected account identity and a unique deployment/operation;
requires exact account and positions GET policy plus catch-all denial; and
coordinates restart, audit, one-shot observation, revocation and rollback
through injected ports. A protected fsynced journal precedes the first gateway
mutation and records intent/commit phases. Exact interrupted operations recover
idempotently, while unjournaled or extra resources fail as foreign collisions.
Runtime removal requires the journaled protected-parent and runtime device/inode
identities and never trusts the operation marker by itself. An unpredictable
staging path is committed first; its inode and files are fsynced before atomic
no-replace rename exposes the requested runtime path. Recovery cannot pass or remove its
journal while that requested path remains unexpected. Audit collection
follows all requests and requires 17 ordered rows across both policy matrices,
the observation and revoked identity under one correlation fingerprint. The
module has no live transport or process capability. Its deterministic evidence
schema excludes raw identities and credentials and cannot convert observer
health into reconciliation or deployment readiness.
The operator-controlled OneCLI bootstrap, dedicated paper-credential import and
reviewed target adapter remain external prerequisites.

Runtime publication is Linux-specific and requires
`renameat2(RENAME_NOREPLACE)`. Missing or unsupported support fails closed;
plain rename is not a fallback because it can replace an empty foreign
directory.

## Pure Alpaca paper snapshot mapping

A lead-selected bounded implementation under Decision 262, in
`execution/alpaca_snapshots.py`, maps already-decoded Alpaca account and
positions responses into immutable `PAPER` account and position snapshots. It
requires a predeclared instrument registry whose entries are USD equity or ETF
instruments using whole shares, and rejects incomplete metadata or valuation,
invalid identifiers, and inconsistent quantity, side, or market-value signs.
For short observations its
conservative input contract requires negative quantity and market value; this
is an offline fixture contract, not broker-native short-position proof, since no
credentialed positions read ran. The mapper has no transport, worker, order, or
persistence integration. Its caller supplies an observation timestamp; that
timestamp records observation timing only and does not establish that the
separate account and positions responses were atomic or that market data was
fresh. This is a bounded normalization mechanism and does not claim gateway
adoption, worker readiness, order activation, or execution acceptance.

## Paper journal foundation

`PaperOrderJournal` uses a separate SQLite file at an explicit absolute path
for one `PaperDeploymentBinding`. It refuses an existing foreign or research
database, has no default research-database path, and validates its schema and
paper identity metadata. It durably deduplicates canonical versioned order-intent
envelopes, preserving a stable client idempotency key. A claim is atomically
recorded before a future adapter could call a broker and can occur only once;
pending or unknown claims never requeue automatically after restart. This is
durable at-most-one claim evidence, not an exactly-once broker guarantee.

Initialization creates the version-2 metadata contract and account/deployment
identity in one transaction. Version 2 additionally persists the
owner-attestation reference in exact journal metadata. Reopening requires the
version-2 metadata and the existing table and index constraints, including
unique intent, idempotency, and broker-order identities; version-1 journals
are rejected and there is no automatic schema migration. Decimal canonicalization preserves
all supplied digits independently of the caller's arithmetic precision.

Each operation verifies the intent hash and identity, permitted event sequence,
event payloads, and terminal evidence inside its transaction. A corrupted or
inconsistent record fails closed before a claim or state change commits.
Acknowledgement and rejection retries preserve the existing outcome; a broker
order cannot belong to two intents in this journal. These are local consistency
checks, not cryptographic tamper protection or evidence from a broker. This
foundation adds no adapter, credentials, endpoint, order activation, or runtime
migration.

## Offline Alpaca paper boundary

`execution/alpaca_paper.py` maps neutral `equity` and `etf` whole-share USD
market or limit DAY intents to Alpaca order requests. `us_equity` belongs only
to the broker response. This deliberately narrow implementation uses simple
regular-hours orders, an explicit boolean `extended_hours: false`, and the
fixed `https://paper-api.alpaca.markets` origin. It supplies no concrete HTTP
transport, credentials, environment activation, CLI, or research integration.
The injected transport contract prohibits endpoint rewriting, hidden retries,
and redirects; the future worker must enforce that contract.

The required `PaperDeploymentBinding` is checked against journal metadata and
intent scope. These checks are local assertions; the attestation reference
only identifies external evidence and is not verified here. They do not verify
the actual broker account, destination, credential isolation, or authority to
trade. ADR 0010 proof and execution-ownership checks remain required before
credential use or actual broker access.

Before creating or claiming an intent, the boundary rejects unsupported inputs.
Exact decimal strings retain all supplied digits independently of arithmetic
precision, with at most two fractional digits for limits at or above one dollar
and four below it after removing trailing zeros. Numeric representations are
bounded to 64 characters; the supported symbol spelling uses at most 15 uppercase
ASCII letters, digits or dots, starting with a letter. These are conservative
mechanism choices for this slice, not instrument eligibility or exposure limits.
A pinned version-1 canonical JSON identity maps to a stable 48-character client
order ID; its encoding must remain stable for recovery across restarts.

Submission builds its request from the validated durable claim and makes at
most one injected POST call. Losing a claim returns a fresh validated journal
entry. Pending and unknown claims never submit again. Explicit recovery looks
up an existing pending or unknown claim through
`GET /v2/orders:by_client_order_id?client_order_id=...`; it cannot create or claim
an intent. A 404, non-2xx result, timeout, malformed response, or mismatched
identity/economics remains inconclusive and never requeues the order. Recovery
returns existing terminal journal evidence without another request.

Only broker `accepted` or `new` responses with zero filled quantity and matching
simple-order economics can produce a submission receipt. Broker IDs must be
canonical UUIDs, numerical fields must be bounded decimal strings, and broker
submission time must be timezone-aware. Acknowledgement identity and timestamp
are derived from that broker order ID and submission time, so identical
concurrent recovery is idempotent. Conflicting valid receipts report an explicit
sanitized persistence/conflict failure while preserving durable state. A timeout
cannot overwrite an acknowledgement already recorded by another recovery.

Other broker states, including filled, partially filled, rejected, canceled,
and expired, remain unknown in this slice. This is not fill/cancellation
reconciliation or an execution-ready worker. Only receipt IDs, scope and time
are persisted; the checked response economics and raw response are not retained
as durable broker evidence. Untrusted response and exception text is neither
logged nor stored. Failure to persist a receipt or an unknown state is an
explicit sanitized error; the durable pending/unknown claim still prohibits a
second POST.

The mapping follows Alpaca's [create-order reference](https://docs.alpaca.markets/us/reference/postorder),
[client-ID lookup reference](https://docs.alpaca.markets/us/reference/getorderbyclientorderid),
[timeout guidance](https://docs.alpaca.markets/us/docs/working-with-orders), and
[order precision and states](https://docs.alpaca.markets/us/docs/orders-at-alpaca).
The fixed-origin interface does not replace the separate
[authentication boundary](https://docs.alpaca.markets/us/docs/authentication).
