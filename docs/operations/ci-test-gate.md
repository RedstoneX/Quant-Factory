# CI Test Gate

## Purpose

CI must execute the public test contract and GitHub must require the applicable
checks before merging to `main`. Workflow presence or a green run alone does
not prove enforcement.

## Workflow contract

The workflow runs on pull requests and pushes to `main` with read-only contents
permission. Actions are pinned to reviewed commit SHAs. Checkout uses
`persist-credentials: false`. The portable job installs only public
dependencies, produces a JUnit report, verifies that report, and uploads it as
a bounded artifact. Dependency review runs only for pull requests with no
comment or write permission.

The Test workflow concurrency group includes `github.ref`; cancellation is
therefore limited to a newer run on the same ref. Independent pull-request refs
can run concurrently. The repository uses no merge queue.

For a push whose `github.event.before` value is all zeroes, run the
documentation validator without `--base-ref`; otherwise preserve the append-
only incident check against the supplied base revision.

## Required-gate proof

1. Create a disposable branch and pull request containing one controlled,
   obvious test failure.
2. Observe the expected required check fail.
3. Verify GitHub reports merging blocked because that required check failed.
4. Record only public-safe revision, workflow, job, check, and protection
   evidence.
5. Revert the deliberate failure without merging it.
6. Verify the restored revision passes and the merge requirement is satisfied.

Never override the gate or merge deliberate failure code. Configure required
checks with `strict`/up-to-date set to `false` permanently unless the owner
changes Decision 276. Keep `Documentation contracts`, `Portable tests`, and
`Dependency review` required, keep `enforce_admins` enabled, and keep repository
auto-merge and merged-branch deletion enabled. An independent green pull
request may merge without rebasing, updating, rebuilding, or serializing merely
because another independent pull request merged first. Overlapping or
dependent changes still merge serially and are retested against the resulting
`main`.

## Verified canonical proof — 2026-09-18

GitHub API inspection after canonical cutover confirmed
`required_status_checks.strict: false`; required checks `Documentation
contracts`, `Portable tests`, and `Dependency review` from GitHub Actions app
ID 15368; `enforce_admins: true`; force-push and branch deletion disabled by
protection; repository auto-merge and merged-branch deletion enabled; and no
repository ruleset or merge queue.

Controlled PR #1 supplied the enforcement proof. Revision
`61e64bc17debf557d742d94dc498caba039aab2f` failed the required `Portable tests`
check and GitHub blocked merging. Corrected revision
`1031911391f10c063c746149fc1c5f1b56c642b3` passed all three required checks.
The PR was closed without merging on 2026-09-18. This is CI-enforcement
evidence only, not target-environment proof.

Independent same-base PRs #2 and #3 supplied the throughput proof. Both passed
all three required checks. PR #3 merged while PR #2 remained open; afterward,
GitHub still reported PR #2 as `CLEAN` and `MERGEABLE` with the same Test run
`35301119002` and Dependency Review run `35301119008`. No refresh run occurred,
and PR #2 was then closed without merging. The proof establishes that an
unrelated merge does not serialize independent green work; it does not remove
the retest requirement for dependent or overlapping changes.

CI proves only its own environment. Runtime configuration, dependencies,
secret injection, startup, and target behavior require separate target-
environment evidence.
