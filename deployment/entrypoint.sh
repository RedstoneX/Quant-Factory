#!/bin/sh
set -eu

runtime_root=${QF_RUNTIME_ROOT:-/var/lib/quant-factory}

require_absolute_external_path() {
    name=$1
    value=$2
    case "$value" in
        /*) ;;
        *) echo "$name must be absolute" >&2; exit 64 ;;
    esac
    resolved=$(python3 -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).resolve())' "$value")
    case "$resolved" in
        "$runtime_root"|"$runtime_root"/*) ;;
        *) echo "$name must be an absolute path below $runtime_root" >&2; exit 64 ;;
    esac
}

: "${QUANT_FACTORY_DB_PATH:?QUANT_FACTORY_DB_PATH is required}"
: "${QUANT_FACTORY_ARTIFACT_ROOT:?QUANT_FACTORY_ARTIFACT_ROOT is required}"
: "${QUANT_FACTORY_DATA_LOCATIONS:?QUANT_FACTORY_DATA_LOCATIONS is required}"

case "$runtime_root" in
    /*) ;;
    *) echo "QF_RUNTIME_ROOT must be absolute" >&2; exit 64 ;;
esac
require_absolute_external_path QUANT_FACTORY_DB_PATH "$QUANT_FACTORY_DB_PATH"
require_absolute_external_path QUANT_FACTORY_ARTIFACT_ROOT "$QUANT_FACTORY_ARTIFACT_ROOT"

case "$QUANT_FACTORY_DATA_LOCATIONS" in
    /*) ;;
    *) echo "QUANT_FACTORY_DATA_LOCATIONS must be an absolute path" >&2; exit 64 ;;
esac

[ -d "$runtime_root" ] || { echo "runtime root is not mounted" >&2; exit 65; }
[ -d "$(dirname "$QUANT_FACTORY_DB_PATH")" ] || { echo "database parent is not mounted" >&2; exit 65; }
[ -d "$QUANT_FACTORY_ARTIFACT_ROOT" ] || { echo "artifact root is not mounted" >&2; exit 65; }
[ -w "$(dirname "$QUANT_FACTORY_DB_PATH")" ] || { echo "database parent is not writable" >&2; exit 65; }
[ -w "$QUANT_FACTORY_ARTIFACT_ROOT" ] || { echo "artifact root is not writable" >&2; exit 65; }
[ -r "$QUANT_FACTORY_DATA_LOCATIONS" ] || { echo "data-location config is not readable" >&2; exit 65; }
[ -d "$runtime_root/market-data" ] || { echo "market-data root is not mounted" >&2; exit 65; }

cd "$runtime_root"
exec "$@"
