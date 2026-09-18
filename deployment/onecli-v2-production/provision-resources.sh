#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then echo "usage: $0 /absolute/runtime.env /absolute/secrets.env" >&2; exit 64; fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd); repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
docker_cmd(){ sudo -n docker "$@"; }
safe=$(python3 "$script_dir/validate_inputs.py" "$1" "$2" "$repo_root")
field(){ python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1" <<<"$safe"; }
project=$(field QF_ONECLI_PROJECT); pgvol=$(field QF_ONECLI_POSTGRES_VOLUME); appvol=$(field QF_ONECLI_APP_VOLUME); actor=$(field QF_ONECLI_ACTOR_NETWORK)
[ -z "$(docker_cmd ps -aq --filter "label=com.docker.compose.project=$project")" ] || { echo "provision=failed reason=project_collision" >&2; exit 1; }
for spec in "volume:$pgvol" "volume:$appvol" "network:$actor"; do kind=${spec%%:*}; name=${spec#*:}; ! docker_cmd "$kind" inspect "$name" >/dev/null 2>&1 || { echo "provision=failed reason=resource_collision" >&2; exit 1; }; done
tmpdir=$(mktemp -d); created_pg=0; created_app=0; created_net=0
cleanup(){ code=$?; if [ "$code" -ne 0 ]; then [ "$created_net" -eq 0 ] || docker_cmd network rm "$actor" >/dev/null; [ "$created_app" -eq 0 ] || docker_cmd volume rm "$appvol" >/dev/null; [ "$created_pg" -eq 0 ] || docker_cmd volume rm "$pgvol" >/dev/null; fi; rm -rf "$tmpdir"; exit "$code"; }; trap cleanup EXIT
docker_cmd volume create --label com.quant-factory.stack=onecli-v2-production --label "com.quant-factory.project=$project" --label com.quant-factory.role=postgres-data "$pgvol" >/dev/null
docker_cmd volume inspect "$pgvol" >"$tmpdir/pg.json"; python3 "$script_dir/validate_resource.py" volume "$pgvol" "$project" postgres-data "$tmpdir/pg.json"; created_pg=1
docker_cmd volume create --label com.quant-factory.stack=onecli-v2-production --label "com.quant-factory.project=$project" --label com.quant-factory.role=app-data "$appvol" >/dev/null
docker_cmd volume inspect "$appvol" >"$tmpdir/app.json"; python3 "$script_dir/validate_resource.py" volume "$appvol" "$project" app-data "$tmpdir/app.json"; created_app=1
docker_cmd network create --driver bridge --internal --label com.quant-factory.stack=onecli-v2-production --label "com.quant-factory.project=$project" --label com.quant-factory.role=actor "$actor" >/dev/null
docker_cmd network inspect "$actor" >"$tmpdir/actor.json"; python3 "$script_dir/validate_resource.py" network "$actor" "$project" actor "$tmpdir/actor.json"; created_net=1
trap - EXIT; rm -rf "$tmpdir"
printf 'provision=passed project=%s volumes=2 actor_network=%s\n' "$project" "$actor"
