"""Run only a fresh, disposable credential-proof canary stack.

Requires root on the approved target. Prints a redacted report, never child output.
No existing OneCLI state, credentials, or management endpoints are consulted.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

BASE = Path(os.environ.get(
    "QF_CREDENTIAL_PROOF_ROOT",
    "/srv/quant-factory/state/credential-proof",
))
SOURCE = Path(__file__).resolve().parent
ONECLI = "sha256:d0177458b1f9ecece4abbe9abb6c5f925475357c1734f50a675d83a2ef9c8687"
POSTGRES = "sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15"


class CommandFailure(RuntimeError):
    def __init__(self, code):
        super().__init__("bounded command failed")
        self.code = code


def command(args, timeout=120):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    if result.returncode:
        raise CommandFailure(result.returncode)
    return result.stdout


def passes(report):
    """Full agent acceptance is deliberately a separate, never-asserted claim."""
    try:
        for phase in ("initial", "after_restart"):
            actor = report[phase]
            positive = actor["allowed"]
            if not (positive["status"] == 200 and positive["injected"] and positive["proxy_auth_absent"]):
                return False
            for name in ("wrong_path", "wrong_host", "wrong_identity", "missing_identity",
                         "admin_proxy", "admin_loopback_proxy", "relay_admin_proxy", "missing_identity_admin"):
                if actor[name].get("denied") is not True:
                    return False
            direct = actor["direct_blocked"]
            if set(direct) != {"admin_dns", "admin_ip", "database_ip", "fixture_ip", "internet_tcp", "relay_admin"}:
                return False
            if not all(value is True for value in direct.values()):
                return False
            if any(item.get("response_leak", False) for item in actor.values()):
                return False
        return (report["after_revoke"]["allowed"].get("denied") is True
                and not any(item.get("response_leak", False) for item in report["after_revoke"].values())
                and report["audit"]["allow_seen"] and report["audit"]["deny_seen"]
                and report["audit"]["identity_time_present"]
                and report["no_leak"]["logs"] and report["no_leak"]["process_arguments"])
    except (KeyError, TypeError):
        return False


def safe_scan(data, canary, token):
    values = (canary, token, base64.b64encode(b"qf:" + token))
    return not any(value and value in data for value in values)


def run():
    if os.geteuid() != 0 or SOURCE != BASE / "harness" or BASE.is_symlink():
        raise RuntimeError("approved target and root required")
    available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:")))
    if available < 3 * 1024 * 1024:
        raise RuntimeError("insufficient available memory")
    os.umask(0o077)
    project = "qf-credential-proof-" + secrets.token_hex(5)
    runtime = BASE / project
    runtime.mkdir(mode=0o700)
    for folder in ("actor", "controller", "fixture"):
        (runtime / folder).mkdir(mode=0o755)
        (runtime / folder).chmod(0o755)
    canary = ("qf_canary_" + secrets.token_hex(32)).encode()
    (runtime / "fixture/canary").write_bytes(canary)
    (runtime / "fixture/canary").chmod(0o444)
    password = secrets.token_hex(32)
    (runtime / "db-password").write_text(password)
    (runtime / "db-password").chmod(0o444)
    (runtime / "onecli.env").write_text("DATABASE_URL=postgresql://proof:" + password + "@db:5432/proof\n")
    environment = runtime / "compose.env"
    environment.write_text("PROOF_PROJECT=" + project + "\nPROOF_RUNTIME=" + str(runtime) + "\n")
    compose = ["docker", "compose", "--env-file", str(environment), "-f", str(SOURCE / "compose.yaml")]

    def dc(*args, timeout=120):
        return command(compose + list(args), timeout)

    def role(service, name):
        return json.loads(dc("run", "--rm", "--no-deps", "-T", service,
                             "python", "/harness/probe.py", name, timeout=80))

    def ready():
        for _ in range(40):
            try:
                if role("controller", "ready").get("ready") is True:
                    return
            except Exception:
                pass
            time.sleep(2)
        raise RuntimeError("fresh gateway readiness failed")

    report = {"project": project, "started_at": datetime.now(timezone.utc).isoformat(),
              "http_actor_isolation_proven": False, "full_agent_isolation_proven": False,
              "real_credentials_used": False, "images": {"onecli": ONECLI, "postgres": POSTGRES},
              "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in SOURCE.iterdir() if p.is_file()}}
    stage = "compose_validation"
    try:
        config = json.loads(dc("config", "--format", "json"))
        for service in config["services"].values():
            if service.get("ports") or service.get("privileged"):
                raise RuntimeError("published port or privileged service forbidden")
        if not all(network.get("internal") is True for network in config["networks"].values()):
            raise RuntimeError("all proof networks must be internal")
        # Image/entrypoint inspection does not read any existing container state.
        command(["docker", "image", "inspect", ONECLI, POSTGRES])
        stage = "startup"
        dc("up", "-d", "db", "onecli", "fixture", "gateway-relay", timeout=180)
        ready()
        addresses = {}
        ids = {}
        for name in ("onecli", "db", "fixture", "gateway-relay"):
            ids[name] = dc("ps", "-q", name).decode().strip()
            inspected = json.loads(command(["docker", "inspect", ids[name]]))[0]
            addresses[name] = next(iter(inspected["NetworkSettings"]["Networks"].values()))["IPAddress"]
        public = runtime / "actor/private-addresses.json"
        public.write_text(json.dumps(addresses))
        public.chmod(0o444)
        stage = "fresh_canary_grant"
        report["preparation"] = role("controller", "prepare")
        stage = "initial_actor"
        report["initial"] = role("actor", "actor")
        stage = "restart"
        dc("restart", "onecli")
        ready()
        report["after_restart"] = role("actor", "actor")
        stage = "revoke"
        report["revocation"] = role("controller", "revoke")
        report["after_revoke"] = role("actor", "actor")
        stage = "audit_and_leaks"
        # Read only non-secret request evidence in our fresh database. No vault rows.
        query = "SELECT COALESCE(json_agg(t),'[]'::json) FROM (SELECT agent_id,method,host,path,status,injection_count,created_at FROM request_logs ORDER BY created_at LIMIT 200) t;"
        audit = json.loads(dc("exec", "-T", "db", "psql", "-U", "proof", "-d", "proof", "-At", "-c", query))
        report["audit"] = {"record_count": len(audit), "allow_seen": any(r["status"] == 200 and r["injection_count"] == 1 for r in audit),
                           "deny_seen": any(r["status"] in (401, 403, 407) for r in audit),
                           "identity_time_present": bool(audit) and all(r["agent_id"] and r["created_at"] for r in audit),
                           "records": audit}
        token = (runtime / "actor/capability").read_bytes()
        stage = "bounded_log_scan"
        logs = dc("logs", "--no-color", "--tail", "2000", timeout=30)
        report["no_leak"] = {"logs": safe_scan(logs, canary, token)}
        arguments = b""
        for name, cid in ids.items():
            stage = "process_arguments_" + name
            arguments += command(["docker", "exec", cid, "sh", "-c",
                                  'for f in /proc/[0-9]*/cmdline; do cat "$f" 2>/dev/null || true; done'])
        report["no_leak"] = {"logs": safe_scan(logs, canary, token),
                             "process_arguments": safe_scan(arguments, canary, token),
                             "scan_scope": "bounded service logs, running service arguments, actor responses"}
        report["http_actor_isolation_proven"] = passes(report)
        report["result"] = "passed_http_actor_scope" if passes(report) else "security_acceptance_failed"
    except Exception as error:
        report["result"] = "proof_incomplete"
        report["failed_stage"] = stage
        report["error"] = "bounded proof operation failed; no raw diagnostic emitted"
        if isinstance(error, CommandFailure):
            report["command_exit_code"] = error.code
    finally:
        # Stop only this unique fresh project; retain private canary state for review.
        try:
            dc("down", timeout=90)
            report["containers_stopped"] = True
        except Exception:
            report["containers_stopped"] = False
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (runtime / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["http_actor_isolation_proven"] else 1


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:
        print('{"result":"proof_not_started","error":"approved preconditions failed"}')
        sys.exit(1)
