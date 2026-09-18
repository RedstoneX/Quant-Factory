"""Prepare the explicitly labelled Milestone 23 browser acceptance fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from prefect_spike.milestone23_browser_fixture import (
    prepare_milestone23_browser_fixture,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the deterministic Milestone 23 infrastructure acceptance "
            "fixture. This is not production research evidence."
        )
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    prepare: Callable[..., object] = prepare_milestone23_browser_fixture,
) -> int:
    args = build_parser().parse_args(argv)
    summary = prepare(database=args.database, artifact_root=args.artifact_root)
    print(json.dumps(summary.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
