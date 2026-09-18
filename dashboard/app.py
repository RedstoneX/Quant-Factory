"""Plotly Dash application assembly for Quant Factory."""

from __future__ import annotations

from dashboard import application as _application

for _name in dir(_application):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_application, _name)


def _sync_compatibility_overrides() -> None:
    _application.list_saved_configurations = globals()["list_saved_configurations"]
    _application._callback_triggered_id = globals()["_callback_triggered_id"]


def create_app(*args, **kwargs):
    _sync_compatibility_overrides()
    return _application.create_app(*args, **kwargs)


def _system_page(*args, **kwargs):
    """Call the exported helper with its supported compatibility override."""
    original = _application.load_spym_manifest
    _application.load_spym_manifest = globals()["load_spym_manifest"]
    try:
        return _application._system_page(*args, **kwargs)
    finally:
        _application.load_spym_manifest = original


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8050, debug=False)
