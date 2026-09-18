#!/usr/bin/env python3
"""Validate Docker inspection data for private control/actor and gateway egress."""
from __future__ import annotations
import base64,binascii,hashlib,hmac,ipaddress,json,os,re,stat,sys
IMAGES={"postgres":"postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2","migrations":"ghcr.io/onecli/onecli-migrations@sha256:8293f29e22024a789c987593a512b18140056bf6a522324616c1b48699ac2fa8","api":"ghcr.io/onecli/onecli-api@sha256:48f9b66cda3a136428cf530d4cb934d1ce6bf3a186dd592f02ea3b40a48e2e44","web":"ghcr.io/onecli/onecli-web@sha256:123907a95915db1f645be11bf54709f2aa81c44706f263fdd7cef9141ed73118","gateway":"ghcr.io/onecli/onecli-gateway@sha256:e2bb74a919a34ec8e268168930a0ad38b7adbdbe4a2766afc08eeca1f083354f"}
ENTRYPOINT={"postgres":["docker-entrypoint.sh"],"migrations":["docker-entrypoint.sh"],"api":["/sbin/tini","--"],"web":["/sbin/tini","--"],"gateway":["onecli-gateway"]}
COMMAND={"postgres":["postgres"],"migrations":["./migrate.sh"],"api":["node","apps/api-server/dist/index.mjs"],"web":["node","apps/web/server.js"],"gateway":["--port","10255","--data-dir","/app/data"]}
HEALTH={
 "postgres":{"Test":["CMD-SHELL","pg_isready -U onecli -d onecli"],"Interval":5_000_000_000,"Timeout":3_000_000_000,"StartPeriod":15_000_000_000,"Retries":10},
 "migrations":None,
 "api":{"Test":["CMD-SHELL","wget -qO- http://127.0.0.1:10256/v1/health || exit 1"],"Interval":10_000_000_000,"Timeout":5_000_000_000,"StartPeriod":60_000_000_000,"Retries":3},
 "web":{"Test":["CMD-SHELL","wget -qO- http://127.0.0.1:10254/healthz || exit 1"],"Interval":10_000_000_000,"Timeout":5_000_000_000,"StartPeriod":60_000_000_000,"Retries":3},
 "gateway":{"Test":["CMD","onecli-gateway","--healthcheck"],"Interval":10_000_000_000,"Timeout":5_000_000_000,"StartPeriod":30_000_000_000,"Retries":3},
}
RESOURCES={"postgres":(512*1024*1024,500_000_000,128),"migrations":(256*1024*1024,500_000_000,96),"api":(512*1024*1024,750_000_000,192),"web":(384*1024*1024,500_000_000,128),"gateway":(384*1024*1024,500_000_000,128)}
USER={"postgres":"","migrations":"node","api":"node","web":"node","gateway":"onecli"}
WORKDIR={"postgres":"/","migrations":"/app","api":"/app","web":"/app","gateway":"/app"}
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
DEFAULT_ENV={
 "postgres":{"PATH":PATH,"GOSU_VERSION":"1.19","LANG":"en_US.utf8","PG_MAJOR":"18","PG_VERSION":"18.6","PG_SHA256":"555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f","DOCKER_PG_LLVM_DEPS":"llvm21-dev \t\tclang21","PGDATA":"/var/lib/postgresql/18/docker"},
 "migrations":{"PATH":PATH,"NODE_VERSION":"22.23.2","YARN_VERSION":"1.22.22","APP_VERSION":"2.4.0"},
 "api":{"PATH":PATH,"NODE_VERSION":"22.23.2","YARN_VERSION":"1.22.22","NODE_ENV":"production","NO_COLOR":"1","FORCE_COLOR":"0","PORT":"10256","APP_VERSION":"2.4.0","NODE_OPTIONS":"--enable-source-maps"},
 "web":{"PATH":PATH,"NODE_VERSION":"22.23.2","YARN_VERSION":"1.22.22","NODE_ENV":"production","NEXT_TELEMETRY_DISABLED":"1","NO_COLOR":"1","FORCE_COLOR":"0","PORT":"10254","HOSTNAME":"0.0.0.0","APP_VERSION":"2.4.0"},
 "gateway":{"PATH":PATH,"APP_VERSION":"2.4.0"},
}
def fail(reason): raise SystemExit(f"runtime=failed reason={reason}")
def load(path):
 try:
  data=json.load(open(path,encoding="utf-8"))
  if not isinstance(data,list): fail("inspect_json")
  return data
 except (OSError,json.JSONDecodeError): fail("inspect_json")
def ident(c):
 labels=(c.get("Config") or {}).get("Labels") or {}
 return labels.get("com.docker.compose.project"),labels.get("com.docker.compose.service")
def network(path,name,internal):
 docs=load(path)
 if len(docs)!=1: fail("network_inspect")
 n=docs[0]
 if n.get("Name")!=name or n.get("Internal") is not internal or n.get("Driver")!="bridge" or n.get("Scope")!="local" or n.get("Attachable") is not False or n.get("Ingress") is not False or n.get("EnableIPv6") is not False or n.get("ConfigOnly") not in (None,False) or (n.get("Options") or {})!={}: fail("network_options")
 ipam=n.get("IPAM") or {};configs=ipam.get("Config") or []
 if ipam.get("Driver")!="default" or (ipam.get("Options") or {})!={} or len(configs)!=1 or set(configs[0])-{"Subnet","Gateway","IPRange"}: fail("network_ipam")
 try:
  subnet=ipaddress.ip_network(configs[0]["Subnet"]);gateway=ipaddress.ip_address(configs[0]["Gateway"])
  if not subnet.is_private or gateway not in subnet: fail("network_ipam")
 except (KeyError,ValueError): fail("network_ipam")
 return n
def members(n,containers):
 by_id={c.get("Id",""):c for c in containers if isinstance(c,dict) and c.get("Id")};result=[]
 for cid in (n.get("Containers") or {}):
  match=[c for key,c in by_id.items() if key.startswith(cid) or cid.startswith(key)]
  if len(match)!=1: fail("network_member_inspect")
  result.append(match[0])
 return result
def require_compose_labels(c,project,service):
 labels=(c.get("Config") or {}).get("Labels") or {}
 expected={"com.docker.compose.project":project,"com.docker.compose.service":service,"com.docker.compose.container-number":"1","com.docker.compose.oneoff":"False"}
 if any(labels.get(k)!=v for k,v in expected.items()): fail("container_labels")
 if re.fullmatch(r"[0-9a-f]{64}",labels.get("com.docker.compose.config-hash", "")) is None: fail("container_config_label")
def expected_volumes(service,pgvol,appvol):
 if service=="postgres": return [(pgvol,"/var/lib/postgresql",True)]
 if service=="api": return [(appvol,"/app/data",False)]
 if service=="gateway": return [(appvol,"/app/data",True)]
 return []
def validate_gateway_topology(path,c,project,actor_name):
 endpoints=(c.get("NetworkSettings") or {}).get("Networks") or {}
 expected={f"{project}_control":("eth0",0),actor_name:("eth1",0),f"{project}_egress":("eth2",1)}
 if set(endpoints)!=set(expected): fail("runtime_gateway_topology")
 interface_ips={}
 for network_name,(interface_name,gw_priority) in expected.items():
  endpoint=endpoints.get(network_name)
  if not isinstance(endpoint,dict) or endpoint.get("GwPriority")!=gw_priority: fail("runtime_gateway_priority")
  if endpoint.get("DriverOpts")!={"com.docker.network.endpoint.ifname":interface_name}: fail("runtime_gateway_interface")
  address=endpoint.get("IPAddress")
  try:
   if not isinstance(address,str) or not ipaddress.ip_address(address).is_private: fail("runtime_gateway_topology")
  except ValueError: fail("runtime_gateway_topology")
  interface_ips[interface_name]=address
 if path=="-": return
 try:
  topology=json.load(open(path,encoding="utf-8"))
 except (OSError,json.JSONDecodeError): fail("runtime_gateway_topology")
 if not isinstance(topology,dict) or set(topology)!={"interfaces","default_interfaces"}: fail("runtime_gateway_topology")
 if topology.get("interfaces")!=interface_ips or topology.get("default_interfaces")!=["eth2"]: fail("runtime_gateway_topology")
def parse_env(c):
 entries=(c.get("Config") or {}).get("Env")
 if not isinstance(entries,list): fail("runtime_environment")
 result={}
 for entry in entries:
  if not isinstance(entry,str) or "=" not in entry: fail("runtime_environment")
  key,value=entry.split("=",1)
  if not key or key in result: fail("runtime_environment")
  result[key]=value
 return result
def secret_digests(path):
 try:
  source=__import__("pathlib").Path(path);source_stat=source.lstat()
  if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode) or stat.S_IMODE(source_stat.st_mode)!=0o600 or source_stat.st_uid!=os.geteuid(): fail("runtime_secret_digest")
  data=json.load(open(source,encoding="utf-8"));keys={"POSTGRES_PASSWORD","BETTER_AUTH_SECRET","SECRET_ENCRYPTION_KEY","GATEWAY_INTERNAL_SECRET"}
  if not isinstance(data,dict) or set(data)!=keys or any(not isinstance(value,str) or re.fullmatch(r"[0-9a-f]{64}",value) is None for value in data.values()): fail("runtime_secret_digest")
  return data
 except (OSError,json.JSONDecodeError): fail("runtime_secret_digest")
def validate_environments(by_service,digests=None):
 env={name:parse_env(c) for name,c in by_service.items()}
 pgpass=env["postgres"].get("POSTGRES_PASSWORD");better=env["api"].get("BETTER_AUTH_SECRET");encryption=env["api"].get("SECRET_ENCRYPTION_KEY");internal=env["api"].get("GATEWAY_INTERNAL_SECRET")
 if any(not isinstance(x,str) for x in (pgpass,better,encryption,internal)): fail("runtime_secret_format")
 if any(re.fullmatch(r"[0-9a-f]{64}",x) is None for x in (pgpass,better,internal)): fail("runtime_secret_format")
 try: decoded=base64.b64decode(encryption,validate=True)
 except (binascii.Error,ValueError): fail("runtime_secret_format")
 if len(decoded)!=32 or base64.b64encode(decoded).decode()!=encryption: fail("runtime_secret_format")
 if len({pgpass,better,encryption,internal})!=4: fail("runtime_secret_reuse")
 if digests is not None:
  actual={"POSTGRES_PASSWORD":pgpass,"BETTER_AUTH_SECRET":better,"SECRET_ENCRYPTION_KEY":encryption,"GATEWAY_INTERNAL_SECRET":internal}
  if any(not hmac.compare_digest(hashlib.sha256(value.encode("utf-8")).hexdigest(),digests[key]) for key,value in actual.items()): fail("runtime_secret_binding")
 dburl=f"postgresql://onecli:{pgpass}@postgres:5432/onecli"
 supplied={
  "postgres":{"POSTGRES_USER":"onecli","POSTGRES_PASSWORD":pgpass,"POSTGRES_DB":"onecli"},
  "migrations":{"DATABASE_URL":dburl},
  "api":{"DATABASE_URL":dburl,"BETTER_AUTH_SECRET":better,"SECRET_ENCRYPTION_KEY":encryption,"GATEWAY_INTERNAL_SECRET":internal,"GATEWAY_INTERNAL_URL":"http://gateway:10255","ONECLI_AGENT_PROXY_ADDRESS":"gateway-relay:10255","ONECLI_APP_PORT":"10254","ONECLI_API_PORT":"10256","ONECLI_GATEWAY_PORT":"10255"},
  "web":{"DATABASE_URL":dburl,"BETTER_AUTH_SECRET":better,"SECRET_ENCRYPTION_KEY":encryption},
  "gateway":{"DATABASE_URL":dburl,"BETTER_AUTH_SECRET":better,"SECRET_ENCRYPTION_KEY":encryption,"GATEWAY_INTERNAL_SECRET":internal,"INTERNAL_API_URL":"http://api:10256"},
 }
 for name in IMAGES:
  expected=dict(DEFAULT_ENV[name]);expected.update(supplied[name])
  if env[name]!=expected: fail("runtime_environment")
def attest_container(c,project,service,pgvol,appvol,actor_name,topology_path):
 config=c.get("Config") or {};host=c.get("HostConfig") or {};network=c.get("NetworkSettings") or {}
 if config.get("Image")!=IMAGES[service]: fail("image_pin")
 if config.get("User")!=USER[service] or config.get("WorkingDir")!=WORKDIR[service]: fail("runtime_identity")
 if config.get("Entrypoint")!=ENTRYPOINT[service] or config.get("Cmd")!=COMMAND[service]: fail("runtime_command")
 if config.get("Healthcheck")!=HEALTH[service]: fail("runtime_healthcheck_identity")
 if host.get("Privileged") is not False or host.get("CapAdd") not in (None,[]): fail("runtime_privilege")
 expected_drop=None if service=="postgres" else ["ALL"]
 if host.get("CapDrop")!=expected_drop or host.get("SecurityOpt")!=["no-new-privileges:true"]: fail("runtime_security")
 forbidden_empty=("Devices","DeviceCgroupRules","DeviceRequests","ExtraHosts","Dns","DnsOptions","DnsSearch","Links","VolumesFrom","GroupAdd","Ulimits")
 if any(host.get(k) not in (None,[]) for k in forbidden_empty): fail("runtime_host_override")
 if host.get("Sysctls") not in (None,{}) or host.get("Tmpfs") not in (None,{}): fail("runtime_host_override")
 if host.get("PidMode") not in (None,"") or host.get("IpcMode") not in (None,"","private") or host.get("UTSMode") not in (None,"") or host.get("UsernsMode") not in (None,""): fail("runtime_namespace")
 if host.get("Runtime")!="runc" or host.get("Isolation") not in (None,"") or host.get("CgroupnsMode")!="private" or host.get("CgroupParent") not in (None,""): fail("runtime_cgroup")
 if host.get("NetworkMode")!=f"{project}_control": fail("runtime_network_mode")
 expected_restart={"Name":"no" if service=="migrations" else "unless-stopped","MaximumRetryCount":0}
 if host.get("RestartPolicy")!=expected_restart: fail("runtime_restart")
 if (host.get("Memory"),host.get("NanoCpus"),host.get("PidsLimit"))!=RESOURCES[service]: fail("runtime_resources")
 if host.get("LogConfig")!={"Type":"json-file","Config":{"max-file":"3","max-size":"5m"}}: fail("runtime_logging")
 if host.get("PublishAllPorts") is not False: fail("host_ports")
 if host.get("PortBindings") not in (None,{}) or any(v not in (None,[]) for v in (network.get("Ports") or {}).values()): fail("host_ports")
 expected=expected_volumes(service,pgvol,appvol)
 expected_binds=[f"{source}:{target}:{'rw' if rw else 'ro'}" for source,target,rw in expected]
 if (host.get("Binds") or [])!=expected_binds or host.get("Mounts") not in (None,[]): fail("runtime_mount_configuration")
 mounts=c.get("Mounts") or []
 actual=[]
 for mount in mounts:
  if mount.get("Type")!="volume" or mount.get("Driver")!="local" or mount.get("Propagation") not in (None,""): fail("runtime_mount")
  actual.append((mount.get("Name"),mount.get("Destination"),mount.get("RW"),mount.get("Mode")))
 wanted=[(source,target,rw,"rw" if rw else "ro") for source,target,rw in expected]
 if actual!=wanted or len(actual)!=len({(x[0],x[1]) for x in actual}): fail("runtime_mount")
 if service=="gateway": validate_gateway_topology(topology_path,c,project,actor_name)
def main():
 if len(sys.argv)!=12 or sys.argv[1] not in {"preflight","post-start"}: fail("arguments")
 mode,project,pgvol,appvol,actor_name,actor_path,control_path,egress_path,containers_path,digests_path,topology_path=sys.argv[1:]
 if mode=="post-start" and digests_path=="-": fail("arguments")
 digests=None if digests_path=="-" else secret_digests(digests_path)
 containers=load(containers_path);actor=network(actor_path,actor_name,True)
 actor_labels=actor.get("Labels") or {}
 if actor_labels!={"com.quant-factory.stack":"onecli-v2-production","com.quant-factory.project":project,"com.quant-factory.role":"actor"}: fail("actor_network_labels")
 actor_cs=members(actor,containers);actor_ids=[ident(c) for c in actor_cs]
 allowed={(project,"gateway"),("quant-factory-paper-observer","paper-observer")}
 if any(x not in allowed for x in actor_ids) or len(actor_ids)!=len(set(actor_ids)): fail("actor_membership")
 if actor_ids.count((project,"gateway"))>(1) or (mode=="post-start" and actor_ids.count((project,"gateway"))!=1): fail("actor_gateway_membership")
 for c in actor_cs:
  p,s=ident(c);require_compose_labels(c,p,s)
  networks=set(((c.get("NetworkSettings") or {}).get("Networks") or {}))
  expected={actor_name} if p=="quant-factory-paper-observer" else {actor_name,f"{project}_control",f"{project}_egress"}
  if networks!=expected: fail("actor_network_escape")
  if (p,s)==(project,"gateway"):
   endpoint=((c.get("NetworkSettings") or {}).get("Networks") or {}).get(actor_name)
   aliases=endpoint.get("Aliases") if isinstance(endpoint,dict) else None
   if not isinstance(aliases,list) or aliases.count("gateway-relay")!=1: fail("actor_gateway_alias")
 control_ids=[];egress_ids=[]
 if control_path!="-":
  control=network(control_path,f"{project}_control",True)
  if (control.get("Labels") or {}).get("com.docker.compose.project")!=project or (control.get("Labels") or {}).get("com.docker.compose.network")!="control": fail("control_network_labels")
  control_cs=members(control,containers);control_ids=[ident(c) for c in control_cs]
  if any(p!=project or s not in IMAGES for p,s in control_ids) or len(control_ids)!=len(set(control_ids)): fail("control_membership")
 if egress_path!="-":
  egress=network(egress_path,f"{project}_egress",False)
  if (egress.get("Labels") or {}).get("com.docker.compose.project")!=project or (egress.get("Labels") or {}).get("com.docker.compose.network")!="egress": fail("egress_network_labels")
  egress_cs=members(egress,containers);egress_ids=[ident(c) for c in egress_cs]
  if egress_ids not in ([],[(project,"gateway")]) or (mode=="post-start" and egress_ids!=[(project,"gateway")]): fail("egress_membership")
 elif mode=="post-start": fail("egress_network")
 project_cs=[c for c in containers if ident(c)[0]==project]
 if mode=="preflight" and bool(project_cs)!=(digests is not None): fail("runtime_secret_binding")
 if any(ident(c) not in {(project,name) for name in IMAGES}|{("quant-factory-paper-observer","paper-observer")} for c in containers): fail("container_inventory")
 identities=[ident(c) for c in project_cs]
 if len(identities)!=len(set(identities)) or any(s not in IMAGES for _,s in identities): fail("service_set")
 for c in project_cs:
  _,service=ident(c);require_compose_labels(c,project,service)
  attest_container(c,project,service,pgvol,appvol,actor_name,topology_path)
 if project_cs and (set(control_ids)!={(project,x) for x in ("postgres","api","web","gateway")} or set(identities)!={(project,x) for x in IMAGES} or egress_ids!=[(project,"gateway")]): fail("service_set")
 if project_cs: validate_environments({ident(c)[1]:c for c in project_cs},digests)
 if mode=="post-start":
  for c in project_cs:
   _,name=ident(c);state=c.get("State") or {}
   if name=="migrations":
    if state.get("Status")!="exited" or state.get("ExitCode")!=0: fail("migrations")
   elif state.get("Status")!="running" or (state.get("Health") or {}).get("Status")!="healthy": fail("service_health")
 print(f"runtime=passed mode={mode} actor_members={len(actor_ids)} control_members={len(control_ids)} egress_members={len(egress_ids)}")
if __name__=="__main__": main()
