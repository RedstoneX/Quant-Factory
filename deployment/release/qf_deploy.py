#!/usr/bin/env python3
"""Put merged Quant Factory code live: only commits on GitHub main can deploy.

Runs as root from a fixed installed copy (/usr/local/sbin/qf-deploy), never from a
checkout, so merging a change to this file cannot run that change as root.  Code
(the Dashboard release and the research image) follows main automatically.
Privileged configuration tracked in the repository (compose.yaml and the Dashboard
systemd unit) changes only when an administrator runs ``qf-deploy --install-infra``;
until then the automatic deploy waits and records why.

Before anything switches, the licensed VectorBT test lane (the tests GitHub CI cannot
run) runs inside the newly built research image with no network, and its pytest
summary (pass/fail counts) is logged.  A failing revision
is refused, recorded as ``failed_revision`` and not retried until main moves.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ORIGIN = "https://github.com/RedstoneX/Quant-Factory.git"
ROOT = Path(os.environ.get("QF_DEPLOY_HOME", "/opt/quant-factory-dashboard"))
RESEARCH = Path(os.environ.get("QF_RESEARCH_HOME", "/opt/quant-factory-research"))
REPO = ROOT / "repo.git"
RELEASES = ROOT / "releases"
VENVS = ROOT / "venvs"
CURRENT = ROOT / "current"
STATE = ROOT / "deployed.json"
UNIT_NAME = "quant-factory-dashboard.service"
DASHBOARD_URL = "http://127.0.0.1:8050"
IMAGE = "quant-factory-research"
GATEWAY_CLIENT = Path("/opt/quant-factory-gateway/client/agent_gateway")
KEEP_RELEASES = 5
GATEWAY_DB = Path(os.environ.get("QF_GATEWAY_DB", "/opt/quant-factory-gateway/state/agent_gateway.sqlite3"))
# Drain marker: shared with the gateway container through its /run/quant-factory mount.
DRAIN_MARKER = Path(os.environ.get("QF_DEPLOY_DRAIN_MARKER", "/run/quant-factory/deploy-drain"))
FULL_SHA = re.compile(r"[0-9a-f]{40}")
REQUIREMENTS = ("requirements-runtime.txt", "requirements-dashboard.txt")
# The research image ships no test runner: pytest is installed at its requirements-ci.txt
# pin into the release and mounted read-only into the network-less test container.
TEST_DEPS = ".qf-pytest"
# Runs inside the image over only the files holding licensed tests, so test modules that
# need the Dashboard's packages (absent from the research image) are never imported.
LICENSED_LANE = (
    "import sys, pytest\n"
    "from tests.conftest import LICENSED_VECTORBT_NODE_IDS as ids\n"
    "files = sorted({node.split('::')[0] for node in ids})\n"
    "sys.exit(pytest.main(['-q', '-rfE', '-p', 'no:cacheprovider', '-m', 'licensed_vectorbt', *files]))\n"
)
PYTEST_SUMMARY = re.compile(r"\b(\d+) (?:failed|errors?)\b")
# Tracked privileged files and where they are installed; only --install-infra copies them.
INFRA = {
    "compose.yaml": RESEARCH / "compose.yaml",
    f"deployment/dashboard/{UNIT_NAME}": Path("/etc/systemd/system") / UNIT_NAME,
    "agent_gateway/contracts.py": GATEWAY_CLIENT / "contracts.py",
    "agent_gateway/cli.py": GATEWAY_CLIENT / "cli.py",
    "agent_gateway/ssh_command.py": GATEWAY_CLIENT / "ssh_command.py",
}


class DeployError(RuntimeError):
    pass


class InfraPending(DeployError):
    pass


def log(message: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {message}", flush=True)


def run(*args: str, capture: bool = False) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=capture)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[-400:]
        raise DeployError(f"`{' '.join(args)}` exited {result.returncode} {detail}".strip())
    return (result.stdout or "").strip()


def succeeds(*args: str) -> bool:
    return subprocess.run(args, check=False, capture_output=True).returncode == 0


# Pure helpers (unit tested).

def licensed_lane_command(release: Path, revision: str) -> list[str]:
    """The throwaway, network-less container run of the licensed lane in ``revision``'s image."""
    return ["docker", "run", "--rm", "--name", licensed_container_name(revision),
            "--network", "none", "--cpus", "2", "--entrypoint", "python",
            "--workdir", "/app", "--volume", f"{release / TEST_DEPS}:/opt/qf-pytest:ro",
            # The image is runtime-only (.dockerignore leaves tests out); the release export has them.
            "--volume", f"{release / 'tests'}:/app/tests:ro",
            # The same read-only price store and data config the research services mount (compose.yaml).
            "--volume", f"{RESEARCH / 'market-data'}:/var/lib/quant-factory/market-data:ro",
            "--volume", f"{RESEARCH / 'config' / 'data_locations.local.toml'}:/app/config/data_locations.local.toml:ro",
            "--env", "QUANT_FACTORY_DATA_LOCATIONS=/app/config/data_locations.local.toml",
            "--env", "PYTHONPATH=/app:/opt/qf-pytest", f"{IMAGE}:{revision}", "-c", LICENSED_LANE]


def licensed_container_name(revision: str) -> str:
    """Deterministic name of the lane container, so a leftover from a timed-out run can be removed."""
    return f"qf-licensed-{revision[:12]}"


def failed_node_ids(output: str, limit: int = 20) -> list[str]:
    """The FAILED/ERROR lines of pytest's ``-rfE`` short summary, at most ``limit``."""
    lines = [line.strip() for line in output.splitlines()]
    return [line for line in lines if line.startswith(("FAILED ", "ERROR "))][:limit]


def summary_line(output: str) -> str:
    """Pytest's final summary line, e.g. ``87 passed in 120.00s`` (empty when there is no output)."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def failing_count(output: str) -> int:
    """Failed plus errored tests on pytest's final summary line (0 when it reports none)."""
    return sum(int(count) for count in PYTEST_SUMMARY.findall(summary_line(output)))


def set_env_revision(text: str, revision: str) -> str:
    """Return compose .env text with its single QF_REVISION line set to ``revision``."""
    if not FULL_SHA.fullmatch(revision):
        raise DeployError(f"not a full commit sha: {revision!r}")
    lines = text.splitlines(keepends=True)
    hits = [index for index, line in enumerate(lines) if line.startswith("QF_REVISION=")]
    if len(hits) != 1:
        raise DeployError(f"expected exactly one QF_REVISION line in the compose .env, found {len(hits)}")
    lines[hits[0]] = f"QF_REVISION={revision}\n"
    return "".join(lines)


def env_revision(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("QF_REVISION="):
            value = line.partition("=")[2].strip()
            return value if FULL_SHA.fullmatch(value) else None
    return None


def requirements_key(release: Path) -> str:
    digest = hashlib.sha256(sys.version.encode())
    for name in REQUIREMENTS:
        digest.update(name.encode() + b"\0" + (release / name).read_bytes() + b"\0")
    return digest.hexdigest()[:16]


def infra_drift(release: Path, installed: dict[str, Path]) -> list[str]:
    """Tracked privileged files whose installed copy differs from the release."""
    drift = []
    for tracked, target in installed.items():
        source = release / tracked
        if source.is_symlink() or not source.is_file():
            raise DeployError(f"{tracked} must be a regular tracked file")
        if not target.is_file() or source.read_bytes() != target.read_bytes():
            drift.append(tracked)
    return drift


# Steps.

def fetch_main() -> str:
    if not (REPO / "HEAD").exists():
        run("git", "init", "--quiet", "--bare", str(REPO))
    run("git", "-C", str(REPO), "fetch", "--quiet", "--prune", ORIGIN, "+refs/heads/main:refs/heads/main")
    return run("git", "-C", str(REPO), "rev-parse", "refs/heads/main^{commit}", capture=True)


def resolve_target(requested: str | None, main: str) -> str:
    if requested is None:
        return main
    revision = run("git", "-C", str(REPO), "rev-parse", "--verify", f"{requested}^{{commit}}", capture=True)
    if not succeeds("git", "-C", str(REPO), "merge-base", "--is-ancestor", revision, main):
        raise DeployError(f"{revision[:12]} is not on GitHub main; only merged code can go live")
    return revision


def export_release(revision: str) -> Path:
    release = RELEASES / revision
    if release.is_dir():
        return release
    RELEASES.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{revision[:12]}-", dir=RELEASES))
    archive = staging.with_suffix(".tar")
    run("git", "-C", str(REPO), "-c", "tar.umask=022", "archive", "--format=tar", "-o", str(archive), revision)
    run("tar", "-xf", str(archive), "-C", str(staging), "--no-same-owner")
    archive.unlink()
    (staging / ".qf-build-revision").write_text(revision + "\n", encoding="utf-8")
    os.chmod(staging, 0o755)
    staging.rename(release)
    return release


def ensure_venv(release: Path) -> Path:
    # Built in place: a venv's scripts embed their absolute path, so it cannot be renamed.
    venv = VENVS / requirements_key(release)
    if not (venv / ".complete").is_file():
        shutil.rmtree(venv, ignore_errors=True)
        VENVS.mkdir(parents=True, exist_ok=True)
        log(f"building Python environment {venv.name}")
        run(sys.executable, "-m", "venv", str(venv))
        install = [str(venv / "bin" / "python"), "-m", "pip", "install", "--quiet", "--no-cache-dir",
                   "--only-binary=:all:", "--constraint", str(release / REQUIREMENTS[0])]
        for name in REQUIREMENTS:
            install += ["--requirement", str(release / name)]
        run(*install)
        (venv / ".complete").write_text(release.name + "\n", encoding="utf-8")
    link = release / ".venv"
    if link.is_symlink() and link.resolve() == venv.resolve():
        return venv
    if link.exists() or link.is_symlink():
        raise DeployError(f"{release.name[:12]} already contains .venv; refusing to replace it")
    link.symlink_to(venv)
    return venv


def ensure_image(release: Path, revision: str) -> None:
    tag = f"{IMAGE}:{revision}"
    label = subprocess.run(["docker", "image", "inspect", "--format", '{{ index .Config.Labels "qf.deploy" }}', tag],
                           check=False, capture_output=True, text=True).stdout.strip()
    if label == revision:
        return
    log(f"building research image {revision[:12]}")
    run("docker", "build", "--quiet", "--build-context", f"vectorbt_private={RESEARCH / 'private'}",
        "--build-arg", f"QF_REVISION={revision}", "--label", f"qf.deploy={revision}", "--tag", tag, str(release))


def verify_image(release: Path, revision: str, venv: Path) -> None:
    """Refuse ``revision`` unless the licensed lane passes inside its research image."""
    deps = release / TEST_DEPS
    shutil.rmtree(deps, ignore_errors=True)  # never reuse a half-finished install
    run(str(venv / "bin" / "python"), "-m", "pip", "install", "--quiet", "--no-cache-dir", "--only-binary=:all:",
        "--target", str(deps), "--constraint", str(release / "requirements-ci.txt"), "pytest")
    # A lane killed by a timeout leaves its container running; the fixed name lets us clear it first.
    subprocess.run(["docker", "rm", "-f", licensed_container_name(revision)], check=False, capture_output=True)
    log(f"running licensed tests in research image {revision[:12]}")
    result = subprocess.run(licensed_lane_command(release, revision), check=False, text=True, capture_output=True)
    log(f"licensed tests on {revision[:12]}: {summary_line(result.stdout or '') or 'no pytest summary'} "
        f"(pytest exit {result.returncode})")
    if result.returncode != 0:
        for line in failed_node_ids(result.stdout or ""):
            log(line)
        raise DeployError(f"licensed tests failed on {revision[:12]}: {failing_count(result.stdout)} failing "
                          f"(pytest exit {result.returncode}); not switching")


def install_infra(release: Path, drift: list[str]) -> list[tuple[Path, Path | None]]:
    restored: list[tuple[Path, Path | None]] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for tracked in drift:
        target = INFRA[tracked]
        backup = target.with_name(f"{target.name}.before-{stamp}") if target.exists() else None
        if backup:
            shutil.copy2(target, backup)
        shutil.copyfile(release / tracked, target)
        os.chmod(target, 0o600 if target.parent == RESEARCH else 0o644)
        restored.append((target, backup))
        log(f"installed {tracked} -> {target}")
    run("systemctl", "daemon-reload")
    return restored


def compose(*args: str) -> None:
    run("docker", "compose", "--project-directory", str(RESEARCH), "--file", str(RESEARCH / "compose.yaml"), *args)


def switch_containers(revision: str) -> None:
    env_file = RESEARCH / ".env"
    staged = env_file.with_name(".env.qf-deploy")
    staged.write_text(set_env_revision(env_file.read_text(encoding="utf-8"), revision), encoding="utf-8")
    os.chmod(staged, 0o600)
    os.replace(staged, env_file)
    compose("up", "--detach", "--wait", "--wait-timeout", "300")


def switch_dashboard(release: Path) -> None:
    staged = ROOT / ".current.new"
    if staged.is_symlink() or staged.exists():
        staged.unlink()
    staged.symlink_to(release)
    os.replace(staged, CURRENT)
    run("systemctl", "restart", UNIT_NAME)
    wait_for_dashboard()


def wait_for_dashboard(timeout: float = 90.0) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline, last = time.monotonic() + timeout, "no response"
    while time.monotonic() < deadline:
        try:
            for path in ("/", "/_dash-layout"):
                with opener.open(DASHBOARD_URL + path, timeout=15) as response:
                    if response.status != 200:
                        raise DeployError(f"{path} returned {response.status}")
            return
        except (OSError, http.client.HTTPException, DeployError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
    raise DeployError(f"Dashboard unhealthy after restart ({last})")


def rollback(revision: str | None, release: Path | None, restored: list[tuple[Path, Path | None]]) -> None:
    for target, backup in restored:
        if backup:
            shutil.copy2(backup, target)
        else:
            target.unlink(missing_ok=True)
    if restored:
        run("systemctl", "daemon-reload")
    if revision:
        switch_containers(revision)
    if release:
        switch_dashboard(release)
    else:
        run("systemctl", "restart", UNIT_NAME)
        wait_for_dashboard()


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(**changes: object) -> None:
    state = read_state() | changes | {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    staged = STATE.with_suffix(".new")
    staged.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(staged, 0o644)
    os.replace(staged, STATE)


def prune(keep: set[str]) -> None:
    for leftover in RELEASES.glob(".*"):
        if leftover.is_dir():
            shutil.rmtree(leftover, ignore_errors=True)
        else:
            leftover.unlink()
    releases = sorted((path for path in RELEASES.iterdir() if FULL_SHA.fullmatch(path.name)),
                      key=lambda path: path.stat().st_mtime, reverse=True)
    for old in releases[KEEP_RELEASES:]:
        if old.name not in keep:
            shutil.rmtree(old)
    used = {(path / ".venv").resolve() for path in RELEASES.iterdir() if (path / ".venv").is_symlink()}
    for venv in VENVS.iterdir():
        if venv.resolve() not in used:
            shutil.rmtree(venv, ignore_errors=True)


def running_auto_tests(database: Path | None = None) -> int | None:
    """Ideas whose latest campaign event is "running" (read-only); None if the store cannot be read.

    Only "running" blocks: the gateway counts attempts as "running" events, so restarting
    a merely "queued" idea burns none. Same query as GatewayStore.latest_campaign_events.
    """
    database = database or GATEWAY_DB
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)
        try:
            return int(connection.execute(
                "SELECT COUNT(*) FROM campaign_events event JOIN ("
                "SELECT candidate_id, MAX(event_id) event_id FROM campaign_events GROUP BY candidate_id"
                ") latest ON latest.event_id = event.event_id WHERE event.state = 'running'"
            ).fetchone()[0])
        finally:
            connection.close()
    except sqlite3.Error as exc:
        log(f"WARNING: cannot read the auto-test store, deploying without the drain check: {exc}")
        return None


def set_drain_marker() -> None:
    """Ask the gateway not to start new auto-tests; keep the first mtime so a stale marker expires."""
    try:
        if not DRAIN_MARKER.exists():
            DRAIN_MARKER.write_text(datetime.now(timezone.utc).isoformat(timespec="seconds") + "\n", encoding="utf-8")
            os.chmod(DRAIN_MARKER, 0o664)
    except OSError as exc:
        log(f"WARNING: cannot set the drain marker: {exc}")


def clear_drain_marker() -> None:
    try:
        DRAIN_MARKER.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        log(f"WARNING: cannot clear the drain marker: {exc}")


def deploy(requested: str | None, *, admin: bool, force: bool, unpin: bool) -> int:
    state = read_state()
    if state.get("pinned") and requested is None and not unpin:
        log(f"pinned at {state['pinned'][:12]} by an administrator; run qf-deploy --unpin to follow main again")
        return 0
    target = resolve_target(requested, fetch_main())
    if state.get("failed_revision") == target and not force:
        log(f"{target[:12]} failed to deploy before; waiting for a newer merge or qf-deploy --force")
        return 1
    release = export_release(target)
    drift = infra_drift(release, INFRA)
    if drift and not admin:
        raise InfraPending(f"{target[:12]} changes {', '.join(drift)}; an administrator must run: sudo qf-deploy --install-infra")
    if state.get("revision") == target and not drift and not force:
        if unpin:
            write_state(pinned=None)
        clear_drain_marker()
        return 0
    if os.environ.get("QF_DEPLOY_FORCE") != "1":
        running = running_auto_tests()
        if running:
            # Recreating the gateway interrupts a running test and burns one of its 3 attempts.
            log(f"deploy deferred: {running} auto-tests running; draining (no new tests start)")
            set_drain_marker()
            return 0
    clear_drain_marker()
    try:
        return _switch(target, release, drift, state, pinned=requested is not None)
    except Exception as exc:
        # Recorded so the timer does not retry (and restart services) every 3 minutes.
        write_state(failed_revision=target, failure=f"{type(exc).__name__}: {exc}")
        raise


def _switch(target: str, release: Path, drift: list[str], state: dict, *, pinned: bool) -> int:
    venv = ensure_venv(release)
    ensure_image(release, target)
    verify_image(release, target, venv)  # before anything switches; a failure is recorded as failed_revision
    env_file = RESEARCH / ".env"
    set_env_revision(env_file.read_text(encoding="utf-8"), target)  # refuse before changing anything
    previous_revision = env_revision(env_file.read_text(encoding="utf-8"))
    previous_release = CURRENT.resolve() if CURRENT.is_symlink() else None
    restored: list[tuple[Path, Path | None]] = []
    try:
        restored = install_infra(release, drift) if drift else []
        switch_containers(target)
        switch_dashboard(release)
    except Exception as exc:
        log(f"deploy of {target[:12]} failed, rolling back: {exc}")
        rollback(previous_revision, previous_release, restored)
        raise
    write_state(revision=target, previous=state.get("revision"), pending=None, failure=None, failed_revision=None,
                pinned=target if pinned else None, deployed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    prune({target, str(state.get("revision"))})
    log(f"live at {target[:12]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--revision", help="deploy and pin this commit (must already be on GitHub main); default: main's tip")
    parser.add_argument("--install-infra", action="store_true",
                        help="administrator: also install tracked compose.yaml and the Dashboard unit")
    parser.add_argument("--force", action="store_true", help="redeploy even if the target is live or failed before")
    parser.add_argument("--unpin", action="store_true", help="clear a --revision pin and follow main's tip again")
    parser.add_argument("--status", action="store_true", help="print the deployed state and exit")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_state(), indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise SystemExit("qf-deploy must run as root")
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(ROOT / ".lock", "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("another deploy is running")
            return 0
        try:
            return deploy(args.revision, admin=args.install_infra, force=args.force, unpin=args.unpin)
        except InfraPending as exc:
            log(f"WAITING: {exc}")
            write_state(pending=str(exc))
            return 3
        except DeployError as exc:
            log(f"FAILED: {exc}")
            write_state(failure=str(exc))
            return 1


if __name__ == "__main__":
    sys.exit(main())
