from pathlib import Path
import os,sys,subprocess,hashlib,json,shutil
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=HERE/"source"
TARGET=ROOT/"target/asgi-coverage"
sep=chr(31)
env=os.environ.copy()
env.update({"RUSTC_WORKSPACE_WRAPPER":"","CARGO_TARGET_DIR":str(TARGET),"CARGO_LLVM_COV_TARGET_DIR":str(TARGET),"CARGO_LLVM_COV_BUILD_DIR":str(TARGET),"LLVM_PROFILE_FILE":str(HERE/"build-profiles/%p-%m.profraw"),"RUSTC_WRAPPER":str(Path.home()/".cargo/bin/cargo-llvm-cov"),"CARGO_LLVM_COV":"1","CARGO_LLVM_COV_SHOW_ENV":"1","__CARGO_LLVM_COV_RUSTC_WRAPPER":"1","__CARGO_LLVM_COV_RUSTC_WRAPPER_RUSTFLAGS":f"-C{sep}instrument-coverage{sep}--cfg=coverage","__CARGO_LLVM_COV_RUSTC_WRAPPER_CRATE_NAMES":"uvicorn_rs"})
if sys.platform=="darwin":env["RUSTFLAGS"]="-C link-arg=-undefined -C link-arg=dynamic_lookup"
(HERE/"build-profiles").mkdir(exist_ok=True)
command=["cargo","build","--locked","--manifest-path",str(SOURCE/"Cargo.toml"),"--release","--lib"]
started=datetime.now(timezone.utc).isoformat()
with (HERE/"build.log").open("w") as log:
 result=subprocess.run(command,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT,check=False)
record={"schema":"uvicorn-rs-regression/isolated-build@1","status":"passed" if result.returncode==0 else "failed","command":command,"started_at":started,"finished_at":datetime.now(timezone.utc).isoformat(),"exit_code":result.returncode,"source_sha256":hashlib.sha256((SOURCE/"src/lib.rs").read_bytes()).hexdigest(),"normal_behavior":"source81 deferred joins plus exact three current coverage-only seams","installed":False,"build_log_sha256":hashlib.sha256((HERE/"build.log").read_bytes()).hexdigest(),"environment_overrides":{key:env[key] for key in ("CARGO_TARGET_DIR","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","RUSTFLAGS","__CARGO_LLVM_COV_RUSTC_WRAPPER_RUSTFLAGS","__CARGO_LLVM_COV_RUSTC_WRAPPER_CRATE_NAMES")}}
if result.returncode==0:
 lib=TARGET/"release/libuvicorn_rs.dylib";dest=HERE/"native/_native.abi3.so";dest.parent.mkdir(exist_ok=True);shutil.copy2(lib,dest);record["native_sha256"]=hashlib.sha256(dest.read_bytes()).hexdigest();record["native_path"]=str(dest)
(HERE/"build-receipt.json").write_text(json.dumps(record,indent=2)+"\n")
print(json.dumps(record,indent=2));sys.exit(result.returncode)
