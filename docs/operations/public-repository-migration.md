# Public repository migration

## Status and authority

Decision 275 authorizes a sanitized clean-history public repository. This
runbook is retained as the operating procedure and publication checklist.

Until every pre-publication check passes and the controlled cutover completes,
the existing repository remains private, canonical, and authoritative. Its Git
history must not be rewritten or deleted. At cutover it is renamed, kept
private, and archived read-only as historical evidence. The validated
clean-history repository then assumes the canonical name and becomes the sole
forward source of truth.

This work is bounded R01 remediation. It does not change Decision 274's
dashboard-first product order, modify the production runtime, use credentials,
or authorize strategy discovery, backtesting before its gate, paper orders, or
live capital.

Public visibility does not grant a source-code license. Unless the owner separately
approves a specific license, do not add a `LICENSE` file or license grant; the
published source remains all rights reserved.

## Stop conditions

Stop before publication or cutover if any of the following is true:

- a credential, key, token, private key, environment file, licensed package,
  downloaded market data, generated result, database, or non-public account
  identifier is present;
- private infrastructure coordinates, machine-specific paths, personal
  information, or operational screenshots/mockups remain without an explicit
  public-safe reason;
- the candidate content cannot be traced to the accepted private `main` source
  revision and an explicit sanitization manifest;
- required portable and documentation validation fails;
- the private archive name or candidate canonical name is ambiguous or already
  occupied;
- the original repository cannot remain private and recoverable;
- repository visibility, required checks, or strict/up-to-date behavior cannot
  be verified after cutover.

Do not solve a stop condition by weakening a test, deleting the private
archive, rewriting its history, or publishing first and cleaning up later.

## 1. Freeze and identify the source

1. Record the existing repository name, visibility, default branch, accepted
   `main` commit, open pull requests/issues, Actions state, releases, packages,
   webhooks, deploy keys, environments, and repository-level secrets by name
   only. Never print secret values.
2. Confirm the selected source worktree is clean and that the recorded commit
   is the intended import baseline. Reconcile or stop on concurrent writes.
3. Record a collision-free private archive name and a temporary private
   candidate name. Do not rename or change visibility yet.
4. Pause repository cutover operations while the candidate is validated;
   ordinary Milestone 23 work may continue only if its accepted source revision
   can still be reconciled into the candidate before publication.

## 2. Build the clean-history candidate

1. Create a new private candidate repository with no imported Git history,
   issues, pull requests, Actions logs/artifacts, releases, discussions, or
   repository metadata from the original.
2. Populate a fresh working tree from an explicit allowlist. Sanitize or omit
   private infrastructure details, machine paths, account metadata, personal
   attribution, private operational evidence, and unmarked mockups. Preserve
   the private originals only in the private archive.
3. Exclude all secrets and environment files, private or licensed dependencies,
   market-data payloads, databases, artifacts, logs, recovery bundles, and
   machine-local state. Public templates may contain names and placeholders but
   no values.
4. Record the source revision, each intentional omission/generalization, and
   the resulting tree identity in a redacted migration evidence manifest held
   outside the public candidate. Do not create a second roadmap or status
   authority.
5. Create only the reviewed clean-history import commit(s). Verify that the
   candidate contains no parentage or objects from the private repository.

## 3. Validate before publication

Run the narrowest decisive checks first, then the candidate's complete public
CI selection:

1. Scan the candidate working tree and every candidate Git object for secrets,
   credentials, private keys, private infrastructure, personal information,
   machine paths, account metadata, licensed/private packages, datasets,
   databases, result artifacts, and oversized or unexpected binary files.
2. Inspect tracked files, Git LFS pointers, submodules, workflow definitions,
   release inputs, package configuration, and documentation links. External
   references must be intentionally public.
3. Run `python tools/check_documentation.py` and
   `python -m unittest tests.test_documentation_governance -v`.
4. Run the current public dependency/portable CI selection from a clean
   environment and inspect its exact pass, fail, error, and skip counts.
5. Review the candidate diff against the allowlisted source and inspect the
   complete candidate log/object inventory. A scanner pass alone is not a
   publication decision.

The candidate remains private if any check is incomplete, inconclusive, or
failed.

## 4. Prove the temporary public candidate, then cut over

1. While the original remains private, canonical, writable, and authoritative,
   make the validated candidate public under its temporary name. Verify an
   unauthenticated fresh clone resolves to the expected clean history and tree,
   exposes no excluded private content, and contains no unapproved source-code
   license or license grant.
2. On that temporary public candidate, configure pull-request protection and
   require every applicable observed CI check. Set GitHub's
   required-status-check `strict`/up-to-date option to **false** so independent
   pull requests do not each wait for another full refresh build after an
   unrelated merge. Do not use that setting for overlapping or dependent
   changes; serialize and retest those changes against the resulting `main`.
3. Block ordinary candidate merges until required-check enforcement is proven
   using the controlled-failure procedure in
   [CI test gate](ci-test-gate.md#required-gate-proof). Capture the candidate
   revision, workflow run, job, failed check, GitHub blocked-merge state,
   restored green revision, and protection configuration. Never merge the
   deliberate failure or use an override. If proof fails, return the candidate
   to private visibility; the original remains untouched and authoritative.
4. Only after the anonymous-publication and enforcement proofs pass, freeze
   every writer, automation token, deploy key, and approved clone. Record final
   private `main`, candidate commit, and the original repository's immutable
   GitHub repository ID as `ARCHIVE_REPOSITORY_ID` in private cutover evidence.
   Reusing the canonical name overrides GitHub's normal old-repository redirect;
   a stale clone can otherwise resolve its old remote to the new public
   repository and push to the wrong history. If
   the private source advanced after the candidate's recorded source revision,
   reconcile the intended changes through the sanitization and validation
   procedure and repeat all affected candidate checks before continuing.
5. Rename the original repository to the recorded archive name, verify it is
   still private and that its immutable repository ID equals
   `ARCHIVE_REPOSITORY_ID`, then archive it read-only. Do not delete it or alter
   its history. Disable or rotate any writer that cannot be proven frozen.
6. Rename the proven candidate to the canonical public name. Verify the rename
   preserved public visibility, the required-check set, `strict: false`, branch
   restrictions, and the restored-green revision. Verify an unauthenticated
   fresh clone at the canonical name resolves to the same proven clean history
   and tree. The public repository is now the sole forward authority; the
   private archive is historical evidence only.
7. Update approved development clones and automation to the canonical public
   repository only after every post-rename check passes. Production runtime
   changes are a separate authorized, backed-up, validated deployment slice.

## 5. Verification and rollback

Verify all of the following before closing R01:

- the canonical repository is public and exposes only the reviewed clean
  history;
- the renamed original is private, archived read-only, and recoverable;
- the renamed archive matches the privately recorded immutable repository ID,
  and no stale clone or automation can write through the reused canonical name;
- `main` is the canonical default branch and direct/force pushes and deletion
  are prohibited as configured;
- applicable CI checks are required, `strict` is false, a controlled failure
  blocks merging, and the restored green path passes;
- unauthenticated browsing and cloning expose no private repository metadata or
  intentionally excluded content;
- no source-code license or license grant is present unless the owner separately
  approved it; public visibility alone leaves the source all rights reserved;
- authoritative documentation names the public canonical repository and the
  private archive's historical-only role without changing product gates.

If temporary-candidate publication or protection verification fails, stop
merges and return the candidate to private visibility; the original remains
private and authoritative. If a post-cutover check fails, stop merges, return
the replacement to private visibility when safe, and restore the original
repository name/authority from the untouched private archive. Record the exact
failure before retrying. Rollback never deletes either repository or rewrites
history.
