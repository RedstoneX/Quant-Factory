import base64, copy, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path
import yaml
ROOT=Path(__file__).parents[1]; D=ROOT/'deployment/onecli-v2-production'
INPUT=D/'validate_inputs.py'; RENDER=D/'validate_rendered_config.py'; RUNTIME=D/'validate_runtime_state.py'; RESOURCE=D/'validate_resource.py'
CAPTURE_SPEC=importlib.util.spec_from_file_location('capture_gateway_topology',D/'capture_gateway_topology.py');CAPTURE=importlib.util.module_from_spec(CAPTURE_SPEC);CAPTURE_SPEC.loader.exec_module(CAPTURE)
IMAGES={"postgres":"postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2","migrations":"ghcr.io/onecli/onecli-migrations@sha256:8293f29e22024a789c987593a512b18140056bf6a522324616c1b48699ac2fa8","api":"ghcr.io/onecli/onecli-api@sha256:48f9b66cda3a136428cf530d4cb934d1ce6bf3a186dd592f02ea3b40a48e2e44","web":"ghcr.io/onecli/onecli-web@sha256:123907a95915db1f645be11bf54709f2aa81c44706f263fdd7cef9141ed73118","gateway":"ghcr.io/onecli/onecli-gateway@sha256:e2bb74a919a34ec8e268168930a0ad38b7adbdbe4a2766afc08eeca1f083354f"}
ENTRYPOINT={"postgres":["docker-entrypoint.sh"],"migrations":["docker-entrypoint.sh"],"api":["/sbin/tini","--"],"web":["/sbin/tini","--"],"gateway":["onecli-gateway"]}
COMMAND={"postgres":["postgres"],"migrations":["./migrate.sh"],"api":["node","apps/api-server/dist/index.mjs"],"web":["node","apps/web/server.js"],"gateway":["--port","10255","--data-dir","/app/data"]}
HEALTH={"postgres":{"Test":["CMD-SHELL","pg_isready -U onecli -d onecli"],"Interval":5_000_000_000,"Timeout":3_000_000_000,"StartPeriod":15_000_000_000,"Retries":10},"migrations":None,"api":{"Test":["CMD-SHELL","wget -qO- http://127.0.0.1:10256/v1/health || exit 1"],"Interval":10_000_000_000,"Timeout":5_000_000_000,"StartPeriod":60_000_000_000,"Retries":3},"web":{"Test":["CMD-SHELL","wget -qO- http://127.0.0.1:10254/healthz || exit 1"],"Interval":10_000_000_000,"Timeout":5_000_000_000,"StartPeriod":60_000_000_000,"Retries":3},"gateway":{"Test":["CMD","onecli-gateway","--healthcheck"],"Interval":10_000_000_000,"Timeout":5_000_000_000,"StartPeriod":30_000_000_000,"Retries":3}}
USER={"postgres":"","migrations":"node","api":"node","web":"node","gateway":"onecli"};WORKDIR={"postgres":"/","migrations":"/app","api":"/app","web":"/app","gateway":"/app"};IMAGE_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
DEFAULT_ENV={"postgres":{"PATH":IMAGE_PATH,"GOSU_VERSION":"1.19","LANG":"en_US.utf8","PG_MAJOR":"18","PG_VERSION":"18.6","PG_SHA256":"555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f","DOCKER_PG_LLVM_DEPS":"llvm21-dev \t\tclang21","PGDATA":"/var/lib/postgresql/18/docker"},"migrations":{"PATH":IMAGE_PATH,"NODE_VERSION":"22.23.2","YARN_VERSION":"1.22.22","APP_VERSION":"2.4.0"},"api":{"PATH":IMAGE_PATH,"NODE_VERSION":"22.23.2","YARN_VERSION":"1.22.22","NODE_ENV":"production","NO_COLOR":"1","FORCE_COLOR":"0","PORT":"10256","APP_VERSION":"2.4.0","NODE_OPTIONS":"--enable-source-maps"},"web":{"PATH":IMAGE_PATH,"NODE_VERSION":"22.23.2","YARN_VERSION":"1.22.22","NODE_ENV":"production","NEXT_TELEMETRY_DISABLED":"1","NO_COLOR":"1","FORCE_COLOR":"0","PORT":"10254","HOSTNAME":"0.0.0.0","APP_VERSION":"2.4.0"},"gateway":{"PATH":IMAGE_PATH,"APP_VERSION":"2.4.0"}}

def environments():
 pg='a'*64;db=f'postgresql://onecli:{pg}@postgres:5432/onecli';better='b'*64;enc=base64.b64encode(bytes(range(32))).decode();internal='d'*64
 return {'postgres':{'POSTGRES_USER':'onecli','POSTGRES_PASSWORD':pg,'POSTGRES_DB':'onecli'},'migrations':{'DATABASE_URL':db},'api':{'DATABASE_URL':db,'BETTER_AUTH_SECRET':better,'SECRET_ENCRYPTION_KEY':enc,'GATEWAY_INTERNAL_SECRET':internal,'GATEWAY_INTERNAL_URL':'http://gateway:10255','ONECLI_AGENT_PROXY_ADDRESS':'gateway-relay:10255','ONECLI_APP_PORT':'10254','ONECLI_API_PORT':'10256','ONECLI_GATEWAY_PORT':'10255'},'web':{'DATABASE_URL':db,'BETTER_AUTH_SECRET':better,'SECRET_ENCRYPTION_KEY':enc},'gateway':{'DATABASE_URL':db,'BETTER_AUTH_SECRET':better,'SECRET_ENCRYPTION_KEY':enc,'GATEWAY_INTERNAL_SECRET':internal,'INTERNAL_API_URL':'http://api:10256'}}
def document():
 services={};env=environments()
 resources={'postgres':('512m',0.5,128),'migrations':('256m',0.5,96),'api':('512m',0.75,192),'web':('384m',0.5,128),'gateway':('384m',0.5,128)}
 depends={'postgres':{},'migrations':{'postgres':{'condition':'service_healthy'}},'api':{'postgres':{'condition':'service_healthy'},'migrations':{'condition':'service_completed_successfully'}},'web':{'api':{'condition':'service_healthy'}},'gateway':{'api':{'condition':'service_healthy'}}}
 for name in IMAGES:
  nets={'control':{}} if name!='gateway' else {'control':{'interface_name':'eth0','priority':1000},'actor':{'aliases':['gateway-relay'],'interface_name':'eth1','priority':500},'egress':{'interface_name':'eth2','priority':100,'gw_priority':1}}
  vols=[]
  if name=='postgres':vols=[{'type':'volume','source':'postgres-data','target':'/var/lib/postgresql','read_only':False}]
  if name=='api':vols=[{'type':'volume','source':'app-data','target':'/app/data','read_only':True}]
  if name=='gateway':vols=[{'type':'volume','source':'app-data','target':'/app/data','read_only':False}]
  services[name]={'image':IMAGES[name],'environment':env[name],'networks':nets,'volumes':vols,'security_opt':['no-new-privileges:true'],'mem_limit':resources[name][0],'cpus':resources[name][1],'pids_limit':resources[name][2],'depends_on':depends[name],'logging':{'driver':'json-file','options':{'max-file':'3','max-size':'5m'}},'restart':'no' if name=='migrations' else 'unless-stopped'}
  if name!='postgres':services[name]['cap_drop']=['ALL']
  if name=='postgres':services[name]['healthcheck']={'test':['CMD-SHELL','pg_isready -U onecli -d onecli'],'interval':'5s','timeout':'3s','start_period':'15s','retries':10}
 return {'name':'qf-onecli-production','services':services,'networks':{'control':{'internal':True,'name':'qf-onecli-production_control'},'actor':{'external':True,'name':'quant-factory-paper-read'},'egress':{'name':'qf-onecli-production_egress'}},'volumes':{'postgres-data':{'external':True,'name':'qf-onecli-production_postgres-data'},'app-data':{'external':True,'name':'qf-onecli-production_app-data'}}}
def validate_render(d):
 with tempfile.NamedTemporaryFile('w') as f:
  json.dump(d,f);f.flush();return subprocess.run([sys.executable,str(RENDER),'qf-onecli-production','qf-onecli-production_postgres-data','qf-onecli-production_app-data','quant-factory-paper-read',f.name],capture_output=True,text=True)
def test_rendered_boundary_accepts_only_exact_topology(): assert validate_render(document()).returncode==0
def test_actual_compose_declares_exact_gateway_network_mapping():
 compose=yaml.safe_load((D/'compose.yaml').read_text())
 assert compose['services']['gateway']['networks']=={
  'control':{'interface_name':'eth0','priority':1000},
  'actor':{'aliases':['gateway-relay'],'interface_name':'eth1','priority':500},
  'egress':{'interface_name':'eth2','priority':100,'gw_priority':1},
 }
def test_capture_helper_output_requires_a_real_slash_zero_and_uses_observed_interface():
 routes='''Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT
eth2 00000000 0100000A 0003 0 0 0 00000080 0 0 0
wan9 00000000 0100000B 0003 0 0 0 00000000 0 0 0
eth7 00000001 0100000C 0003 0 0 0 00000000 0 0 0
'''.splitlines()[1:]
 output=json.loads(CAPTURE.render_topology({'wan9':'10.0.0.2'},routes))
 assert output=={'interfaces':{'wan9':'10.0.0.2'},'default_interfaces':['wan9']}
 only_slash_one=[routes[0]]
 assert json.loads(CAPTURE.render_topology({'eth2':'10.0.0.3'},only_slash_one))['default_interfaces']==[]
def test_rendered_boundary_rejects_independent_security_and_routing_mutations():
 mutations=[lambda d:d['services']['gateway']['environment'].update(INTERNAL_API_URL='http://attacker'),lambda d:d['services']['api']['environment'].pop('ONECLI_AGENT_PROXY_ADDRESS'),lambda d:d['services']['api']['environment'].update(ONECLI_AGENT_PROXY_ADDRESS='gateway:10255'),lambda d:d['services']['gateway'].update(cap_add=['SYS_ADMIN']),lambda d:d['services']['gateway'].update(extra_hosts=['paper-api.alpaca.markets:127.0.0.1']),lambda d:d['services']['gateway'].update(security_opt=['seccomp=unconfined']),lambda d:d['services']['gateway'].update(dns=['8.8.8.8']),lambda d:d['services']['gateway'].update(pid='host'),lambda d:d['services']['gateway'].update(devices=['/dev/sda']),lambda d:d['services']['web'].update(ports=['8050:8050']),lambda d:d['services']['web']['environment'].update(GATEWAY_INTERNAL_SECRET='d'*64),lambda d:d['services']['gateway']['networks']['actor'].update(aliases=['other']),lambda d:d['volumes']['app-data'].update(name='onecli_app-data'),lambda d:d['volumes']['app-data'].update(driver='local'),lambda d:d['networks']['egress'].update(ipam={'config':[{'subnet':'10.0.0.0/8'}]}),lambda d:d['services']['gateway'].update(command=['sh']),lambda d:d['services']['gateway'].update(entrypoint=['sh']),lambda d:d['services']['gateway'].update(build='.'),lambda d:d['services']['gateway'].update(volumes_from=['postgres']),lambda d:d['services']['gateway'].update(links=['api']),lambda d:d['services']['gateway'].update(external_links=['other']),lambda d:d['services']['gateway'].update(group_add=['0']),lambda d:d['services']['gateway'].update(sysctls={'net.ipv4.ip_forward':1}),lambda d:d['services']['gateway'].update(ulimits={'nofile':999999}),lambda d:d['services']['gateway'].update(tmpfs=['/run']),lambda d:d['services']['gateway'].update(configs=[]),lambda d:d['services']['gateway'].update(secrets=[]),lambda d:d['services']['gateway'].update(profiles=['debug']),lambda d:d['services']['gateway'].update(healthcheck={'test':['NONE']}),lambda d:d['services']['gateway']['volumes'].append(copy.deepcopy(d['services']['gateway']['volumes'][0])),lambda d:d['services']['gateway'].update(user='0:0'),lambda d:d['services']['gateway'].update(working_dir='/tmp'),lambda d:d['services']['gateway'].update(runtime='runc-alt'),lambda d:d['services']['gateway'].update(isolation='hyperv'),lambda d:d['services']['gateway'].update(cgroup='host'),lambda d:d['services']['gateway'].update(cgroup_parent='other'),lambda d:d['services']['gateway'].update(cgroupns_mode='host')]
 for mutation in mutations:
  candidate=copy.deepcopy(document());mutation(candidate);assert validate_render(candidate).returncode!=0

def test_rendered_boundary_rejects_gateway_interface_priority_and_default_route_drift():
 mutations=[
  lambda d:d['services']['gateway']['networks']['control'].pop('interface_name'),
  lambda d:d['services']['gateway']['networks']['control'].update(interface_name='eth2'),
  lambda d:d['services']['gateway']['networks']['control'].update(priority=999),
  lambda d:d['services']['gateway']['networks']['actor'].pop('interface_name'),
  lambda d:d['services']['gateway']['networks']['actor'].update(priority=1000),
  lambda d:d['services']['gateway']['networks']['egress'].pop('gw_priority'),
  lambda d:d['services']['gateway']['networks']['egress'].update(interface_name='eth0'),
  lambda d:d['services']['gateway']['networks']['egress'].update(gw_priority=0),
 ]
 for mutation in mutations:
  candidate=copy.deepcopy(document());mutation(candidate);assert validate_render(candidate).returncode!=0

def test_rendered_boundary_revalidates_secret_formats_and_uniqueness_without_output():
 candidates=[('GATEWAY_INTERNAL_SECRET','a'*63+'!'),('SECRET_ENCRYPTION_KEY',base64.b64encode(b'x'*31).decode()),('GATEWAY_INTERNAL_SECRET','b'*64)]
 for key,value in candidates:
  candidate=document()
  candidate['services']['api']['environment'][key]=value
  result=validate_render(candidate);assert result.returncode!=0;assert value not in result.stdout+result.stderr

def write_inputs(root,mode=0o600,duplicate=False,changes=None):
 runtime=root/'runtime.env';secret=root/'secrets.env';runtime.write_text('QF_ONECLI_PROJECT=qf-onecli-production\nQF_ONECLI_POSTGRES_VOLUME=qf-onecli-production_postgres-data\nQF_ONECLI_APP_VOLUME=qf-onecli-production_app-data\nQF_ONECLI_ACTOR_NETWORK=quant-factory-paper-read\n')
 values={'QF_ONECLI_POSTGRES_PASSWORD':'a'*64,'QF_ONECLI_BETTER_AUTH_SECRET':'b'*64,'QF_ONECLI_SECRET_ENCRYPTION_KEY':base64.b64encode(bytes(range(32))).decode(),'QF_ONECLI_GATEWAY_INTERNAL_SECRET':'d'*64};values.update(changes or {})
 secret.write_text('\n'.join(f'{k}={v}' for k,v in values.items())+('\nQF_ONECLI_POSTGRES_PASSWORD='+'e'*64 if duplicate else '')+'\n');runtime.chmod(mode);secret.chmod(0o600);return runtime,secret
def validate_inputs(tmp_path,**kwargs):
 runtime,secret=write_inputs(tmp_path,**kwargs);return subprocess.run([sys.executable,str(INPUT),str(runtime),str(secret),str(ROOT)],capture_output=True,text=True)
def test_external_inputs_require_mode_keys_unique_secrets_and_expected_names(tmp_path):
 ok=validate_inputs(tmp_path);assert ok.returncode==0;assert 'a'*64 not in ok.stdout
 runtime,secret=write_inputs(tmp_path,mode=0o644);assert subprocess.run([sys.executable,str(INPUT),str(runtime),str(secret),str(ROOT)],capture_output=True).returncode!=0
 assert validate_inputs(tmp_path,duplicate=True).returncode!=0
def test_secret_formats_reject_delimiters_base64_length_and_reuse_without_echo(tmp_path):
 invalid=[{'QF_ONECLI_POSTGRES_PASSWORD':'a:b@c/'+'a'*58},{'QF_ONECLI_BETTER_AUTH_SECRET':'b'*63+'!'},{'QF_ONECLI_GATEWAY_INTERNAL_SECRET':'d'*63},{'QF_ONECLI_SECRET_ENCRYPTION_KEY':'not-standard-base64'},{'QF_ONECLI_SECRET_ENCRYPTION_KEY':base64.b64encode(b'x'*31).decode()},{'QF_ONECLI_SECRET_ENCRYPTION_KEY':base64.b64encode(b'x'*33).decode()},{'QF_ONECLI_BETTER_AUTH_SECRET':'a'*64}]
 for changes in invalid:
  result=validate_inputs(tmp_path,changes=changes);assert result.returncode!=0;assert all(v not in result.stdout+result.stderr for v in changes.values())

def fake_network(name,internal,members,labels):
 return {'Name':name,'Internal':internal,'Driver':'bridge','Scope':'local','Attachable':False,'Ingress':False,'EnableIPv6':False,'ConfigOnly':False,'Options':{},'Labels':labels,'IPAM':{'Driver':'default','Options':{},'Config':[{'Subnet':'172.30.0.0/24','Gateway':'172.30.0.1'}]},'Containers':{cid:{} for cid in members}}
def fake_container(cid,project,service,status='running',health='healthy',exit_code=0,networks=None):
 if networks is None: networks={'qf-onecli-production_control'} if service!='gateway' else {'qf-onecli-production_control','quant-factory-paper-read','qf-onecli-production_egress'}
 labels={'com.docker.compose.project':project,'com.docker.compose.service':service,'com.docker.compose.container-number':'1','com.docker.compose.oneoff':'False','com.docker.compose.config-hash':'e'*64}
 if service not in IMAGES:return {'Id':cid,'Config':{'Image':'observer','Labels':labels},'NetworkSettings':{'Networks':{n:{} for n in networks}}}
 resources={'postgres':(512*1024*1024,500_000_000,128),'migrations':(256*1024*1024,500_000_000,96),'api':(512*1024*1024,750_000_000,192),'web':(384*1024*1024,500_000_000,128),'gateway':(384*1024*1024,500_000_000,128)}
 volumes={'postgres':[('qf-onecli-production_postgres-data','/var/lib/postgresql',True)],'api':[('qf-onecli-production_app-data','/app/data',False)],'gateway':[('qf-onecli-production_app-data','/app/data',True)]}.get(service,[])
 binds=[f"{source}:{target}:{'rw' if rw else 'ro'}" for source,target,rw in volumes]
 mounts=[{'Type':'volume','Name':source,'Source':f'/var/lib/docker/volumes/{source}/_data','Destination':target,'Driver':'local','Mode':'rw' if rw else 'ro','RW':rw,'Propagation':''} for source,target,rw in volumes]
 memory,nano,pids=resources[service]
 host={'PortBindings':{},'PublishAllPorts':False,'Binds':binds or None,'Mounts':None,'Privileged':False,'CapAdd':None,'CapDrop':None if service=='postgres' else ['ALL'],'SecurityOpt':['no-new-privileges:true'],'Devices':None,'DeviceCgroupRules':None,'DeviceRequests':None,'ExtraHosts':[],'Dns':[],'DnsOptions':[],'DnsSearch':[],'Links':None,'VolumesFrom':None,'GroupAdd':None,'Ulimits':None,'Sysctls':{},'Tmpfs':{},'PidMode':'','IpcMode':'private','UTSMode':'','UsernsMode':'','Runtime':'runc','Isolation':'','CgroupnsMode':'private','CgroupParent':'','NetworkMode':'qf-onecli-production_control','RestartPolicy':{'Name':'no' if service=='migrations' else 'unless-stopped','MaximumRetryCount':0},'Memory':memory,'NanoCpus':nano,'PidsLimit':pids,'LogConfig':{'Type':'json-file','Config':{'max-file':'3','max-size':'5m'}}}
 combined=dict(DEFAULT_ENV[service]);combined.update(environments()[service])
 endpoint_networks={n:{} for n in networks}
 if service=='gateway':
  endpoint_networks['qf-onecli-production_control']={'DriverOpts':{'com.docker.network.endpoint.ifname':'eth0'},'IPAddress':'172.21.0.5','GwPriority':0}
  endpoint_networks['quant-factory-paper-read']={'Aliases':['gateway','gateway-relay'],'DriverOpts':{'com.docker.network.endpoint.ifname':'eth1'},'IPAddress':'172.22.0.5','GwPriority':0}
  endpoint_networks['qf-onecli-production_egress']={'DriverOpts':{'com.docker.network.endpoint.ifname':'eth2'},'IPAddress':'172.23.0.5','GwPriority':1}
 return {'Id':cid,'Config':{'Image':IMAGES[service],'Labels':labels,'Healthcheck':HEALTH[service],'Entrypoint':ENTRYPOINT[service],'Cmd':COMMAND[service],'User':USER[service],'WorkingDir':WORKDIR[service],'Env':[f'{k}={v}' for k,v in combined.items()]},'HostConfig':host,'Mounts':mounts,'NetworkSettings':{'Networks':endpoint_networks,'Ports':{}},'State':{'Status':status,'ExitCode':exit_code,'Health':{'Status':health}}}
def valid_inspection(): return [fake_container('p','qf-onecli-production','postgres'),fake_container('a','qf-onecli-production','api'),fake_container('w','qf-onecli-production','web'),fake_container('g','qf-onecli-production','gateway'),fake_container('m','qf-onecli-production','migrations',status='exited',health='none',exit_code=0,networks=set())]
def expected_digests(tmp_path,changes=None):
 directory=Path(tempfile.mkdtemp(dir=tmp_path));secret=directory/'secrets.env';values={'QF_ONECLI_POSTGRES_PASSWORD':'a'*64,'QF_ONECLI_BETTER_AUTH_SECRET':'b'*64,'QF_ONECLI_SECRET_ENCRYPTION_KEY':base64.b64encode(bytes(range(32))).decode(),'QF_ONECLI_GATEWAY_INTERNAL_SECRET':'d'*64};values.update(changes or {})
 secret.write_text('\n'.join(f'{key}={value}' for key,value in values.items())+'\n');secret.chmod(0o600);digest=directory/'digests.json'
 result=subprocess.run([sys.executable,str(D/'derive_secret_digests.py'),str(secret),str(digest)],capture_output=True,text=True);assert result.returncode==0
 assert digest.stat().st_mode&0o777==0o600 and directory.stat().st_mode&0o777==0o700
 return digest
def validate_runtime(tmp_path,actor_members,control_members,egress_members,containers,network_mutation=None,secret_changes=None,topology_mutation=None):
 networks=[fake_network('quant-factory-paper-read',True,actor_members,{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'actor'}),fake_network('qf-onecli-production_control',True,control_members,{'com.docker.compose.project':'qf-onecli-production','com.docker.compose.network':'control'}),fake_network('qf-onecli-production_egress',False,egress_members,{'com.docker.compose.project':'qf-onecli-production','com.docker.compose.network':'egress'})]
 if network_mutation:network_mutation(networks)
 paths=[]
 for name,data in zip(('actor.json','control.json','egress.json'),networks): path=tmp_path/name;path.write_text(json.dumps([data]));paths.append(path)
 path=tmp_path/'containers.json';path.write_text(json.dumps(containers));paths.append(path)
 topology_data={'interfaces':{'eth0':'172.21.0.5','eth1':'172.22.0.5','eth2':'172.23.0.5'},'default_interfaces':['eth2']}
 if topology_mutation:topology_mutation(topology_data)
 topology=tmp_path/'gateway-topology.json';topology.write_text(json.dumps(topology_data))
 return subprocess.run([sys.executable,str(RUNTIME),'post-start','qf-onecli-production','qf-onecli-production_postgres-data','qf-onecli-production_app-data','quant-factory-paper-read',*[str(x) for x in paths],str(expected_digests(tmp_path,secret_changes)),str(topology)],capture_output=True,text=True)
def test_fake_docker_inspection_accepts_exact_gateway_and_optional_observer(tmp_path):
 containers=valid_inspection();assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers).returncode==0
 observer=fake_container('o','quant-factory-paper-observer','paper-observer',networks={'quant-factory-paper-read'});assert validate_runtime(tmp_path,['g','o'],['p','a','w','g'],['g'],containers+[observer]).returncode==0
def test_fake_docker_inspection_rejects_foreign_actor_control_egress_and_escape(tmp_path):
 containers=valid_inspection();foreign=fake_container('x','foreign-project','sidecar')
 assert validate_runtime(tmp_path,['g','x'],['p','a','w','g'],['g'],containers+[foreign]).returncode!=0
 assert validate_runtime(tmp_path,['g'],['p','a','w','g','x'],['g'],containers+[foreign]).returncode!=0
 assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g','x'],containers+[foreign]).returncode!=0
 observer=fake_container('o','quant-factory-paper-observer','paper-observer',networks={'quant-factory-paper-read','qf-onecli-production_egress'});assert validate_runtime(tmp_path,['g','o'],['p','a','w','g'],['g'],containers+[observer]).returncode!=0
 disconnected=fake_container('x','foreign-project','sidecar',networks=set());assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers+[disconnected]).returncode!=0
def test_runtime_inspection_requires_gateway_relay_alias_and_exact_supplied_secrets(tmp_path):
 containers=valid_inspection();endpoint=containers[3]['NetworkSettings']['Networks']['quant-factory-paper-read'];endpoint.pop('Aliases');assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers).returncode!=0
 containers=valid_inspection();containers[3]['NetworkSettings']['Networks']['quant-factory-paper-read']['Aliases']=['other'];assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers).returncode!=0
 containers=valid_inspection();alternate={'QF_ONECLI_BETTER_AUTH_SECRET':'c'*64};result=validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers,secret_changes=alternate);assert result.returncode!=0 and alternate['QF_ONECLI_BETTER_AUTH_SECRET'] not in result.stdout+result.stderr
def test_runtime_inspection_rejects_gateway_priority_interface_and_default_route_drift(tmp_path):
 container_mutations=[
  lambda c:c[3]['NetworkSettings']['Networks']['qf-onecli-production_egress'].pop('GwPriority'),
  lambda c:c[3]['NetworkSettings']['Networks']['qf-onecli-production_egress'].update(GwPriority=0),
  lambda c:c[3]['NetworkSettings']['Networks']['quant-factory-paper-read'].update(GwPriority=1),
  lambda c:c[3]['NetworkSettings']['Networks']['qf-onecli-production_control'].pop('DriverOpts'),
  lambda c:c[3]['NetworkSettings']['Networks']['quant-factory-paper-read'].update(DriverOpts={'com.docker.network.endpoint.ifname':'eth2'}),
 ]
 for mutation in container_mutations:
  containers=valid_inspection();mutation(containers);assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers).returncode!=0
 topology_mutations=[
  lambda t:t['interfaces'].pop('eth0'),
  lambda t:t['interfaces'].update(eth0=t['interfaces']['eth2'],eth2=t['interfaces']['eth0']),
  lambda t:t.update(default_interfaces=['eth1']),
  lambda t:t.update(default_interfaces=['eth2','eth1']),
 ]
 for mutation in topology_mutations:
  containers=valid_inspection();assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers,topology_mutation=mutation).returncode!=0
def test_fake_docker_inspection_rejects_ipam_duplicate_labels_image_and_health(tmp_path):
 containers=valid_inspection();assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers,lambda ns:ns[2].update(Options={'x':'y'})).returncode!=0
 duplicate=fake_container('g2','qf-onecli-production','gateway');assert validate_runtime(tmp_path,['g','g2'],['p','a','w','g'],['g'],containers+[duplicate]).returncode!=0
 bad=valid_inspection();bad[0]['Config']['Image']='postgres:latest';assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],bad).returncode!=0
 bad=valid_inspection();bad[3]['State']['Health']['Status']='unhealthy';assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],bad).returncode!=0
 bad=valid_inspection();bad[3]['Config']['Labels']['com.docker.compose.container-number']='2';assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],bad).returncode!=0

def test_runtime_inspection_rejects_hostconfig_mount_command_health_and_resource_mutations(tmp_path):
 mutations=[lambda c:c[3]['HostConfig'].update(Privileged=True),lambda c:c[3]['HostConfig'].update(CapAdd=['SYS_ADMIN']),lambda c:c[3]['HostConfig'].update(CapDrop=[]),lambda c:c[3]['HostConfig'].update(SecurityOpt=[]),lambda c:c[3]['HostConfig'].update(Binds=['/host:/app/data:rw']),lambda c:c[3]['HostConfig'].update(Devices=[{'PathOnHost':'/dev/sda'}]),lambda c:c[3]['HostConfig'].update(DeviceCgroupRules=['c 1:3 rwm']),lambda c:c[3]['HostConfig'].update(DeviceRequests=[{'Driver':'nvidia'}]),lambda c:c[3]['HostConfig'].update(ExtraHosts=['broker:127.0.0.1']),lambda c:c[3]['HostConfig'].update(Dns=['8.8.8.8']),lambda c:c[3]['HostConfig'].update(DnsOptions=['use-vc']),lambda c:c[3]['HostConfig'].update(DnsSearch=['example.test']),lambda c:c[3]['HostConfig'].update(Links=['/other:/gateway/other']),lambda c:c[3]['HostConfig'].update(VolumesFrom=['other']),lambda c:c[3]['HostConfig'].update(GroupAdd=['0']),lambda c:c[3]['HostConfig'].update(Ulimits=[{'Name':'nofile','Soft':999999,'Hard':999999}]),lambda c:c[3]['HostConfig'].update(Sysctls={'net.ipv4.ip_forward':'1'}),lambda c:c[3]['HostConfig'].update(Tmpfs={'/run':'rw'}),lambda c:c[3]['HostConfig'].update(PidMode='host'),lambda c:c[3]['HostConfig'].update(IpcMode='host'),lambda c:c[3]['HostConfig'].update(UTSMode='host'),lambda c:c[3]['HostConfig'].update(UsernsMode='host'),lambda c:c[3]['HostConfig'].update(Runtime='kata'),lambda c:c[3]['HostConfig'].update(Isolation='hyperv'),lambda c:c[3]['HostConfig'].update(CgroupnsMode='host'),lambda c:c[3]['HostConfig'].update(CgroupParent='other'),lambda c:c[3]['HostConfig'].update(NetworkMode='host'),lambda c:c[3]['HostConfig'].update(NetworkMode='quant-factory-paper-read'),lambda c:c[3]['HostConfig'].update(RestartPolicy={'Name':'always','MaximumRetryCount':0}),lambda c:c[3]['HostConfig'].update(Memory=0),lambda c:c[3]['HostConfig'].update(NanoCpus=0),lambda c:c[3]['HostConfig'].update(PidsLimit=0),lambda c:c[3]['HostConfig'].update(LogConfig={'Type':'none','Config':{}}),lambda c:c[3]['HostConfig'].update(PublishAllPorts=True),lambda c:c[3]['Config'].update(Cmd=['sh']),lambda c:c[3]['Config'].update(Entrypoint=['sh']),lambda c:c[3]['Config'].update(Healthcheck={'Test':['NONE']}),lambda c:c[3]['Config'].update(User='0:0'),lambda c:c[3]['Config'].update(WorkingDir='/tmp'),lambda c:c[3]['Mounts'].append(copy.deepcopy(c[3]['Mounts'][0])),lambda c:c[3]['Mounts'][0].update(Name='foreign'),lambda c:c[3]['Mounts'][0].update(Type='bind'),lambda c:c[3]['Mounts'][0].update(RW=False),lambda c:c[2]['HostConfig'].update(CapDrop=None),lambda c:c[0]['HostConfig'].update(CapDrop=['ALL']),lambda c:c[3]['NetworkSettings'].update(Ports={'10255/tcp':[{'HostPort':'10255'}]}),lambda c:c[3]['Config']['Labels'].update({'com.docker.compose.config-hash':'bad'})]
 for mutation in mutations:
  containers=valid_inspection();mutation(containers);assert validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers).returncode!=0

def replace_env(container,key,value):
 container['Config']['Env']=[f'{key}={value}' if item.startswith(key+'=') else item for item in container['Config']['Env']]
def remove_env(container,key):
 container['Config']['Env']=[item for item in container['Config']['Env'] if not item.startswith(key+'=')]
def test_runtime_inspection_rejects_environment_extra_missing_drift_and_secret_errors_without_output(tmp_path):
 bad_secret='not-standard-base64'
 mutations=[lambda c:c[3]['Config']['Env'].append('EXTRA=value'),lambda c:c[3]['Config']['Env'].pop(),lambda c:replace_env(c[3],'INTERNAL_API_URL','http://attacker'),lambda c:remove_env(c[1],'ONECLI_AGENT_PROXY_ADDRESS'),lambda c:replace_env(c[1],'ONECLI_AGENT_PROXY_ADDRESS','gateway:10255'),lambda c:replace_env(c[1],'SECRET_ENCRYPTION_KEY',bad_secret),lambda c:c[1]['Config']['Env'].append('DATABASE_URL=duplicate')]
 for mutation in mutations:
  containers=valid_inspection();mutation(containers);result=validate_runtime(tmp_path,['g'],['p','a','w','g'],['g'],containers);assert result.returncode!=0;assert bad_secret not in result.stdout+result.stderr

def test_provisioned_resource_inspection_requires_exact_labels_driver_and_options(tmp_path):
 volume={'Name':'qf-onecli-production_app-data','Driver':'local','Options':{},'Labels':{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'app-data'}}
 path=tmp_path/'resource.json';path.write_text(json.dumps([volume]));args=[sys.executable,str(RESOURCE),'volume',volume['Name'],'qf-onecli-production','app-data',str(path)];assert subprocess.run(args,capture_output=True).returncode==0
 volume['Options']={'type':'none'};path.write_text(json.dumps([volume]));assert subprocess.run(args,capture_output=True).returncode!=0

def test_provisioner_fails_before_mutation_on_resource_collision(tmp_path):
 runtime,secret=write_inputs(tmp_path);fake=tmp_path/'sudo';fake.write_text('#!/bin/sh\n[ "$1" = "-n" ] && shift\n[ "$1" = "docker" ] && shift\nif [ "$1" = "ps" ]; then exit 0; fi\nif [ "$1" = "volume" ] && [ "$2" = "inspect" ]; then exit 0; fi\nexit 99\n');fake.chmod(0o755)
 result=subprocess.run([str(D/'provision-resources.sh'),str(runtime),str(secret)],capture_output=True,text=True,env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH']))
 assert result.returncode!=0 and 'reason=resource_collision' in result.stderr and 'volume create' not in result.stdout+result.stderr

def test_compose_and_paper_share_one_external_actor_network_and_gateway_only_egress():
 production=(D/'compose.yaml').read_text();paper=(ROOT/'deployment/paper/compose.yaml').read_text()
 assert 'aliases: [gateway-relay]' in production and 'QF_ONECLI_ACTOR_NETWORK' in production and 'egress: {}' in production
 assert 'QF_ONECLI_ACTOR_NETWORK=quant-factory-paper-read' in (D/'runtime.env.example').read_text();assert 'external: true' in paper and 'name: quant-factory-paper-read' in paper
 assert 'ports:' not in production and 'docker.sock' not in production and 'runner:' not in production
 verifier=(D/'verify-runtime.sh').read_text();preflight=(D/'preflight.sh').read_text();assert '--pull never' in verifier and 'timeout --signal=TERM --kill-after=5s 30s' in verifier
 assert 'derive_secret_digests.py' in verifier and 'capture_gateway_topology.py' in verifier and '--network "container:$gateway_id"' in verifier
 assert 'volume=$name' in verifier and 'volume=$name' in preflight and 'umask 077' in verifier and 'chmod 700 "$tmpdir"' in verifier
def test_preflight_and_runtime_reject_disconnected_foreign_volume_consumers(tmp_path):
 runtime,secret=write_inputs(tmp_path);rendered=tmp_path/'rendered.json';rendered.write_text(json.dumps(document()))
 fake=tmp_path/'sudo';fake.write_text('''#!/bin/sh
[ "$1" = "-n" ] && shift
[ "$1" = "docker" ] && shift
case "$1" in
 compose) cat "$QF_RENDERED" ;;
 volume) exit 1 ;;
 network) if [ ! -e "$QF_FAKE_NETWORK_STATE" ]; then : > "$QF_FAKE_NETWORK_STATE"; exit 1; fi; printf '[{"Containers":{}}]\\n' ;;
 ps) case "$*" in *volume=*) echo foreign ;; esac ;;
 inspect) [ "$2" = "-f" ] && echo foreign-project ;;
esac
''');fake.chmod(0o755)
 env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],QF_RENDERED=str(rendered),QF_FAKE_NETWORK_STATE=str(tmp_path/'network-inspected'))
 for script,prefix in ((D/'preflight.sh','preflight'),(D/'verify-runtime.sh','runtime')):
  result=subprocess.run([str(script),str(runtime),str(secret)],capture_output=True,text=True,env=env)
  assert result.returncode!=0 and f'{prefix}=failed reason=volume_consumer' in result.stderr
  assert secret.read_text() not in result.stdout+result.stderr
def test_preflight_binds_managed_stack_to_supplied_secrets_before_compose_mutation(tmp_path):
 runtime,secret=write_inputs(tmp_path);rendered=tmp_path/'rendered.json';rendered.write_text(json.dumps(document()))
 containers=tmp_path/'containers.json';containers.write_text(json.dumps(valid_inspection()))
 actor=tmp_path/'actor.json';actor.write_text(json.dumps([fake_network('quant-factory-paper-read',True,['g'],{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'actor'})]))
 control=tmp_path/'control.json';control.write_text(json.dumps([fake_network('qf-onecli-production_control',True,['p','a','w','g'],{'com.docker.compose.project':'qf-onecli-production','com.docker.compose.network':'control'})]))
 egress=tmp_path/'egress.json';egress.write_text(json.dumps([fake_network('qf-onecli-production_egress',False,['g'],{'com.docker.compose.project':'qf-onecli-production','com.docker.compose.network':'egress'})]))
 volumes=tmp_path/'volumes.json';volumes.write_text(json.dumps([{'Name':'qf-onecli-production_postgres-data','Driver':'local','Options':{},'Labels':{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'postgres-data'}},{'Name':'qf-onecli-production_app-data','Driver':'local','Options':{},'Labels':{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'app-data'}}]))
 fake=tmp_path/'sudo';fake.write_text('''#!/bin/sh
[ "$1" = "-n" ] && shift
[ "$1" = "docker" ] && shift
printf '%s\\n' "$*" >> "$QF_FAKE_LOG"
case "$1" in
 compose) cat "$QF_RENDERED" ;;
 ps) case "$*" in *volume=qf-onecli-production_postgres-data*) echo p;; *volume=qf-onecli-production_app-data*) printf 'a\\ng\\n';; *com.docker.compose.project*) printf 'p\\na\\nw\\ng\\nm\\n';; esac ;;
 container) exit 0 ;;
 volume) if [ "$2" = inspect ] && [ "$3" = -f ]; then case "$4" in *stack*) echo onecli-v2-production;; *project*) echo qf-onecli-production;; *role*) case "$5" in qf-onecli-production_postgres-data) echo postgres-data;; qf-onecli-production_app-data) echo app-data;; esac;; esac; else case "$3" in qf-onecli-production_postgres-data) printf '[{"Name":"qf-onecli-production_postgres-data","Driver":"local","Options":{},"Labels":{"com.quant-factory.stack":"onecli-v2-production","com.quant-factory.project":"qf-onecli-production","com.quant-factory.role":"postgres-data"}}]\n';; qf-onecli-production_app-data) printf '[{"Name":"qf-onecli-production_app-data","Driver":"local","Options":{},"Labels":{"com.quant-factory.stack":"onecli-v2-production","com.quant-factory.project":"qf-onecli-production","com.quant-factory.role":"app-data"}}]\n';; esac; fi ;;
 network) if [ "$2" = inspect ] && [ "$3" = -f ]; then case "$4" in *Internal*) echo true;; *Driver*) echo bridge;; *stack*) echo onecli-v2-production;; *project*) echo qf-onecli-production;; *role*) echo actor;; esac; else case "$3" in quant-factory-paper-read) cat "$QF_ACTOR";; qf-onecli-production_control) cat "$QF_CONTROL";; qf-onecli-production_egress) cat "$QF_EGRESS";; esac; fi ;;
 inspect) if [ "$2" = -f ]; then case "$3" in *project*) case "$4" in p|qf-onecli-production-postgres-1|a|qf-onecli-production-api-1|w|qf-onecli-production-web-1|g|qf-onecli-production-gateway-1|m|qf-onecli-production-migrations-1) echo qf-onecli-production;; esac;; *service*) case "$4" in p|qf-onecli-production-postgres-1) echo postgres;; a|qf-onecli-production-api-1) echo api;; w|qf-onecli-production-web-1) echo web;; g|qf-onecli-production-gateway-1) echo gateway;; m|qf-onecli-production-migrations-1) echo migrations;; esac;; esac; else cat "$QF_CONTAINERS"; fi ;;
esac
''');fake.chmod(0o755)
 log=tmp_path/'calls';env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],QF_RENDERED=str(rendered),QF_CONTAINERS=str(containers),QF_ACTOR=str(actor),QF_CONTROL=str(control),QF_EGRESS=str(egress),QF_VOLUMES=str(volumes),QF_FAKE_LOG=str(log))
 result=subprocess.run([str(D/'preflight.sh'),str(runtime),str(secret)],capture_output=True,text=True,env=env)
 assert result.returncode==0 and 'preflight=passed project=qf-onecli-production resources=managed' in result.stdout
 different_root=tmp_path/'different';different_root.mkdir()
 _,different=write_inputs(different_root,changes={'QF_ONECLI_BETTER_AUTH_SECRET':'c'*64})
 result=subprocess.run([str(D/'preflight.sh'),str(runtime),str(different)],capture_output=True,text=True,env=env)
 assert result.returncode!=0 and 'runtime=failed reason=runtime_secret_binding' in result.stderr
 assert 'c'*64 not in result.stdout+result.stderr
 assert all(not call.startswith('compose ') or ' config ' in f' {call} ' for call in log.read_text().splitlines())
def test_provisioner_reinspects_before_owning_raced_resource(tmp_path):
 runtime,secret=write_inputs(tmp_path);fake=tmp_path/'sudo';log=tmp_path/'calls';state=tmp_path/'created'
 fake.write_text('''#!/bin/sh
[ "$1" = "-n" ] && shift
[ "$1" = "docker" ] && shift
printf '%s\\n' "$*" >> "$QF_FAKE_LOG"
if [ "$1" = "ps" ]; then exit 0; fi
if [ "$1" = "volume" ] && [ "$2" = "create" ]; then : > "$QF_FAKE_STATE"; echo "$8"; exit 0; fi
if [ "$1" = "volume" ] && [ "$2" = "inspect" ] && [ -f "$QF_FAKE_STATE" ]; then echo '[{"Name":"foreign","Driver":"local","Labels":{},"Options":{}}]'; exit 0; fi
if { [ "$1" = "volume" ] || [ "$1" = "network" ]; } && [ "$2" = "inspect" ]; then exit 1; fi
exit 99
''');fake.chmod(0o755)
 env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],QF_FAKE_LOG=str(log),QF_FAKE_STATE=str(state))
 result=subprocess.run([str(D/'provision-resources.sh'),str(runtime),str(secret)],capture_output=True,text=True,env=env)
 assert result.returncode!=0 and 'resource=failed' in result.stderr
 assert 'volume rm' not in log.read_text()

def test_full_length_inventory_ids_are_delimited_and_never_truncated(tmp_path):
 runtime,secret=write_inputs(tmp_path);rendered=tmp_path/'rendered.json';rendered.write_text(json.dumps(document()))
 ids={name:f'{index:x}'*64 for index,name in enumerate(('postgres','api','web','gateway','migrations'),1)}
 containers=valid_inspection()
 for container,name in zip(containers,('postgres','api','web','gateway','migrations')): container['Id']=ids[name]
 networks=[fake_network('quant-factory-paper-read',True,[ids['gateway']],{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'actor'}),fake_network('qf-onecli-production_control',True,[ids[name] for name in ('postgres','api','web','gateway')],{'com.docker.compose.project':'qf-onecli-production','com.docker.compose.network':'control'}),fake_network('qf-onecli-production_egress',False,[ids['gateway']],{'com.docker.compose.project':'qf-onecli-production','com.docker.compose.network':'egress'})]
 files={}
 for name,data in zip(('actor','control','egress'),networks): path=tmp_path/f'{name}.json';path.write_text(json.dumps([data]));files[name]=path
 containers_path=tmp_path/'containers.json';containers_path.write_text(json.dumps(containers))
 volumes=[{'Name':'qf-onecli-production_postgres-data','Driver':'local','Options':{},'Labels':{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'postgres-data'}},{'Name':'qf-onecli-production_app-data','Driver':'local','Options':{},'Labels':{'com.quant-factory.stack':'onecli-v2-production','com.quant-factory.project':'qf-onecli-production','com.quant-factory.role':'app-data'}}]
 pg_volume=tmp_path/'postgres-volume.json';pg_volume.write_text(json.dumps([volumes[0]]));app_volume=tmp_path/'app-volume.json';app_volume.write_text(json.dumps([volumes[1]]))
 fake=tmp_path/'sudo';fake.write_text('''#!/bin/sh
[ "$1" = -n ] && shift; [ "$1" = docker ] && shift
printf '%s\\n' "$*" >> "$QF_LOG"
case "$1" in
 compose) cat "$QF_RENDERED" ;;
 ps) case "$*" in *--no-trunc*) :;; *) exit 97;; esac; case "$*" in *com.docker.compose.service=gateway*) printf '%s\\n' "$QF_GATEWAY";; *postgres-data*) printf '%s\\n' "$QF_POSTGRES";; *app-data*) printf '%s\\n' "$QF_API" "$QF_GATEWAY";; *com.docker.compose.project*) printf '%s\\n' "$QF_POSTGRES" "$QF_API" "$QF_WEB" "$QF_GATEWAY" "$QF_MIGRATIONS";; esac ;;
 container) exit 0 ;;
 volume) if [ "$3" = -f ]; then case "$4" in *stack*) echo onecli-v2-production;; *project*) echo qf-onecli-production;; *role*) case "$5" in *postgres*) echo postgres-data;; *) echo app-data;; esac;; esac; else case "$3" in *postgres*) cat "$QF_PG_VOLUME";; *) cat "$QF_APP_VOLUME";; esac; fi ;;
 network) if [ "$3" = -f ]; then case "$4" in *Internal*) echo true;; *Driver*) echo bridge;; *stack*) echo onecli-v2-production;; *project*) echo qf-onecli-production;; *role*) echo actor;; esac; else case "$3" in quant-factory-paper-read) cat "$QF_ACTOR";; *control) cat "$QF_CONTROL";; *egress) cat "$QF_EGRESS";; esac; fi ;;
 inspect) if [ "$2" = -f ]; then case "$3" in *project*) echo qf-onecli-production;; *service*) case "$4" in 1*|*postgres*) echo postgres;; 2*|*api*) echo api;; 3*|*web*) echo web;; 4*|*gateway*) echo gateway;; 5*|*migrations*) echo migrations;; esac;; esac; else shift; for id; do case "$id" in "$QF_POSTGRES"|"$QF_API"|"$QF_WEB"|"$QF_GATEWAY"|"$QF_MIGRATIONS") :;; *) exit 98;; esac; done; python3 -c 'import json,sys; docs=json.load(open(sys.argv[1])); by_id={doc["Id"]:doc for doc in docs}; print(json.dumps([by_id[item] for item in sys.argv[2:]]))' "$QF_CONTAINERS" "$@"; fi ;;
 image) exit 0 ;;
 run) case "$*" in *container:*) printf '%s\\n' '{"interfaces":{"eth0":"172.21.0.5","eth1":"172.22.0.5","eth2":"172.23.0.5"},"default_interfaces":["eth2"]}';; *) echo internal_health=passed;; esac ;;
esac
''');fake.chmod(0o755)
 log=tmp_path/'calls';env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],QF_LOG=str(log),QF_RENDERED=str(rendered),QF_PG_VOLUME=str(pg_volume),QF_APP_VOLUME=str(app_volume),QF_ACTOR=str(files['actor']),QF_CONTROL=str(files['control']),QF_EGRESS=str(files['egress']),QF_CONTAINERS=str(containers_path),**{f'QF_{name.upper()}':value for name,value in ids.items()})
 for script in (D/'preflight.sh',D/'verify-runtime.sh'):
  result=subprocess.run([str(script),str(runtime),str(secret)],capture_output=True,text=True,env=env);assert result.returncode==0,result.stderr
 calls=log.read_text();assert calls.count('ps -aq --no-trunc')>=6
