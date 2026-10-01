#!/usr/bin/env python3
"""Measure and enforce Quant Factory's internal Python dependency boundaries.

The checker uses only the Python standard library so it can run before project
dependencies are installed.  Runtime imports and imports guarded by
``TYPE_CHECKING`` are recorded separately.  Existing runtime cycle edges and
forbidden dependency edges are kept in an exact-module baseline: they may
disappear, but a new edge (including one recreated under a renamed module)
fails the check.
"""

from __future__ import annotations

import argparse
import ast
from fnmatch import fnmatchcase
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_POLICY = Path("config/architecture.json")
DEFAULT_BASELINE = Path("config/architecture-baseline.json")
IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "tests",
}


@dataclass(frozen=True, order=True)
class Edge:
    source: str
    target: str

    def key(self) -> str:
        return f"{self.source} -> {self.target}"


@dataclass(frozen=True)
class Component:
    name: str
    patterns: tuple[str, ...]
    allowed_dependencies: frozenset[str]


@dataclass(frozen=True)
class Analysis:
    modules: frozenset[str]
    runtime_edges: frozenset[Edge]
    type_only_edges: frozenset[Edge]
    components: Mapping[str, str]
    strongly_connected_components: tuple[tuple[str, ...], ...]
    cyclic_edges: frozenset[Edge]
    forbidden_edges: frozenset[Edge]
    source_lines: Mapping[str, int]


@dataclass(frozen=True)
class SizeBackstop:
    """Secondary guard against renewed responsibility accumulation."""

    max_lines: int
    grandfathered_modules: Mapping[str, int]


class ImportCollector(ast.NodeVisitor):
    """Collect imports while retaining whether they are type-only."""

    def __init__(self, module: str, is_package: bool, known_modules: set[str]) -> None:
        self.module = module
        self.package = module if is_package else module.rpartition(".")[0]
        self.known_modules = known_modules
        self.runtime: list[str] = []
        self.type_only: list[str] = []
        self._type_only_depth = 0
        self._import_module_names: set[str] = set()
        self._importlib_names: set[str] = set()

    def _record(self, name: str | None) -> None:
        if not name:
            return
        target = self.type_only if self._type_only_depth else self.runtime
        target.append(name)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802 - ast API
        if _is_type_checking_guard(node.test):
            self._type_only_depth += 1
            for statement in node.body:
                self.visit(statement)
            self._type_only_depth -= 1
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast API
        for alias in node.names:
            self._record(alias.name)
            if alias.name == "importlib":
                self._importlib_names.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast API
        base = _resolve_from(self.package, node.level, node.module)
        recorded_base = False
        for alias in node.names:
            candidate = f"{base}.{alias.name}" if alias.name != "*" and base else ""
            if candidate in self.known_modules:
                self._record(candidate)
            elif not recorded_base:
                self._record(base)
                recorded_base = True
            if node.level == 0 and node.module == "importlib" and alias.name == "import_module":
                self._import_module_names.add(alias.asname or alias.name)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast API
        name: str | None = None
        if isinstance(node.func, ast.Name):
            if node.func.id == "__import__" or node.func.id in self._import_module_names:
                name = _literal_first_argument(node)
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self._importlib_names
        ):
            name = _literal_first_argument(node)
        if name:
            if name.startswith("."):
                name = _resolve_dynamic_relative(self.package, name)
            self._record(name)
        self.generic_visit(node)


def _literal_first_argument(node: ast.Call) -> str | None:
    if not node.args:
        return None
    argument = node.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    return None


def _is_type_checking_guard(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
        or isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr == "TYPE_CHECKING"
    )


def _resolve_from(package: str, level: int, module: str | None) -> str:
    if level == 0:
        return module or ""
    parts = package.split(".") if package else []
    keep = len(parts) - level + 1
    if keep < 0:
        return ""
    prefix = parts[:keep]
    if module:
        prefix.extend(module.split("."))
    return ".".join(prefix)


def _resolve_dynamic_relative(package: str, name: str) -> str:
    level = len(name) - len(name.lstrip("."))
    return _resolve_from(package, level, name[level:] or None)


def _module_name(root: Path, path: Path) -> tuple[str, bool]:
    relative = path.relative_to(root)
    parts = list(relative.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def discover_modules(root: Path) -> dict[str, tuple[Path, bool]]:
    modules: dict[str, tuple[Path, bool]] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS or part.startswith(".") for part in relative.parts):
            continue
        module, is_package = _module_name(root, path)
        if module:
            modules[module] = (path, is_package)
    return modules


def _known_target(name: str, modules: set[str]) -> str | None:
    candidate = name
    while candidate:
        if candidate in modules:
            return candidate
        candidate = candidate.rpartition(".")[0]
    return None


def collect_edges(
    root: Path,
    modules: Mapping[str, tuple[Path, bool]],
) -> tuple[set[Edge], set[Edge], list[str]]:
    runtime: set[Edge] = set()
    type_only: set[Edge] = set()
    errors: list[str] = []
    names = set(modules)
    for module, (path, is_package) in modules.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"cannot parse {path.relative_to(root)}: {exc}")
            continue
        collector = ImportCollector(module, is_package, names)
        collector.visit(tree)
        for imported in collector.runtime:
            target = _known_target(imported, names)
            if target and target != module:
                runtime.add(Edge(module, target))
        for imported in collector.type_only:
            target = _known_target(imported, names)
            if target and target != module:
                type_only.add(Edge(module, target))
    return runtime, type_only, errors


def _pattern_specificity(pattern: str) -> tuple[int, int]:
    return (len(pattern.replace("*", "")), 0 if "*" in pattern else 1)


def _matches(module: str, pattern: str) -> bool:
    if pattern.endswith(".*") and module == pattern[:-2]:
        return True
    return fnmatchcase(module, pattern)


def load_policy(path: Path) -> tuple[tuple[Component, ...], list[str]]:
    errors: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (), [f"cannot load architecture policy {path}: {exc}"]
    raw_components = document.get("components")
    if document.get("schema_version") != 1:
        errors.append("architecture policy schema_version must be 1")
    if not isinstance(raw_components, dict):
        return (), ["architecture policy must contain a components object"]
    components: list[Component] = []
    names = set(raw_components)
    for name, value in raw_components.items():
        if not isinstance(value, dict):
            errors.append(f"component {name} must be an object")
            continue
        patterns = value.get("patterns")
        allowed = value.get("allowed_dependencies")
        if not isinstance(patterns, list) or not patterns or not all(
            isinstance(item, str) and item for item in patterns
        ):
            errors.append(f"component {name} must define nonempty string patterns")
            continue
        if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
            errors.append(f"component {name} must define allowed_dependencies")
            continue
        unknown = set(allowed) - names
        if unknown:
            errors.append(f"component {name} allows unknown components: {sorted(unknown)}")
        components.append(
            Component(
                name=name,
                patterns=tuple(patterns),
                allowed_dependencies=frozenset(allowed) | {name},
            )
        )
    return tuple(components), errors


def classify_modules(
    modules: Iterable[str],
    components: Sequence[Component],
) -> tuple[dict[str, str], list[str]]:
    assignments: dict[str, str] = {}
    errors: list[str] = []
    ordered_patterns = sorted(
        ((pattern, component.name) for component in components for pattern in component.patterns),
        key=lambda item: _pattern_specificity(item[0]),
        reverse=True,
    )
    for module in sorted(modules):
        matches = [name for pattern, name in ordered_patterns if _matches(module, pattern)]
        if not matches:
            errors.append(f"unclassified production module: {module}")
            continue
        assignments[module] = matches[0]
    return assignments, errors


def _strongly_connected_components(
    modules: Iterable[str], edges: Iterable[Edge]
) -> tuple[tuple[str, ...], ...]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source].add(edge.target)
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[tuple[str, ...]] = []

    def connect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(adjacency[node]):
            if target not in indices:
                connect(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1:
                result.append(tuple(sorted(component)))

    for module in sorted(modules):
        if module not in indices:
            connect(module)
    return tuple(sorted(result, key=lambda item: (-len(item), item)))


def analyze_repository(root: Path, policy_path: Path) -> tuple[Analysis | None, list[str]]:
    modules = discover_modules(root)
    runtime, type_only, errors = collect_edges(root, modules)
    components, policy_errors = load_policy(policy_path)
    errors.extend(policy_errors)
    assignments, classification_errors = classify_modules(modules, components)
    errors.extend(classification_errors)
    if errors:
        return None, errors
    component_map = {component.name: component for component in components}
    forbidden = {
        edge
        for edge in runtime
        if assignments[edge.target]
        not in component_map[assignments[edge.source]].allowed_dependencies
    }
    sccs = _strongly_connected_components(modules, runtime)
    cyclic_membership = {
        member: frozenset(component) for component in sccs for member in component
    }
    cyclic_edges = {
        edge
        for edge in runtime
        if edge.source in cyclic_membership
        and edge.target in cyclic_membership[edge.source]
    }
    return (
        Analysis(
            modules=frozenset(modules),
            runtime_edges=frozenset(runtime),
            type_only_edges=frozenset(type_only),
            components=assignments,
            strongly_connected_components=sccs,
            cyclic_edges=frozenset(cyclic_edges),
            forbidden_edges=frozenset(forbidden),
            source_lines={
                module: len(path.read_text(encoding="utf-8").splitlines())
                for module, (path, _) in modules.items()
            },
        ),
        [],
    )


def load_size_backstop(path: Path) -> tuple[SizeBackstop | None, list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot load architecture policy {path}: {exc}"]
    raw = document.get("size_growth_backstop")
    if raw is None:
        return None, []
    if not isinstance(raw, dict):
        return None, ["size_growth_backstop must be an object"]
    max_lines = raw.get("max_lines")
    grandfathered = raw.get("grandfathered_modules")
    errors: list[str] = []
    if not isinstance(max_lines, int) or isinstance(max_lines, bool) or max_lines < 1:
        errors.append("size_growth_backstop max_lines must be a positive integer")
    if not isinstance(grandfathered, dict) or not all(
        isinstance(module, str)
        and module
        and isinstance(limit, int)
        and not isinstance(limit, bool)
        and limit > 0
        for module, limit in (grandfathered.items() if isinstance(grandfathered, dict) else ())
    ):
        errors.append(
            "size_growth_backstop grandfathered_modules must map modules to positive integers"
        )
    if errors:
        return None, errors
    return SizeBackstop(max_lines=max_lines, grandfathered_modules=grandfathered), []


def check_size_backstop(backstop: SizeBackstop, analysis: Analysis) -> list[str]:
    """Keep oversized legacy modules from growing; this is not a split heuristic."""

    errors: list[str] = []
    for module, line_count in sorted(analysis.source_lines.items()):
        recorded = backstop.grandfathered_modules.get(module)
        if line_count <= backstop.max_lines:
            if recorded is not None:
                errors.append(
                    f"stale size exception for {module}: {line_count} <= {backstop.max_lines}"
                )
            continue
        if recorded is None:
            errors.append(
                f"module exceeds {backstop.max_lines}-line size backstop: "
                f"{module} ({line_count})"
            )
        elif line_count > recorded:
            errors.append(
                f"oversized module grew beyond its recorded backstop: "
                f"{module} ({line_count} > {recorded})"
            )
        elif line_count < recorded:
            errors.append(
                f"stale size exception for {module}: record reduced size {line_count}"
            )
    for module in sorted(set(backstop.grandfathered_modules) - set(analysis.source_lines)):
        errors.append(f"stale size exception for missing module: {module}")
    return errors


def check_size_backstop_history(
    root: Path, policy_path: Path, base_ref: str | None
) -> list[str]:
    """Prevent limits or the grandfathered set from expanding after establishment."""

    if not base_ref:
        return []
    try:
        relative = policy_path.resolve().relative_to(root).as_posix()
    except ValueError:
        return ["architecture policy must be inside the repository root"]
    completed = subprocess.run(
        ["git", "show", f"{base_ref}:{relative}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    try:
        previous = json.loads(completed.stdout).get("size_growth_backstop")
        current = json.loads(policy_path.read_text(encoding="utf-8")).get(
            "size_growth_backstop"
        )
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot compare size backstop with {base_ref}: {exc}"]
    if previous is None:
        return []
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return ["cannot compare malformed size_growth_backstop"]
    errors: list[str] = []
    old_max = previous.get("max_lines")
    new_max = current.get("max_lines")
    if isinstance(old_max, int) and isinstance(new_max, int) and new_max > old_max:
        errors.append(f"size backstop max_lines may not grow: {new_max} > {old_max}")
    old_modules = previous.get("grandfathered_modules")
    new_modules = current.get("grandfathered_modules")
    if not isinstance(old_modules, dict) or not isinstance(new_modules, dict):
        return [*errors, "cannot compare malformed grandfathered_modules"]
    for module in sorted(set(new_modules) - set(old_modules)):
        errors.append(f"size backstop may not add a grandfathered module: {module}")
    for module in sorted(set(new_modules) & set(old_modules)):
        if new_modules[module] > old_modules[module]:
            errors.append(
                f"size exception may not grow for {module}: "
                f"{new_modules[module]} > {old_modules[module]}"
            )
    return errors


def _baseline_document(analysis: Analysis) -> dict[str, object]:
    return {
        "schema_version": 1,
        "runtime_cyclic_edges": [edge.key() for edge in sorted(analysis.cyclic_edges)],
        "forbidden_runtime_edges": [edge.key() for edge in sorted(analysis.forbidden_edges)],
    }


def write_baseline(path: Path, analysis: Analysis) -> None:
    path.write_text(
        json.dumps(_baseline_document(analysis), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def check_baseline(path: Path, analysis: Analysis) -> list[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot load architecture baseline {path}: {exc}"]
    errors: list[str] = []
    if document.get("schema_version") != 1:
        errors.append("architecture baseline schema_version must be 1")
    fields = {
        "runtime_cyclic_edges": analysis.cyclic_edges,
        "forbidden_runtime_edges": analysis.forbidden_edges,
    }
    for field, current_edges in fields.items():
        raw = document.get(field)
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            errors.append(f"architecture baseline {field} must be a string list")
            continue
        baseline = set(raw)
        current = {edge.key() for edge in current_edges}
        for edge in sorted(current - baseline):
            errors.append(f"new {field.removesuffix('_edges').replace('_', ' ')}: {edge}")
        for edge in sorted(baseline - current):
            errors.append(f"stale {field.removesuffix('_edges').replace('_', ' ')}: {edge}")
    return errors


def check_baseline_history(root: Path, path: Path, base_ref: str | None) -> list[str]:
    """Require the committed violation baseline to stay the same or shrink."""

    if not base_ref:
        return []
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return ["architecture baseline must be inside the repository root"]
    completed = subprocess.run(
        ["git", "show", f"{base_ref}:{relative}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        # The establishing PR has no historical architecture baseline.
        return []
    try:
        previous = json.loads(completed.stdout)
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot compare architecture baseline with {base_ref}: {exc}"]
    errors: list[str] = []
    for field in ("runtime_cyclic_edges", "forbidden_runtime_edges"):
        old_values = previous.get(field)
        new_values = current.get(field)
        if not isinstance(old_values, list) or not isinstance(new_values, list):
            errors.append(f"cannot compare malformed baseline field: {field}")
            continue
        additions = set(new_values) - set(old_values)
        for edge in sorted(additions):
            errors.append(f"architecture baseline may not grow ({field}): {edge}")
    return errors


def report(analysis: Analysis) -> str:
    lines = [
        "Architecture dependency report",
        f"modules: {len(analysis.modules)}",
        f"runtime edges: {len(analysis.runtime_edges)}",
        f"type-only edges: {len(analysis.type_only_edges)}",
        f"runtime SCCs: {len(analysis.strongly_connected_components)}",
        f"runtime cyclic edges: {len(analysis.cyclic_edges)}",
        f"forbidden runtime edges: {len(analysis.forbidden_edges)}",
        f"largest module lines: {max(analysis.source_lines.values(), default=0)}",
    ]
    for index, component in enumerate(analysis.strongly_connected_components, start=1):
        lines.append(f"SCC {index} ({len(component)} modules): {', '.join(component)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--base-ref")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    policy = args.policy if args.policy.is_absolute() else root / args.policy
    baseline = args.baseline if args.baseline.is_absolute() else root / args.baseline
    analysis, errors = analyze_repository(root, policy)
    if errors or analysis is None:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(report(analysis))
    size_backstop, size_errors = load_size_backstop(policy)
    if size_errors:
        for error in size_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.write_baseline:
        write_baseline(baseline, analysis)
        print(f"Wrote architecture baseline: {baseline.relative_to(root)}")
        return 0
    errors = check_baseline(baseline, analysis)
    errors.extend(check_baseline_history(root, baseline, args.base_ref))
    if size_backstop is not None:
        errors.extend(check_size_backstop(size_backstop, analysis))
        errors.extend(check_size_backstop_history(root, policy, args.base_ref))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Architecture dependency checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
