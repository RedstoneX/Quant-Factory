"""Page-level wording and component rules for the Dashboard pages."""

from __future__ import annotations

from dashboard.plain_labels import FAILED_TESTING, LIFECYCLE_LABELS
from dashboard.ui.factory import _stage_word
from dashboard.ui.results import _signed_color, _stat


def test_screened_out_ideas_are_not_called_failed() -> None:
    assert FAILED_TESTING == "Screened out"
    assert "Failed testing" not in LIFECYCLE_LABELS.values()


def test_stat_card_colour_is_never_null() -> None:
    # Mantine throws on a null colour, which re-rendered the whole page in a loop.
    assert _stat("Trades", "3").children.children[1].c == "white"
    assert _stat("Net return", "+3%", _signed_color("+3%")).children.children[1].c == "teal.4"
    assert _signed_color("-2%") == "red.4"
    assert _signed_color("—") is None


def test_stage_names_use_plain_words() -> None:
    assert _stage_word("oos") == "Unseen-data test"
    assert _stage_word("walk_forward") == "Rolling test"
    assert _stage_word("custom_stage") == "Custom Stage"
