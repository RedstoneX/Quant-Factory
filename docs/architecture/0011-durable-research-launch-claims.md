# ADR 0011: Durable research-launch claims

- **Status:** Accepted and implemented
- **Date:** 2026-09-18
- **Presentation authority:** None

## Purpose

A research request must acquire a durable identity before external invocation.
This prevents duplicate work and false completion claims when a request is
replayed, a response is lost, or a process exits during submission. This ADR
defines launch semantics only. It does not define pages, routes, controls,
wording, visual treatment, current sequencing, or milestone status.

## Contract

- One idempotency key identifies exactly one operation kind, canonical launch
  request, Quant Factory run, and acknowledged external identity.
- Claim creation, input binding, and invocation ownership are transactional.
- Exactly one caller may own the initial invocation. Same-key delivery reopens
  the existing claim; it never creates another intent or launch.
- Acknowledged, succeeded, failed, cancelled, failed-before-submission,
  abandoned, and submission-unknown are distinct persisted states.
- When external outcome cannot be proved, the claim becomes
  `submission_unknown`. It is not rounded to failed and is not retried.
- Recovery requires positive identity and state evidence. Age, PID absence,
  worker restart, or request timeout alone proves neither success nor failure.
- Cancellation is cooperative, idempotent, and cannot overwrite a terminal
  outcome.
- Durable identity does not imply durable computation. A separate worker or
  deployment is required before computation may be claimed to survive loss of
  its initiating process.

## Client obligations

Every launch, reproduction, or historical-relaunch client must:

1. prepare a key bound to the exact immutable inputs and operation;
2. submit that key only after an explicit authorized action;
3. disable repeat submission while the request is pending;
4. derive visible state from persisted claim, run, and event records;
5. preserve the submitted key across refresh and restart;
6. rotate only an unused key when its bound inputs change; and
7. visibly disable the action if the client has not adopted this contract.

UI session state is a convenience, not authority. No inactive route or passive
refresh may claim, invoke, retry, cancel, or recover work.

## Persistence and reconciliation

Research claims use the Quant Factory persistence boundary, not the separate
paper-order journal. Events are concise and append-only. External scheduler
identities reconcile to the same run. Migration completes before concurrent
writers begin. Artifact, evidence, and lineage truth remain governed by their
own contracts.

## Proof boundary

Focused proof must cover concurrent same-key delivery, request mismatch,
replay after refresh/restart, acknowledgement loss, submission-unknown,
reconciliation, cancellation races, and atomic terminal outcomes. Licensed
integration evidence is separate from deterministic concurrency/fault proof.
Neither this technical proof nor this ADR accepts the reconstructed interface,
authorizes a Candidate campaign, or changes paper/live authority.
