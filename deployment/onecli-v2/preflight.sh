#!/usr/bin/env bash
# Render and inspect only safe Compose metadata. Never print the runtime env or
# rendered configuration because both contain synthetic authentication values.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /absolute/path/to/onecli-v2.env" >&2
  exit 64
fi

runtime_env=$1
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file=$script_dir/compose.yaml
validator=$script_dir/validate_rendered_config.py
docker_cmd() { sudo -n docker "$@"; }

[ -f "$runtime_env" ] || { echo "preflight=failed reason=runtime_env_missing" >&2; exit 1; }
[ "$(stat -c '%a' "$runtime_env")" = 600 ] || { echo "preflight=failed reason=runtime_env_mode" >&2; exit 1; }
project=$(sed -n 's/^ONECLI_V2_PROJECT=//p' "$runtime_env")
case "$project" in ''|onecli|quant-factory-research|*[!a-zA-Z0-9_.-]*) echo "preflight=failed reason=project_name" >&2; exit 1;; esac

rendered=$(mktemp)
trap 'rm -f "$rendered"' EXIT
docker_cmd compose --project-name "$project" --env-file "$runtime_env" -f "$compose_file" config --format json > "$rendered"
rendered_summary=$(python3 "$validator" "$project" "$rendered")
available_mib=$(awk '/MemAvailable:/{print int($2 / 1024)}' /proc/meminfo)
[ "$available_mib" -ge 4096 ] || { echo "preflight=failed reason=host_memory" >&2; exit 1; }
if [ -n "$(docker_cmd ps -aq --filter "label=com.docker.compose.project=$project")" ]; then
  echo "preflight=failed reason=container_name_collision" >&2
  exit 1
fi
if docker_cmd volume ls --format '{{.Name}}' | grep -Fxq "${project}_postgres-data" || docker_cmd volume ls --format '{{.Name}}' | grep -Fxq "${project}_app-data"; then
  echo "preflight=failed reason=volume_name_collision" >&2
  exit 1
fi
printf '%s host_available_mib=%s\n' "$rendered_summary" "$available_mib"
