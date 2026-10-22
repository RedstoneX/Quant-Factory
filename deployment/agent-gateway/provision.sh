#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "provisioning requires root" >&2
    exit 77
fi

source_root=${QF_GATEWAY_SOURCE_ROOT:?set QF_GATEWAY_SOURCE_ROOT}
local_user=${QF_GATEWAY_LOCAL_USER:-ubuntu}
public_key=${QF_GATEWAY_PUBLIC_KEY:-}
runtime_root=${QF_RUNTIME_ROOT:-/opt/quant-factory-research/runtime}
runtime_gid=${QF_RUNTIME_GID:-10001}
data_locations=${QF_DATA_LOCATIONS_PATH:-/opt/quant-factory-research/config/data_locations.local.toml}
install_root=/opt/quant-factory-gateway
client_root=$install_root/client/agent_gateway
state_root=$install_root/state
socket_root=/run/quant-factory
inventory=$install_root/identity.env
credential_root=$install_root/credentials
registry=$install_root/identity-registry.json

[ -f "$source_root/agent_gateway/cli.py" ] || { echo "gateway client source is missing" >&2; exit 66; }
id "$local_user" >/dev/null 2>&1 || { echo "local agent user does not exist" >&2; exit 67; }

install -o root -g root -m 0755 "$source_root/deployment/agent-gateway/qf-agent" /usr/local/bin/qf-agent
install -o root -g root -m 0755 "$source_root/deployment/agent-gateway/qf-agent-ssh-gateway" /usr/local/bin/qf-agent-ssh-gateway

getent group qf-agent-access >/dev/null 2>&1 || groupadd --system qf-agent-access
getent group qf-gateway >/dev/null 2>&1 || groupadd --system qf-gateway
id qf-gateway >/dev/null 2>&1 || useradd --system --gid qf-gateway --home-dir /nonexistent --shell /usr/sbin/nologin qf-gateway
id qf-research >/dev/null 2>&1 || useradd --system --user-group --create-home --home-dir /var/lib/qf-research --shell /usr/local/bin/qf-agent-ssh-gateway qf-research
usermod --shell /usr/local/bin/qf-agent-ssh-gateway --password '*' qf-research
usermod --append --groups qf-agent-access qf-research
usermod --append --groups qf-agent-access "$local_user"

install -d -o root -g root -m 0755 "$install_root" "$install_root/client"
install -d -o root -g root -m 0755 "$client_root"
: > "$client_root/__init__.py"
chmod 0644 "$client_root/__init__.py"
for name in contracts.py cli.py ssh_command.py; do
    install -o root -g root -m 0644 "$source_root/agent_gateway/$name" "$client_root/$name"
done
install -d -o root -g root -m 0711 "$credential_root"
local_group=$(id -gn "$local_user")
create_credential() {
    target=$1
    if [ ! -s "$target" ]; then
        umask 077
        od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > "$target"
    fi
    chown "$local_user:$local_group" "$target"
    chmod 0400 "$target"
}
codex_credential=$credential_root/codex-local.token
claude_credential=$credential_root/claude-local.token
create_credential "$codex_credential"
create_credential "$claude_credential"
codex_digest=$(sha256sum "$codex_credential" | cut -d' ' -f1)
claude_digest=$(sha256sum "$claude_credential" | cut -d' ' -f1)
registry_tmp=$install_root/.identity-registry.tmp
cat > "$registry_tmp" <<EOF
{"schema":"qf_agent_identity_registry_v1","identities":[{"agent_id":"codex-local","provider":"openai","client":"codex","transport":"local","authority_level":2,"credential_sha256":"$codex_digest"},{"agent_id":"claude-local","provider":"anthropic","client":"claude-code","transport":"local","authority_level":1,"credential_sha256":"$claude_digest"},{"agent_id":"grok-remote","provider":"xai","client":"grok","transport":"ssh","authority_level":1}]}
EOF
chown qf-gateway:qf-gateway "$registry_tmp"
chmod 0400 "$registry_tmp"
mv "$registry_tmp" "$registry"
install -d -o qf-gateway -g qf-gateway -m 0700 "$state_root"
install -d -o qf-gateway -g qf-agent-access -m 2770 "$socket_root"
if [ -d "$runtime_root/state" ]; then
    chgrp "$runtime_gid" "$runtime_root" "$runtime_root/state"
    chmod 2775 "$runtime_root"
    chmod 2770 "$runtime_root/state"
    if [ -f "$runtime_root/state/quant_factory.sqlite3" ]; then
        chgrp "$runtime_gid" "$runtime_root/state/quant_factory.sqlite3"
        chmod 0660 "$runtime_root/state/quant_factory.sqlite3"
    fi
fi
if [ -f "$data_locations" ]; then
    chgrp "$runtime_gid" "$data_locations"
    chmod 0440 "$data_locations"
fi
cat > /etc/tmpfiles.d/quant-factory-agent-gateway.conf <<'EOF'
d /run/quant-factory 2770 qf-gateway qf-agent-access -
EOF
chmod 0644 /etc/tmpfiles.d/quant-factory-agent-gateway.conf

install -d -o qf-research -g qf-research -m 0700 /var/lib/qf-research/.ssh
authorized_keys=/var/lib/qf-research/.ssh/authorized_keys
if [ -n "$public_key" ]; then
    case "$public_key" in
        ssh-ed25519\ *|sk-ssh-ed25519@openssh.com\ *) ;;
        *) echo "QF_GATEWAY_PUBLIC_KEY must be an Ed25519 public key" >&2; exit 68 ;;
    esac
    printf '%s %s\n' 'restrict,command="/usr/local/bin/qf-agent-ssh-gateway",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty' "$public_key" > "$authorized_keys"
else
    : > "$authorized_keys"
fi
chown qf-research:qf-research "$authorized_keys"
chmod 0600 "$authorized_keys"

install -o root -g root -m 0644 "$source_root/deployment/agent-gateway/sshd-qf-research.conf" /etc/ssh/sshd_config.d/90-qf-research.conf
sshd -t
systemctl reload ssh.service 2>/dev/null || systemctl reload sshd.service

gateway_uid=$(id -u qf-gateway)
gateway_gid=$(id -g qf-gateway)
research_uid=$(id -u qf-research)
access_gid=$(getent group qf-agent-access | cut -d: -f3)
local_uid=$(id -u "$local_user")
umask 077
cat > "$inventory" <<EOF
QF_GATEWAY_UID=$gateway_uid
QF_GATEWAY_GID=$gateway_gid
QF_RESEARCH_UID=$research_uid
QF_AGENT_ACCESS_GID=$access_gid
QF_GATEWAY_LOCAL_UIDS=$local_uid
QF_GATEWAY_STATE_ROOT=$state_root
QF_GATEWAY_SOCKET_ROOT=$socket_root
QF_GATEWAY_IDENTITY_REGISTRY_PATH=$registry
QF_RUNTIME_GID=$runtime_gid
EOF
chown root:root "$inventory"
chmod 0600 "$inventory"

echo "gateway_identity=qf-gateway uid=$gateway_uid gid=$gateway_gid"
echo "research_identity=qf-research uid=$research_uid access_gid=$access_gid"
echo "local_agent_user=$local_user uid=$local_uid"
echo "codex_credential_file=$codex_credential"
echo "claude_credential_file=$claude_credential"
if [ -n "$public_key" ]; then
    echo "remote_key=installed"
else
    echo "remote_key=awaiting_owner_public_key"
fi
