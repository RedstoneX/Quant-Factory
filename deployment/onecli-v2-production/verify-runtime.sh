#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "$#" -ne 2 ]; then echo "usage: $0 /absolute/runtime.env /absolute/secrets.env" >&2; exit 64; fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd); repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
docker_cmd(){ sudo -n docker "$@"; }
runtime_env=$1; secrets_env=$2
safe=$(python3 "$script_dir/validate_inputs.py" "$runtime_env" "$secrets_env" "$repo_root")
field(){ python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1" <<<"$safe"; }
project=$(field QF_ONECLI_PROJECT); pgvol=$(field QF_ONECLI_POSTGRES_VOLUME); appvol=$(field QF_ONECLI_APP_VOLUME); actor=$(field QF_ONECLI_ACTOR_NETWORK); control="$project"_control; egress="$project"_egress
tmpdir=$(mktemp -d); chmod 700 "$tmpdir"; cleanup(){ rm -rf "$tmpdir"; }; trap cleanup EXIT; trap 'exit 1' HUP INT TERM
expected_digests=$tmpdir/expected-secret-digests.json
python3 "$script_dir/derive_secret_digests.py" "$secrets_env" "$expected_digests"
probe_image=python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
docker_cmd image inspect "$probe_image" >/dev/null 2>&1 || { echo "health=failed reason=probe_image_missing" >&2; exit 1; }
inventory_volume_consumers(){
 target=$1
 : >"$target"
 for spec in "$pgvol:postgres" "$appvol:api,gateway"; do
  name=${spec%%:*}; allowed=${spec#*:}
  while IFS= read -r id; do
   [ -n "$id" ] || continue
   consumer_project=$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$id")
   consumer_service=$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$id")
   case ",$allowed," in *",$consumer_service,"*) :;; *) echo "runtime=failed reason=volume_consumer" >&2; exit 1;; esac
   [ "$consumer_project" = "$project" ] || { echo "runtime=failed reason=volume_consumer" >&2; exit 1; }
   printf '%s\n' "$id" >>"$target"
  done < <(docker_cmd ps -aq --no-trunc --filter "volume=$name")
 done
 sort -u "$target" -o "$target"
}
capture_and_validate(){
 suffix=$1
 docker_cmd network inspect "$actor" >"$tmpdir/actor-$suffix.json"
 docker_cmd network inspect "$control" >"$tmpdir/control-$suffix.json"
 docker_cmd network inspect "$egress" >"$tmpdir/egress-$suffix.json"
 python3 - "$tmpdir/actor-$suffix.json" "$tmpdir/control-$suffix.json" "$tmpdir/egress-$suffix.json" "$tmpdir/ids-$suffix" <<'PY'
import json,sys
ids=set()
for path in sys.argv[1:4]: ids.update((json.load(open(path))[0].get("Containers") or {}).keys())
open(sys.argv[4],"w").write("".join(f"{id}\n" for id in sorted(ids)))
PY
 docker_cmd ps -aq --no-trunc --filter "label=com.docker.compose.project=$project" >>"$tmpdir/ids-$suffix"
 inventory_volume_consumers "$tmpdir/volume-ids-$suffix"
 if [ -s "$tmpdir/volume-ids-$suffix" ]; then cat "$tmpdir/volume-ids-$suffix" >>"$tmpdir/ids-$suffix"; fi
 sort -u "$tmpdir/ids-$suffix" -o "$tmpdir/ids-$suffix"
 [ -s "$tmpdir/ids-$suffix" ] || { echo "runtime=failed reason=service_set" >&2; exit 1; }
 docker_cmd inspect $(cat "$tmpdir/ids-$suffix") >"$tmpdir/containers-$suffix.json"
 gateway_id=$(docker_cmd ps -q --no-trunc --filter "label=com.docker.compose.project=$project" --filter "label=com.docker.compose.service=gateway")
 [ -n "$gateway_id" ] && [ "${gateway_id#*$'\n'}" = "$gateway_id" ] || { echo "runtime=failed reason=gateway_identity" >&2; exit 1; }
 timeout --signal=TERM --kill-after=5s 30s sudo -n docker run --rm -i --pull never --network "container:$gateway_id" --read-only --tmpfs /tmp:rw,nosuid,nodev,noexec,size=8m --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 32 --memory 64m --cpus 0.25 --user 65532:65532 "$probe_image" python - <"$script_dir/capture_gateway_topology.py" >"$tmpdir/gateway-topology-$suffix.json"
 python3 "$script_dir/validate_runtime_state.py" post-start "$project" "$pgvol" "$appvol" "$actor" "$tmpdir/actor-$suffix.json" "$tmpdir/control-$suffix.json" "$tmpdir/egress-$suffix.json" "$tmpdir/containers-$suffix.json" "$expected_digests" "$tmpdir/gateway-topology-$suffix.json"
}
capture_and_validate before
timeout --signal=TERM --kill-after=5s 30s sudo -n docker run --rm -i --pull never --network "$control" --read-only --tmpfs /tmp:rw,nosuid,nodev,noexec,size=8m --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 32 --memory 64m --cpus 0.25 --user 65532:65532 "$probe_image" python - <"$script_dir/probe_internal_health.py"
capture_and_validate after
printf 'health=passed gateway=healthy api=healthy web=healthy exposure=private\n'
