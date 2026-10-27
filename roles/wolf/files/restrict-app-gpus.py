#!/usr/bin/env python3
"""Restrict saved Wolf app runners without rewriting client pairing data."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import tomllib


def restrict_gpus(text, gpu_uuid):
    def update(match):
        options = json.loads(match[3])
        host = options.setdefault("HostConfig", {})
        request = [{"Driver": "nvidia", "DeviceIDs": [gpu_uuid],
                    "Capabilities": [["gpu"]]}]
        if host.get("DeviceRequests") == request and host.get("Runtime") == "nvidia":
            return match[0]
        host.update(DeviceRequests=request, Runtime="nvidia")
        return match[1] + match[2] + json.dumps(options, indent=2) + match[2]

    result = re.sub(r"(\bbase_create_json\s*=\s*)('''|\"\"\")(.*?)\2",
                    update, text, flags=re.DOTALL)
    config = tomllib.loads(result)
    for profile in config["profiles"]:
        for app in profile.get("apps", []):
            runner = app.get("runner", {})
            if runner.get("type") == "docker":
                host = json.loads(runner["base_create_json"])["HostConfig"]
                if host["DeviceRequests"][0]["DeviceIDs"] != [gpu_uuid]:
                    raise ValueError("An app runner was not restricted")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("gpu_uuid")
    args = parser.parse_args()
    original = args.config.read_text()
    updated = restrict_gpus(original, args.gpu_uuid)
    if updated != original:
        backup = args.config.with_name(args.config.name + f".gpu-backup-{time.time_ns()}")
        shutil.copy2(args.config, backup)
        os.chmod(backup, 0o600)
        stat = args.config.stat()
        fd, temp = tempfile.mkstemp(dir=args.config.parent)
        try:
            with os.fdopen(fd, "w") as output:
                output.write(updated)
            os.chmod(temp, stat.st_mode & 0o777)
            os.chown(temp, stat.st_uid, stat.st_gid)
            os.replace(temp, args.config)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        print("changed")
