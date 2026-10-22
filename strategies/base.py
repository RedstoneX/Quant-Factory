"""Minimal interface implemented by Quant Factory strategies."""

from typing import Any, Mapping, Protocol

import pandas as pd

from strategies.models import SignalResult, StrategySpecification


class Strategy(Protocol):
    @property
    def spec(self) -> StrategySpecification: ...

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]: ...

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult: ...
