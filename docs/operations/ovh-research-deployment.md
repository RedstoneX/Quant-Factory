# Research Deployment Runbook

> **Production/go-live procedure:** This procedure applies to an
> owner-accepted go-live, persistent/schema migration, destructive state
> change, or explicit owner-requested backup. It does not apply to reversible
> private-beta UI/code review deployments; see the lean procedure below.

This runbook describes a portable Linux research deployment. `OVH` is retained
in the filename for historical navigation only; no provider-specific host,
address, account, or port is required.

## Paths and inputs

Define external roots before rendering configuration:

- `QF_REPO_ROOT`, for example `/srv/quant-factory/repo`
- `QF_DEPLOY_ROOT`, for example `/srv/quant-factory/deploy`
- `QF_DATA_ROOT`, for example `/srv/quant-factory/data`
- `QF_STATE_ROOT`, for example `/srv/quant-factory/state`
- `QF_BACKUP_ROOT`, for example `/srv/quant-factory/backups`

The VectorBT Pro wheel is supplied through an authorized private build context
and is never copied into this repository or a public image registry.

## Lean private-beta review deployment

For an unaccepted single-owner beta with no persistent/schema or destructive
state change:

1. Consolidate related corrections and use focused non-browser checks locally.
2. Complete one repository/CI cycle at the owner-walkthrough boundary.
3. Rebuild and restart only the changed service; a dashboard-only correction
   does not restart Prefect or the Agent Research Gateway.
4. Verify deployed revision, service health, and private reachability.
5. Retain only the current and immediately previous release/image and remove
   superseded beta artifacts. Do not create a backup, rollback bundle, browser
   capture archive, or repeated deployment evidence.
6. Terry performs browser QA. Stop for acceptance or one consolidated defect
   list.

## Accepted go-live or state-changing deployment

1. Freeze and record the approved source revision and rendered configuration.
2. Inventory database, artifacts, market-data manifests, configuration, and
   service ownership. Stop on any unexplained writer.
3. Stop writers and create an encrypted backup under `QF_BACKUP_ROOT`. Verify
   decryption and every retained checksum in an isolated restore.
4. Build non-root containers from pinned public dependencies plus the private
   licensed build context. Record image identity without exposing secrets.
5. Restore into fresh external state under `QF_STATE_ROOT`; never overwrite a
   newer target silently.
6. Start the dashboard and orchestration services on private networking only.
7. Verify health, page/layout/callback endpoints, database schema, artifact
   identity, manifest identity, restart, and rollback.
8. Terry runs the accepted browser workflow. Runtime reachability and automated
   tests do not equal operator acceptance.

## Network and rollback

Bind application services to loopback or an authenticated private network.
Document public-safe examples with RFC 5737 addresses such as `192.0.2.10`,
never real private hostnames or addresses. Do not expose database or
administration ports, use public tunnels, or bypass venue eligibility.

For an accepted go-live or state-changing deployment, rollback stops the
candidate services, preserves their state for diagnosis, restores the verified
prior image/configuration/state snapshot, and reruns health and identity checks
before Terry's browser check. A production runtime change is always a separate
authorized, backed-up, validated slice. An unaccepted reversible private-beta
deployment uses the lean procedure above.
