#!/usr/bin/env python3
"""Capture a live LiteLLM stack without printing secrets; prepare an isolated restore.

Run as root. The snapshot directory contains credentials and must stay private.
Postgres uses pg_dump; Redis uses its replication snapshot, not a live AOF copy.
"""
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


CONTAINERS = {
    "postgres": "litellm-postgres",
    "redis": "litellm-redis",
    "proxy": "litellm-proxy-container",
    "cpa": "cli-proxy-api",
    "ha-mcp": "ha-mcp",
    "caddy": "caddy",
}


def run(*args):
    return subprocess.check_output(args)


def image_tag(config_digest):
    return "litellm-remote/snapshot:" + config_digest.removeprefix("sha256:")


def import_images(root):
    # Docker 28's untagged multi-image export has an incomplete OCI index.
    # Use its complete Docker manifest and explicit tags for Docker 29's store.
    process = subprocess.Popen(["docker", "load"], stdin=subprocess.PIPE)
    try:
        with tarfile.open(root / "images.tar.gz", "r|gz") as source:
            with tarfile.open(fileobj=process.stdin, mode="w|") as dest:
                for member in source:
                    if member.name in ("index.json", "oci-layout"):
                        continue
                    content = source.extractfile(member) if member.isfile() else None
                    if member.name == "manifest.json":
                        manifest = json.load(content)
                        for entry in manifest:
                            entry["RepoTags"] = [image_tag(Path(entry["Config"]).name)]
                        content = io.BytesIO(json.dumps(manifest).encode())
                        member.size = content.getbuffer().nbytes
                    dest.addfile(member, content)
        process.stdin.close()
        assert process.wait() == 0, "Image import failed"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def snapshot(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    metadata = {}
    for service, container in CONTAINERS.items():
        obj = json.loads(run("docker", "inspect", container))[0]
        metadata[service] = {
            "image": obj["Image"],
            "environment": dict(x.split("=", 1) for x in obj["Config"]["Env"]),
        }
    (root / "runtime.json").write_text(json.dumps(metadata))
    shutil.copy2("/home/nuc/config/litellm/config.yaml", root / "config.original.yaml")
    shutil.copytree("/home/nuc/config/cpa/auths", root / "cpa-auths")
    shutil.copy2("/home/nuc/config/cpa/config.yaml", root / "cpa-config.yaml")
    shutil.copy2("/etc/ssl/certs/ca-certificates.crt", root / "ca-certificates.crt")
    with (root / "postgres.dump").open("wb") as out:
        subprocess.run(["docker", "exec", "litellm-postgres", "pg_dump", "-U",
                        "litellm", "-d", "litellm", "-Fc"], stdout=out, check=True)
    subprocess.run(["docker", "exec", "litellm-redis", "redis-cli", "--rdb",
                    "/data/litellm-remote-snapshot.rdb"], check=True)
    subprocess.run(["docker", "cp", "litellm-redis:/data/litellm-remote-snapshot.rdb",
                    str(root / "redis.rdb")], check=True)
    subprocess.run(["docker", "exec", "litellm-redis", "rm",
                    "/data/litellm-remote-snapshot.rdb"], check=True)
    # This also records row counts without exposing user data or key values.
    query = "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    tables = run("docker", "exec", "litellm-postgres", "psql", "-U", "litellm",
                 "-d", "litellm", "-Atc", query).decode().splitlines()
    counts = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        counts[table] = int(run("docker", "exec", "litellm-postgres", "psql", "-U",
                               "litellm", "-d", "litellm", "-Atc",
                               "SELECT count(*) FROM " + quoted))
    (root / "table-counts.json").write_text(json.dumps(counts, indent=2))
    print("Snapshot complete; tables:", len(counts))


def prepare(root, backup, address):
    import yaml
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime = json.loads((backup / "runtime.json").read_text())
    config = yaml.safe_load((backup / "config.original.yaml").read_text())
    rewritten = 0
    for model in config["model_list"]:
        params = model.get("litellm_params", {})
        url = params.get("api_base", "")
        if url.startswith("http://192.168.50.5:8317"):
            params["api_base"] = url.replace("http://192.168.50.5:8317", "http://cpa:8317", 1)
            rewritten += 1
    assert rewritten > 0, "Expected CPA routes missing; do not start a home-dependent copy"
    config["litellm_settings"]["callbacks"] = []  # Phoenix lives at home.
    config["general_settings"]["mcp_trusted_proxy_ranges"] = ["172.30.80.0/24"]
    (root / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    if not (root / "cpa-auths").exists():
        shutil.copytree(backup / "cpa-auths", root / "cpa-auths")
    shutil.copy2(backup / "cpa-config.yaml", root / "cpa-config.yaml")
    shutil.copy2(backup / "ca-certificates.crt", root / "ca-certificates.crt")
    for folder in ("postgres", "redis", "caddy-data", "caddy-config"):
        (root / folder).mkdir(exist_ok=True)
    if not any((root / "redis").iterdir()):
        shutil.copy2(backup / "redis.rdb", root / "redis/dump.rdb")
        os.chown(root / "redis/dump.rdb", 999, 999)
    services = {}
    for name, info in runtime.items():
        env = info["environment"]
        if name == "proxy":
            env = {k: v for k, v in env.items() if not k.startswith("GENERIC_")}
            env["PROXY_BASE_URL"] = "https://litellm-remote.kirelabs.org"
            env["REDIS_HOST"] = "litellm-redis"
            env.pop("PHOENIX_COLLECTOR_ENDPOINT", None)
        if name == "caddy":
            env = {"REGFISH_TOKEN": env["REGFISH_TOKEN"]}
        services[name] = {
            "image": image_tag(info["image"]), "pull_policy": "never", "restart": "unless-stopped",
            "dns": ["1.1.1.1", "8.8.8.8"],
            "environment": {k: v.replace("$", "$$") for k, v in env.items()},
            "networks": {"remote": {"aliases": [CONTAINERS[name]]}},
        }
    services["postgres"].update(volumes=["./postgres:/var/lib/postgresql/data"],
        healthcheck={"test": ["CMD-SHELL", "pg_isready -U litellm"], "interval": "5s", "retries": 20})
    # Start from the RDB snapshot; Redis can write subsequent snapshots normally.
    services["redis"].update(volumes=["./redis:/data"])
    services["cpa"].update(volumes=["./cpa-config.yaml:/CLIProxyAPI/config.yaml:ro",
                                                   "./cpa-auths:/root/.cli-proxy-api"])
    services["ha-mcp"].update(command=["ha-mcp-web"])
    services["proxy"].update(init=True, command=["--config", "/app/config.yaml", "--port", "4000"],
        volumes=["./config.yaml:/app/config.yaml:ro",
                 "./ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro"],
        ports=[address + ":4000:4000"],
        ulimits={"stack": {"soft": 67108864, "hard": 67108864}},
        depends_on={"postgres": {"condition": "service_healthy"},
                    "redis": {"condition": "service_started"},
                    "cpa": {"condition": "service_started"},
                    "ha-mcp": {"condition": "service_started"}})
    services["caddy"].update(ports=[address + ":443:443"],
        volumes=["./Caddyfile:/etc/caddy/Caddyfile:ro", "./caddy-data:/data", "./caddy-config:/config"])
    (root / "compose.json").write_text(json.dumps({"name": "litellm-remote", "services": services,
        "networks": {"remote": {"ipam": {"config": [{"subnet": "172.30.80.0/24"}]}}}}, indent=2))
    print("Prepared remote stack; CPA routes:", rewritten)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "prepare", "import-images"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--address", default="100.121.44.75")
    args = parser.parse_args()
    if args.action == "snapshot":
        snapshot(args.directory)
    elif args.action == "import-images":
        import_images(args.directory)
    else:
        assert args.backup and (args.backup / "postgres.dump").is_file()
        prepare(args.directory, args.backup, args.address)
