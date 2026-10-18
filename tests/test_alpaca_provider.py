"""Tests for the Alpaca request identity and credential loader kept after the old bulk downloader was removed."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from market_data.providers.alpaca import AlpacaBarsRequest, AlpacaCredentials


def test_feed_is_part_of_dataset_identity() -> None:
    iex = AlpacaBarsRequest(feed="iex")
    sip = replace(
        AlpacaBarsRequest(feed="sip"),
        dataset_id="equities_SPY_1m_alpaca_sip",
        filename="SPY_1m_alpaca_sip.parquet",
    )
    assert "iex" in iex.dataset_id
    assert "iex" in iex.canonical_relative_path.name
    assert "sip" in sip.dataset_id
    assert "sip" in sip.canonical_relative_path.name
    assert iex.canonical_relative_path != sip.canonical_relative_path


def test_credentials_loader_accepts_shell_export_lines(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text(
        "export APCA_API_KEY_ID='id-value'\n"
        'export APCA_API_SECRET_KEY="secret-value"\n'
        "IGNORED=value\n",
        encoding="utf-8",
    )
    credentials = AlpacaCredentials.from_env_file(secrets)
    assert credentials.key_id == "id-value"
    assert credentials.secret_key == "secret-value"
