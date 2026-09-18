"""Fail-closed orchestration for one authenticated paper observer proof.

This controller has no transport, process, Docker, OneCLI, or broker client.
A reviewed target adapter supplies the narrow ports below. Broker credential
values never enter the controller and public evidence is strictly redacted.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Callable, Protocol
from uuid import UUID, uuid4

from execution.paper_binding import PaperDeploymentBinding, PaperDeploymentBindingError


EVIDENCE_SCHEMA = "qf.paper-observer-bootstrap-evidence.v1"
JOURNAL_SCHEMA = "qf.paper-observer-bootstrap-journal.v1"
PLAN_SCHEMA = "qf.paper-observer-bootstrap-plan.v1"
PAPER_HOST = "paper-api.alpaca.markets"
OWNER_ATTESTATION = "owner-attestation:decision-272"
ALLOWED_REQUESTS = (
    ("GET", PAPER_HOST, "/v2/account"),
    ("GET", PAPER_HOST, "/v2/positions"),
)
SECRET_HEADERS = {
    "Dedicated Paper Account - Key ID": "APCA-API-KEY-ID",
    "Dedicated Paper Account - Secret": "APCA-API-SECRET-KEY",
}
_HEX40 = re.compile(r"[0-9a-f]{40}", re.ASCII)
_OPERATION = re.compile(r"[a-z0-9][a-z0-9-]{7,63}", re.ASCII)
_JOURNAL_DIR = ".qf-paper-observer-journals"
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class BootstrapFailure(RuntimeError):
    """A sanitized failure carrying only a fixed stage name."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]{3,64}", stage) else "internal"
        super().__init__("paper observer bootstrap rejected")


def _uuid(value: object) -> str:
    if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
        raise BootstrapFailure("configuration")
    return value


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


@dataclass(frozen=True, repr=False)
class BootstrapPlan:
    """Protected plan for one disposable proof transaction."""

    operation_id: str
    deployment_id: str
    owner_attestation_reference: str
    expected_account_id: str = field(repr=False)
    source_revision: str
    schema: str = PLAN_SCHEMA

    def __post_init__(self) -> None:
        try:
            if self.schema != PLAN_SCHEMA or not _OPERATION.fullmatch(self.operation_id):
                raise BootstrapFailure("configuration")
            if not _HEX40.fullmatch(self.source_revision):
                raise BootstrapFailure("configuration")
            binding = PaperDeploymentBinding(
                account_id=self.expected_account_id,
                deployment_id=self.deployment_id,
                owner_attestation_reference=self.owner_attestation_reference,
            )
            if binding.owner_attestation_reference != OWNER_ATTESTATION:
                raise BootstrapFailure("account_binding")
        except (PaperDeploymentBindingError, TypeError):
            raise BootstrapFailure("account_binding") from None

    @property
    def binding(self) -> PaperDeploymentBinding:
        return PaperDeploymentBinding(
            account_id=self.expected_account_id,
            deployment_id=self.deployment_id,
            owner_attestation_reference=self.owner_attestation_reference,
        )


class GatewayControl(Protocol):
    """Privileged port implemented only by a separately reviewed adapter."""

    def preflight(self) -> dict[str, object]: ...
    def owned_resources(self, operation_id: str) -> dict[str, list[str]]: ...
    def secret_metadata(self) -> list[dict[str, object]]: ...
    def create_rule(self, *, name: str, action: str, targets: list[dict[str, str]]) -> str: ...
    def set_rule_order(self, rule_ids: list[str]) -> None: ...
    def publish(self) -> None: ...
    def create_actor(self, *, name: str, identifier: str) -> str: ...
    def grant_secret(self, actor_id: str, secret_id: str) -> None: ...
    def issue_capability(self, actor_id: str) -> bytes: ...
    def export_ca(self) -> bytes: ...
    def restart_gateway(self) -> None: ...
    def audit_summary(self, actor_id: str, correlation_fingerprint: str) -> dict[str, object]: ...
    def delete_grant(self, actor_id: str, secret_id: str) -> None: ...
    def delete_actor(self, actor_id: str) -> None: ...
    def delete_rule(self, rule_id: str) -> None: ...
    def no_leak_scan(self, *, sensitive_values: tuple[bytes, ...], secret_ids: tuple[str, ...]) -> bool: ...


class ObserverProof(Protocol):
    """Unprivileged one-shot proof port; it has no persistent serve operation."""

    def policy_matrix(self, *, identity_file: Path, ca_file: Path) -> dict[str, dict[str, object]]: ...
    def observe_once(self, *, config_file: Path, identity_file: Path, ca_file: Path) -> dict[str, object]: ...
    def revoked_identity(self, *, identity_file: Path, ca_file: Path) -> dict[str, object]: ...
    def no_leak_scan(self, *, sensitive_values: tuple[bytes, ...]) -> bool: ...


def validate_secret_metadata(rows: object) -> tuple[str, str]:
    """Return the two secret IDs after validating metadata without values."""
    if type(rows) is not list or len(rows) != 2:
        raise BootstrapFailure("credential_metadata")
    found: dict[str, str] = {}
    expected_keys = {"id", "name", "type", "hostPattern", "pathPattern", "injectionConfig"}
    for row in rows:
        if type(row) is not dict or set(row) != expected_keys:
            raise BootstrapFailure("credential_metadata")
        name = row.get("name")
        header = SECRET_HEADERS.get(name) if type(name) is str else None
        injection = row.get("injectionConfig")
        if (header is None or row.get("type") != "generic"
                or row.get("hostPattern") != PAPER_HOST
                or row.get("pathPattern") not in {None, ""}
                or type(injection) is not dict
                or injection != {"headerName": header, "valueFormat": "{value}"}):
            raise BootstrapFailure("credential_metadata")
        secret_id = _uuid(row.get("id"))
        if name in found or secret_id in found.values():
            raise BootstrapFailure("credential_metadata")
        found[name] = secret_id
    if set(found) != set(SECRET_HEADERS):
        raise BootstrapFailure("credential_metadata")
    return tuple(found[name] for name in SECRET_HEADERS)  # type: ignore[return-value]


def validate_preflight(value: object, source_revision: str) -> None:
    expected = {
        "source_revision": source_revision,
        "images_pinned": True,
        "services_healthy": True,
        "gateway_only_egress": True,
        "gateway_only_actor": True,
        "actor_network_internal": True,
        "published_host_ports": 0,
        "credentialless_defaults_preserved": True,
    }
    if value != expected:
        raise BootstrapFailure("target_preflight")


def _matrix_expected() -> dict[str, dict[str, object]]:
    return {
        "account": {"method": "GET", "host": PAPER_HOST, "path": "/v2/account", "status": 200, "injection_count": 2},
        "positions": {"method": "GET", "host": PAPER_HOST, "path": "/v2/positions", "status": 200, "injection_count": 2},
        "wrong_host": {"method": "GET", "host": "fixture.qf.invalid", "path": "/v2/account", "status": 403, "injection_count": 0},
        "wrong_path": {"method": "GET", "host": PAPER_HOST, "path": "/v2/qf-denial-probe", "status": 403, "injection_count": 0},
        "wrong_method": {"method": "POST", "host": PAPER_HOST, "path": "/v2/account", "status": 403, "injection_count": 0},
        "missing_identity": {"method": "GET", "host": PAPER_HOST, "path": "/v2/account", "status": 407, "injection_count": 0},
        "invalid_identity": {"method": "GET", "host": PAPER_HOST, "path": "/v2/account", "status": 407, "injection_count": 0},
    }


def validate_policy_matrix(value: object, stage: str) -> None:
    if value != _matrix_expected():
        raise BootstrapFailure(stage)


def _audit_expected(plan: BootstrapPlan) -> dict[str, object]:
    correlation = _fingerprint(plan.operation_id)
    phases: list[dict[str, object]] = []
    sequence = 1
    matrix = _matrix_expected()
    phase_requests = (
        ("pre_restart", list(matrix.items())),
        ("post_restart", list(matrix.items())),
        ("observation", [("account", matrix["account"]), ("positions", matrix["positions"])]),
        ("revocation", [("retired_identity", {
            "method": "GET", "host": PAPER_HOST, "path": "/v2/account",
            "status": 407, "injection_count": 0,
        })]),
    )
    for phase_name, requests in phase_requests:
        rows = []
        for case, request in requests:
            rows.append({
                "sequence": sequence,
                "case": case,
                **request,
                "correlation_fingerprint": correlation,
                "recorded": True,
                "timestamp_present": True,
            })
            sequence += 1
        phases.append({"name": phase_name, "request_count": len(rows), "rows": rows})
    return {"correlation_fingerprint": correlation, "request_count": sequence - 1, "phases": phases}


def validate_audit(value: object, plan: BootstrapPlan) -> None:
    if value != _audit_expected(plan):
        raise BootstrapFailure("audit")


_HEALTH_KEYS = {
    "ready", "account_verified", "gateway_status", "observed_at", "position_count",
    "blocked_reason", "account_authorization_status", "deployment_ready", "order_submission_enabled",
}


def validate_observation(value: object, plan: BootstrapPlan) -> dict[str, object]:
    if type(value) is not dict or set(value) != {"health", "account_fingerprint", "requests"}:
        raise BootstrapFailure("observer")
    health = value.get("health")
    if (type(health) is not dict or set(health) != _HEALTH_KEYS
            or health.get("ready") is not True or health.get("account_verified") is not True
            or health.get("gateway_status") != "reachable" or health.get("blocked_reason") is not None
            or health.get("deployment_ready") is not False
            or health.get("order_submission_enabled") is not False
            or health.get("account_authorization_status") != "external_attestation_reference_unverified"
            or type(health.get("position_count")) is not int or health["position_count"] < 0
            or type(health.get("observed_at")) is not str
            or value.get("account_fingerprint") != _fingerprint(plan.expected_account_id)
            or value.get("requests") != [list(ALLOWED_REQUESTS[0]), list(ALLOWED_REQUESTS[1])]):
        raise BootstrapFailure("observer")
    try:
        observed = datetime.fromisoformat(health["observed_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError):
        raise BootstrapFailure("observer") from None
    return dict(health)


def _validate_owned(value: object, *, empty: bool) -> dict[str, list[str]]:
    if type(value) is not dict or set(value) != {"actors", "rules", "grants"}:
        raise BootstrapFailure("resource_ownership")
    if any(type(items) is not list or any(type(item) is not str for item in items) for items in value.values()):
        raise BootstrapFailure("resource_ownership")
    if empty and any(value.values()):
        raise BootstrapFailure("resource_collision")
    return value


def _safe_write(path: Path, data: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=False) as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _protected_parent(runtime_root: Path) -> tuple[Path, os.stat_result]:
    if not runtime_root.is_absolute() or runtime_root.name in {"", ".", ".."}:
        raise BootstrapFailure("runtime_staging")
    parent = runtime_root.parent
    try:
        parent_stat = parent.lstat()
        if (not stat.S_ISDIR(parent_stat.st_mode) or parent.is_symlink()
                or parent.resolve(strict=True) != parent
                or parent_stat.st_uid != os.geteuid()
                or stat.S_IMODE(parent_stat.st_mode) & 0o077):
            raise BootstrapFailure("runtime_staging")
    except (OSError, RuntimeError):
        raise BootstrapFailure("runtime_staging") from None
    return parent, parent_stat


def _journal_path(plan: BootstrapPlan, runtime_root: Path) -> Path:
    return runtime_root.parent / _JOURNAL_DIR / f"{plan.operation_id}.json"


def _journal_bytes(state: dict[str, object]) -> bytes:
    return (json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _journal_create(path: Path, state: dict[str, object]) -> None:
    _safe_write(path, _journal_bytes(state), 0o600)
    _fsync_directory(path.parent)


def _journal_write(path: Path, state: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        _safe_write(temporary, _journal_bytes(state), 0o600)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _new_journal(plan: BootstrapPlan, runtime_root: Path) -> tuple[Path, dict[str, object]]:
    parent, parent_stat = _protected_parent(runtime_root)
    journal_dir = parent / _JOURNAL_DIR
    try:
        if journal_dir.exists() or journal_dir.is_symlink():
            directory_stat = journal_dir.lstat()
            if (journal_dir.is_symlink() or not stat.S_ISDIR(directory_stat.st_mode)
                    or directory_stat.st_uid != os.geteuid()
                    or stat.S_IMODE(directory_stat.st_mode) != 0o700):
                raise BootstrapFailure("journal_ownership")
        else:
            journal_dir.mkdir(mode=0o700)
            os.chmod(journal_dir, 0o700)
            _fsync_directory(parent)
        path = _journal_path(plan, runtime_root)
        if path.exists() or path.is_symlink():
            raise BootstrapFailure("recovery_required")
        staging_path = parent / (
            f".qf-{plan.operation_id}-{uuid4().hex}.runtime-stage"
        )
        if staging_path.exists() or staging_path.is_symlink():
            raise BootstrapFailure("runtime_staging")
        state: dict[str, object] = {
            "schema": JOURNAL_SCHEMA,
            "operation_id": plan.operation_id,
            "operation_fingerprint": _fingerprint(plan.operation_id),
            "deployment_fingerprint": _fingerprint(plan.deployment_id),
            "account_fingerprint": _fingerprint(plan.expected_account_id),
            "attestation_reference": plan.owner_attestation_reference,
            "source_revision": plan.source_revision,
            "phase": "prepared",
            "protected_root": {"path": str(parent), "device": parent_stat.st_dev, "inode": parent_stat.st_ino},
            "runtime": {
                "path": str(runtime_root),
                "staging_path": str(staging_path),
                "creation_pending": False,
                "created": False,
                "published": False,
                "device": None,
                "inode": None,
            },
            "rules": [],
            "actor_id": None,
            "grants": [],
            "policy_mutated": False,
        }
        _journal_create(path, state)
        return path, state
    except BootstrapFailure:
        raise
    except Exception:
        raise BootstrapFailure("journal_ownership") from None


def _validated_journal(plan: BootstrapPlan, runtime_root: Path) -> tuple[Path, dict[str, object]]:
    parent, parent_stat = _protected_parent(runtime_root)
    path = _journal_path(plan, runtime_root)
    try:
        directory_stat = path.parent.lstat()
        if (path.parent.is_symlink() or not stat.S_ISDIR(directory_stat.st_mode)
                or directory_stat.st_uid != os.geteuid()
                or stat.S_IMODE(directory_stat.st_mode) != 0o700):
            raise BootstrapFailure("recovery_ownership")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            file_stat = os.fstat(descriptor)
            if (not stat.S_ISREG(file_stat.st_mode)
                    or file_stat.st_uid != os.geteuid()
                    or stat.S_IMODE(file_stat.st_mode) != 0o600):
                raise BootstrapFailure("recovery_ownership")
            with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as source:
                state = json.load(source)
        finally:
            os.close(descriptor)
    except BootstrapFailure:
        raise
    except Exception:
        raise BootstrapFailure("recovery_ownership") from None
    expected_keys = {
        "schema", "operation_id", "operation_fingerprint", "deployment_fingerprint",
        "account_fingerprint", "attestation_reference", "source_revision", "phase",
        "protected_root", "runtime", "rules", "actor_id", "grants", "policy_mutated",
    }
    protected = state.get("protected_root") if type(state) is dict else None
    runtime = state.get("runtime") if type(state) is dict else None
    valid = (
        type(state) is dict and set(state) == expected_keys
        and state.get("schema") == JOURNAL_SCHEMA
        and state.get("operation_id") == plan.operation_id
        and state.get("operation_fingerprint") == _fingerprint(plan.operation_id)
        and state.get("deployment_fingerprint") == _fingerprint(plan.deployment_id)
        and state.get("account_fingerprint") == _fingerprint(plan.expected_account_id)
        and state.get("attestation_reference") == plan.owner_attestation_reference
        and state.get("source_revision") == plan.source_revision
        and type(state.get("phase")) is str
        and type(state.get("rules")) is list
        and all(type(item) is str for item in state.get("rules", []))
        and (state.get("actor_id") is None or type(state.get("actor_id")) is str)
        and type(state.get("grants")) is list
        and all(type(item) is str for item in state.get("grants", []))
        and type(state.get("policy_mutated")) is bool
        and type(protected) is dict and set(protected) == {"path", "device", "inode"}
        and protected.get("path") == str(parent)
        and protected.get("device") == parent_stat.st_dev
        and protected.get("inode") == parent_stat.st_ino
        and type(runtime) is dict
        and set(runtime) == {
            "path", "staging_path", "creation_pending", "created", "published",
            "device", "inode",
        }
        and runtime.get("path") == str(runtime_root)
        and type(runtime.get("created")) is bool
        and type(runtime.get("creation_pending")) is bool
        and type(runtime.get("published")) is bool
    )
    if not valid:
        raise BootstrapFailure("recovery_ownership")
    staging_path = Path(runtime["staging_path"]) if type(runtime.get("staging_path")) is str else None
    staging_name = (
        re.fullmatch(
            rf"\.qf-{re.escape(plan.operation_id)}-[0-9a-f]{{32}}\.runtime-stage",
            staging_path.name,
        )
        if staging_path is not None else None
    )
    if (staging_path is None or not staging_path.is_absolute()
            or staging_path.parent != parent or staging_name is None
            or runtime["published"] is True and runtime["created"] is not True
            or runtime["created"] is True and runtime["creation_pending"] is True):
        raise BootstrapFailure("recovery_ownership")
    if runtime["created"] is True:
        if type(runtime.get("device")) is not int or type(runtime.get("inode")) is not int:
            raise BootstrapFailure("recovery_ownership")
    elif runtime.get("device") is not None or runtime.get("inode") is not None:
        raise BootstrapFailure("recovery_ownership")
    return path, state


def _record(
    path: Path,
    state: dict[str, object],
    phase: str,
    checkpoint: Callable[[str], None] | None,
) -> None:
    state["phase"] = phase
    _journal_write(path, state)
    if checkpoint is not None:
        checkpoint(phase)


def _intent(path: Path, state: dict[str, object], phase: str) -> None:
    state["phase"] = f"{phase}_intent"
    _journal_write(path, state)


def _runtime_paths(root: Path) -> tuple[Path, Path, Path, Path]:
    return root / ".qf-owned-operation", root / "identity", root / "gateway-ca.pem", root / "config.json"


def _runtime_configuration(plan: BootstrapPlan) -> bytes:
    value = {
        "expected_account_id": plan.expected_account_id,
        "deployment_id": plan.deployment_id,
        "owner_attestation_reference": plan.owner_attestation_reference,
        "proxy_url": "http://gateway-relay:10255",
        "identity_file": "/run/paper/identity",
        "ca_file": "/run/paper/gateway-ca.pem",
        "refresh_seconds": 60,
    }
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _publish_runtime(staging_path: Path, runtime_root: Path) -> None:
    """Publish with Linux renameat2 and never fall back to replacing rename.

    A missing libc symbol, unsupported kernel, or unsupported filesystem fails
    the transaction. Falling back to os.rename would replace an empty foreign
    directory and violate the runtime ownership boundary.
    """
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        raise BootstrapFailure("runtime_staging")
    renameat2.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD, os.fsencode(staging_path),
        _AT_FDCWD, os.fsencode(runtime_root),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _remove_owned_runtime(
    plan: BootstrapPlan,
    state: dict[str, object],
    runtime_root: Path,
) -> bool:
    runtime = state["runtime"]
    protected = state["protected_root"]
    assert isinstance(runtime, dict) and isinstance(protected, dict)
    staging_path = Path(runtime["staging_path"])
    try:
        parent_stat = runtime_root.parent.lstat()
        if (parent_stat.st_dev != protected["device"]
                or parent_stat.st_ino != protected["inode"]):
            return False

        staging_present = staging_path.exists() or staging_path.is_symlink()
        if staging_present:
            stage_stat = staging_path.lstat()
            if staging_path.is_symlink() or not stat.S_ISDIR(stage_stat.st_mode):
                return False
            if runtime.get("created") is True:
                if (stage_stat.st_dev != runtime["device"]
                        or stage_stat.st_ino != runtime["inode"]):
                    return False
                marker, _, _, _ = _runtime_paths(staging_path)
                marker_invalid = (
                    (marker.exists() or marker.is_symlink())
                    and (
                        marker.is_symlink()
                        or marker.read_text("ascii") != plan.operation_id
                    )
                )
                if marker_invalid:
                    return False
                shutil.rmtree(staging_path)
            elif (runtime.get("creation_pending") is True
                    and not any(staging_path.iterdir())):
                # The unpredictable staging name was committed to the journal
                # before mkdir. An empty directory at that name is the only
                # safe recovery case before its inode can be recorded.
                staging_path.rmdir()
            else:
                return False

        requested_present = runtime_root.exists() or runtime_root.is_symlink()
        if requested_present:
            if runtime.get("created") is not True:
                return False
            root_stat = runtime_root.lstat()
            marker, _, _, _ = _runtime_paths(runtime_root)
            marker_invalid = (
                (marker.exists() or marker.is_symlink())
                and (
                    marker.is_symlink()
                    or marker.read_text("ascii") != plan.operation_id
                )
            )
            if (runtime_root.is_symlink() or not stat.S_ISDIR(root_stat.st_mode)
                    or root_stat.st_dev != runtime["device"]
                    or root_stat.st_ino != runtime["inode"]
                    or marker_invalid):
                return False
            shutil.rmtree(runtime_root)

        return (
            not runtime_root.exists() and not runtime_root.is_symlink()
            and not staging_path.exists() and not staging_path.is_symlink()
        )
    except Exception:
        return False


def _policy_rules(operation_id: str) -> tuple[dict[str, object], ...]:
    return (
        {"name": f"qf-{operation_id}-account", "action": "allow", "targets": [{"kind": "network", "hostPattern": PAPER_HOST, "pathPattern": "/v2/account", "method": "GET"}]},
        {"name": f"qf-{operation_id}-positions", "action": "allow", "targets": [{"kind": "network", "hostPattern": PAPER_HOST, "pathPattern": "/v2/positions", "method": "GET"}]},
        {"name": f"qf-{operation_id}-block", "action": "block", "targets": [{"kind": "network", "hostPattern": "*"}]},
    )


def _base_report(plan: BootstrapPlan) -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA,
        "outcome": "failed_closed",
        "failed_stage": None,
        "source_revision": plan.source_revision,
        "operation_fingerprint": _fingerprint(plan.operation_id),
        "authorized_requests": ["GET paper-api.alpaca.markets/v2/account", "GET paper-api.alpaca.markets/v2/positions"],
        "account_binding": {"decision": 272, "fingerprint_match": False, "external_attestation_verified_by_process": False},
        "checks": {
            "target_preflight": False, "unique_ownership": False, "credential_metadata": False,
            "durable_journal": False, "policy_before_restart": False, "policy_after_restart": False,
            "observer": False, "revocation": False, "audit": False, "no_leak": False, "cleanup": False,
        },
        "observer_health": None,
        "persistent_worker_started": False,
        "order_submission_enabled": False,
        "credential_values_exposed": False,
    }


def _grant_pairs(
    owned: dict[str, list[str]], actors: list[str], journal_grants: list[str],
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in journal_grants + owned["grants"]:
        try:
            actor_id, secret_id = item.split(":", 1)
            _uuid(actor_id)
            _uuid(secret_id)
        except (ValueError, BootstrapFailure):
            raise BootstrapFailure("recovery_ownership") from None
        if actor_id not in actors:
            raise BootstrapFailure("recovery_ownership")
        pair = (actor_id, secret_id)
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def _recovery_inventory(
    state: dict[str, object],
    owned: dict[str, list[str]],
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """Accept only resources explained by the journal or its current intent."""
    phase = state["phase"]
    assert isinstance(phase, str)
    journal_actor = state.get("actor_id")
    journal_actors = [journal_actor] if isinstance(journal_actor, str) else []
    for actor_id in [*journal_actors, *owned["actors"]]:
        _uuid(actor_id)
    unknown_actors = [
        actor_id for actor_id in owned["actors"] if actor_id not in journal_actors
    ]
    if unknown_actors and not (
        not journal_actors and phase == "actor_created_intent"
        and len(unknown_actors) == 1
    ):
        raise BootstrapFailure("recovery_collision")
    actors = list(dict.fromkeys([*journal_actors, *owned["actors"]]))

    journal_rules = list(state["rules"])  # type: ignore[arg-type]
    for rule_id in [*journal_rules, *owned["rules"]]:
        _uuid(rule_id)
    unknown_rules = [
        rule_id for rule_id in owned["rules"] if rule_id not in journal_rules
    ]
    rule_intent = re.fullmatch(r"rule_([123])_created_intent", phase)
    if unknown_rules and not (
        rule_intent is not None and len(unknown_rules) == 1
        and len(journal_rules) + 1 == int(rule_intent.group(1))
    ):
        raise BootstrapFailure("recovery_collision")
    rules = list(dict.fromkeys([*journal_rules, *owned["rules"]]))

    journal_grants = list(state["grants"])  # type: ignore[arg-type]
    grants = _grant_pairs(owned, actors, journal_grants)
    unknown_grants = [
        item for item in owned["grants"] if item not in journal_grants
    ]
    grant_intent = re.fullmatch(r"grant_([12])_created_intent", phase)
    if unknown_grants and not (
        grant_intent is not None and len(unknown_grants) == 1
        and len(journal_grants) + 1 == int(grant_intent.group(1))
    ):
        raise BootstrapFailure("recovery_collision")
    return actors, rules, grants


def recover_bootstrap(
    plan: BootstrapPlan,
    gateway: GatewayControl,
    *,
    runtime_root: Path,
    checkpoint: Callable[[str], None] | None = None,
) -> bool:
    """Idempotently remove only an exact journaled interrupted operation.

    A caller marker never establishes ownership. Recovery requires a protected
    journal matching the plan and path. Runtime deletion additionally requires
    the journaled parent and runtime device/inode pair.
    """
    path, state = _validated_journal(plan, runtime_root)
    try:
        owned = _validate_owned(gateway.owned_resources(plan.operation_id), empty=False)
    except BootstrapFailure:
        raise
    except Exception:
        return False
    actors, rules, grants = _recovery_inventory(state, owned)
    cleanup_ok = True
    try:
        for actor_id, secret_id in reversed(grants.copy()):
            phase = f"cleanup_grant_{len(grants)}"
            _intent(path, state, phase)
            try:
                gateway.delete_grant(actor_id, secret_id)
            except Exception:
                cleanup_ok = False
                continue
            grants.remove((actor_id, secret_id))
            state["grants"] = [f"{actor}:{secret}" for actor, secret in grants]
            _record(path, state, phase, checkpoint)
        for actor_id in reversed(actors):
            _intent(path, state, "cleanup_actor")
            try:
                gateway.delete_actor(actor_id)
            except Exception:
                cleanup_ok = False
                continue
            if state.get("actor_id") == actor_id:
                state["actor_id"] = None
            _record(path, state, "cleanup_actor", checkpoint)
        for rule_id in reversed(rules.copy()):
            phase = f"cleanup_rule_{len(rules)}"
            _intent(path, state, phase)
            try:
                gateway.delete_rule(rule_id)
            except Exception:
                cleanup_ok = False
                continue
            rules.remove(rule_id)
            state["rules"] = list(rules)
            _record(path, state, phase, checkpoint)
        if state.get("policy_mutated"):
            _intent(path, state, "cleanup_publish")
            try:
                gateway.publish()
            except Exception:
                cleanup_ok = False
            else:
                state["policy_mutated"] = False
                _record(path, state, "cleanup_publish", checkpoint)
        runtime = state["runtime"]
        assert isinstance(runtime, dict)
        _intent(path, state, "cleanup_runtime")
        if not _remove_owned_runtime(plan, state, runtime_root):
            cleanup_ok = False
        else:
            state["runtime"] = {
                "path": str(runtime_root),
                "staging_path": runtime["staging_path"],
                "creation_pending": False,
                "created": False,
                "published": False,
                "device": None,
                "inode": None,
            }
            _record(path, state, "cleanup_runtime", checkpoint)
        if any(_validate_owned(gateway.owned_resources(plan.operation_id), empty=False).values()):
            cleanup_ok = False
    except Exception:
        cleanup_ok = False
    if cleanup_ok:
        try:
            state["phase"] = "cleanup_complete"
            _journal_write(path, state)
            path.unlink()
            _fsync_directory(path.parent)
        except Exception:
            cleanup_ok = False
    return cleanup_ok


def run_bootstrap(
    plan: BootstrapPlan,
    gateway: GatewayControl,
    observer: ObserverProof,
    *,
    runtime_root: Path,
    checkpoint: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Run one transaction and always attempt exact journaled cleanup."""
    report = _base_report(plan)
    checks = report["checks"]
    assert isinstance(checks, dict)
    stage = "target_preflight"
    journal_path: Path | None = None
    journal: dict[str, object] | None = None
    actor_id: str | None = None
    secret_ids: tuple[str, ...] = ()
    capability = b""
    try:
        validate_preflight(gateway.preflight(), plan.source_revision)
        checks[stage] = True
        stage = "unique_ownership"
        candidate_journal = _journal_path(plan, runtime_root)
        if candidate_journal.exists() or candidate_journal.is_symlink():
            raise BootstrapFailure("recovery_required")
        _validate_owned(gateway.owned_resources(plan.operation_id), empty=True)
        checks[stage] = True
        stage = "credential_metadata"
        secret_ids = validate_secret_metadata(gateway.secret_metadata())
        checks[stage] = True
        stage = "runtime_staging"
        _protected_parent(runtime_root)
        if runtime_root.exists() or runtime_root.is_symlink():
            raise BootstrapFailure(stage)

        stage = "durable_journal"
        journal_path, journal = _new_journal(plan, runtime_root)
        checks[stage] = True
        if checkpoint is not None:
            checkpoint("prepared")

        stage = "policy_creation"
        rules = list(journal["rules"])
        for index, rule in enumerate(_policy_rules(plan.operation_id), start=1):
            phase = f"rule_{index}_created"
            # The intent must assume the remote create may commit even when its
            # response is lost; recovery will therefore republish after delete.
            journal["policy_mutated"] = True
            _intent(journal_path, journal, phase)
            rule_id = _uuid(gateway.create_rule(**rule))  # type: ignore[arg-type]
            rules.append(rule_id)
            journal["rules"] = list(rules)
            _record(journal_path, journal, phase, checkpoint)
        _intent(journal_path, journal, "rule_order_set")
        gateway.set_rule_order(rules)
        _record(journal_path, journal, "rule_order_set", checkpoint)
        _intent(journal_path, journal, "policy_published")
        gateway.publish()
        _record(journal_path, journal, "policy_published", checkpoint)

        stage = "actor_creation"
        _intent(journal_path, journal, "actor_created")
        actor_id = _uuid(gateway.create_actor(
            name="Quant Factory Dedicated Paper Account observer proof",
            identifier=f"qf-{plan.operation_id}",
        ))
        journal["actor_id"] = actor_id
        _record(journal_path, journal, "actor_created", checkpoint)
        grants: list[str] = []
        for index, secret_id in enumerate(secret_ids, start=1):
            phase = f"grant_{index}_created"
            _intent(journal_path, journal, phase)
            gateway.grant_secret(actor_id, secret_id)
            grants.append(f"{actor_id}:{secret_id}")
            journal["grants"] = list(grants)
            _record(journal_path, journal, phase, checkpoint)
        _intent(journal_path, journal, "capability_issued")
        capability = gateway.issue_capability(actor_id)
        if not 16 <= len(capability) <= 1024 or not re.fullmatch(rb"[!-~]+", capability):
            raise BootstrapFailure("runtime_staging")
        _record(journal_path, journal, "capability_issued", checkpoint)
        ca = gateway.export_ca()
        if b"PRIVATE KEY" in ca or b"BEGIN CERTIFICATE" not in ca:
            raise BootstrapFailure("runtime_staging")

        stage = "runtime_staging"
        runtime_state = journal["runtime"]
        assert isinstance(runtime_state, dict)
        staging_root = Path(runtime_state["staging_path"])
        runtime_state["creation_pending"] = True
        _intent(journal_path, journal, "runtime_created")
        staging_root.mkdir(mode=0o700, parents=False)
        directory = os.open(
            staging_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            os.fchmod(directory, 0o700)
            os.fsync(directory)
            root_stat = os.fstat(directory)
        finally:
            os.close(directory)
        journal["runtime"] = {
            "path": str(runtime_root),
            "staging_path": str(staging_root),
            "creation_pending": False,
            "created": True,
            "published": False,
            "device": root_stat.st_dev, "inode": root_stat.st_ino,
        }
        _record(journal_path, journal, "runtime_created", checkpoint)
        marker, identity_file, ca_file, config_file = _runtime_paths(staging_root)
        for phase, file_path, contents, mode in (
            ("runtime_marker_written", marker, plan.operation_id.encode("ascii"), 0o400),
            ("runtime_identity_written", identity_file, capability, 0o400),
            ("runtime_ca_written", ca_file, ca, 0o444),
            ("runtime_config_written", config_file, _runtime_configuration(plan), 0o400),
        ):
            _intent(journal_path, journal, phase)
            _safe_write(file_path, contents, mode)
            _fsync_directory(staging_root)
            _record(journal_path, journal, phase, checkpoint)

        _intent(journal_path, journal, "runtime_published")
        _publish_runtime(staging_root, runtime_root)
        _fsync_directory(runtime_root.parent)
        journal["runtime"]["published"] = True  # type: ignore[index]
        _record(journal_path, journal, "runtime_published", checkpoint)
        marker, identity_file, ca_file, config_file = _runtime_paths(runtime_root)

        stage = "policy_before_restart"
        validate_policy_matrix(
            observer.policy_matrix(identity_file=identity_file, ca_file=ca_file), stage,
        )
        checks[stage] = True
        stage = "restart"
        _intent(journal_path, journal, "gateway_restarted")
        gateway.restart_gateway()
        _record(journal_path, journal, "gateway_restarted", checkpoint)
        validate_preflight(gateway.preflight(), plan.source_revision)
        stage = "policy_after_restart"
        validate_policy_matrix(
            observer.policy_matrix(identity_file=identity_file, ca_file=ca_file), stage,
        )
        checks[stage] = True

        stage = "observer"
        health = validate_observation(
            observer.observe_once(
                config_file=config_file, identity_file=identity_file, ca_file=ca_file,
            ),
            plan,
        )
        report["observer_health"] = health
        binding = report["account_binding"]
        assert isinstance(binding, dict)
        binding["fingerprint_match"] = True
        checks[stage] = True
        stage = "no_leak"
        sensitive = (capability, plan.expected_account_id.encode("ascii"))
        if (gateway.no_leak_scan(sensitive_values=sensitive, secret_ids=secret_ids) is not True
                or observer.no_leak_scan(sensitive_values=sensitive) is not True):
            raise BootstrapFailure(stage)
        checks[stage] = True

        stage = "revocation"
        for index, secret_id in reversed(list(enumerate(secret_ids, start=1))):
            phase = f"grant_{index}_revoked"
            _intent(journal_path, journal, phase)
            gateway.delete_grant(actor_id, secret_id)
            grant = f"{actor_id}:{secret_id}"
            grants.remove(grant)
            journal["grants"] = list(grants)
            _record(journal_path, journal, phase, checkpoint)
        _intent(journal_path, journal, "actor_revoked")
        gateway.delete_actor(actor_id)
        journal["actor_id"] = None
        _record(journal_path, journal, "actor_revoked", checkpoint)
        revoked = observer.revoked_identity(identity_file=identity_file, ca_file=ca_file)
        if revoked != {"status": 407, "injection_count": 0}:
            raise BootstrapFailure(stage)
        checks[stage] = True

        stage = "audit"
        validate_audit(
            gateway.audit_summary(actor_id, _fingerprint(plan.operation_id)), plan,
        )
        checks[stage] = True
    except BootstrapFailure as error:
        report["failed_stage"] = error.stage
    except Exception:
        report["failed_stage"] = stage
    finally:
        if journal_path is not None and journal is not None:
            checks["cleanup"] = recover_bootstrap(
                plan, gateway, runtime_root=runtime_root, checkpoint=checkpoint,
            )
        else:
            checks["cleanup"] = True
        if all(checks.values()):
            report["outcome"] = "passed_ephemeral_observer_proof"
            report["failed_stage"] = None
        elif report["failed_stage"] is None:
            report["failed_stage"] = "cleanup"
    return report
