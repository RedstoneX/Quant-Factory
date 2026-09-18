#!/usr/bin/env python3
"""Validate secret-bearing Compose JSON without ever serializing it to output."""
import json
import sys

EXPECTED_IMAGES = {
    "postgres": "postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2",
    "migrations": "ghcr.io/onecli/onecli-migrations@sha256:8293f29e22024a789c987593a512b18140056bf6a522324616c1b48699ac2fa8",
    "api": "ghcr.io/onecli/onecli-api@sha256:48f9b66cda3a136428cf530d4cb934d1ce6bf3a186dd592f02ea3b40a48e2e44",
    "web": "ghcr.io/onecli/onecli-web@sha256:123907a95915db1f645be11bf54709f2aa81c44706f263fdd7cef9141ed73118",
    "gateway": "ghcr.io/onecli/onecli-gateway@sha256:e2bb74a919a34ec8e268168930a0ad38b7adbdbe4a2766afc08eeca1f083354f",
}
EXPECTED_NETWORKS = {
    "postgres": {"control"}, "migrations": {"control"}, "api": {"control"},
    "web": {"control"}, "gateway": {"control", "actor"},
}
EXPECTED_VOLUMES = {
    "postgres": {("postgres-data", "/var/lib/postgresql", False)},
    "api": {("app-data", "/app/data", True)},
    "gateway": {("app-data", "/app/data", False)},
    "migrations": set(), "web": set(),
}

def fail(reason: str) -> None:
    raise SystemExit(f"preflight=failed reason={reason}")

def mib(value) -> int:
    raw = str(value).lower()
    if raw.endswith("m"):
        return int(raw[:-1])
    if raw.isdigit():
        return int(raw) // (1024 * 1024)
    fail("rendered_memory_format")

def main(project: str, path: str) -> None:
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            fail("rendered_json")
        if data.get("name") != project:
            fail("rendered_project_name")
        services = data.get("services")
        if not isinstance(services, dict) or set(services) != set(EXPECTED_IMAGES):
            fail("rendered_service_set")
        memory = 0
        for name, expected_image in EXPECTED_IMAGES.items():
            service = services[name]
            if not isinstance(service, dict):
                fail("rendered_service_set")
            if service.get("image") != expected_image:
                fail("rendered_image_pin")
            if service.get("ports"):
                fail("rendered_host_ports")
            if "docker.sock" in json.dumps(service.get("volumes", [])):
                fail("rendered_docker_socket")
            rendered_networks = set((service.get("networks") or {}).keys())
            if rendered_networks != EXPECTED_NETWORKS[name]:
                fail("rendered_network_membership")
            rendered_volumes = set()
            for volume in service.get("volumes", []):
                if not isinstance(volume, dict) or volume.get("type") != "volume" or volume.get("external"):
                    fail("rendered_volume_type")
                rendered_volumes.add((volume.get("source"), volume.get("target"), bool(volume.get("read_only"))))
            if rendered_volumes != EXPECTED_VOLUMES[name]:
                fail("rendered_volume_boundary")
            if "mem_limit" not in service:
                fail("rendered_memory_missing")
            memory += mib(service["mem_limit"])
        networks = data.get("networks") or {}
        if not isinstance(networks, dict) or set(networks) != {"control", "actor"} or not all(isinstance(networks[n], dict) and networks[n].get("internal") is True for n in networks):
            fail("rendered_network_boundary")
        volumes = data.get("volumes") or {}
        if not isinstance(volumes, dict) or set(volumes) != {"postgres-data", "app-data"}:
            fail("rendered_volume_set")
        for volume_name in volumes:
            volume = volumes[volume_name]
            if not isinstance(volume, dict) or volume.get("external") or volume.get("name") != f"{project}_{volume_name}":
                fail("rendered_volume_identity")
            if volume.get("driver") or volume.get("driver_opts"):
                fail("rendered_volume_driver")
        for network_name, network in networks.items():
            if network.get("external") or network.get("name") != f"{project}_{network_name}":
                fail("rendered_network_identity")
        if memory != 2048 or memory > 3072:
            fail("rendered_memory_limit")
    except (OSError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        fail("rendered_json")
    print(f"rendered=passed project={project} services=5 memory_mib={memory} ports=0")


if len(sys.argv) != 3:
    fail("rendered_arguments")
main(sys.argv[1], sys.argv[2])
