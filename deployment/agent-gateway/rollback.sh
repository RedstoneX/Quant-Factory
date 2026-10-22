#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "rollback requires root" >&2
    exit 77
fi

deploy_root=${QF_DEPLOY_ROOT:-/opt/quant-factory-research}
local_user=${QF_GATEWAY_LOCAL_USER:-ubuntu}

if [ -f "$deploy_root/compose.yaml" ] && [ -f "$deploy_root/.env" ]; then
    docker compose -f "$deploy_root/compose.yaml" --env-file "$deploy_root/.env" stop agent-gateway || true
fi
if [ -f /var/lib/qf-research/.ssh/authorized_keys ]; then
    : > /var/lib/qf-research/.ssh/authorized_keys
    chown qf-research:qf-research /var/lib/qf-research/.ssh/authorized_keys
    chmod 0600 /var/lib/qf-research/.ssh/authorized_keys
fi
if id "$local_user" >/dev/null 2>&1 && getent group qf-agent-access >/dev/null 2>&1; then
    gpasswd --delete "$local_user" qf-agent-access >/dev/null 2>&1 || true
fi

echo "gateway_access=disabled"
echo "gateway_state=retained"
echo "qf_candidates=retained"
