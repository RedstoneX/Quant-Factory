from types import SimpleNamespace

from dash import Dash

from dashboard.callbacks import settings


def _save_callback(app: Dash):
    entry = next(
        value
        for key, value in app.callback_map.items()
        if "settings-save-status.children" in key
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def test_settings_claim_application_without_promising_browser_persistence(
    monkeypatch,
) -> None:
    app = Dash(__name__)
    settings.register_settings_callbacks(app)
    save = _save_callback(app)

    monkeypatch.setattr(
        settings,
        "ctx",
        SimpleNamespace(triggered_id="save-display-preferences"),
    )
    preferences, message, message_class = save(1, 0, "dark", "compact")

    assert preferences == {"theme": "dark", "density": "compact"}
    assert message == (
        "Display preferences applied. This browser will retain them when local "
        "storage is available."
    )
    assert message_class == "save-message save-message-success"
