import importlib.util
import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch, Mock

import yaml


spec = importlib.util.spec_from_file_location(
    "snapshot", Path(__file__).parents[1] / "scripts/litellm_remote_snapshot.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class RemoteSnapshotTest(unittest.TestCase):
    def test_image_import_uses_all_manifest_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with tarfile.open(root / "images.tar.gz", "w:gz") as archive:
                entries = {"index.json": b"{}", "oci-layout": b"{}", "blobs/sha256/abc": b"content",
                           "manifest.json": json.dumps([
                               {"Config": "blobs/sha256/abc", "RepoTags": None},
                               {"Config": "blobs/sha256/def", "RepoTags": None}]).encode()}
                for name, content in entries.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
            output = root / "import.tar"
            process = Mock(stdin=output.open("wb"))
            process.wait.return_value = 0
            process.poll.return_value = 0
            with patch.object(snapshot.subprocess, "Popen", return_value=process):
                snapshot.import_images(root)
            with tarfile.open(output) as archive:
                self.assertNotIn("index.json", archive.getnames())
                self.assertNotIn("oci-layout", archive.getnames())
                manifest = json.load(archive.extractfile("manifest.json"))
                self.assertEqual([e["RepoTags"] for e in manifest],
                                 [["litellm-remote/snapshot:abc"], ["litellm-remote/snapshot:def"]])
                self.assertEqual(archive.extractfile("blobs/sha256/abc").read(), b"content")

    def test_restore_routes_and_private_ports_preserve_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "backup"
            backup.mkdir()
            root = Path(directory) / "runtime"
            runtime = {name: {"image": "sha256:fixture", "environment": {}}
                       for name in snapshot.CONTAINERS}
            runtime["caddy"]["environment"] = {"REGFISH_TOKEN": "test$token"}
            runtime["proxy"]["environment"] = {
                "LITELLM_MASTER_KEY": "test$key", "GENERIC_CLIENT_SECRET": "sso"}
            (backup / "runtime.json").write_text(json.dumps(runtime))
            (backup / "config.original.yaml").write_text(yaml.safe_dump({
                "model_list": [{"litellm_params": {"api_base": "http://192.168.50.5:8317/v1"}},
                               {"litellm_params": {"api_base": "https://external.example/v1"}}],
                "litellm_settings": {"callbacks": ["arize_phoenix"]},
                "general_settings": {}, "mcp_servers": {"test": {"access_groups": ["web"]}}}))
            (backup / "cpa-auths").mkdir()
            for filename in ("cpa-config.yaml", "ca-certificates.crt", "redis.rdb"):
                (backup / filename).write_text("fixture")
            with patch.object(snapshot.os, "chown"):
                snapshot.prepare(root, backup, "100.121.44.75")
            config = yaml.safe_load((root / "config.yaml").read_text())
            self.assertEqual(config["model_list"][0]["litellm_params"]["api_base"], "http://cpa:8317/v1")
            self.assertEqual(config["model_list"][1]["litellm_params"]["api_base"], "https://external.example/v1")
            self.assertEqual(config["mcp_servers"]["test"]["access_groups"], ["web"])
            services = json.loads((root / "compose.json").read_text())["services"]
            self.assertEqual(services["proxy"]["environment"]["LITELLM_MASTER_KEY"], "test$$key")
            self.assertNotIn("GENERIC_CLIENT_SECRET", services["proxy"]["environment"])
            for service in ("postgres", "redis", "cpa", "ha-mcp"):
                self.assertNotIn("ports", services[service])
            for service in services.values():
                self.assertEqual(service["dns"], ["1.1.1.1", "8.8.8.8"])
            self.assertEqual(services["caddy"]["ports"], ["100.121.44.75:443:443"])
            # Preparing again must not overwrite live OAuth or Redis state.
            (root / "cpa-auths/live").write_text("keep")
            (root / "redis/dump.rdb").write_text("live")
            snapshot.prepare(root, backup, "100.121.44.75")
            self.assertEqual((root / "cpa-auths/live").read_text(), "keep")
            self.assertEqual((root / "redis/dump.rdb").read_text(), "live")


if __name__ == "__main__":
    unittest.main()
