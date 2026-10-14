"""The research image must contain every repository module its entrypoints import.

.dockerignore is an allow-list, so a new package is silently left out of the
image until someone lists it; the container then fails at start-up, after merge.
"""

from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ("deployment/agent_gateway_server.py", "prefect_spike/candidate_pipeline_flow.py")


def _ignore_rules() -> list[tuple[bool, str]]:
    rules = []
    for raw in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        allow = line.startswith("!")
        rules.append((allow, line[1:] if allow else line))
    return rules


def _matches(pattern: str, path: str) -> bool:
    pattern = pattern.rstrip("/")
    if pattern == "**":
        return True
    if pattern.startswith("**/"):
        tail = pattern[3:]
        return any(fnmatch.fnmatchcase("/".join(path.split("/")[i:]), tail) for i in range(path.count("/") + 1))
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/")
    return fnmatch.fnmatchcase(path, pattern)


def _in_image(path: str) -> bool:
    included = True
    for allow, pattern in _ignore_rules():
        if _matches(pattern, path):
            included = allow
    return included


def _local_module_file(name: str) -> Path | None:
    parts = name.split(".")
    for candidate in (ROOT.joinpath(*parts).with_suffix(".py"), ROOT.joinpath(*parts, "__init__.py")):
        if candidate.is_file():
            return candidate
    return None


def _imported_files(path: Path) -> set[Path]:
    found: set[Path] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
        for name in names:
            parts = name.split(".")
            for depth in range(1, len(parts) + 1):
                module = _local_module_file(".".join(parts[:depth]))
                if module is not None:
                    found.add(module)
    return found


def _import_closure() -> set[Path]:
    pending = [ROOT / entry for entry in ENTRYPOINTS]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        pending.extend(_imported_files(path) - seen)
    return seen


def test_every_module_the_entrypoints_import_is_in_the_image() -> None:
    missing = sorted(
        path.relative_to(ROOT).as_posix()
        for path in _import_closure()
        if not _in_image(path.relative_to(ROOT).as_posix())
    )

    assert missing == [], f"add these to the .dockerignore allow-list: {missing}"


def test_the_check_catches_an_unlisted_package() -> None:
    assert _in_image("strategies/__init__.py")
    assert not _in_image("results/anything.py")
    assert not _in_image("strategies/__pycache__/x.cpython-312.pyc")
