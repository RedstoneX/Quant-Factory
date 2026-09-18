#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "$#" -ne 2 ]; then echo "usage: $0 /absolute/runtime.env /absolute/secrets.env" >&2; exit 64; fi
runtime_env=$1; secrets_env=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd); repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
docker_cmd(){ sudo -n docker "$@"; }
safe=$(python3 "$script_dir/validate_inputs.py" "$runtime_env" "$secrets_env" "$repo_root")
field(){ python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1" <<<"$safe"; }
project=$(field QF_ONECLI_PROJECT); pgvol=$(field QF_ONECLI_POSTGRES_VOLUME); appvol=$(field QF_ONECLI_APP_VOLUME); actor=$(field QF_ONECLI_ACTOR_NETWORK)
tmpdir=$(mktemp -d); chmod 700 "$tmpdir"; cleanup(){ rm -rf "$tmpdir"; }; trap cleanup EXIT; trap 'exit 1' HUP INT TERM
expected_digests=$tmpdir/expected-secret-digests.json
python3 "$script_dir/derive_secret_digests.py" "$secrets_env" "$expected_digests"
rendered=$tmpdir/rendered.json
docker_cmd compose --project-name "$project" --env-file "$runtime_env" --env-file "$secrets_env" -f "$script_dir/compose.yaml" config --format json >"$rendered"
python3 "$script_dir/validate_rendered_config.py" "$project" "$pgvol" "$appvol" "$actor" "$rendered"
present=0
for spec in "volume:$pgvol" "volume:$appvol" "network:$actor"; do kind=${spec%%:*}; name=${spec#*:}; if docker_cmd "$kind" inspect "$name" >/dev/null 2>&1; then present=$((present+1)); fi; done
[ "$present" -eq 0 ] || [ "$present" -eq 3 ] || { echo "preflight=failed reason=partial_resource_collision" >&2; exit 1; }
state=unprovisioned
project_ids=$(docker_cmd ps -aq --no-trunc --filter "label=com.docker.compose.project=$project")
volume_ids=$tmpdir/volume-ids
: >"$volume_ids"
for spec in "$pgvol:postgres" "$appvol:api,gateway"; do
 name=${spec%%:*}; allowed=${spec#*:}
 while IFS= read -r id; do
  [ -n "$id" ] || continue
  consumer_project=$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$id")
  consumer_service=$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$id")
  case ",$allowed," in *",$consumer_service,"*) :;; *) echo "preflight=failed reason=volume_consumer" >&2; exit 1;; esac
  [ "$consumer_project" = "$project" ] || { echo "preflight=failed reason=volume_consumer" >&2; exit 1; }
  printf '%s\n' "$id" >>"$volume_ids"
 done < <(docker_cmd ps -aq --no-trunc --filter "volume=$name")
done
sort -u "$volume_ids" -o "$volume_ids"
for service in postgres migrations api web gateway; do
 name="$project-$service-1"
 if docker_cmd container inspect "$name" >/dev/null 2>&1; then
  [ "$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$name")" = "$project" ] && [ "$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$name")" = "$service" ] || { echo "preflight=failed reason=container_collision" >&2; exit 1; }
 fi
done
for id in $project_ids; do
 service=$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$id")
 case "$service" in postgres|migrations|api|web|gateway) :;; *) echo "preflight=failed reason=container_collision" >&2; exit 1;; esac
done
if [ "$present" -eq 3 ]; then
 for spec in "$pgvol:postgres-data" "$appvol:app-data"; do name=${spec%%:*}; role=${spec#*:};
  [ "$(docker_cmd volume inspect -f '{{index .Labels "com.quant-factory.stack"}}' "$name")" = onecli-v2-production ] || { echo "preflight=failed reason=volume_label" >&2; exit 1; }
  [ "$(docker_cmd volume inspect -f '{{index .Labels "com.quant-factory.project"}}' "$name")" = "$project" ] || { echo "preflight=failed reason=volume_project" >&2; exit 1; }
  [ "$(docker_cmd volume inspect -f '{{index .Labels "com.quant-factory.role"}}' "$name")" = "$role" ] || { echo "preflight=failed reason=volume_role" >&2; exit 1; }
  docker_cmd volume inspect "$name" >"$tmpdir/volume-$role.json"
  python3 "$script_dir/validate_resource.py" volume "$name" "$project" "$role" "$tmpdir/volume-$role.json"
 done
 [ "$(docker_cmd network inspect -f '{{.Internal}}' "$actor")" = true ] || { echo "preflight=failed reason=actor_network_external" >&2; exit 1; }
 [ "$(docker_cmd network inspect -f '{{.Driver}}' "$actor")" = bridge ] || { echo "preflight=failed reason=actor_network_driver" >&2; exit 1; }
 [ "$(docker_cmd network inspect -f '{{index .Labels "com.quant-factory.role"}}' "$actor")" = actor ] || { echo "preflight=failed reason=actor_network_role" >&2; exit 1; }
 [ "$(docker_cmd network inspect -f '{{index .Labels "com.quant-factory.stack"}}' "$actor")" = onecli-v2-production ] || { echo "preflight=failed reason=actor_network_label" >&2; exit 1; }
 [ "$(docker_cmd network inspect -f '{{index .Labels "com.quant-factory.project"}}' "$actor")" = "$project" ] || { echo "preflight=failed reason=actor_network_project" >&2; exit 1; }
 docker_cmd network inspect "$actor" >"$tmpdir/actor.json"
 control="$project"_control; egress="$project"_egress; control_arg=-; egress_arg=-
 if docker_cmd network inspect "$control" >"$tmpdir/control.json" 2>/dev/null; then control_arg=$tmpdir/control.json; elif [ -n "$project_ids" ]; then echo "preflight=failed reason=control_network_missing" >&2; exit 1; fi
 if docker_cmd network inspect "$egress" >"$tmpdir/egress.json" 2>/dev/null; then egress_arg=$tmpdir/egress.json; elif [ -n "$project_ids" ]; then echo "preflight=failed reason=egress_network_missing" >&2; exit 1; fi
 python3 - "$tmpdir/actor.json" "$control_arg" "$egress_arg" "$tmpdir/ids" <<'PY'
import json,sys
ids=set()
for path in sys.argv[1:4]:
 if path!="-": ids.update((json.load(open(path))[0].get("Containers") or {}).keys())
open(sys.argv[4],"w").write("".join(f"{id}\n" for id in sorted(ids)))
PY
 if [ -n "$project_ids" ]; then printf '%s\n' $project_ids >>"$tmpdir/ids"; fi
 if [ -s "$volume_ids" ]; then cat "$volume_ids" >>"$tmpdir/ids"; fi
 sort -u "$tmpdir/ids" -o "$tmpdir/ids"
 if [ -s "$tmpdir/ids" ]; then docker_cmd inspect $(cat "$tmpdir/ids") >"$tmpdir/containers.json"; else printf '[]\n' >"$tmpdir/containers.json"; fi
 digests_arg=-
 if [ -n "$project_ids" ]; then digests_arg=$expected_digests; fi
 python3 "$script_dir/validate_runtime_state.py" preflight "$project" "$pgvol" "$appvol" "$actor" "$tmpdir/actor.json" "$control_arg" "$egress_arg" "$tmpdir/containers.json" "$digests_arg" -
 state=managed
fi
available_mib=$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)
[ "$available_mib" -ge 3072 ] || { echo "preflight=failed reason=host_memory" >&2; exit 1; }
printf 'preflight=passed project=%s resources=%s host_available_mib=%s\n' "$project" "$state" "$available_mib"
