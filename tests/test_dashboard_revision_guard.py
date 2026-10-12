from __future__ import annotations

from dashboard.ui.app import app


def test_stale_dash_callback_client_receives_explicit_reload_contract():
    client = app.server.test_client()
    index = client.get("/factory")
    revision = index.headers["X-QF-Revision"]
    assert revision
    assert "qf_revision=" in index.headers["Set-Cookie"]

    client.set_cookie("qf_revision", "obsolete-revision")
    response = client.post("/_dash-update-component", json={})

    assert response.status_code == 409
    assert response.json["error"] == "revision_mismatch"
    assert response.headers["X-QF-Revision-Mismatch"] == revision


def test_revision_probe_is_uncached_and_matches_page_revision():
    client = app.server.test_client()
    page = client.get("/")
    probe = client.get("/__qf_revision__")
    assert probe.status_code == 200
    assert probe.headers["Cache-Control"] == "no-store"
    assert probe.json["revision"] == page.headers["X-QF-Revision"]
