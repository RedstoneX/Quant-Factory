#!/usr/bin/env python3
"""Validate production Compose JSON without printing rendered secrets."""
import base64,binascii,json,re,sys
IMAGES={"postgres":"postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2","migrations":"ghcr.io/onecli/onecli-migrations@sha256:8293f29e22024a789c987593a512b18140056bf6a522324616c1b48699ac2fa8","api":"ghcr.io/onecli/onecli-api@sha256:48f9b66cda3a136428cf530d4cb934d1ce6bf3a186dd592f02ea3b40a48e2e44","web":"ghcr.io/onecli/onecli-web@sha256:123907a95915db1f645be11bf54709f2aa81c44706f263fdd7cef9141ed73118","gateway":"ghcr.io/onecli/onecli-gateway@sha256:e2bb74a919a34ec8e268168930a0ad38b7adbdbe4a2766afc08eeca1f083354f"}
NETS={"postgres":{"control"},"migrations":{"control"},"api":{"control"},"web":{"control"},"gateway":{"control","actor","egress"}}
GATEWAY_NETS={
 "control":{"interface_name":"eth0","priority":1000},
 "actor":{"aliases":["gateway-relay"],"interface_name":"eth1","priority":500},
 "egress":{"interface_name":"eth2","priority":100,"gw_priority":1},
}
VOLS={"postgres":{("postgres-data","/var/lib/postgresql",False)},"api":{("app-data","/app/data",True)},"gateway":{("app-data","/app/data",False)},"migrations":set(),"web":set()}
RESOURCES={"postgres":(512,0.5,128),"migrations":(256,0.5,96),"api":(512,0.75,192),"web":(384,0.5,128),"gateway":(384,0.5,128)}
DEPENDS={"postgres":{},"migrations":{"postgres":"service_healthy"},"api":{"postgres":"service_healthy","migrations":"service_completed_successfully"},"web":{"api":"service_healthy"},"gateway":{"api":"service_healthy"}}
FORBIDDEN=("ports","cap_add","dns","dns_search","dns_opt","extra_hosts","devices","device_cgroup_rules","device_requests","network_mode","pid","ipc","userns_mode","uts","privileged","build","volumes_from","links","external_links","group_add","sysctls","ulimits","tmpfs","configs","secrets","profiles","user","working_dir","runtime","isolation","cgroup","cgroup_parent","cgroupns_mode")
POSTGRES_HEALTH={"test":["CMD-SHELL","pg_isready -U onecli -d onecli"],"interval":"5s","timeout":"3s","start_period":"15s","retries":10}
def fail(r): raise SystemExit(f"preflight=failed reason={r}")
def memory_mib(value):
 raw=str(value).lower()
 if raw.endswith("m"): return int(raw[:-1])
 if raw.isdigit(): return int(raw)//(1024*1024)
 fail("rendered_resources")
def validate_secrets(pgpass,better,encryption,internal):
 if any(not isinstance(x,str) for x in (pgpass,better,encryption,internal)): fail("rendered_secret_format")
 if any(re.fullmatch(r"[0-9a-f]{64}",x) is None for x in (pgpass,better,internal)): fail("rendered_secret_format")
 try:
  decoded=base64.b64decode(encryption,validate=True)
 except (binascii.Error,ValueError): fail("rendered_secret_format")
 if len(decoded)!=32 or base64.b64encode(decoded).decode()!=encryption: fail("rendered_secret_format")
 if len({pgpass,better,encryption,internal})!=4: fail("rendered_secret_reuse")
def main():
 if len(sys.argv)!=6: fail("rendered_arguments")
 project,pgvol,appvol,actor,path=sys.argv[1:]
 try: data=json.load(open(path,encoding="utf-8"))
 except Exception: fail("rendered_json")
 services=data.get("services",{})
 if data.get("name")!=project or set(services)!=set(IMAGES): fail("rendered_identity")
 pgpass=(services.get("postgres",{}).get("environment") or {}).get("POSTGRES_PASSWORD")
 if not pgpass: fail("rendered_environment")
 dburl=f"postgresql://onecli:{pgpass}@postgres:5432/onecli"
 api_env={"DATABASE_URL":dburl,"BETTER_AUTH_SECRET":None,"SECRET_ENCRYPTION_KEY":None,"GATEWAY_INTERNAL_SECRET":None,"GATEWAY_INTERNAL_URL":"http://gateway:10255","ONECLI_AGENT_PROXY_ADDRESS":"gateway-relay:10255","ONECLI_APP_PORT":"10254","ONECLI_API_PORT":"10256","ONECLI_GATEWAY_PORT":"10255"}
 actual_api=services.get("api",{}).get("environment") or {}
 for key in ("BETTER_AUTH_SECRET","SECRET_ENCRYPTION_KEY","GATEWAY_INTERNAL_SECRET"): api_env[key]=actual_api.get(key)
 validate_secrets(pgpass,api_env["BETTER_AUTH_SECRET"],api_env["SECRET_ENCRYPTION_KEY"],api_env["GATEWAY_INTERNAL_SECRET"])
 expected_env={
  "postgres":{"POSTGRES_USER":"onecli","POSTGRES_PASSWORD":pgpass,"POSTGRES_DB":"onecli"},
  "migrations":{"DATABASE_URL":dburl},
  "api":api_env,
  "web":{"DATABASE_URL":dburl,"BETTER_AUTH_SECRET":api_env["BETTER_AUTH_SECRET"],"SECRET_ENCRYPTION_KEY":api_env["SECRET_ENCRYPTION_KEY"]},
  "gateway":{"DATABASE_URL":dburl,"BETTER_AUTH_SECRET":api_env["BETTER_AUTH_SECRET"],"SECRET_ENCRYPTION_KEY":api_env["SECRET_ENCRYPTION_KEY"],"GATEWAY_INTERNAL_SECRET":api_env["GATEWAY_INTERNAL_SECRET"],"INTERNAL_API_URL":"http://api:10256"},
 }
 for name,image in IMAGES.items():
  s=services[name]
  if s.get("image")!=image: fail("rendered_image_pin")
  if (s.get("environment") or {})!=expected_env[name] or any(value in (None,"") for value in expected_env[name].values()): fail("rendered_environment")
  if any(key in s for key in FORBIDDEN): fail("rendered_exposure")
  # Compose v5 normalizes absent command/entrypoint keys to JSON null.
  if s.get("command") is not None or s.get("entrypoint") is not None: fail("rendered_exposure")
  expected_drop=None if name=="postgres" else ["ALL"]
  if s.get("cap_drop")!=expected_drop or s.get("security_opt")!=["no-new-privileges:true"]: fail("rendered_security")
  if set((s.get("networks") or {}).keys())!=NETS[name]: fail("rendered_network_membership")
  entries=s.get("volumes",[])
  got={(v.get("source"),v.get("target"),bool(v.get("read_only"))) for v in entries if isinstance(v,dict)}
  if got!=VOLS[name] or len(entries)!=len(VOLS[name]) or any(v.get("type")!="volume" for v in entries): fail("rendered_volume_boundary")
  if (memory_mib(s.get("mem_limit")),float(s.get("cpus",0)),s.get("pids_limit"))!=RESOURCES[name]: fail("rendered_resources")
  if {k:v.get("condition") for k,v in (s.get("depends_on") or {}).items()}!=DEPENDS[name]: fail("rendered_dependencies")
  if (s.get("logging") or {})!={"driver":"json-file","options":{"max-file":"3","max-size":"5m"}}: fail("rendered_logging")
  if s.get("restart")!=("no" if name=="migrations" else "unless-stopped"): fail("rendered_restart")
  expected_health=POSTGRES_HEALTH if name=="postgres" else None
  if s.get("healthcheck")!=expected_health: fail("rendered_healthcheck")
 nets=data.get("networks",{});vols=data.get("volumes",{})
 if set(nets)!={"control","actor","egress"}: fail("rendered_network_boundary")
 if not nets["control"].get("internal") or nets["control"].get("external") or nets["control"].get("name")!=f"{project}_control": fail("rendered_network_boundary")
 if nets["actor"].get("name")!=actor or not nets["actor"].get("external"): fail("rendered_network_boundary")
 if nets["egress"].get("internal") or nets["egress"].get("external") or nets["egress"].get("name")!=f"{project}_egress": fail("rendered_network_boundary")
 for network in nets.values():
  if network.get("driver") or network.get("driver_opts") or network.get("ipam") or network.get("attachable") or network.get("enable_ipv6"): fail("rendered_network_options")
 if set(vols)!={"postgres-data","app-data"} or vols["postgres-data"].get("name")!=pgvol or vols["app-data"].get("name")!=appvol or not all(vols[x].get("external") for x in vols): fail("rendered_volume_identity")
 if any(vols[x].get("driver") or vols[x].get("driver_opts") for x in vols): fail("rendered_volume_driver")
 if (services["gateway"].get("networks",{}).get("actor",{}).get("aliases") or [])!=["gateway-relay"]: fail("rendered_gateway_alias")
 if services["gateway"].get("networks")!=GATEWAY_NETS: fail("rendered_gateway_network_order")
 print(f"rendered=passed project={project} services=5 ports=0 actor_network={actor} egress=gateway-only")
if __name__=="__main__": main()
