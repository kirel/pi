from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "files" / "ai_media.py"
SPEC = importlib.util.spec_from_file_location("ai_media", SCRIPT)
assert SPEC and SPEC.loader
ai_media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ai_media)


FAKE_FFPROBE = r"""#!/usr/bin/env python3
import json, pathlib, sys
p = pathlib.Path(sys.argv[-1])
if p.suffix.lower() in {'.mp4', '.mkv', '.mov', '.webm'}:
    data = {'streams': [{'codec_type': 'video', 'codec_name': 'h264'}], 'format': {}}
else:
    tags = {}
    try:
        first = p.read_bytes().splitlines()[0]
        if first.startswith(b'TAGS:'):
            tags = json.loads(first[5:])
    except Exception:
        pass
    data = {'streams': [{'codec_type': 'audio', 'codec_name': 'flac'}], 'format': {'tags': tags}}
print(json.dumps(data))
"""


FAKE_FFMPEG = r"""#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv[1:]
source = pathlib.Path(args[args.index('-i') + 1])
destination = pathlib.Path(args[-1])
tags = {}
for i, arg in enumerate(args):
    if arg == '-metadata':
        key, value = args[i + 1].split('=', 1)
        tags[key] = value
destination.write_bytes(b'TAGS:' + json.dumps(tags).encode() + b'\n' + source.read_bytes())
"""


class AiMediaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.sources = self.base / "outputs"
        self.archive = self.base / "generated"
        self.bin = self.base / "bin"
        self.sources.mkdir()
        self.archive.mkdir()
        self.bin.mkdir()
        for name, content in (("ffprobe", FAKE_FFPROBE), ("ffmpeg", FAKE_FFMPEG)):
            path = self.bin / name
            path.write_text(content)
            path.chmod(0o755)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "AI_MEDIA_ROOT": str(self.archive),
                "AI_MEDIA_ALLOWED_SOURCE_ROOTS": str(self.sources),
                "AI_MEDIA_OWNER_UID": str(os.getuid()),
                "AI_MEDIA_OWNER_GID": str(os.getgid()),
                "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            },
        )
        self.environment.start()
        self.image_validation = mock.patch.object(
            ai_media,
            "_validate_image",
            return_value={"type": "image", "format": "PNG", "width": 1, "height": 1},
        )
        self.image_validation.start()

    def tearDown(self) -> None:
        self.image_validation.stop()
        self.environment.stop()
        self.temp.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, dict, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = ai_media.main(list(arguments))
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1, stdout.getvalue())
        return exit_code, json.loads(lines[0]), stderr.getvalue()

    def archive_args(
        self,
        *sources: Path,
        model: str = "test-model",
        wangp_job_id: str = "wangp-upstream-job-123",
    ) -> list[str]:
        result = ["archive"]
        for source in sources:
            result.extend(("--source", str(source)))
        result.extend(
            (
                "--wangp-job-id",
                wangp_job_id,
                "--model",
                model,
                "--prompt",
                "full prompt & details",
                "--seed",
                "42",
                "--settings-json",
                '{"steps":8,"resolution":"1x1"}',
                "--title",
                "Test title",
            )
        )
        return result

    def test_multi_output_image_archive_and_xmp_provenance(self) -> None:
        first = self.sources / "one.png"
        second = self.sources / "two.png"
        first.write_bytes(b"image-one")
        second.write_bytes(b"image-two")

        arguments = self.archive_args(first, second) + ["--tag", "Project/Test"]
        code, result, error = self.run_cli(*arguments)

        self.assertEqual(code, 0, error)
        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        self.assertRegex(result["job_id"], ai_media.JOB_ID_RE)
        self.assertEqual(result["wangp_job_id"], "wangp-upstream-job-123")
        self.assertEqual(len(result["media"]), 2)
        self.assertEqual(
            result["tags"],
            ["AI Generated", "WanGP", "Model/test-model", "Project/Test"],
        )
        self.assertEqual(len({item["media_id"] for item in result["media"]}), 2)
        for item in result["media"]:
            media_path = Path(item["path"])
            sidecar = Path(item["sidecar_path"])
            self.assertTrue(media_path.is_file())
            self.assertTrue(sidecar.is_file())
            xmp = sidecar.read_text()
            self.assertIn(result["job_id"], xmp)
            self.assertIn("wangp-upstream-job-123", xmp)
            self.assertIn(item["media_id"], xmp)
            self.assertIn("test-model", xmp)
            self.assertIn("full prompt &amp; details", xmp)
            self.assertIn("Seed", xmp)
            self.assertIn("SettingsJSON", xmp)
            root = ai_media.ET.parse(sidecar).getroot()
            self.assertEqual(
                ai_media._xmp_tags(root),
                ["AI Generated", "WanGP", "Model/test-model", "Project/Test"],
            )

        code, duplicate, _ = self.run_cli(*arguments, "--tag", "Selected")
        self.assertEqual(code, 0)
        self.assertFalse(duplicate["created"])
        self.assertEqual(duplicate["job_id"], result["job_id"])
        self.assertEqual(duplicate["sidecars_updated"], 2)
        self.assertIn("Selected", duplicate["tags"])
        for item in duplicate["media"]:
            self.assertIn(
                "Selected",
                ai_media._xmp_tags(ai_media.ET.parse(item["sidecar_path"]).getroot()),
            )

    def test_backfill_tags_preserves_existing_tags_and_rating(self) -> None:
        image = self.sources / "existing.png"
        image.write_bytes(b"existing-image")
        _, archived, _ = self.run_cli(*self.archive_args(image), "--tag", "Daniel/Keep")
        sidecar = Path(archived["media"][0]["sidecar_path"])
        root = ai_media.ET.parse(sidecar).getroot()
        collection = root.find(
            f".//{{{ai_media.DIGIKAM_NS}}}TagsList/{{{ai_media.RDF_NS}}}Seq"
        )
        self.assertIsNotNone(collection)
        assert collection is not None
        for item in list(collection):
            if item.text != "Daniel/Keep":
                collection.remove(item)
        description = root.find(f".//{{{ai_media.RDF_NS}}}Description")
        self.assertIsNotNone(description)
        assert description is not None
        rating_name = "{http://ns.adobe.com/xap/1.0/}Rating"
        description.set(rating_name, "4")
        sidecar.write_bytes(
            ai_media.ET.tostring(root, encoding="utf-8", xml_declaration=True)
        )

        code, preview, error = self.run_cli("backfill-tags", "--dry-run")
        self.assertEqual(code, 0, error)
        self.assertEqual(preview["updated"], 1)
        self.assertEqual(
            ai_media._xmp_tags(ai_media.ET.parse(sidecar).getroot()), ["Daniel/Keep"]
        )

        code, result, error = self.run_cli("backfill-tags")
        self.assertEqual(code, 0, error)
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["updated"], 1)
        updated_root = ai_media.ET.parse(sidecar).getroot()
        self.assertEqual(
            ai_media._xmp_tags(updated_root),
            ["Daniel/Keep", "AI Generated", "WanGP", "Model/test-model"],
        )
        self.assertEqual(
            updated_root.find(f".//{{{ai_media.RDF_NS}}}Description").get(rating_name),
            "4",
        )

        code, repeated, error = self.run_cli("backfill-tags")
        self.assertEqual(code, 0, error)
        self.assertEqual(repeated["updated"], 0)
        self.assertEqual(repeated["unchanged"], 1)

    def test_video_archive_uses_visuals_and_exact_find(self) -> None:
        video = self.sources / "final.mp4"
        video.write_bytes(b"fake-video")
        code, archived, error = self.run_cli(*self.archive_args(video))
        self.assertEqual(code, 0, error)
        self.assertEqual(archived["category"], "visuals")
        media_id = archived["media"][0]["media_id"]

        code, found, error = self.run_cli("find", media_id)
        self.assertEqual(code, 0, error)
        self.assertEqual(found["id_type"], "media")
        self.assertEqual(found["job_id"], archived["job_id"])
        self.assertTrue(Path(found["sidecar_path"]).is_file())

        code, not_exact, error = self.run_cli("find", media_id[:-1])
        self.assertEqual(code, 2)
        self.assertFalse(not_exact["ok"])
        self.assertIn("invalid media ID", error)

    def test_music_archive_embeds_default_and_provenance_tags(self) -> None:
        audio = self.sources / "song.flac"
        audio.write_bytes(b"fake-audio")
        code, archived, error = self.run_cli(
            *self.archive_args(audio, model="ace-step")
        )
        self.assertEqual(code, 0, error)
        self.assertEqual(archived["category"], "music")
        item = archived["media"][0]
        self.assertIsNone(item["sidecar_path"])
        first_line = Path(item["path"]).read_bytes().splitlines()[0]
        tags = json.loads(first_line.removeprefix(b"TAGS:").decode())
        self.assertEqual(tags["artist"], "AI Generated")
        self.assertEqual(tags["title"], "Test title")
        self.assertRegex(tags["album"], r"^Generated \d{4}$")
        provenance = json.loads(tags["comment"])
        self.assertEqual(provenance["job_id"], archived["job_id"])
        self.assertEqual(provenance["wangp_job_id"], "wangp-upstream-job-123")
        self.assertEqual(provenance["model"], "ace-step")
        self.assertEqual(provenance["prompt"], "full prompt & details")
        self.assertEqual(provenance["settings"]["steps"], 8)

    def test_path_traversal_symlink_and_mixed_media_are_rejected(self) -> None:
        image = self.sources / "image.png"
        image.write_bytes(b"image")
        traversal = str(self.sources / "sub" / ".." / "image.png")
        code, result, error = self.run_cli(*self.archive_args(Path(traversal)))
        self.assertEqual(code, 2)
        self.assertFalse(result["ok"])
        self.assertIn("traversal", error)

        link = self.sources / "link.png"
        link.symlink_to(image)
        code, result, error = self.run_cli(*self.archive_args(link))
        self.assertEqual(code, 2)
        self.assertIn("symlink", error)

        audio = self.sources / "song.wav"
        audio.write_bytes(b"audio")
        code, result, error = self.run_cli(*self.archive_args(image, audio))
        self.assertEqual(code, 2)
        self.assertIn("cannot mix", error)

    def test_delete_media_removes_sidecar_and_delete_job_is_exact(self) -> None:
        first = self.sources / "one.png"
        second = self.sources / "two.png"
        first.write_bytes(b"one")
        second.write_bytes(b"two")
        _, archived, _ = self.run_cli(*self.archive_args(first, second))
        first_item, second_item = archived["media"]

        code, deleted, error = self.run_cli("delete", first_item["media_id"])
        self.assertEqual(code, 0, error)
        self.assertEqual(len(deleted["removed"]), 2)
        self.assertFalse(Path(first_item["path"]).exists())
        self.assertFalse(Path(first_item["sidecar_path"]).exists())
        self.assertTrue(Path(second_item["path"]).exists())

        code, found_job, error = self.run_cli("find", archived["job_id"])
        self.assertEqual(code, 0, error)
        self.assertEqual(found_job["media_paths"], [second_item["path"]])

        code, invalid, _ = self.run_cli("delete-job", archived["job_id"][:-1])
        self.assertEqual(code, 2)
        self.assertFalse(invalid["ok"])
        self.assertTrue(Path(second_item["path"]).exists())

        code, deleted_job, error = self.run_cli("delete-job", archived["job_id"])
        self.assertEqual(code, 0, error)
        self.assertTrue(deleted_job["sync_pending"])
        self.assertFalse(Path(found_job["path"]).exists())

    def test_failure_cleans_staging_and_preserves_json_error_contract(self) -> None:
        image = self.sources / "image.png"
        image.write_bytes(b"image")
        with mock.patch.object(
            ai_media, "_xmp_bytes", side_effect=RuntimeError("boom")
        ):
            code, result, error = self.run_cli(*self.archive_args(image))
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("unexpected failure", error)
        staging = self.archive / ".staging"
        self.assertEqual(list(staging.iterdir()), [])
        visuals = self.archive / "visuals"
        self.assertEqual(list(visuals.iterdir()), [])

    def test_not_found_has_distinct_safe_nonzero_exit(self) -> None:
        code, result, error = self.run_cli("find", "job-0123456789abcdef")
        self.assertEqual(code, 4)
        self.assertEqual(result["exit_code"], 4)
        self.assertIn("not found", error)

    def test_argument_errors_also_use_json_contract(self) -> None:
        code, result, error = self.run_cli("archive", "--source", "/tmp/nope")
        self.assertEqual(code, 2)
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("required", error)

    def test_upstream_job_id_distinguishes_identical_outputs(self) -> None:
        image = self.sources / "same.png"
        image.write_bytes(b"same-output")
        _, first, _ = self.run_cli(
            *self.archive_args(image, wangp_job_id="wan-job-one")
        )
        _, second, _ = self.run_cli(
            *self.archive_args(image, wangp_job_id="wan-job-two")
        )
        self.assertNotEqual(first["job_id"], second["job_id"])
        self.assertNotEqual(
            first["media"][0]["media_id"], second["media"][0]["media_id"]
        )


if __name__ == "__main__":
    unittest.main()
