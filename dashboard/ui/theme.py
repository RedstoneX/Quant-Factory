"""One shared look for the Dashboard: Mantine theme, Plotly template and font.

Values come from the approved design mock. Pages inherit them through the
MantineProvider in the app shell and through Plotly's default template, so no
page should restate colours, sizes or radii.
"""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio

FONT_URL = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap"
FONT_FAMILY = "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

BG, PANEL, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED = "#e6edf3", "#7d8590"
ACCENT, UP, DOWN, WARNING = "#58a6ff", "#26a69a", "#ef5350", "#d29922"

# Mantine dark mode reads body from dark[7], surfaces from dark[6], borders from dark[4], dimmed text from dark[2].
_DARK = [TEXT, "#c9d1d9", MUTED, "#6e7681", BORDER, "#21262d", PANEL, BG, "#010409", "#010409"]
_BLUE = ["#cae8ff", "#a5d6ff", "#79c0ff", ACCENT, "#388bfd", "#1f6feb", "#1158c7", "#0d419d", "#0c2d6b", "#051d4d"]

MANTINE_THEME = {
    "fontFamily": FONT_FAMILY,
    "headings": {"fontFamily": FONT_FAMILY, "fontWeight": "600", "sizes": {
        "h1": {"fontSize": "22px", "lineHeight": "1.3"}, "h2": {"fontSize": "18px", "lineHeight": "1.35"},
        "h3": {"fontSize": "16px", "lineHeight": "1.4"}, "h4": {"fontSize": "16px", "lineHeight": "1.4"},
        "h5": {"fontSize": "15px", "lineHeight": "1.4"}, "h6": {"fontSize": "15px", "lineHeight": "1.4"},
    }},
    "fontSizes": {"xs": "13px", "sm": "14px", "md": "15px", "lg": "17px", "xl": "20px"},
    "spacing": {"xs": "4px", "sm": "8px", "md": "12px", "lg": "16px", "xl": "24px"},
    "radius": {"xs": "4px", "sm": "6px", "md": "6px", "lg": "8px", "xl": "12px"},
    "defaultRadius": "sm",
    "colors": {"dark": _DARK, "blue": _BLUE},
    "primaryColor": "blue",
    "primaryShade": {"light": 5, "dark": 5},
    "black": BG,
    "white": TEXT,
    "shadows": {size: "none" for size in ("xs", "sm", "md", "lg", "xl")},
    "components": {
        "Button": {"defaultProps": {"size": "xs"}},
        "Badge": {"defaultProps": {"variant": "light", "size": "sm"}},
        "Paper": {"defaultProps": {"withBorder": True}},
    },
}

_AXIS = {"gridcolor": "rgba(255,255,255,0.04)", "zeroline": False, "showline": False, "title": {"text": ""},
         "tickfont": {"color": MUTED, "size": 13}, "showspikes": True, "spikemode": "across",
         "spikethickness": 1, "spikedash": "dot", "spikecolor": "#484f58"}

QF_TEMPLATE = go.layout.Template(pio.templates["plotly_dark"])
QF_TEMPLATE.layout.update(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font={"family": FONT_FAMILY, "size": 13, "color": MUTED},
    colorway=[ACCENT, UP, DOWN, WARNING],
    hovermode="x unified",
    hoverlabel={"bgcolor": PANEL, "bordercolor": BORDER, "font": {"color": TEXT, "size": 12, "family": FONT_FAMILY}},
    legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.02, "yanchor": "bottom",
            "bgcolor": "rgba(0,0,0,0)", "font": {"color": MUTED, "size": 13}},
    margin={"l": 48, "r": 16, "t": 32, "b": 32},
    xaxis={**_AXIS, "rangeslider": {"visible": False}},
    yaxis={**_AXIS, "side": "right"},
)
pio.templates["qf"] = QF_TEMPLATE
pio.templates.default = "qf"

# AG Grid Theming API: every grid passes this as dashGridOptions["theme"]; dash-ag-grid evaluates the function string.
AG_GRID_THEME = {"function": "themeQuartz.withParams(" + json.dumps({
    "browserColorScheme": "dark", "backgroundColor": PANEL, "foregroundColor": TEXT, "chromeBackgroundColor": PANEL,
    "headerBackgroundColor": PANEL, "headerTextColor": MUTED, "headerFontWeight": 500, "borderColor": BORDER,
    "accentColor": ACCENT, "oddRowBackgroundColor": PANEL, "fontFamily": FONT_FAMILY, "fontSize": 14,
    "headerFontSize": 14, "rowHeight": 40, "headerHeight": 40, "wrapperBorder": False, "spacing": 6,
    "cellHorizontalPaddingScale": 0.75,
}) + ")"}


# Columns share the panel width: long headers wrap instead of widening a column.
COLUMN_DEFAULTS = {"resizable": True, "sortable": True, "wrapHeaderText": True, "autoHeaderHeight": True, "minWidth": 70}
NARROW_GRID_PX = 576  # Mantine "sm" breakpoint (36em)


def grid_options(empty: str, **options: Any) -> dict[str, Any]:
    """dashGridOptions: shared theme and a plain sentence when there are no rows.

    Pair with columnSize="responsiveSizeToFit" and flex columns so the grid fits its panel.
    The sentence goes through AG Grid's locale text: dash-ag-grid blocks HTML overlay templates.
    """
    return {"theme": AG_GRID_THEME, "localeText": {"noRowsToShow": empty}, **options}


def hide_when_narrow(*col_ids: str) -> dict[str, list[str]]:
    """AgGrid eventListeners: hide low-priority columns while the grid is narrower than the phone breakpoint.

    dash-ag-grid attaches listeners after the first size event, so the first rows loaded also apply the rule.
    """
    cols = json.dumps(list(col_ids))
    return {
        "gridSizeChanged": [f"params.api.setColumnsVisible({cols}, params.clientWidth >= {NARROW_GRID_PX})"],
        "modelUpdated": [f"params.api.setColumnsVisible({cols}, params.api.getHorizontalPixelRange().right - params.api.getHorizontalPixelRange().left >= {NARROW_GRID_PX})"],
    }
