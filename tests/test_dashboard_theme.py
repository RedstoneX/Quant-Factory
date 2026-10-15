"""The shared Dashboard theme: one Plotly default, one AG Grid theme, nothing under 11px."""

from __future__ import annotations

from pathlib import Path
import re

import plotly.io as pio

from dashboard.ui import theme

ASSETS = Path(__file__).resolve().parents[1] / "dashboard" / "ui" / "assets"


def test_plotly_default_template_is_qf() -> None:
    assert pio.templates.default == "qf"
    assert pio.templates["qf"].layout.font.size == 13


def test_grid_theme_is_shared_quartz_params() -> None:
    options = theme.grid_options("Nothing here.")
    assert options["theme"]["function"].startswith("themeQuartz.withParams(")
    assert options["localeText"]["noRowsToShow"] == "Nothing here."


def test_mantine_theme_type_scale_has_no_text_under_11px() -> None:
    sizes = [int(value.removesuffix("px")) for value in theme.MANTINE_THEME["fontSizes"].values()]
    assert min(sizes) >= 11


def test_css_has_no_tiny_text_gradients_or_glows() -> None:
    css = "".join(path.read_text() for path in ASSETS.glob("*.css"))
    assert not [px for px in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", css) if float(px) < 11]
    assert not re.search(r"gradient|box-shadow:[^;}]*\d+px [^;}]*\d+px [^;}]*rgba", css)
