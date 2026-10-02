"""Focused contracts for the structural-maintainability ratchet."""

from __future__ import annotations

import json
from pathlib import Path

from tools.check_structural_maintainability import (
    Baseline,
    FILE_LIMIT,
    FUNCTION_LIMIT,
    baseline_document,
    compare_baselines,
    compare_measurement,
    main,
    measure_repository,
    parse_baseline,
)


def _oversized_module(*, file_lines: int = 610, function_lines: int = 160) -> str:
    lines = ["def oversized():"]
    lines.extend("    value = 1" for _ in range(function_lines - 2))
    lines.append("    return value")
    lines.extend("# file padding" for _ in range(file_lines - len(lines)))
    assert len(lines) == file_lines
    return "\n".join(lines) + "\n"


def _baseline(measurement) -> Baseline:
    baseline, errors = parse_baseline(baseline_document(measurement), source="test")
    assert errors == []
    assert baseline is not None
    return baseline


def test_measurement_uses_qualified_function_identity_and_exact_sizes(tmp_path: Path) -> None:
    source = tmp_path / "large.py"
    source.write_text(_oversized_module(), encoding="utf-8")

    measurement = measure_repository(tmp_path, ["large.py"])

    assert measurement.oversized_files == {"large.py": 610}
    assert list(measurement.oversized_functions.values()) == [160]
    identity = next(iter(measurement.oversized_functions))
    assert json.loads(identity) == ["large.py", "oversized", "FunctionDef", 1]
    assert compare_measurement(measurement, _baseline(measurement)) == []


def test_size_ratchets_reject_new_growth_and_stale_reductions(tmp_path: Path) -> None:
    source = tmp_path / "large.py"
    source.write_text(_oversized_module(), encoding="utf-8")
    initial = measure_repository(tmp_path, ["large.py"])
    baseline = _baseline(initial)

    source.write_text(_oversized_module(file_lines=611, function_lines=161), encoding="utf-8")
    growth = compare_measurement(measure_repository(tmp_path, ["large.py"]), baseline)
    assert any("oversized source file grew" in error for error in growth)
    assert any("oversized function grew" in error for error in growth)

    source.write_text(_oversized_module(file_lines=609, function_lines=159), encoding="utf-8")
    stale = compare_measurement(measure_repository(tmp_path, ["large.py"]), baseline)
    assert any("stale source file allowance must shrink" in error for error in stale)
    assert any("stale function allowance must shrink" in error for error in stale)

    second = tmp_path / "second.py"
    second.write_text(_oversized_module(), encoding="utf-8")
    new = compare_measurement(
        measure_repository(tmp_path, ["large.py", "second.py"]),
        _baseline(measure_repository(tmp_path, ["large.py"])),
    )
    assert any("new oversized source file: second.py" in error for error in new)
    assert any("new oversized function" in error and "second.py" in error for error in new)


def test_broad_handler_identity_survives_line_shifts_and_ratchets_removal(tmp_path: Path) -> None:
    source = tmp_path / "runtime.py"
    body = (
        "def operation():\n"
        "    try:\n"
        "        return work()\n"
        "    except Exception:\n"
        "        return None\n"
    )
    source.write_text(body, encoding="utf-8")
    initial = measure_repository(tmp_path, ["runtime.py"])
    assert len(initial.broad_nonreraising_handlers) == 1
    identity = next(iter(initial.broad_nonreraising_handlers))
    assert json.loads(identity) == ["runtime.py", "operation", "Exception", 1]

    source.write_text("\n\n" + body, encoding="utf-8")
    shifted = measure_repository(tmp_path, ["runtime.py"])
    assert shifted.broad_nonreraising_handlers == initial.broad_nonreraising_handlers

    source.write_text(body.replace("        return None", "        raise"), encoding="utf-8")
    removed = compare_measurement(measure_repository(tmp_path, ["runtime.py"]), _baseline(initial))
    assert removed == [f"stale broad-handler allowance must be removed: {identity}"]


def test_prohibited_constructor_bypass_and_licensed_test_double_are_detected(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    source = tests / "test_contract.py"
    source.write_text(
        "import pytest\n"
        "class Value: pass\n"
        "def test_bypass():\n"
        "    object.__new__(Value)\n"
        "@pytest.mark.licensed_vectorbt\n"
        "def test_licensed(monkeypatch):\n"
        "    monkeypatch.setattr(Value, 'answer', 1)\n",
        encoding="utf-8",
    )

    measurement = measure_repository(tmp_path, ["tests/test_contract.py"])

    assert len(measurement.hard_constructor_bypasses) == 1
    assert measurement.hard_constructor_bypasses[0].owner == "test_bypass"
    assert measurement.licensed_test_doubles
    errors = compare_measurement(measurement, _baseline(measurement))
    assert any("hard constructor bypass" in error for error in errors)
    assert any("licensed VectorBT test double" in error for error in errors)


def test_real_licensed_test_without_double_is_allowed(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_real.py").write_text(
        "import pytest\n"
        "@pytest.mark.licensed_vectorbt\n"
        "def test_real_engine():\n"
        "    import vectorbtpro as vbt\n"
        "    assert vbt is not None\n",
        encoding="utf-8",
    )

    measurement = measure_repository(tmp_path, ["tests/test_real.py"])

    assert measurement.licensed_test_doubles == ()
    assert measurement.hard_constructor_bypasses == ()


def test_baseline_is_monotonic_but_may_shrink() -> None:
    prior = Baseline({"large.py": 700}, {"fn": 200}, frozenset({"handler"}))

    assert compare_baselines(
        Baseline({"large.py": 699}, {"fn": 199}, frozenset()), prior
    ) == []
    errors = compare_baselines(
        Baseline(
            {"large.py": 701, "new.py": 650},
            {"fn": 201, "new-fn": 180},
            frozenset({"handler", "new-handler"}),
        ),
        prior,
    )
    assert any("may not raise oversized source file" in error for error in errors)
    assert any("may not add oversized source file" in error for error in errors)
    assert any("may not raise oversized function" in error for error in errors)
    assert any("may not add oversized function" in error for error in errors)
    assert any("may not add broad non-reraising handler" in error for error in errors)


def test_baseline_schema_cannot_loosen_limits_or_grandfather_small_items() -> None:
    document = {
        "schema_version": 1,
        "limits": {"source_file_lines": FILE_LIMIT + 1, "python_function_lines": FUNCTION_LIMIT},
        "oversized_source_files": {"small.py": FILE_LIMIT},
        "oversized_python_functions": {"small": FUNCTION_LIMIT},
        "runtime_broad_nonreraising_handlers": [],
    }

    baseline, errors = parse_baseline(document, source="test")

    assert baseline is None
    assert any("limits must remain" in error for error in errors)
    assert any("source-file allowance at or below" in error for error in errors)
    assert any("function allowance at or below" in error for error in errors)


def test_current_repository_matches_structural_baseline() -> None:
    root = Path(__file__).resolve().parents[1]

    assert main(["--root", str(root)]) == 0
