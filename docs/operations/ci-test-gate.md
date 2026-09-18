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
checks with strict/up-to-date disabled so independent work is not forced
through repeated refresh builds. Overlapping or dependent changes still merge
serially and are retested against the resulting `main`.

CI proves only its own environment. Runtime configuration, dependencies,
secret injection, startup, and target behavior require separate target-
environment evidence.
