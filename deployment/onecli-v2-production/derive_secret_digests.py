#!/usr/bin/env python3
"""Write protected SHA-256 digests for the supplied OneCLI secret dotenv."""
from __future__ import annotations
import hashlib,json,os,stat,sys
from pathlib import Path
SOURCE_KEYS={"QF_ONECLI_POSTGRES_PASSWORD":"POSTGRES_PASSWORD","QF_ONECLI_BETTER_AUTH_SECRET":"BETTER_AUTH_SECRET","QF_ONECLI_SECRET_ENCRYPTION_KEY":"SECRET_ENCRYPTION_KEY","QF_ONECLI_GATEWAY_INTERNAL_SECRET":"GATEWAY_INTERNAL_SECRET"}
def fail(reason): raise SystemExit(f"runtime=failed reason={reason}")
def main():
 if len(sys.argv)!=3: fail("secret_digest_arguments")
 source,target=map(Path,sys.argv[1:])
 try:
  source_stat=source.lstat();parent_stat=target.parent.lstat()
  if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode) or stat.S_IMODE(source_stat.st_mode)!=0o600 or source_stat.st_uid!=os.geteuid(): fail("secret_digest_source")
  if not stat.S_ISDIR(parent_stat.st_mode) or stat.S_IMODE(parent_stat.st_mode)!=0o700 or parent_stat.st_uid!=os.geteuid() or target.exists(): fail("secret_digest_target")
  values={}
  for line in source.read_text(encoding="utf-8").splitlines():
   if not line or line.startswith("#"): continue
   key,value=line.split("=",1);values[key]=value
  if set(values)!=set(SOURCE_KEYS): fail("secret_digest_source")
  digests={target_key:hashlib.sha256(values[source_key].encode("utf-8")).hexdigest() for source_key,target_key in SOURCE_KEYS.items()}
  fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
  with os.fdopen(fd,"w",encoding="utf-8") as handle:
   json.dump(digests,handle,sort_keys=True,separators=(",",":"));handle.write("\n")
  os.chmod(target,0o600)
 except (OSError,UnicodeError,ValueError): fail("secret_digest_io")
if __name__=="__main__": main()
