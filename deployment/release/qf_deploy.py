#!/usr/bin/env python3
"""Put merged Quant Factory code live: only commits on GitHub main can deploy.

Runs as root from a fixed installed copy (/usr/local/sbin/qf-deploy), never from a
checkout, so merging a change to this file cannot run that change as root.  Code
(the Dashboard release and the research image) follows main automatically.
Privileged configuration tracked in the repository (compose.yaml and the Dashboard
systemd unit) changes only when an administrator runs ``qf-deploy --install-infra``;
until then the automatic deploy waits and records why.
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
KEEP_RELEASES = 5
FULL_SHA = re.compile(r"[0-9a-f]{40}")
REQUIREMENTS = ("requirements-runtime.txt", "requirements-dashboard.txt")
# Tracked privileged files and where they are installed; only --install-infra copies them.
INFRA = {
    "compose.yaml": RESEARCH / "compose.yaml",
    f"deployment/dashboard/{UNIT_NAME}": Path("/etc/systemd/system") / UNIT_NAME,
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


def compose(*args: str, capture: bool = False) -> str:
    return run("docker", "compose", "--project-directory", str(RESEARCH), "--file", str(RESEARCH / "compose.yaml"),
               *args, capture=capture)


def active_flow_runs() -> int:
    """Count Prefect flow runs in RUNNING or PENDING state (Prefect's own CLI, run inside the prefect service)."""
    out = compose("exec", "-T", "-e", "PREFECT_API_URL=http://127.0.0.1:4200/api", "prefect", "prefect", "flow-run", "ls",
                  "--state-type", "RUNNING", "--state-type", "PENDING", "--limit", "200", "--output", "json", capture=True)
    return len(json.loads(out or "[]"))


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
        return 0
    busy = active_flow_runs()
    if busy and not force:
        log(f"deferred: {busy} tests running; {target[:12]} will deploy when they finish")
        return 0
    try:
        return _switch(target, release, drift, state, pinned=requested is not None)
    except Exception as exc:
        # Recorded so the timer does not retry (and restart services) every 3 minutes.
        write_state(failed_revision=target, failure=f"{type(exc).__name__}: {exc}")
        raise


def _switch(target: str, release: Path, drift: list[str], state: dict, *, pinned: bool) -> int:
    ensure_venv(release)
    ensure_image(release, target)
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
