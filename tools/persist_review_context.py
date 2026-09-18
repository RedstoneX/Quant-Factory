"""Persist one explicit durable-review context artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

from persistence import PersistenceService
from persistence.evidence_service import ValidationEvidenceArtifactService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist an explicit Quant Factory durable-review context."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--target-run-id", required=True)
    parser.add_argument("--source-lock-run-id", required=True)
    parser.add_argument("--source-lock-artifact-id", required=True, type=int)
    parser.add_argument("--walk-forward-run-id", required=True)
    parser.add_argument("--monte-carlo-run-id", required=True)
    parser.add_argument("--robustness-run-id", required=True)
    parser.add_argument(
        "--protected-data-state",
        required=True,
        choices=("gated", "spent", "invalid"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = PersistenceService(args.database)
    try:
        record = ValidationEvidenceArtifactService(service).persist_review_context(
            target_run_id=args.target_run_id,
            source_lock_run_id=args.source_lock_run_id,
            source_lock_artifact_id=args.source_lock_artifact_id,
            walk_forward_run_id=args.walk_forward_run_id,
            monte_carlo_run_id=args.monte_carlo_run_id,
            robustness_run_id=args.robustness_run_id,
            protected_data_state=args.protected_data_state,
            artifact_root=args.artifact_root,
        )
    finally:
        service.close()
    print(record.context_identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
