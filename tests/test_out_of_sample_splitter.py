import pandas as pd

from backtesting.out_of_sample import ChronologicalSplitConfig, split_chronologically


def _bars(days: int, freq: str) -> pd.DataFrame:
    sessions = pd.bdate_range("2024-01-02", periods=days, tz="America/New_York")
    parts = [
        pd.date_range(d + pd.Timedelta(hours=9, minutes=30), periods=26, freq=freq)
        for d in sessions
    ]
    index = parts[0].append(parts[1:])
    values = pd.Series(range(len(index)), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": values, "High": values, "Low": values, "Close": values, "Volume": 1},
        index=index,
    )


def test_intraday_split_holds_whole_days_and_no_date_in_two_partitions():
    # 7 sessions x 26 bars: a row-fraction cut lands mid-day (0.6 * 182 = 109.2).
    data = _bars(7, "15min")
    split = split_chronologically(
        data, ChronologicalSplitConfig(minimum_rows_per_partition=10)
    )
    parts = (split.train, split.selection, split.test)
    dates = [set(p.data.index.normalize()) for p in parts]
    assert dates[0].isdisjoint(dates[1])
    assert dates[1].isdisjoint(dates[2])
    assert dates[0].isdisjoint(dates[2])
    assert sum(p.row_count for p in parts) == len(data)
    assert split.train.end < split.selection.start < split.test.start


def test_daily_counts_unchanged():
    index = pd.date_range("2020-01-01", periods=100, freq="D", tz="America/New_York")
    data = pd.DataFrame({"Close": range(100)}, index=index, dtype=float)
    split = split_chronologically(
        data, ChronologicalSplitConfig(minimum_rows_per_partition=10)
    )
    assert (split.train.row_count, split.selection.row_count, split.test.row_count) == (
        60,
        20,
        20,
    )
