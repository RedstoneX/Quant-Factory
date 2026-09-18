"""Dependency-boundary checks for the public CI environment."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from typing import Any, get_type_hints

import pandas as pd
import pytest

import backtesting.experiments.runner as experiment_runner
import backtesting.vectorbt_runtime as vectorbt_runtime
import market_data.providers.yahoo as yahoo_provider
import prefect_spike.spym_vectorbt_fixture as spym_fixture
import strategies.rsi_mean_reversion as rsi_mean_reversion
from backtesting.experiments import ExecutionConfig
from backtesting.vectorbt_runtime import VectorBTProUnavailableError
from strategies.models import SignalResult
from tools import assert_junit_report


def test_market_data_import_does_not_require_vectorbtpro() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import market_data, sys; assert 'vectorbtpro' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_stored_evidence_interfaces_import_without_vectorbtpro() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import dashboard, persistence, backtesting.experiments, strategies, sys; "
                "from dashboard import SelectedPortfolioData; "
                "from persistence import PersistenceService; "
                "from backtesting.experiments import ExperimentConfig; "
                "from strategies import get_strategy; "
                "assert 'vectorbtpro' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_experiment_runner_type_hints_resolve_without_vectorbtpro() -> None:
    assert get_type_hints(experiment_runner._construct_portfolio)["return"] is Any
    assert get_type_hints(experiment_runner.build_portfolio)["return"] is Any
    assert get_type_hints(experiment_runner.extract_metrics)["portfolio"] is Any


def _missing_vectorbtpro() -> None:
    raise VectorBTProUnavailableError(
        "VectorBT Pro is required for this research operation"
    )


def test_vectorbt_loader_reports_the_licensed_engine_boundary(monkeypatch) -> None:
    def missing_module(name: str):
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.setattr(vectorbt_runtime, "import_module", missing_module)

    with pytest.raises(
        VectorBTProUnavailableError,
        match="separately licensed engine",
    ):
        vectorbt_runtime.require_vectorbtpro()


def test_vectorbt_loader_does_not_mask_a_missing_transitive_dependency(
    monkeypatch,
) -> None:
    def missing_dependency(_name: str):
        raise ModuleNotFoundError("No module named 'llvmlite'", name="llvmlite")

    monkeypatch.setattr(vectorbt_runtime, "import_module", missing_dependency)

    with pytest.raises(ModuleNotFoundError, match="llvmlite"):
        vectorbt_runtime.require_vectorbtpro()


def test_rsi_calculation_loads_vectorbtpro_only_when_invoked(monkeypatch) -> None:
    monkeypatch.setattr(rsi_mean_reversion, "require_vectorbtpro", _missing_vectorbtpro)
    close = pd.Series([100.0, 99.0, 98.0])

    with pytest.raises(
        VectorBTProUnavailableError,
        match="required for this research operation",
    ):
        rsi_mean_reversion.generate_signals(close, 7, 20, 50)


def test_portfolio_construction_loads_vectorbtpro_only_when_invoked(monkeypatch) -> None:
    monkeypatch.setattr(experiment_runner, "require_vectorbtpro", _missing_vectorbtpro)
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    data = pd.DataFrame(
        {"Open": [100.0, 101.0], "Close": [100.5, 101.5]},
        index=index,
    )
    signals = SignalResult(
        entries=pd.Series([False, True], index=index),
        exits=pd.Series([False, False], index=index),
        parameters={},
    )
    config = SimpleNamespace(
        execution=ExecutionConfig.next_bar_open(
            initial_cash=10_000,
            fees=0.0,
            slippage=0.0,
            direction="longonly",
            leverage=1.0,
            accumulate=False,
        )
    )

    with pytest.raises(
        VectorBTProUnavailableError,
        match="required for this research operation",
    ):
        experiment_runner._construct_portfolio(data, signals, config)


def test_yahoo_provider_loads_vectorbtpro_only_when_invoked(monkeypatch) -> None:
    monkeypatch.setattr(yahoo_provider, "require_vectorbtpro", _missing_vectorbtpro)

    with pytest.raises(
        VectorBTProUnavailableError,
        match="required for this research operation",
    ):
        yahoo_provider.download_yahoo_data(None, None)


def test_spym_benchmark_loads_vectorbtpro_only_when_invoked(monkeypatch) -> None:
    monkeypatch.setattr(spym_fixture, "require_vectorbtpro", _missing_vectorbtpro)

    with pytest.raises(
        VectorBTProUnavailableError,
        match="required for this research operation",
    ):
        spym_fixture._benchmark_document(None, None)


def test_junit_report_accepts_matching_nested_testcase_counts(tmp_path, monkeypatch) -> None:
    report = tmp_path / "portable.xml"
    report.write_text(
        "<testsuites><testsuite name=\"portable\" tests=\"2\" skipped=\"0\" "
        "failures=\"0\" errors=\"0\"><testcase/><testcase/></testsuite></testsuites>"
    )
    monkeypatch.setattr(sys, "argv", ["assert_junit_report.py", str(report)])

    assert assert_junit_report.main() == 0


@pytest.mark.parametrize(
    "xml",
    [
        '<testsuite tests="0" skipped="0" failures="0" errors="0"/>',
        '<testsuite tests="1" skipped="0" failures="0" errors="0"/>',
        '<testsuite tests="1" skipped="0" failures="0" errors="0"><testcase><skipped/></testcase></testsuite>',
        '<testsuite tests="many" skipped="0" failures="0" errors="0"><testcase/></testsuite>',
        '<testsuites><testsuite tests="1" skipped="0" failures="0" errors="0"><testcase/><testcase/></testsuite></testsuites>',
        '<testsuites tests="2" skipped="0" failures="0" errors="0"><testsuite tests="1" skipped="0" failures="0" errors="0"><testcase/></testsuite></testsuites>',
    ],
)
def test_junit_report_rejects_invalid_or_non_passing_counts(tmp_path, monkeypatch, xml) -> None:
    report = tmp_path / "portable.xml"
    monkeypatch.setattr(sys, "argv", ["assert_junit_report.py", str(report)])
    report.write_text(xml)

    assert assert_junit_report.main() == 1
