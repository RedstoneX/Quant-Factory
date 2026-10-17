"""Price download and top-up through VectorBT PRO's own data features.

One setting chooses the path: ``QF_PRICE_DOWNLOADER=vbt`` uses this module,
``legacy`` keeps the earlier code (``market_data.cache`` + ``providers.yahoo`` for
daily Yahoo data, ``providers.alpaca_sip.AlpacaSipProvider`` for the Alpaca SIP
one-minute library). The legacy modules are kept unchanged as the backup.

What VectorBT does here (this module only translates):
- first download: ``vbt.YFData.pull`` / ``vbt.AlpacaData.pull``
- top-up: ``data.update(end=..., return_meta=True)``, which re-fetches the last
  stored bar and reports it under ``revised`` if its prices moved. For Alpaca SIP the
  stored data is first cut (``data.loc``) before the most recent session, so that whole
  session is re-fetched: the vendor fills late gaps and corrects bars there. A revised or
  removed bar means the provider re-adjusted history (split or dividend), so the
  symbol is pulled again in full instead of mixing adjustment bases.
- first VBT run over an existing store: the saved VBT copy is seeded from the stored,
  validated bars with ``AlpacaData.from_data`` (no history download), then topped up
  like any other run. A full ``pull`` happens only when nothing is stored yet.
- persistence: ``data.save(path)`` / ``vbt.load(path)``. API keys are set with
  ``AlpacaData.set_custom_settings`` so they are never stored in the saved file.

The Alpaca SIP path still commits through the legacy slot/manifest/validation
store, so every reader and every integrity check stays exactly as before; the
prefix check there also proves on live data that a VBT top-up reproduces the
stored bars.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
import warnings

import pandas as pd

from backtesting.vectorbt_runtime import require_vectorbtpro
from market_data.alpaca_sip_universe import HISTORY_START
from market_data.models import MarketDataConfig, OHLCV_COLUMNS
from market_data.providers.alpaca import VBT_ALPACA_COLUMNS
from market_data.providers.alpaca_sip import (
    ADJUSTMENT,
    FEED,
    MARKET_TIMEZONE,
    AlpacaSipError,
    AlpacaSipProvider,
    SipDataset,
    TopUpResult,
    bars_to_frame,
    ends_at_or_after,
    last_session_start,
    mark_sessions,
    same_bars,
)
from market_data.alpaca_sip_universe import asset_type

PRICE_DOWNLOADER_VARIABLE = "QF_PRICE_DOWNLOADER"
PRICE_DOWNLOADERS = ("vbt", "legacy")
DEFAULT_PRICE_DOWNLOADER = "vbt"  # QF_PRICE_DOWNLOADER=legacy selects the old downloader


def price_downloader(environ: Mapping[str, str] | None = None) -> str:
    """Return ``vbt`` or ``legacy`` from ``QF_PRICE_DOWNLOADER``."""
    values = os.environ if environ is None else environ
    choice = values.get(PRICE_DOWNLOADER_VARIABLE, DEFAULT_PRICE_DOWNLOADER).strip().lower()
    if choice not in PRICE_DOWNLOADERS:
        raise ValueError(f"{PRICE_DOWNLOADER_VARIABLE} must be one of {PRICE_DOWNLOADERS}, not {choice!r}")
    return choice


@dataclass(frozen=True)
class VbtPull:
    data: Any  # vbt.Data
    status: str  # full | incremental | refetched_after_adjustment_change | current


def pull_or_update(
    data_cls: Any, path: Path, symbol: str, *, end: Any, keep_before: Any = None, **pull_kwargs: Any
) -> VbtPull:
    """Load ``path`` and ``update`` it, or ``pull`` in full; save when anything changed.

    ``keep_before`` drops stored bars at or after it first, so ``update`` re-fetches them.
    """
    vbt = require_vectorbtpro()
    status = "full"
    if path.is_file():
        stored = vbt.load(path)
        stored_kwargs = stored.select_fetch_kwargs(symbol)
        same_request = all(stored_kwargs.get(key) == value for key, value in pull_kwargs.items())
        if same_request and keep_before is not None:
            kept = stored.wrapper.index < keep_before
            stored = stored.loc[kept] if kept.any() else None
        if same_request and stored is not None:
            meta = stored.update(end=end, return_meta=True, silence_warnings=True)
            if len(meta["revised"]) or len(meta["removed"]):
                status = "refetched_after_adjustment_change"
            else:
                status = "incremental" if len(meta["appended"]) else "current"
                if status == "incremental":
                    _save(meta["data"], path)
                return VbtPull(meta["data"], status)
    data = data_cls.pull(symbol, end=end, silence_warnings=True, **pull_kwargs)
    _save(data, path)
    return VbtPull(data, status)


def _save(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + "_tmp" + path.suffix)  # VBT reads extra dots as formats
    written = data.save(tmp)
    os.replace(written, path)


def yahoo_store_path(config: MarketDataConfig) -> Path:
    return config.cache_path.with_name(config.cache_path.stem.replace(".", "_") + "_vbt.pickle")


def download_yahoo_data(
    config: MarketDataConfig, completed_through: pd.Timestamp
) -> tuple[pd.DataFrame, list[str]]:
    """Same output as ``providers.yahoo.download_yahoo_data``, topped up incrementally."""
    vbt = require_vectorbtpro()
    end_exclusive = (pd.Timestamp(completed_through) + pd.Timedelta(days=1)).date().isoformat()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            pulled = pull_or_update(
                vbt.YFData,
                yahoo_store_path(config),
                config.symbol,
                end=end_exclusive,
                start=config.requested_start,
                timeframe=config.interval,
                tz=config.market_timezone,
                auto_adjust=config.adjusted,
                actions=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Yahoo Finance download failed: {exc}") from exc
    data = pulled.data
    if len(data.index) == 0:
        raise RuntimeError("Yahoo Finance returned no market data")
    frame = pd.concat({column: data.get(column) for column in OHLCV_COLUMNS}, axis=1)
    frame = frame.loc[frame.index < pd.Timestamp(end_exclusive, tz=frame.index.tz)]
    return frame, [str(warning.message) for warning in caught]


def sip_store_path(locations: Any, symbol: str) -> Path:
    relative = SipDataset(symbol).slot_relative_path("a")
    return locations.root / "vbt" / relative.parent / f"{symbol}_1m_alpaca_sip_vbt.pickle"


def vbt_bars_to_frame(data: Any) -> pd.DataFrame:
    """VBT Alpaca data -> the stored SIP column layout (as ``fetch_alpaca_bars`` returns)."""
    raw = data.get()
    frame = raw.rename(columns=VBT_ALPACA_COLUMNS).reindex(columns=list(VBT_ALPACA_COLUMNS.values()))
    frame.insert(0, "timestamp", pd.DatetimeIndex(raw.index).tz_convert("UTC").astype("datetime64[ns, UTC]"))
    return bars_to_frame(frame.reset_index(drop=True))


def seed_from_stored(data_cls: Any, symbol: str, stored_bars: pd.DataFrame, pull_kwargs: dict) -> Any:
    """Stored SIP bars -> VBT Alpaca data, as ``pull`` would have returned them (``from_data``)."""
    names = {stored: vbt_name for vbt_name, stored in VBT_ALPACA_COLUMNS.items()}
    frame = stored_bars.set_index(pd.DatetimeIndex(stored_bars["timestamp"], name=None))
    frame = frame[list(names)].rename(columns=names).astype({"Trade count": "float64"})
    return data_cls.from_data({symbol: frame}, fetch_kwargs={symbol: dict(pull_kwargs)})


class VbtSipProvider(AlpacaSipProvider):
    """Alpaca SIP top-up via ``vbt.AlpacaData.pull`` / ``update`` / ``save``.

    Commits through the legacy store (slots, manifest, validation, quarantine).
    """

    def top_up(self, symbol: str, *, since: str = HISTORY_START) -> TopUpResult:
        dataset = SipDataset(symbol)
        asset_type(symbol)
        end = self.available_end()
        target, existing = self._committed(dataset)
        slot = "b" if target is not None and target.name.endswith(".a.parquet") else "a"
        if existing is not None and not existing.empty and existing["timestamp"].iloc[-1] >= end:
            return TopUpResult(symbol, "current", len(existing), 0, target)
        data_cls = self.alpaca_data or require_vectorbtpro().AlpacaData
        data_cls.set_custom_settings(
            client_config=dict(api_key=self.credentials.key_id, secret_key=self.credentials.secret_key)
        )
        has_existing = existing is not None and not existing.empty
        store_path = sip_store_path(self.locations, symbol)
        pull_kwargs = dict(
            start=pd.Timestamp(since, tz=MARKET_TIMEZONE),
            client_type="stocks",
            timeframe="1m",
            feed=FEED,
            adjustment=ADJUSTMENT,
            sort="asc",
        )
        if has_existing and not store_path.exists():
            # First VBT run over an existing store: seed the VBT copy from the stored bars
            # instead of downloading the whole history again (that pull ran out of memory).
            _save(seed_from_stored(data_cls, symbol, existing, pull_kwargs), store_path)
        # Re-fetch the whole most recent session (late vendor gap fills and corrections).
        session_start = last_session_start(existing["timestamp"]) if has_existing else None
        try:
            pulled = pull_or_update(
                data_cls,
                store_path,
                symbol,
                end=end + pd.Timedelta(minutes=1),  # VBT's end is exclusive
                keep_before=session_start,
                **pull_kwargs,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            raise AlpacaSipError(f"Alpaca bars request failed: HTTP {status} {type(exc).__name__}: {exc}") from exc
        frame = mark_sessions(vbt_bars_to_frame(pulled.data))
        if has_existing and (not ends_at_or_after(frame, existing) or same_bars(frame, existing)):
            return TopUpResult(symbol, "current", len(existing), 0, target)
        adjusted = pulled.status == "refetched_after_adjustment_change"
        # Every bar before the re-fetched session must still match byte-for-byte.
        previous = existing.loc[existing["timestamp"] < session_start] if has_existing and not adjusted else None
        if not has_existing:
            mode = "full"
        else:
            mode = "refetched_after_adjustment_change" if adjusted else "incremental"
        start = frame["timestamp"].iloc[0]
        stored_rows = len(existing) if has_existing else None
        return self._store(dataset, frame, previous, mode, start, end, slot, stored_rows=stored_rows)


def sip_provider_class(environ: Mapping[str, str] | None = None) -> type[AlpacaSipProvider]:
    return VbtSipProvider if price_downloader(environ) == "vbt" else AlpacaSipProvider
