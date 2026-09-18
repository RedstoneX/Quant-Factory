"""Dashboard startup must use stored evidence without launching research."""

from dashboard import application
from dashboard.app import create_app
from persistence import PersistenceService
from prefect_spike.spym_vectorbt_fixture import ensure_spym_21c_saved_configuration


def test_dashboard_starts_without_loading_or_running_legacy_research(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Opening the dashboard must not load or run research")

    monkeypatch.setattr(application, "load_dashboard_context", forbidden)
    monkeypatch.setattr(application, "load_market_data", forbidden)
    monkeypatch.setattr(application, "execute_experiment", forbidden)
    database = tmp_path / "dashboard.sqlite3"
    monkeypatch.setenv("QUANT_FACTORY_DB_PATH", str(database))
    app = create_app()
    client = app.server.test_client()
    assert client.get("/research/backtest-results").status_code == 200
    layout = client.get("/_dash-layout")
    assert layout.status_code == 200
    assert "Results" in layout.get_data(as_text=True)
    persistence = PersistenceService(database)
    try:
        assert persistence.runs.list() == ()
    finally:
        persistence.close()


def test_explicit_dashboard_database_owns_configuration_and_run_views(tmp_path, monkeypatch):
    database = tmp_path / "selected.sqlite3"
    unrelated = tmp_path / "unrelated.sqlite3"
    monkeypatch.setenv("QUANT_FACTORY_DB_PATH", str(unrelated))
    persistence = PersistenceService(database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(persistence)
    finally:
        persistence.close()
    app = create_app(review_database=database)
    layout = app.server.test_client().get("/_dash-layout").get_data(as_text=True)
    assert configuration_id in layout
    assert not unrelated.exists()


def test_fresh_layout_includes_runs_created_after_server_start(tmp_path):
    from persistence import RunStatus, RunStage

    database = tmp_path / "refresh.sqlite3"
    persistence = PersistenceService(database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(persistence)
        app = create_app(review_database=database)
        client = app.server.test_client()
        assert "created_after_server_start" not in client.get("/_dash-layout").get_data(as_text=True)
        persistence.runs.create(
            configuration_id=configuration_id,
            strategy_id="spym_rsi_mean_reversion_fixture",
            strategy_version="1.0.0",
            stage=RunStage.FIXTURE,
            run_id="created_after_server_start",
            status=RunStatus.FAILED,
        )
        persistence.connection.commit()
        layout = client.get("/_dash-layout")
        assert layout.status_code == 200
        assert "created_after_server_start" in layout.get_data(as_text=True)
    finally:
        persistence.close()
