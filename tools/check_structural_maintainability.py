"""Enforce monotonic structural-maintainability ratchets with the stdlib only."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
FILE_LIMIT = 600
FUNCTION_LIMIT = 150
DEFAULT_BASELINE = Path("config/structural-maintainability-baseline.json")
SOURCE_SUFFIXES = frozenset({".py", ".sh", ".js", ".css", ".yml", ".yaml", ".toml"})
SOURCE_NAMES = frozenset({"Dockerfile", "Makefile"})
TEST_DOUBLE_ARGUMENTS = frozenset({"monkeypatch", "mocker"})
TEST_DOUBLE_CALLS = frozenset(
    {"Mock", "MagicMock", "AsyncMock", "PropertyMock", "create_autospec", "patch", "SimpleNamespace"}
)


@dataclass(frozen=True)
class Location:
    path: str
    line: int
    owner: str
    detail: str


@dataclass(frozen=True)
class Measurement:
    oversized_files: Mapping[str, int]
    oversized_functions: Mapping[str, int]
    broad_nonreraising_handlers: frozenset[str]
    hard_constructor_bypasses: tuple[Location, ...]
    licensed_test_doubles: tuple[Location, ...]
    python_file_count: int
    source_file_count: int


@dataclass(frozen=True)
class Baseline:
    oversized_files: Mapping[str, int]
    oversized_functions: Mapping[str, int]
    broad_nonreraising_handlers: frozenset[str]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def tracked_paths(root: Path) -> tuple[str, ...]:
    result = _git(root, "ls-files", "-z")
    if result.returncode:
        raise RuntimeError(f"cannot enumerate tracked files: {result.stderr.strip()}")
    return tuple(path for path in result.stdout.split("\0") if path)


def _is_source_like(path: str) -> bool:
    candidate = Path(path)
    return candidate.suffix.lower() in SOURCE_SUFFIXES or candidate.name in SOURCE_NAMES


def _physical_lines(text: str) -> int:
    return len(text.splitlines())


def _broad_exception(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(_broad_exception(item) for item in node.elts)
    return False


def _qualified_key(parts: Sequence[object]) -> str:
    """Return an unambiguous compact JSON identity, independent of line numbers."""

    return json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))


def _marker_is_licensed(node: ast.AST) -> bool:
    return any(
        isinstance(item, (ast.Name, ast.Attribute))
        and (item.id if isinstance(item, ast.Name) else item.attr) == "licensed_vectorbt"
        for item in ast.walk(node)
    )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _looks_like_double(name: str) -> bool:
    lowered = name.lower().lstrip("_")
    return (
        lowered.startswith(("fake", "stub", "dummy", "mock"))
        or lowered.endswith(("_fake", "_stub", "_dummy", "_mock"))
    )


class _PythonInventory(ast.NodeVisitor):
    def __init__(self, path: str, *, module_licensed: bool) -> None:
        self.path = path
        self.module_licensed = module_licensed
        self.stack: list[str] = []
        self.class_licensed: list[bool] = []
        self.functions: list[tuple[str, str, int, int]] = []
        self.handlers: list[tuple[str, str, int]] = []
        self.constructor_bypasses: list[Location] = []
        self.licensed_doubles: list[Location] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        inherited = self.class_licensed[-1] if self.class_licensed else self.module_licensed
        self.class_licensed.append(inherited or any(_marker_is_licensed(item) for item in node.decorator_list))
        self.generic_visit(node)
        self.class_licensed.pop()
        self.stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        owner = ".".join([*self.stack, node.name])
        self.functions.append((owner, type(node).__name__, node.lineno, node.end_lineno))
        licensed = (
            node.name.startswith("test_")
            and (
                self.module_licensed
                or bool(self.class_licensed and self.class_licensed[-1])
                or any(_marker_is_licensed(item) for item in node.decorator_list)
            )
        )
        if self.path.startswith("tests/") and licensed:
            self._inspect_licensed_test(node, owner)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if not self.path.startswith("tests/") and _broad_exception(node.type):
            raises = any(
                isinstance(descendant, ast.Raise)
                for statement in node.body
                for descendant in ast.walk(statement)
            )
            if not raises:
                owner = ".".join(self.stack) if self.stack else "<module>"
                caught = "<bare>" if node.type is None else ast.unparse(node.type)
                self.handlers.append((owner, caught, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        direct_new = isinstance(node.func, ast.Attribute) and node.func.attr == "__new__"
        getattr_new = (
            isinstance(node.func, ast.Call)
            and isinstance(node.func.func, ast.Name)
            and node.func.func.id == "getattr"
            and len(node.func.args) >= 2
            and isinstance(node.func.args[1], ast.Constant)
            and node.func.args[1].value == "__new__"
        )
        if direct_new or getattr_new:
            owner = ".".join(self.stack) if self.stack else "<module>"
            self.constructor_bypasses.append(
                Location(self.path, node.lineno, owner, "explicit __new__ call bypasses normal construction")
            )
        self.generic_visit(node)

    def _inspect_licensed_test(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, owner: str
    ) -> None:
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        for argument in arguments:
            if argument.arg in TEST_DOUBLE_ARGUMENTS:
                self.licensed_doubles.append(
                    Location(self.path, argument.lineno, owner, f"licensed test requests {argument.arg}")
                )
        for descendant in ast.walk(node):
            if isinstance(descendant, ast.Call):
                name = _call_name(descendant.func)
                if name in TEST_DOUBLE_CALLS or (name is not None and _looks_like_double(name)):
                    self.licensed_doubles.append(
                        Location(self.path, descendant.lineno, owner, f"licensed test calls test double {name}")
                    )
                if isinstance(descendant.func, ast.Attribute):
                    rendered = ast.unparse(descendant.func.value)
                    if rendered.split(".", 1)[0] in TEST_DOUBLE_ARGUMENTS:
                        self.licensed_doubles.append(
                            Location(
                                self.path,
                                descendant.lineno,
                                owner,
                                f"licensed test uses {rendered}.{descendant.func.attr}",
                            )
                        )
            elif isinstance(descendant, (ast.Name, ast.ClassDef, ast.FunctionDef)):
                name = descendant.id if isinstance(descendant, ast.Name) else descendant.name
                if descendant is not node and _looks_like_double(name):
                    self.licensed_doubles.append(
                        Location(self.path, descendant.lineno, owner, f"licensed test references test double {name}")
                    )


def _module_is_licensed(tree: ast.Module) -> bool:
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in targets):
            value = statement.value
            if value is not None and _marker_is_licensed(value):
                return True
    return False


def measure_repository(root: Path, paths: Iterable[str] | None = None) -> Measurement:
    selected = tuple(paths) if paths is not None else tracked_paths(root)
    source_paths = tuple(path for path in selected if _is_source_like(path))
    python_paths = tuple(path for path in selected if path.endswith(".py"))
    oversized_files: dict[str, int] = {}
    function_rows: list[tuple[str, str, str, int, int]] = []
    handler_rows: list[tuple[str, str, str, int]] = []
    bypasses: list[Location] = []
    doubles: list[Location] = []

    for relative in source_paths:
        text = (root / relative).read_text(encoding="utf-8")
        lines = _physical_lines(text)
        if lines > FILE_LIMIT:
            oversized_files[relative] = lines
        if not relative.endswith(".py"):
            continue
        tree = ast.parse(text, filename=relative)
        inventory = _PythonInventory(relative, module_licensed=_module_is_licensed(tree))
        inventory.visit(tree)
        function_rows.extend(
            (relative, owner, node_type, start, end)
            for owner, node_type, start, end in inventory.functions
            if end - start + 1 > FUNCTION_LIMIT
        )
        handler_rows.extend(
            (relative, owner, caught, line) for owner, caught, line in inventory.handlers
        )
        bypasses.extend(inventory.constructor_bypasses)
        doubles.extend(inventory.licensed_doubles)

    functions: dict[str, int] = {}
    grouped_functions: defaultdict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
    for path, owner, node_type, start, end in function_rows:
        grouped_functions[(path, owner, node_type)].append((start, end))
    for identity, rows in grouped_functions.items():
        for occurrence, (start, end) in enumerate(sorted(rows), 1):
            functions[_qualified_key([*identity, occurrence])] = end - start + 1

    handlers: set[str] = set()
    grouped_handlers: defaultdict[tuple[str, str, str], list[int]] = defaultdict(list)
    for path, owner, caught, line in handler_rows:
        grouped_handlers[(path, owner, caught)].append(line)
    for identity, lines in grouped_handlers.items():
        for occurrence, _line in enumerate(sorted(lines), 1):
            handlers.add(_qualified_key([*identity, occurrence]))

    return Measurement(
        oversized_files=dict(sorted(oversized_files.items())),
        oversized_functions=dict(sorted(functions.items())),
        broad_nonreraising_handlers=frozenset(handlers),
        hard_constructor_bypasses=tuple(sorted(bypasses, key=lambda item: (item.path, item.line))),
        licensed_test_doubles=tuple(sorted(set(doubles), key=lambda item: (item.path, item.line, item.detail))),
        python_file_count=len(python_paths),
        source_file_count=len(source_paths),
    )


def baseline_document(measurement: Measurement) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "limits": {"source_file_lines": FILE_LIMIT, "python_function_lines": FUNCTION_LIMIT},
        "oversized_source_files": dict(measurement.oversized_files),
        "oversized_python_functions": dict(measurement.oversized_functions),
        "runtime_broad_nonreraising_handlers": sorted(measurement.broad_nonreraising_handlers),
    }


def parse_baseline(document: object, *, source: str) -> tuple[Baseline | None, list[str]]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return None, [f"{source} must contain a JSON object"]
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{source} schema_version must be {SCHEMA_VERSION}")
    limits = document.get("limits")
    expected_limits = {"source_file_lines": FILE_LIMIT, "python_function_lines": FUNCTION_LIMIT}
    if limits != expected_limits:
        errors.append(f"{source} limits must remain {expected_limits}")

    def integer_map(name: str) -> dict[str, int]:
        value = document.get(name)
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or isinstance(item, bool) or not isinstance(item, int)
            for key, item in value.items()
        ):
            errors.append(f"{source} {name} must be a string-to-integer object")
            return {}
        return dict(value)

    files = integer_map("oversized_source_files")
    functions = integer_map("oversized_python_functions")
    raw_handlers = document.get("runtime_broad_nonreraising_handlers")
    if not isinstance(raw_handlers, list) or any(not isinstance(item, str) for item in raw_handlers):
        errors.append(f"{source} runtime_broad_nonreraising_handlers must be a string list")
        handlers: frozenset[str] = frozenset()
    elif len(raw_handlers) != len(set(raw_handlers)):
        errors.append(f"{source} runtime_broad_nonreraising_handlers contains duplicates")
        handlers = frozenset(raw_handlers)
    else:
        handlers = frozenset(raw_handlers)
    if any(lines <= FILE_LIMIT for lines in files.values()):
        errors.append(f"{source} contains a source-file allowance at or below {FILE_LIMIT}")
    if any(lines <= FUNCTION_LIMIT for lines in functions.values()):
        errors.append(f"{source} contains a function allowance at or below {FUNCTION_LIMIT}")
    return (None if errors else Baseline(files, functions, handlers)), errors


def load_baseline(path: Path) -> tuple[Baseline | None, list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot load structural baseline {path}: {exc}"]
    return parse_baseline(document, source=str(path))


def compare_measurement(measurement: Measurement, baseline: Baseline) -> list[str]:
    errors: list[str] = []

    def compare_sizes(label: str, current: Mapping[str, int], allowed: Mapping[str, int]) -> None:
        for identity in sorted(current.keys() - allowed.keys()):
            errors.append(f"new oversized {label}: {identity} ({current[identity]} lines)")
        for identity in sorted(allowed.keys() - current.keys()):
            errors.append(f"stale {label} allowance must be removed: {identity}")
        for identity in sorted(current.keys() & allowed.keys()):
            if current[identity] > allowed[identity]:
                errors.append(
                    f"oversized {label} grew: {identity} ({current[identity]} > {allowed[identity]})"
                )
            elif current[identity] < allowed[identity]:
                errors.append(
                    f"stale {label} allowance must shrink: {identity} ({allowed[identity]} -> {current[identity]})"
                )

    compare_sizes("source file", measurement.oversized_files, baseline.oversized_files)
    compare_sizes("function", measurement.oversized_functions, baseline.oversized_functions)
    for identity in sorted(measurement.broad_nonreraising_handlers - baseline.broad_nonreraising_handlers):
        errors.append(f"new broad non-reraising runtime handler: {identity}")
    for identity in sorted(baseline.broad_nonreraising_handlers - measurement.broad_nonreraising_handlers):
        errors.append(f"stale broad-handler allowance must be removed: {identity}")
    for item in measurement.hard_constructor_bypasses:
        errors.append(f"hard constructor bypass: {item.path}:{item.line} {item.owner}: {item.detail}")
    for item in measurement.licensed_test_doubles:
        errors.append(f"licensed VectorBT test double: {item.path}:{item.line} {item.owner}: {item.detail}")
    return errors


def compare_baselines(candidate: Baseline, base: Baseline) -> list[str]:
    errors: list[str] = []

    def monotonic(label: str, current: Mapping[str, int], prior: Mapping[str, int]) -> None:
        for identity in sorted(current.keys() - prior.keys()):
            errors.append(f"baseline may not add {label}: {identity}")
        for identity in sorted(current.keys() & prior.keys()):
            if current[identity] > prior[identity]:
                errors.append(
                    f"baseline may not raise {label}: {identity} ({current[identity]} > {prior[identity]})"
                )

    monotonic("oversized source file", candidate.oversized_files, base.oversized_files)
    monotonic("oversized function", candidate.oversized_functions, base.oversized_functions)
    for identity in sorted(candidate.broad_nonreraising_handlers - base.broad_nonreraising_handlers):
        errors.append(f"baseline may not add broad non-reraising handler: {identity}")
    return errors


def baseline_at_ref(root: Path, baseline_path: Path, ref: str) -> tuple[Baseline | None, list[str]]:
    if not ref or set(ref) == {"0"}:
        return None, []
    verified = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if verified.returncode:
        return None, [f"cannot resolve base ref {ref}: {verified.stderr.strip()}"]
    relative = baseline_path.resolve().relative_to(root.resolve()).as_posix()
    shown = _git(root, "show", f"{ref}:{relative}")
    if shown.returncode:
        return None, []  # Establishing change: the base commit has no baseline yet.
    try:
        document = json.loads(shown.stdout)
    except json.JSONDecodeError as exc:
        return None, [f"cannot parse structural baseline at {ref}: {exc}"]
    return parse_baseline(document, source=f"{ref}:{relative}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--base-ref")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    baseline_path = args.baseline if args.baseline.is_absolute() else root / args.baseline

    try:
        measurement = measure_repository(root)
    except (OSError, RuntimeError, SyntaxError, UnicodeError) as exc:
        print(f"Structural maintainability check failed: {exc}")
        return 1
    print(
        "Structural maintainability report\n"
        f"source-like files: {measurement.source_file_count}\n"
        f"python files: {measurement.python_file_count}\n"
        f"oversized source files: {len(measurement.oversized_files)}\n"
        f"oversized functions: {len(measurement.oversized_functions)}\n"
        f"broad non-reraising runtime handlers: {len(measurement.broad_nonreraising_handlers)}\n"
        f"hard constructor bypasses: {len(measurement.hard_constructor_bypasses)}\n"
        f"licensed-test doubles: {len(measurement.licensed_test_doubles)}"
    )

    if args.write_baseline:
        unsafe = [
            *measurement.hard_constructor_bypasses,
            *measurement.licensed_test_doubles,
        ]
        if unsafe:
            print("Refusing to write a baseline that grandfathers prohibited construction/test behavior.")
            return 1
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(baseline_document(measurement), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote structural baseline: {baseline_path.relative_to(root)}")
        return 0

    baseline, errors = load_baseline(baseline_path)
    if baseline is not None:
        errors.extend(compare_measurement(measurement, baseline))
    if args.base_ref and baseline is not None:
        base, base_errors = baseline_at_ref(root, baseline_path, args.base_ref)
        errors.extend(base_errors)
        if base is not None:
            errors.extend(compare_baselines(baseline, base))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Structural maintainability checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
