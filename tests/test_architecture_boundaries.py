"""Contract tests for the deterministic architecture dependency guard."""

from __future__ import annotations

import json
from pathlib import Path

from tools.check_architecture import (
    Edge,
    analyze_repository,
    main,
    write_baseline,
)


def _write_policy(root: Path, *, a_allows_b: bool) -> Path:
    policy = root / "architecture.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "components": {
                    "a": {
                        "patterns": ["a"],
                        "allowed_dependencies": ["b"] if a_allows_b else [],
                    },
                    "b": {"patterns": ["b"], "allowed_dependencies": []},
                    "c": {"patterns": ["c"], "allowed_dependencies": []},
                },
            }
        ),
        encoding="utf-8",
    )
    return policy


def test_analyzer_separates_runtime_and_type_checking_imports(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from typing import TYPE_CHECKING\nimport b\nif TYPE_CHECKING:\n    import c\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("VALUE = 2\n", encoding="utf-8")
    policy = _write_policy(tmp_path, a_allows_b=True)

    analysis, errors = analyze_repository(tmp_path, policy)

    assert errors == []
    assert analysis is not None
    assert Edge("a", "b") in analysis.runtime_edges
    assert Edge("a", "c") not in analysis.runtime_edges
    assert Edge("a", "c") in analysis.type_only_edges


def test_guard_rejects_then_accepts_a_temporary_forbidden_dependency(
    tmp_path: Path,
) -> None:
    source = tmp_path / "a.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("VALUE = 3\n", encoding="utf-8")
    policy = _write_policy(tmp_path, a_allows_b=False)
    baseline = tmp_path / "baseline.json"
    analysis, errors = analyze_repository(tmp_path, policy)
    assert errors == [] and analysis is not None
    write_baseline(baseline, analysis)

    source.write_text("import b\nVALUE = 1\n", encoding="utf-8")
    assert main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--baseline",
            str(baseline),
        ]
    ) == 1

    source.write_text("VALUE = 1\n", encoding="utf-8")
    assert main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--baseline",
            str(baseline),
        ]
    ) == 0


def test_current_repository_matches_its_ratcheting_baseline() -> None:
    root = Path(__file__).resolve().parents[1]

    assert main(["--root", str(root)]) == 0
