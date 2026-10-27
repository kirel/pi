#!/bin/sh
set -eu
cd /opt/strata/terminal
python=/opt/strata/terminal/python/bin/python3
gpu_indices=$("$python" - <<'PY'
import csv, os, subprocess
rows = subprocess.check_output([
    "nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader,nounits"], text=True)
cards = {uuid.strip(): index.strip() for index, uuid in csv.reader(rows.splitlines())}
print(",".join(cards[uuid] for uuid in os.environ["STRATA_GPU_UUIDS"].split(",")))
PY
)
quant=${STRATA_MODEL:-IQ2_XS}
vision=${STRATA_VISION:-no}
config_name=strata-$(printf %s "$quant" | tr '[:upper:]' '[:lower:]').json
cfg=/data/config/$config_name
if [ "$vision" != no ]; then
    cfg=/data/config/${config_name%.json}-vision-$vision.json
fi
if [ ! -f "$cfg" ]; then
    echo "Missing prepared Strata profile: $cfg. Provision the model before using this LlamaSwap launcher." >&2
    exit 1
fi
# Native conversation parking preserves the HA prefix across auxiliary requests.
# Bound its host RAM separately from the container's existing memory limit.
"$python" - "$cfg" "$gpu_indices" <<'PY'
import json, os, sys
from pathlib import Path
from strata_control import engine_component

path = Path(sys.argv[1])
cfg = json.loads(path.read_text())
args = cfg["args"]
options = {
    "--conversation-cache-mib": int(os.environ.get("STRATA_CONVERSATION_CACHE_MIB", "0")),
    "--conversation-cache-slots": int(os.environ.get("STRATA_CONVERSATION_CACHE_SLOTS", "4")),
    "--conversation-cache-min-free-mib": 6144,
}
assert options["--conversation-cache-mib"] >= 0
assert 1 <= options["--conversation-cache-slots"] <= 8
for flag, value in options.items():
    if flag in args:
        i = args.index(flag)
        del args[i:i+2]
    if options["--conversation-cache-mib"]:
        args.extend([flag, str(value)])
# Adapt only the disposable run config; keep the prepared model profile intact.
engine = Path(engine_component.expand("component:strata-engine", cfg))
cfg["exe"] = str(engine)
cfg["lib_dirs"] = engine_component.package_lib_dirs(engine.parent)
cfg["cwd"] = "/opt/strata/terminal"
cfg["log"] = "/tmp/strata-engine.log"
cfg["gpu"] = [int(index) for index in sys.argv[2].split(",")]
cfg["layer_split"] = os.environ["STRATA_LAYER_SPLIT"]
cfg["port"] = int(os.environ["PORT"])
cfg["args"] = [a.replace("/opt/strata/data/", "/opt/strata/terminal/data/") for a in args]
if cfg.get("vision"):
    cfg["vision"]["exe"] = str(engine.with_name("strata-vision"))
Path("/tmp/strata-runtime.json").write_text(json.dumps(cfg, indent=1) + "\n")
PY
exec "$python" serve/server.py --engine strata --config /tmp/strata-runtime.json --port "$PORT"
