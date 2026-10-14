"""Downloaded manifests live in the data mount and are found next to repo manifests."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_data.catalog import (
    DataLocations,
    DatasetUnavailableError,
    load_data_locations,
    manifest_dir_for,
)


def write_config(path: Path, root: Path, extra: str = "") -> Path:
    path.write_text(
        f'[data]\nroot = "{root}"\nmanifests = "{root.parent / "repo"}"\n'
        f'quarantine = "{root / "quarantine"}"\n{extra}\n'
        "[policy]\nallow_raw_data_in_repository = false\n",
        encoding="utf-8",
    )
    return path


def test_downloaded_manifests_default_inside_data_root(tmp_path):
    locations = load_data_locations(write_config(tmp_path / "c.toml", tmp_path / "data"))
    assert locations.downloaded_manifest_dir == tmp_path / "data" / "manifests"


def test_downloaded_manifests_key_overrides_default(tmp_path):
    extra = f'downloaded_manifests = "{tmp_path / "elsewhere"}"'
    locations = load_data_locations(write_config(tmp_path / "c.toml", tmp_path / "data", extra))
    assert locations.downloaded_manifest_dir == tmp_path / "elsewhere"
    with pytest.raises(ValueError, match="absolute"):
        load_data_locations(write_config(tmp_path / "r.toml", tmp_path / "data", 'downloaded_manifests = "rel"'))


def test_lookup_reads_repo_and_downloaded_folders_and_refuses_duplicates(tmp_path):
    repo, root = tmp_path / "repo", tmp_path / "data"
    (root / "manifests").mkdir(parents=True)
    repo.mkdir()
    locations = DataLocations(root, repo, root / "quarantine", None, None, True)
    (repo / "repo_only.json").write_text("{}")
    (root / "manifests" / "downloaded_only.json").write_text("{}")
    assert manifest_dir_for("repo_only", locations) == repo
    assert manifest_dir_for("downloaded_only", locations) == root / "manifests"
    assert manifest_dir_for("missing", locations) == repo
    (repo / "downloaded_only.json").write_text("{}")
    with pytest.raises(DatasetUnavailableError, match="both"):
        manifest_dir_for("downloaded_only", locations)
