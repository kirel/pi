"""Run with: python3 tests/test_wolf_gpu_config.py"""
import importlib.util
import json
from pathlib import Path
import tomllib

script = Path(__file__).resolve().parents[1] / "roles/wolf/files/restrict-app-gpus.py"
spec = importlib.util.spec_from_file_location("wolf_gpu_config", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

original = """config_version = 7
[[paired_clients]]
app_state_folder = 'existing-client'
[[profiles]]
id = 'user'
[[profiles.apps]]
title = 'Steam'
[profiles.apps.runner]
type = 'docker'
env = ['RUN_SWAY=true']
base_create_json = '''{"HostConfig":{"IpcMode":"host","DeviceRequests":[{"DeviceIDs":["all"]}]}}'''
"""
updated = module.restrict_gpus(original, "GPU-test")
config = tomllib.loads(updated)
runner = config["profiles"][0]["apps"][0]["runner"]
assert config["paired_clients"] == tomllib.loads(original)["paired_clients"]
assert runner["env"] == ["RUN_SWAY=true"]
assert json.loads(runner["base_create_json"])["HostConfig"]["IpcMode"] == "host"
assert module.restrict_gpus(updated, "GPU-test") == updated
print("Wolf GPU config checks passed")
