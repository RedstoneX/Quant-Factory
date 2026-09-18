#!/usr/bin/env python3
"""Validate a just-created external resource before treating it as owned."""
import ipaddress,json,sys
def fail(r): raise SystemExit(f"resource=failed reason={r}")
def main():
 if len(sys.argv)!=6 or sys.argv[1] not in {"volume","network"}: fail("arguments")
 kind,name,project,role,path=sys.argv[1:]
 try: docs=json.load(open(path,encoding="utf-8"))
 except Exception: fail("inspect_json")
 if not isinstance(docs,list) or len(docs)!=1: fail("inspect_json")
 x=docs[0];labels=x.get("Labels") or {};expected={"com.quant-factory.stack":"onecli-v2-production","com.quant-factory.project":project,"com.quant-factory.role":role}
 if x.get("Name")!=name or labels!=expected: fail("identity")
 if kind=="volume":
  if x.get("Driver")!="local" or (x.get("Options") or {})!={}: fail("volume_options")
 else:
  if x.get("Driver")!="bridge" or x.get("Internal") is not True or x.get("Scope")!="local" or x.get("Attachable") is not False or x.get("Ingress") is not False or x.get("EnableIPv6") is not False or (x.get("Options") or {})!={} or (x.get("Containers") or {})!={}: fail("network_options")
  ipam=x.get("IPAM") or {};configs=ipam.get("Config") or []
  try:
   subnet=ipaddress.ip_network(configs[0]["Subnet"]);gateway=ipaddress.ip_address(configs[0]["Gateway"])
  except (IndexError,KeyError,ValueError): fail("network_ipam")
  if ipam.get("Driver")!="default" or (ipam.get("Options") or {})!={} or len(configs)!=1 or not subnet.is_private or gateway not in subnet: fail("network_ipam")
 print(f"resource=passed kind={kind} role={role}")
if __name__=="__main__": main()
