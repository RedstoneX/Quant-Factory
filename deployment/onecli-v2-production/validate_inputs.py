#!/usr/bin/env python3
"""Validate external dotenv inputs without emitting secret values."""
from __future__ import annotations
import base64, binascii, json, os, re, stat, sys
from pathlib import Path
RUNTIME_KEYS={"QF_ONECLI_PROJECT","QF_ONECLI_POSTGRES_VOLUME","QF_ONECLI_APP_VOLUME","QF_ONECLI_ACTOR_NETWORK"}
SECRET_KEYS={"QF_ONECLI_POSTGRES_PASSWORD","QF_ONECLI_BETTER_AUTH_SECRET","QF_ONECLI_SECRET_ENCRYPTION_KEY","QF_ONECLI_GATEWAY_INTERNAL_SECRET"}
SAFE=re.compile(r"^[a-z0-9][a-z0-9_.-]{5,63}$")
HEX64=re.compile(r"^[0-9a-f]{64}$")
def fail(reason): raise SystemExit(f"preflight=failed reason={reason}")
def load(path: Path, expected: set[str], label: str):
 try:
  st=path.lstat()
  if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode): fail(f"{label}_file_type")
  if stat.S_IMODE(st.st_mode)!=0o600: fail(f"{label}_file_mode")
  if st.st_uid != os.geteuid(): fail(f"{label}_file_owner")
  values={}
  for raw in path.read_text(encoding="utf-8").splitlines():
   if not raw or raw.startswith("#"): continue
   if raw != raw.strip(): fail(f"{label}_format")
   line=raw
   if "=" not in line: fail(f"{label}_format")
   key,value=line.split("=",1)
   if key in values: fail(f"{label}_duplicate_key")
   values[key]=value
  if set(values)!=expected: fail(f"{label}_keys")
  return values
 except (OSError,UnicodeError): fail(f"{label}_read")
def main():
 if len(sys.argv)!=4: fail("arguments")
 runtime_path,secret_path,repo_root=map(Path,sys.argv[1:])
 if not runtime_path.is_absolute() or not secret_path.is_absolute(): fail("external_path_absolute")
 repo=repo_root.resolve()
 for p in (runtime_path,secret_path):
  try: p.resolve().relative_to(repo); fail("input_inside_repository")
  except ValueError: pass
 runtime=load(runtime_path,RUNTIME_KEYS,"runtime")
 secrets=load(secret_path,SECRET_KEYS,"secrets")
 project=runtime["QF_ONECLI_PROJECT"]
 if not SAFE.fullmatch(project) or project in {"onecli","quant-factory-research"} or project.startswith("shared") or "rehearsal" in project: fail("project_name")
 if runtime["QF_ONECLI_POSTGRES_VOLUME"]!=f"{project}_postgres-data" or runtime["QF_ONECLI_APP_VOLUME"]!=f"{project}_app-data": fail("volume_identity")
 if runtime["QF_ONECLI_ACTOR_NETWORK"]!="quant-factory-paper-read": fail("actor_network_identity")
 values=list(secrets.values())
 if len(set(values))!=len(values): fail("secret_reuse")
 for key in ("QF_ONECLI_POSTGRES_PASSWORD","QF_ONECLI_BETTER_AUTH_SECRET","QF_ONECLI_GATEWAY_INTERNAL_SECRET"):
  if not HEX64.fullmatch(secrets[key]): fail("secret_value")
 encryption=secrets["QF_ONECLI_SECRET_ENCRYPTION_KEY"]
 try:
  decoded=base64.b64decode(encryption,validate=True)
 except (binascii.Error,ValueError): fail("encryption_key_format")
 if len(decoded)!=32 or base64.b64encode(decoded).decode()!=encryption: fail("encryption_key_format")
 print(json.dumps(runtime,sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
