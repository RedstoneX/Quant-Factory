"""Focused mutation tests for the secret-safe rendered Compose validator."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
VALIDATOR = ROOT / "deployment/onecli-v2/validate_rendered_config.py"
PROJECT = "qf-test"
IMAGES = {
    "postgres": "postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2",
    "migrations": "ghcr.io/onecli/onecli-migrations@sha256:8293f29e22024a789c987593a512b18140056bf6a522324616c1b48699ac2fa8",
    "api": "ghcr.io/onecli/onecli-api@sha256:48f9b66cda3a136428cf530d4cb934d1ce6bf3a186dd592f02ea3b40a48e2e44",
    "web": "ghcr.io/onecli/onecli-web@sha256:123907a95915db1f645be11bf54709f2aa81c44706f263fdd7cef9141ed73118",
    "gateway": "ghcr.io/onecli/onecli-gateway@sha256:e2bb74a919a34ec8e268168930a0ad38b7adbdbe4a2766afc08eeca1f083354f",
}

def rendered():
    services = {name: {"image": image, "mem_limit": limit, "networks": networks, "volumes": volumes}
                for name, image, limit, networks, volumes in [
        ("postgres", IMAGES["postgres"], "512m", {"control": {}}, [{"type": "volume", "source": "postgres-data", "target": "/var/lib/postgresql", "read_only": False}]),
        ("migrations", IMAGES["migrations"], "256m", {"control": {}}, []),
        ("api", IMAGES["api"], "512m", {"control": {}}, [{"type": "volume", "source": "app-data", "target": "/app/data", "read_only": True}]),
        ("web", IMAGES["web"], "384m", {"control": {}}, []),
        ("gateway", IMAGES["gateway"], "384m", {"control": {}, "actor": {}}, [{"type": "volume", "source": "app-data", "target": "/app/data", "read_only": False}]),
    ]}
    return {"name": PROJECT, "services": services,
            "networks": {n: {"internal": True, "name": f"{PROJECT}_{n}"} for n in ("control", "actor")},
            "volumes": {n: {"name": f"{PROJECT}_{n}"} for n in ("postgres-data", "app-data")}}

class RenderedConfigTests(unittest.TestCase):
    def validate(self, document):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            json.dump(document, handle)
            handle.flush()
            return subprocess.run([sys.executable, str(VALIDATOR), PROJECT, handle.name], text=True, capture_output=True)

    def test_accepts_exact_rendered_boundary(self):
        self.assertEqual(self.validate(rendered()).returncode, 0)

    def test_rejects_alias_port_and_memory_mutations(self):
        for mutate in (
            lambda d: d["volumes"]["app-data"].update(name="onecli_app-data"),
            lambda d: d["volumes"]["app-data"].update(driver="local", driver_opts={"type": "none"}),
            lambda d: d["networks"]["actor"].update(name="onecli_onecli"),
            lambda d: d["services"]["web"].update(ports=["127.0.0.1:1:1"]),
            lambda d: d["services"]["web"].pop("mem_limit"),
        ):
            candidate = copy.deepcopy(rendered())
            mutate(candidate)
            self.assertNotEqual(self.validate(candidate).returncode, 0)

    def test_malformed_input_is_rejected_without_echoing_marker(self):
        marker = "PRIVATE_RENDERED_VALUE_MUST_NOT_ESCAPE"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            json.dump([marker], handle)
            handle.flush()
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), PROJECT, handle.name],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn(marker, result.stderr)
