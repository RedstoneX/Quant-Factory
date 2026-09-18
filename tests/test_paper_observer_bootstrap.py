from copy import deepcopy
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import execution.paper_observer_bootstrap as bootstrap_module
from execution.paper_observer_bootstrap import (
    ALLOWED_REQUESTS,
    BootstrapFailure,
    BootstrapPlan,
    EVIDENCE_SCHEMA,
    JOURNAL_SCHEMA,
    OWNER_ATTESTATION,
    PAPER_HOST,
    PLAN_SCHEMA,
    SECRET_HEADERS,
    _audit_expected,
    _matrix_expected,
    recover_bootstrap,
    run_bootstrap,
    validate_secret_metadata,
)


ACCOUNT = "54c41ab9-eab7-4823-a47d-2a0b63b18590"
REVISION = "a" * 40
ACTOR = "11111111-1111-4111-8111-111111111111"
KEY = "22222222-2222-4222-8222-222222222222"
SECRET = "33333333-3333-4333-8333-333333333333"
RULES = [
    "44444444-4444-4555-8555-444444444441",
    "44444444-4444-4555-8555-444444444442",
    "44444444-4444-4555-8555-444444444443",
]
CAPABILITY = b"fixture-capability-must-never-appear-0123456789"
CA = b"-----BEGIN CERTIFICATE-----\nfixture-public-ca\n-----END CERTIFICATE-----\n"


def plan(**changes):
    values = {
        "operation_id": "observer-proof-20260903",
        "deployment_id": "dedicated-paper-observer-proof",
        "owner_attestation_reference": OWNER_ATTESTATION,
        "expected_account_id": ACCOUNT,
        "source_revision": REVISION,
        "schema": PLAN_SCHEMA,
    }
    values.update(changes)
    return BootstrapPlan(**values)


def secrets_metadata():
    ids = [KEY, SECRET]
    return [
        {
            "id": ids[index], "name": name, "type": "generic",
            "hostPattern": PAPER_HOST, "pathPattern": None,
            "injectionConfig": {"headerName": header, "valueFormat": "{value}"},
        }
        for index, (name, header) in enumerate(SECRET_HEADERS.items())
    ]


def preflight():
    return {
        "source_revision": REVISION,
        "images_pinned": True,
        "services_healthy": True,
        "gateway_only_egress": True,
        "gateway_only_actor": True,
        "actor_network_internal": True,
        "published_host_ports": 0,
        "credentialless_defaults_preserved": True,
    }


def audit():
    return _audit_expected(plan())


class FakeGateway:
    def __init__(self):
        self.runtime = preflight()
        self.secrets = secrets_metadata()
        self.actors = {}
        self.rules = {}
        self.grants = set()
        self.calls = []
        self.restart_count = 0
        self.audit = audit()
        self.scan_ok = True
        self.fail = None
        self.ambiguous_rule = False
        self.ambiguous_actor = False
        self.ambiguous_grant = False
        self.cleanup_failure = False

    def _call(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError("untrusted adapter detail must not escape")

    def preflight(self):
        self._call("preflight")
        return deepcopy(self.runtime)

    def owned_resources(self, operation_id):
        self._call("owned_resources")
        needle = f"qf-{operation_id}"
        actors = [value["id"] for value in self.actors.values() if value["identifier"] == needle]
        rules = [key for key, value in self.rules.items() if value["name"].startswith(needle)]
        grants = [f"{actor}:{secret}" for actor, secret in self.grants if actor in actors]
        return {"actors": actors, "rules": rules, "grants": grants}

    def secret_metadata(self):
        self._call("secret_metadata")
        return deepcopy(self.secrets)

    def create_rule(self, **rule):
        self._call("create_rule")
        rule_id = RULES[len(self.rules)]
        self.rules[rule_id] = deepcopy(rule) | {"id": rule_id}
        if self.ambiguous_rule and len(self.rules) == 1:
            raise RuntimeError("ambiguous create")
        return rule_id

    def set_rule_order(self, rule_ids):
        self._call("set_rule_order")
        assert rule_ids == RULES

    def publish(self):
        self._call("publish")

    def create_actor(self, **actor):
        self._call("create_actor")
        self.actors[ACTOR] = deepcopy(actor) | {"id": ACTOR}
        if self.ambiguous_actor:
            raise RuntimeError("ambiguous create")
        return ACTOR

    def grant_secret(self, actor_id, secret_id):
        self._call("grant_secret")
        self.grants.add((actor_id, secret_id))
        if self.ambiguous_grant and len(self.grants) == 1:
            raise RuntimeError("ambiguous grant")

    def issue_capability(self, actor_id):
        self._call("issue_capability")
        assert actor_id == ACTOR
        return CAPABILITY

    def export_ca(self):
        self._call("export_ca")
        return CA

    def restart_gateway(self):
        self._call("restart_gateway")
        self.restart_count += 1

    def audit_summary(self, actor_id, correlation_fingerprint):
        self._call("audit_summary")
        assert actor_id == ACTOR
        assert correlation_fingerprint == hashlib.sha256(
            plan().operation_id.encode()
        ).hexdigest()
        return deepcopy(self.audit)

    def delete_grant(self, actor_id, secret_id):
        self._call("delete_grant")
        self.grants.discard((actor_id, secret_id))

    def delete_actor(self, actor_id):
        self._call("delete_actor")
        if self.cleanup_failure:
            raise RuntimeError("cleanup failed")
        self.actors.pop(actor_id, None)
        self.grants = {grant for grant in self.grants if grant[0] != actor_id}

    def delete_rule(self, rule_id):
        self._call("delete_rule")
        self.rules.pop(rule_id, None)

    def no_leak_scan(self, *, sensitive_values, secret_ids):
        self._call("no_leak_scan")
        assert sensitive_values == (CAPABILITY, ACCOUNT.encode())
        assert secret_ids == (KEY, SECRET)
        return self.scan_ok


class FakeObserver:
    def __init__(self, gateway):
        self.gateway = gateway
        self.matrix = _matrix_expected()
        self.matrix_calls = 0
        self.scan_ok = True
        self.account_fingerprint = hashlib.sha256(ACCOUNT.encode()).hexdigest()
        self.requests = [list(item) for item in ALLOWED_REQUESTS]
        self.observation = None

    def _files(self, identity_file, ca_file):
        assert identity_file.read_bytes() == CAPABILITY
        assert ca_file.read_bytes() == CA
        assert stat.S_IMODE(identity_file.stat().st_mode) == 0o400
        assert stat.S_IMODE(ca_file.stat().st_mode) == 0o444

    def policy_matrix(self, *, identity_file, ca_file):
        self._files(identity_file, ca_file)
        self.gateway.calls.append("observer_policy_matrix")
        self.matrix_calls += 1
        return deepcopy(self.matrix)

    def observe_once(self, *, config_file, identity_file, ca_file):
        self._files(identity_file, ca_file)
        self.gateway.calls.append("observer_observe")
        assert stat.S_IMODE(config_file.stat().st_mode) == 0o400
        config = json.loads(config_file.read_text())
        assert config == {
            "expected_account_id": ACCOUNT,
            "deployment_id": "dedicated-paper-observer-proof",
            "owner_attestation_reference": OWNER_ATTESTATION,
            "proxy_url": "http://gateway-relay:10255",
            "identity_file": "/run/paper/identity",
            "ca_file": "/run/paper/gateway-ca.pem",
            "refresh_seconds": 60,
        }
        self.observation = {
            "health": {
                "ready": True, "account_verified": True, "gateway_status": "reachable",
                "observed_at": "2026-09-03T21:00:00Z", "position_count": 0,
                "blocked_reason": None,
                "account_authorization_status": "external_attestation_reference_unverified",
                "deployment_ready": False, "order_submission_enabled": False,
            },
            "account_fingerprint": self.account_fingerprint,
            "requests": deepcopy(self.requests),
        }
        return deepcopy(self.observation)

    def revoked_identity(self, *, identity_file, ca_file):
        self._files(identity_file, ca_file)
        self.gateway.calls.append("observer_revoked")
        assert not self.gateway.actors and not self.gateway.grants
        return {"status": 407, "injection_count": 0}

    def no_leak_scan(self, *, sensitive_values):
        assert sensitive_values == (CAPABILITY, ACCOUNT.encode())
        return self.scan_ok


class DurableFakeGateway:
    """File-backed fake used to prove recovery after os._exit."""

    def __init__(self, state_path, *, kill_inside=None):
        self.state_path = Path(state_path)
        self.kill_inside = kill_inside
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text())
        else:
            self.state = {
                "actors": {}, "rules": {}, "grants": [], "rule_order": [],
                "publish_count": 0, "restart_count": 0, "capability_active": False,
            }
            self._save()
        self.calls = []
        self.scan_ok = True

    def _inside(self, *phases):
        if self.kill_inside in phases:
            os._exit(93)

    @property
    def actors(self):
        return self.state["actors"]

    @property
    def rules(self):
        return self.state["rules"]

    @property
    def grants(self):
        return {tuple(item) for item in self.state["grants"]}

    def _save(self):
        temporary = self.state_path.with_suffix(".tmp")
        with temporary.open("w") as target:
            json.dump(self.state, target, sort_keys=True)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, self.state_path)
        descriptor = os.open(self.state_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def preflight(self):
        self.calls.append("preflight")
        return preflight()

    def owned_resources(self, operation_id):
        self.calls.append("owned_resources")
        needle = f"qf-{operation_id}"
        actors = [
            value["id"] for value in self.actors.values()
            if value["identifier"] == needle
        ]
        rules = [
            key for key, value in self.rules.items()
            if value["name"].startswith(needle)
        ]
        grants = [
            f"{actor}:{secret}" for actor, secret in self.grants
            if actor in actors
        ]
        return {"actors": actors, "rules": rules, "grants": grants}

    def secret_metadata(self):
        self.calls.append("secret_metadata")
        return secrets_metadata()

    def create_rule(self, **rule):
        index = len(self.rules) + 1
        rule_id = RULES[index - 1]
        self.state["rules"][rule_id] = deepcopy(rule) | {"id": rule_id}
        self._save()
        self._inside(f"rule_{index}_created")
        return rule_id

    def set_rule_order(self, rule_ids):
        self.state["rule_order"] = list(rule_ids)
        self._save()
        self._inside("rule_order_set")

    def publish(self):
        self.state["publish_count"] += 1
        self._save()
        self._inside(
            "policy_published" if self.rules else "cleanup_publish"
        )

    def create_actor(self, **actor):
        self.state["actors"][ACTOR] = deepcopy(actor) | {"id": ACTOR}
        self._save()
        self._inside("actor_created")
        return ACTOR

    def grant_secret(self, actor_id, secret_id):
        grant = [actor_id, secret_id]
        if grant not in self.state["grants"]:
            self.state["grants"].append(grant)
        self._save()
        self._inside(f"grant_{len(self.state['grants'])}_created")

    def issue_capability(self, actor_id):
        assert actor_id == ACTOR
        self.state["capability_active"] = True
        self._save()
        self._inside("capability_issued")
        return CAPABILITY

    def export_ca(self):
        return CA

    def restart_gateway(self):
        self.state["restart_count"] += 1
        self._save()
        self._inside("gateway_restarted")

    def audit_summary(self, actor_id, correlation_fingerprint):
        assert actor_id == ACTOR
        assert correlation_fingerprint == hashlib.sha256(
            plan().operation_id.encode()
        ).hexdigest()
        return audit()

    def delete_grant(self, actor_id, secret_id):
        count = len(self.state["grants"])
        grant = [actor_id, secret_id]
        if grant in self.state["grants"]:
            self.state["grants"].remove(grant)
        self._save()
        explicit = "grant_2_revoked" if secret_id == SECRET else "grant_1_revoked"
        self._inside(explicit, f"cleanup_grant_{count}")

    def delete_actor(self, actor_id):
        self.state["actors"].pop(actor_id, None)
        self.state["grants"] = [
            grant for grant in self.state["grants"] if grant[0] != actor_id
        ]
        self.state["capability_active"] = False
        self._save()
        self._inside("actor_revoked", "cleanup_actor")

    def delete_rule(self, rule_id):
        count = len(self.state["rules"])
        self.state["rules"].pop(rule_id, None)
        self.state["rule_order"] = [
            value for value in self.state["rule_order"] if value != rule_id
        ]
        self._save()
        self._inside(f"cleanup_rule_{count}")

    def no_leak_scan(self, *, sensitive_values, secret_ids):
        assert sensitive_values == (CAPABILITY, ACCOUNT.encode())
        assert secret_ids == (KEY, SECRET)
        return True


def run(tmp_path, gateway=None, observer=None):
    gateway = gateway or FakeGateway()
    observer = observer or FakeObserver(gateway)
    root = tmp_path / "owned-proof-runtime"
    return run_bootstrap(plan(), gateway, observer, runtime_root=root), gateway, observer, root


def _hard_kill_child(phase, state_path, runtime_root):
    gateway = DurableFakeGateway(state_path)
    observer = FakeObserver(gateway)
    if phase.startswith("cleanup_grant") or phase == "cleanup_actor":
        observer.scan_ok = False

    def checkpoint(current):
        if current == phase:
            os._exit(91)

    run_bootstrap(
        plan(), gateway, observer, runtime_root=Path(runtime_root),
        checkpoint=checkpoint,
    )
    os._exit(92)


def _inside_hard_kill_child(phase, state_path, runtime_root):
    gateway = DurableFakeGateway(state_path, kill_inside=phase)
    observer = FakeObserver(gateway)
    if phase.startswith("cleanup_grant") or phase == "cleanup_actor":
        observer.scan_ok = False
    run_bootstrap(
        plan(), gateway, observer, runtime_root=Path(runtime_root),
    )
    os._exit(92)


def _mkdir_hard_kill_child(state_path, runtime_root):
    original = Path.mkdir

    def mkdir_then_die(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path.name.endswith(".runtime-stage"):
            os._exit(94)
        return result

    Path.mkdir = mkdir_then_die
    gateway = DurableFakeGateway(state_path)
    run_bootstrap(
        plan(), gateway, FakeObserver(gateway),
        runtime_root=Path(runtime_root),
    )
    os._exit(92)


def _filesystem_inside_hard_kill_child(mode, state_path, runtime_root):
    if mode == "write":
        original_write = bootstrap_module._safe_write

        def write_then_die(path, data, permissions):
            result = original_write(path, data, permissions)
            if path.name == "identity":
                os._exit(95)
            return result

        bootstrap_module._safe_write = write_then_die
    elif mode == "rename":
        original_publish = bootstrap_module._publish_runtime

        def rename_then_die(path, target):
            result = original_publish(path, target)
            os._exit(95)

        bootstrap_module._publish_runtime = rename_then_die
    elif mode == "rmtree":
        original_rmtree = bootstrap_module.shutil.rmtree

        def rmtree_then_die(path, *args, **kwargs):
            result = original_rmtree(path, *args, **kwargs)
            if Path(path).name == "owned-proof-runtime":
                os._exit(95)
            return result

        bootstrap_module.shutil.rmtree = rmtree_then_die
    else:
        os._exit(92)
    gateway = DurableFakeGateway(state_path)
    run_bootstrap(
        plan(), gateway, FakeObserver(gateway),
        runtime_root=Path(runtime_root),
    )
    os._exit(92)


def test_transaction_proves_exact_boundary_and_returns_only_sanitized_evidence(tmp_path):
    report, gateway, observer, root = run(tmp_path)
    assert report["outcome"] == "passed_ephemeral_observer_proof"
    assert report["schema"] == EVIDENCE_SCHEMA
    assert report["failed_stage"] is None
    assert all(report["checks"].values())
    assert report["account_binding"] == {
        "decision": 272, "fingerprint_match": True, "external_attestation_verified_by_process": False,
    }
    assert report["persistent_worker_started"] is False
    assert report["order_submission_enabled"] is False
    assert report["observer_health"]["deployment_ready"] is False
    assert observer.matrix_calls == 2 and gateway.restart_count == 1
    assert gateway.calls.index("audit_summary") > gateway.calls.index("observer_revoked")
    assert gateway.calls.index("observer_revoked") > gateway.calls.index("observer_observe")
    assert gateway.audit["request_count"] == 17
    assert [phase["name"] for phase in gateway.audit["phases"]] == [
        "pre_restart", "post_restart", "observation", "revocation",
    ]
    assert [phase["request_count"] for phase in gateway.audit["phases"]] == [
        7, 7, 2, 1,
    ]
    assert [
        row["sequence"]
        for phase in gateway.audit["phases"]
        for row in phase["rows"]
    ] == list(range(1, 18))
    assert not gateway.actors and not gateway.rules and not gateway.grants
    assert gateway.secrets == secrets_metadata()
    assert not root.exists()
    serialized = json.dumps(report, sort_keys=True)
    assert ACCOUNT not in serialized and CAPABILITY.decode() not in serialized
    assert KEY not in serialized and SECRET not in serialized
    assert "APCA-API-SECRET-KEY" not in serialized


def test_rules_are_two_exact_gets_then_catch_all_and_never_name_an_order_path(tmp_path):
    gateway = FakeGateway()
    created = []
    original = gateway.create_rule

    def capture(**rule):
        created.append(deepcopy(rule))
        return original(**rule)

    gateway.create_rule = capture
    report, _, _, _ = run(tmp_path, gateway=gateway)
    assert report["outcome"] == "passed_ephemeral_observer_proof"
    assert [row["action"] for row in created] == ["allow", "allow", "block"]
    assert [row["targets"] for row in created[:2]] == [
        [{"kind": "network", "hostPattern": PAPER_HOST, "pathPattern": "/v2/account", "method": "GET"}],
        [{"kind": "network", "hostPattern": PAPER_HOST, "pathPattern": "/v2/positions", "method": "GET"}],
    ]
    assert created[2]["targets"] == [{"kind": "network", "hostPattern": "*"}]
    assert "/v2/orders" not in json.dumps(created)


@pytest.mark.parametrize("changes", [
    {"schema": "wrong"}, {"operation_id": "unsafe operation"}, {"source_revision": "short"},
    {"owner_attestation_reference": "owner-attestation:decision-271"},
    {"expected_account_id": "not-an-account"}, {"deployment_id": "unsafe deployment"},
])
def test_plan_requires_decision_272_binding_and_safe_identity(changes):
    with pytest.raises(BootstrapFailure):
        plan(**changes)


@pytest.mark.parametrize("change", [
    lambda rows: rows + [deepcopy(rows[0])],
    lambda rows: [rows[0]],
    lambda rows: [rows[0] | {"value": "forbidden"}, rows[1]],
    lambda rows: [rows[0] | {"hostPattern": "api.alpaca.markets"}, rows[1]],
    lambda rows: [rows[0] | {"pathPattern": "/v2/account"}, rows[1]],
    lambda rows: [rows[0] | {"injectionConfig": {"headerName": "wrong", "valueFormat": "{value}"}}, rows[1]],
    lambda rows: [rows[0], rows[1] | {"id": rows[0]["id"]}],
])
def test_metadata_accepts_only_the_two_value_free_operator_import_records(change):
    with pytest.raises(BootstrapFailure):
        validate_secret_metadata(change(secrets_metadata()))


def test_target_preflight_fails_before_any_mutation(tmp_path):
    gateway = FakeGateway()
    gateway.runtime["published_host_ports"] = 1
    report, gateway, _, root = run(tmp_path, gateway=gateway)
    assert report["outcome"] == "failed_closed"
    assert report["failed_stage"] == "target_preflight"
    assert "create_rule" not in gateway.calls and "create_actor" not in gateway.calls
    assert report["checks"]["cleanup"] is True and not root.exists()


def test_preexisting_operation_collision_is_preserved_and_never_adopted(tmp_path):
    gateway = FakeGateway()
    gateway.actors[ACTOR] = {"id": ACTOR, "name": "foreign", "identifier": "qf-observer-proof-20260903"}
    report, gateway, _, _ = run(tmp_path, gateway=gateway)
    assert report["failed_stage"] == "resource_collision"
    assert ACTOR in gateway.actors
    assert "delete_actor" not in gateway.calls and "create_rule" not in gateway.calls


@pytest.mark.parametrize("ambiguous", ["rule", "actor", "grant"])
def test_ambiguous_create_recovers_only_uniquely_owned_resources(tmp_path, ambiguous):
    gateway = FakeGateway()
    setattr(gateway, f"ambiguous_{ambiguous}", True)
    report, gateway, _, root = run(tmp_path, gateway=gateway)
    assert report["outcome"] == "failed_closed"
    assert not gateway.actors and not gateway.rules and not gateway.grants
    assert report["checks"]["cleanup"] is True and not root.exists()


@pytest.mark.parametrize("case,stage", [
    ("before_matrix", "policy_before_restart"),
    ("after_matrix", "policy_after_restart"),
    ("audit", "audit"),
    ("fingerprint", "observer"),
    ("requests", "observer"),
    ("gateway_scan", "no_leak"),
    ("observer_scan", "no_leak"),
])
def test_every_evidence_failure_closes_and_cleans_owned_state(tmp_path, case, stage):
    gateway = FakeGateway()
    observer = FakeObserver(gateway)
    if case == "before_matrix":
        observer.matrix["wrong_path"]["status"] = 200
    elif case == "after_matrix":
        original = observer.policy_matrix
        def second_bad(**kwargs):
            value = original(**kwargs)
            if observer.matrix_calls == 2:
                value["missing_identity"]["status"] = 200
            return value
        observer.policy_matrix = second_bad
    elif case == "audit":
        gateway.audit["request_count"] = 16
    elif case == "fingerprint":
        observer.account_fingerprint = "f" * 64
    elif case == "requests":
        observer.requests.append(["GET", PAPER_HOST, "/v2/orders"])
    elif case == "gateway_scan":
        gateway.scan_ok = False
    else:
        observer.scan_ok = False
    report, gateway, _, root = run(tmp_path, gateway=gateway, observer=observer)
    assert report["outcome"] == "failed_closed" and report["failed_stage"] == stage
    assert not gateway.actors and not gateway.rules and not gateway.grants and not root.exists()
    serialized = json.dumps(report)
    assert ACCOUNT not in serialized and CAPABILITY.decode() not in serialized


def test_cleanup_failure_prevents_a_pass_and_reports_no_adapter_text(tmp_path):
    gateway = FakeGateway()
    gateway.cleanup_failure = True
    report, _, _, root = run(tmp_path, gateway=gateway)
    assert report["outcome"] == "failed_closed"
    assert report["checks"]["cleanup"] is False
    assert "cleanup failed" not in json.dumps(report)
    assert not root.exists()


def test_existing_runtime_directory_is_never_removed(tmp_path):
    gateway = FakeGateway()
    observer = FakeObserver(gateway)
    root = tmp_path / "owned-proof-runtime"
    root.mkdir()
    (root / ".qf-owned-operation").write_text(plan().operation_id)
    sentinel = root / "unrelated"
    sentinel.write_text("preserve")
    report = run_bootstrap(plan(), gateway, observer, runtime_root=root)
    assert report["failed_stage"] == "runtime_staging"
    assert report["checks"]["cleanup"] is True
    assert sentinel.read_text() == "preserve"
    assert not gateway.actors and not gateway.rules and not gateway.grants
    assert "create_rule" not in gateway.calls


def test_journal_is_fsynced_before_first_gateway_mutation_and_contains_no_secret(tmp_path):
    gateway = FakeGateway()
    observer = FakeObserver(gateway)
    root = tmp_path / "owned-proof-runtime"
    seen = []
    original = gateway.create_rule

    def first_rule(**rule):
        if seen:
            return original(**rule)
        journal_path = (
            tmp_path / ".qf-paper-observer-journals"
            / f"{plan().operation_id}.json"
        )
        payload = journal_path.read_text()
        state = json.loads(payload)
        assert stat.S_IMODE(journal_path.stat().st_mode) == 0o600
        assert state["schema"] == JOURNAL_SCHEMA
        assert state["phase"] == "rule_1_created_intent"
        assert not state["rules"]
        assert ACCOUNT not in payload
        assert CAPABILITY.decode() not in payload
        seen.append(True)
        return original(**rule)

    gateway.create_rule = first_rule
    report = run_bootstrap(plan(), gateway, observer, runtime_root=root)
    assert report["outcome"] == "passed_ephemeral_observer_proof"
    assert seen == [True]


def test_recovery_without_exact_journal_preserves_operation_tag_collision(tmp_path):
    gateway = FakeGateway()
    gateway.actors[ACTOR] = {
        "id": ACTOR, "name": "foreign",
        "identifier": f"qf-{plan().operation_id}",
    }
    root = tmp_path / "owned-proof-runtime"
    with pytest.raises(BootstrapFailure) as error:
        recover_bootstrap(plan(), gateway, runtime_root=root)
    assert error.value.stage == "recovery_ownership"
    assert ACTOR in gateway.actors
    assert "delete_actor" not in gateway.calls


def test_exact_journal_does_not_adopt_later_foreign_collision(tmp_path):
    root = tmp_path / "owned-proof-runtime"
    state_path = tmp_path / "durable-state.json"
    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()), "--hard-kill-child",
            "prepared", str(state_path), str(root),
        ],
        cwd=Path(__file__).parents[1],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])},
        check=False,
    )
    assert result.returncode == 91
    gateway = DurableFakeGateway(state_path)
    gateway.state["actors"][ACTOR] = {
        "id": ACTOR, "name": "foreign",
        "identifier": f"qf-{plan().operation_id}",
    }
    gateway._save()
    with pytest.raises(BootstrapFailure) as error:
        recover_bootstrap(plan(), gateway, runtime_root=root)
    assert error.value.stage == "recovery_collision"
    assert ACTOR in gateway.actors


def test_recovery_refuses_replaced_inode_even_with_matching_marker(tmp_path):
    root = tmp_path / "owned-proof-runtime"
    state_path = tmp_path / "durable-state.json"
    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()), "--hard-kill-child",
            "runtime_published", str(state_path), str(root),
        ],
        cwd=Path(__file__).parents[1],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])},
        check=False,
    )
    assert result.returncode == 91
    owned_root = tmp_path / "interrupted-owned-runtime"
    root.rename(owned_root)
    root.mkdir(mode=0o700)
    (root / ".qf-owned-operation").write_text(plan().operation_id)
    sentinel = root / "sentinel"
    sentinel.write_text("preserve")
    recovered_gateway = DurableFakeGateway(state_path)
    assert recover_bootstrap(
        plan(), recovered_gateway, runtime_root=root,
    ) is False
    assert sentinel.read_text() == "preserve"
    assert not recovered_gateway.actors
    assert not recovered_gateway.rules
    assert not recovered_gateway.grants
    assert recovered_gateway.state["capability_active"] is False


def test_subprocess_kill_inside_runtime_stage_mkdir_recovers_without_path_residue(
    tmp_path,
):
    root = tmp_path / "owned-proof-runtime"
    state_path = tmp_path / "durable-state.json"
    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()),
            "--mkdir-hard-kill-child", str(state_path), str(root),
        ],
        cwd=Path(__file__).parents[1],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])},
        check=False,
    )
    assert result.returncode == 94
    assert not root.exists()
    assert len(list(tmp_path.glob(".qf-*.runtime-stage"))) == 1
    gateway = DurableFakeGateway(state_path)
    assert recover_bootstrap(plan(), gateway, runtime_root=root)
    assert not root.exists()
    assert not list(tmp_path.glob(".qf-*.runtime-stage"))
    assert not gateway.rules and not gateway.state["rule_order"]
    assert not gateway.actors and not gateway.grants
    assert gateway.state["capability_active"] is False
    journal = (
        tmp_path / ".qf-paper-observer-journals"
        / f"{plan().operation_id}.json"
    )
    assert not journal.exists()


def test_mkdir_crash_preserves_unexpected_requested_runtime_and_journal(tmp_path):
    root = tmp_path / "owned-proof-runtime"
    state_path = tmp_path / "durable-state.json"
    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()),
            "--mkdir-hard-kill-child", str(state_path), str(root),
        ],
        cwd=Path(__file__).parents[1],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])},
        check=False,
    )
    assert result.returncode == 94
    root.mkdir(mode=0o700)
    (root / ".qf-owned-operation").write_text(plan().operation_id)
    sentinel = root / "sentinel"
    sentinel.write_text("preserve")
    gateway = DurableFakeGateway(state_path)
    assert recover_bootstrap(plan(), gateway, runtime_root=root) is False
    assert sentinel.read_text() == "preserve"
    assert not list(tmp_path.glob(".qf-*.runtime-stage"))
    assert not gateway.rules and not gateway.state["rule_order"]
    assert not gateway.actors and not gateway.grants
    assert gateway.state["capability_active"] is False
    journal = (
        tmp_path / ".qf-paper-observer-journals"
        / f"{plan().operation_id}.json"
    )
    assert journal.exists()


def _assert_empty_collision_preserved(root, monkeypatch, publisher):
    gateway = FakeGateway()
    observer = FakeObserver(gateway)
    foreign_inode = []

    def create_collision_then_publish(staging_path, runtime_root):
        runtime_root.mkdir(mode=0o700)
        foreign_inode.append(runtime_root.lstat().st_ino)
        publisher(staging_path, runtime_root)

    monkeypatch.setattr(
        bootstrap_module, "_publish_runtime", create_collision_then_publish,
    )
    report = run_bootstrap(plan(), gateway, observer, runtime_root=root)
    assert report["outcome"] == "failed_closed"
    assert report["failed_stage"] == "runtime_staging"
    assert report["checks"]["cleanup"] is False
    assert root.is_dir() and not root.is_symlink()
    assert root.lstat().st_ino == foreign_inode[0]
    assert not list(root.iterdir())
    assert not list(root.parent.glob(".qf-*.runtime-stage"))
    assert not gateway.rules and not gateway.actors and not gateway.grants
    journal = (
        root.parent / ".qf-paper-observer-journals"
        / f"{plan().operation_id}.json"
    )
    assert journal.exists()
    assert recover_bootstrap(plan(), gateway, runtime_root=root) is False
    assert root.lstat().st_ino == foreign_inode[0]
    assert journal.exists()


def test_atomic_runtime_publish_preserves_empty_foreign_inode(tmp_path, monkeypatch):
    _assert_empty_collision_preserved(
        tmp_path / "owned-proof-runtime",
        monkeypatch,
        bootstrap_module._publish_runtime,
    )


def test_empty_collision_oracle_kills_flag_zero_and_plain_rename_mutations(
    tmp_path, monkeypatch,
):
    flag_case = tmp_path / "flag-zero"
    flag_case.mkdir(mode=0o700)
    with monkeypatch.context() as mutation:
        mutation.setattr(bootstrap_module, "_RENAME_NOREPLACE", 0)
        with pytest.raises(AssertionError):
            _assert_empty_collision_preserved(
                flag_case / "owned-proof-runtime",
                mutation,
                bootstrap_module._publish_runtime,
            )

    plain_case = tmp_path / "plain-rename"
    plain_case.mkdir(mode=0o700)
    with monkeypatch.context() as mutation:
        with pytest.raises(AssertionError):
            _assert_empty_collision_preserved(
                plain_case / "owned-proof-runtime",
                mutation,
                lambda staging, target: staging.rename(target),
            )


def test_linux_renameat2_unavailable_or_unsupported_has_no_plain_fallback(
    tmp_path, monkeypatch,
):
    class MissingRename:
        pass

    missing_source = tmp_path / "missing-source"
    missing_target = tmp_path / "missing-target"
    missing_source.mkdir()
    missing_target.mkdir()
    with monkeypatch.context() as unavailable:
        unavailable.setattr(
            bootstrap_module.ctypes, "CDLL",
            lambda *args, **kwargs: MissingRename(),
        )
        with pytest.raises(BootstrapFailure):
            bootstrap_module._publish_runtime(missing_source, missing_target)
    assert missing_source.is_dir() and missing_target.is_dir()

    class FailingRename:
        def __init__(self, error_number):
            self.error_number = error_number
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            bootstrap_module.ctypes.set_errno(self.error_number)
            return -1

    class FailingLibrary:
        def __init__(self, error_number):
            self.renameat2 = FailingRename(error_number)

    for error_number in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
        case = tmp_path / str(error_number)
        case.mkdir()
        source = case / "source"
        target = case / "target"
        source.mkdir()
        target.mkdir()
        source_inode = source.lstat().st_ino
        target_inode = target.lstat().st_ino
        with monkeypatch.context() as unsupported:
            unsupported.setattr(
                bootstrap_module.ctypes, "CDLL",
                lambda *args, **kwargs: FailingLibrary(error_number),
            )
            with pytest.raises(OSError) as error:
                bootstrap_module._publish_runtime(source, target)
        assert error.value.errno == error_number
        assert source.lstat().st_ino == source_inode
        assert target.lstat().st_ino == target_inode


@pytest.mark.parametrize("inside_call", ["write", "rename", "rmtree"])
def test_subprocess_hard_kill_inside_runtime_calls_recovers_without_residue(
    tmp_path, inside_call,
):
    case_root = tmp_path / inside_call
    case_root.mkdir(mode=0o700)
    root = case_root / "owned-proof-runtime"
    state_path = case_root / "durable-state.json"
    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()),
            "--filesystem-hard-kill-child", inside_call,
            str(state_path), str(root),
        ],
        cwd=Path(__file__).parents[1],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])},
        check=False,
    )
    assert result.returncode == 95, inside_call
    gateway = DurableFakeGateway(state_path)
    assert recover_bootstrap(plan(), gateway, runtime_root=root)
    assert not root.exists()
    assert not list(case_root.glob(".qf-*.runtime-stage"))
    assert not gateway.rules and not gateway.state["rule_order"]
    assert not gateway.actors and not gateway.grants
    assert gateway.state["capability_active"] is False


@pytest.mark.parametrize("mutation", [
    "prepared",
    "rule_1_created", "rule_2_created", "rule_3_created",
    "rule_order_set", "policy_published",
    "actor_created", "grant_1_created", "grant_2_created",
    "capability_issued",
    "runtime_created", "runtime_marker_written", "runtime_identity_written",
    "runtime_ca_written", "runtime_config_written", "runtime_published",
    "gateway_restarted",
    "grant_2_revoked", "grant_1_revoked", "actor_revoked",
    "cleanup_grant_2", "cleanup_grant_1", "cleanup_actor",
    "cleanup_rule_3", "cleanup_rule_2", "cleanup_rule_1",
    "cleanup_publish", "cleanup_runtime",
])
def test_subprocess_hard_kill_after_every_mutation_recovers_exact_operation(
    tmp_path, mutation,
):
    case_root = tmp_path / mutation
    case_root.mkdir(mode=0o700)
    runtime_root = case_root / "owned-proof-runtime"
    state_path = case_root / "durable-state.json"
    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()), "--hard-kill-child",
            mutation, str(state_path), str(runtime_root),
        ],
        cwd=Path(__file__).parents[1],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])},
        check=False,
    )
    assert result.returncode == 91, mutation
    gateway = DurableFakeGateway(state_path)
    assert recover_bootstrap(plan(), gateway, runtime_root=runtime_root), mutation
    assert not gateway.rules
    assert not gateway.state["rule_order"]
    assert not gateway.actors
    assert not gateway.grants
    assert gateway.state["capability_active"] is False
    assert not runtime_root.exists()
    journal = (
        case_root / ".qf-paper-observer-journals"
        / f"{plan().operation_id}.json"
    )
    assert not journal.exists()


@pytest.mark.parametrize("mutation", [
    "rule_1_created", "rule_2_created", "rule_3_created",
    "rule_order_set", "policy_published",
    "actor_created", "grant_1_created", "grant_2_created",
    "capability_issued", "gateway_restarted",
    "grant_2_revoked", "grant_1_revoked", "actor_revoked",
    "cleanup_grant_2", "cleanup_grant_1", "cleanup_actor",
    "cleanup_rule_3", "cleanup_rule_2", "cleanup_rule_1",
    "cleanup_publish",
])
def test_subprocess_hard_kill_inside_each_adapter_mutation_recovers(
    tmp_path, mutation,
):
    case_root = tmp_path / mutation
    case_root.mkdir(mode=0o700)
    root = case_root / "owned-proof-runtime"
    state_path = case_root / "durable-state.json"
    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()),
            "--inside-hard-kill-child", mutation, str(state_path), str(root),
        ],
        cwd=Path(__file__).parents[1],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])},
        check=False,
    )
    assert result.returncode == 93, mutation
    gateway = DurableFakeGateway(state_path)
    assert recover_bootstrap(plan(), gateway, runtime_root=root), mutation
    assert not root.exists()
    assert not list(case_root.glob(".qf-*.runtime-stage"))
    assert not gateway.rules and not gateway.state["rule_order"]
    assert not gateway.actors and not gateway.grants
    assert gateway.state["capability_active"] is False


@pytest.mark.parametrize("mutation", [
    lambda value: value | {"request_count": 16},
    lambda value: value | {"correlation_fingerprint": "f" * 64},
    lambda value: value | {"phases": list(reversed(value["phases"]))},
    lambda value: value | {
        "phases": [
            value["phases"][0] | {
                "rows": [
                    value["phases"][0]["rows"][0] | {"sequence": 2},
                    *value["phases"][0]["rows"][1:],
                ],
            },
            *value["phases"][1:],
        ],
    },
    lambda value: value | {
        "phases": [
            *value["phases"][:2],
            value["phases"][2] | {"request_count": 1},
            value["phases"][3],
        ],
    },
])
def test_audit_requires_complete_correlated_phase_count_and_order(tmp_path, mutation):
    gateway = FakeGateway()
    gateway.audit = mutation(deepcopy(gateway.audit))
    report, _, _, _ = run(tmp_path, gateway=gateway)
    assert report["outcome"] == "failed_closed"
    assert report["failed_stage"] == "audit"


def test_module_has_no_live_transport_or_process_capability():
    source = (Path(__file__).parents[1] / "execution" / "paper_observer_bootstrap.py").read_text()
    for forbidden in ("import requests", "import http", "import socket", "import subprocess", "docker", "curl"):
        assert forbidden not in source
    assert "/v2/orders" not in source


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--hard-kill-child":
        _hard_kill_child(sys.argv[2], sys.argv[3], sys.argv[4])
    if len(sys.argv) == 5 and sys.argv[1] == "--inside-hard-kill-child":
        _inside_hard_kill_child(sys.argv[2], sys.argv[3], sys.argv[4])
    if len(sys.argv) == 4 and sys.argv[1] == "--mkdir-hard-kill-child":
        _mkdir_hard_kill_child(sys.argv[2], sys.argv[3])
    if len(sys.argv) == 5 and sys.argv[1] == "--filesystem-hard-kill-child":
        _filesystem_inside_hard_kill_child(
            sys.argv[2], sys.argv[3], sys.argv[4],
        )
