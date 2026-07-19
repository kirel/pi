#!/usr/bin/env python3
"""Archive and address final WanGP media without a catalog or control files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm"}
AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}
JOB_ID_RE = re.compile(r"^job-[0-9a-f]{16}$")
MEDIA_ID_RE = re.compile(r"^media-[0-9a-f]{20}$")
XMP_META_NS = "adobe:ns:meta/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
DIGIKAM_NS = "http://www.digikam.org/"
AI_NS = "https://kirelabs.org/ns/ai-media/1.0/"
XML_NS = "http://www.w3.org/XML/1998/namespace"

for prefix, namespace in (
    ("x", XMP_META_NS),
    ("rdf", RDF_NS),
    ("dc", DC_NS),
    ("digiKam", DIGIKAM_NS),
    ("ai", AI_NS),
):
    ET.register_namespace(prefix, namespace)


class AiMediaError(Exception):
    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AiMediaError(message)


def _root() -> Path:
    return Path(os.environ.get("AI_MEDIA_ROOT", "/generated")).resolve()


def _source_roots() -> list[Path]:
    raw = os.environ.get(
        "AI_MEDIA_ALLOWED_SOURCE_ROOTS", "/workspace/outputs:/workspace/hermes_outputs"
    )
    roots = [Path(item).resolve() for item in raw.split(os.pathsep) if item]
    if not roots:
        raise AiMediaError("no allowed source roots are configured")
    return roots


def _category_root(category: str) -> Path:
    if category not in {"visuals", "music"}:
        raise AiMediaError(f"invalid archive category: {category}")
    return _root() / category


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_symlink_components(path: Path, root: Path) -> None:
    relative = path.relative_to(root)
    current = root
    if root.is_symlink():
        raise AiMediaError(f"allowed source root is a symlink: {root}")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise AiMediaError(f"source path contains a symlink: {current}")


def _safe_source(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise AiMediaError(f"source path must be absolute: {raw_path}")
    if ".." in candidate.parts:
        raise AiMediaError(f"source path traversal is not allowed: {raw_path}")
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, RuntimeError) as exc:
        raise AiMediaError(f"source does not exist: {raw_path}") from exc
    matching_root = next(
        (root for root in _source_roots() if _is_relative_to(resolved, root)), None
    )
    if matching_root is None:
        raise AiMediaError(f"source is outside allowed WanGP output roots: {raw_path}")
    _reject_symlink_components(candidate, matching_root)
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode):
        raise AiMediaError(f"source is not a regular file: {raw_path}")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_json(command: list[str], label: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=60
        )
    except FileNotFoundError as exc:
        raise AiMediaError(f"required runtime binary is missing: {command[0]}") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise AiMediaError(f"{label} failed: {detail.strip()}") from exc
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AiMediaError(f"{label} returned invalid JSON") from exc


def _probe(path: Path) -> dict[str, Any]:
    return _run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        "ffprobe",
    )


def _validate_image(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise AiMediaError("Pillow is required to validate image archives") from exc
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format or ""
    except Exception as exc:
        raise AiMediaError(f"image validation failed for {path}: {exc}") from exc
    if width < 1 or height < 1:
        raise AiMediaError(f"image has invalid dimensions: {path}")
    return {"type": "image", "format": image_format, "width": width, "height": height}


def _validate_media(path: Path) -> tuple[str, str, dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "visuals", "image", _validate_image(path)
    if suffix not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
        raise AiMediaError(f"unsupported media extension: {suffix or '<none>'}")
    probe = _probe(path)
    streams = probe.get("streams", [])
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    if suffix in VIDEO_EXTENSIONS:
        if not has_video:
            raise AiMediaError(
                f"file extension indicates video but no video stream exists: {path}"
            )
        return "visuals", "video", probe
    if not has_audio:
        raise AiMediaError(
            f"file extension indicates audio but no audio stream exists: {path}"
        )
    if has_video:
        raise AiMediaError(
            f"music archive source unexpectedly contains a video stream: {path}"
        )
    return "music", "audio", probe


def _parse_settings(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AiMediaError(f"--settings-json is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise AiMediaError("--settings-json must contain a JSON object")
    return value


def _stable_job_id(
    category: str,
    wangp_job_id: str,
    model: str,
    prompt: str,
    seed: int,
    settings: dict[str, Any],
    hashes: list[str],
) -> str:
    canonical = json.dumps(
        {
            "category": category,
            "wangp_job_id": wangp_job_id,
            "model": model,
            "prompt": prompt,
            "seed": seed,
            "settings": settings,
            "source_sha256": hashes,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "job-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _validate_wangp_job_id(value: str) -> str:
    if not value or len(value) > 256 or any(ord(character) < 32 for character in value):
        raise AiMediaError(
            "--wangp-job-id must be a nonempty identifier without control characters"
        )
    return value


def _media_id(job_id: str, source_hash: str, index: int) -> str:
    digest = hashlib.sha256(f"{job_id}\0{index}\0{source_hash}".encode()).hexdigest()
    return "media-" + digest[:20]


def _validate_tag(value: str) -> str:
    tag = value.strip()
    if not tag or len(tag) > 256 or any(ord(character) < 32 for character in tag):
        raise AiMediaError(
            "tags must be nonempty, at most 256 characters, and contain no control characters"
        )
    return tag


def _visual_tags(model: str, explicit_tags: list[str]) -> list[str]:
    model_name = _validate_tag(model).replace("/", "-").replace("\\", "-")
    tags = ["AI Generated", "WanGP", f"Model/{model_name}"]
    tags.extend(_validate_tag(tag) for tag in explicit_tags)
    return list(dict.fromkeys(tags))


def _add_tag_list(description: ET.Element, tags: list[str]) -> None:
    tag_list = ET.SubElement(description, f"{{{DIGIKAM_NS}}}TagsList")
    sequence = ET.SubElement(tag_list, f"{{{RDF_NS}}}Seq")
    for tag in tags:
        ET.SubElement(sequence, f"{{{RDF_NS}}}li").text = tag


def _xmp_bytes(provenance: dict[str, Any], tags: list[str]) -> bytes:
    root = ET.Element(f"{{{XMP_META_NS}}}xmpmeta")
    rdf = ET.SubElement(root, f"{{{RDF_NS}}}RDF")
    description = ET.SubElement(
        rdf,
        f"{{{RDF_NS}}}Description",
        {f"{{{RDF_NS}}}about": ""},
    )
    fields = {
        "JobID": provenance["job_id"],
        "WanGPJobID": provenance["wangp_job_id"],
        "MediaID": provenance["media_id"],
        "Model": provenance["model"],
        "Prompt": provenance["prompt"],
        "Seed": str(provenance["seed"]),
        "SettingsJSON": json.dumps(
            provenance["settings"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "SourceSHA256": provenance["source_sha256"],
        "ArchiveSHA256": provenance["archive_sha256"],
        "ArchivedAt": provenance["archived_at"],
    }
    for name, value in fields.items():
        ET.SubElement(description, f"{{{AI_NS}}}{name}").text = value
    title = ET.SubElement(description, f"{{{DC_NS}}}title")
    alt = ET.SubElement(title, f"{{{RDF_NS}}}Alt")
    ET.SubElement(
        alt,
        f"{{{RDF_NS}}}li",
        {f"{{{XML_NS}}}lang": "x-default"},
    ).text = provenance["title"]
    _add_tag_list(description, tags)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _replace_bytes(path: Path, data: bytes) -> None:
    current = path.stat(follow_symlinks=False)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(current.st_mode), follow_symlinks=False)
        os.chown(temporary, current.st_uid, current.st_gid, follow_symlinks=False)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _xmp_description(root: ET.Element) -> ET.Element:
    description = root.find(f".//{{{RDF_NS}}}Description")
    if description is None:
        raise AiMediaError("XMP sidecar has no rdf:Description")
    return description


def _xmp_tags(root: ET.Element) -> list[str]:
    return [
        item.text.strip()
        for item in root.findall(f".//{{{DIGIKAM_NS}}}TagsList//{{{RDF_NS}}}li")
        if item.text and item.text.strip()
    ]


def _merge_xmp_tags(
    sidecar: Path, required_tags: list[str], *, dry_run: bool = False
) -> bool:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise AiMediaError(f"refusing unsafe XMP sidecar: {sidecar}", 5)
    try:
        root = ET.parse(sidecar).getroot()
    except ET.ParseError as exc:
        raise AiMediaError(f"invalid XMP sidecar {sidecar}: {exc}") from exc
    existing = _xmp_tags(root)
    missing = [tag for tag in required_tags if tag not in existing]
    if not missing:
        return False

    description = _xmp_description(root)
    tag_list = description.find(f"{{{DIGIKAM_NS}}}TagsList")
    if tag_list is None:
        _add_tag_list(description, required_tags)
    else:
        collection = next(
            (
                child
                for child in tag_list
                if child.tag in {f"{{{RDF_NS}}}Seq", f"{{{RDF_NS}}}Bag"}
            ),
            None,
        )
        if collection is None:
            raise AiMediaError(f"unsupported XMP TagsList encoding in {sidecar}")
        for tag in missing:
            ET.SubElement(collection, f"{{{RDF_NS}}}li").text = tag

    if not dry_run:
        _replace_bytes(
            sidecar, ET.tostring(root, encoding="utf-8", xml_declaration=True)
        )
    return True


def _tag_audio(source: Path, destination: Path, provenance: dict[str, Any]) -> None:
    compact_provenance = json.dumps(
        {
            "job_id": provenance["job_id"],
            "wangp_job_id": provenance["wangp_job_id"],
            "media_id": provenance["media_id"],
            "model": provenance["model"],
            "prompt": provenance["prompt"],
            "seed": provenance["seed"],
            "settings": provenance["settings"],
            "source_sha256": provenance["source_sha256"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-c",
        "copy",
        "-map_metadata",
        "0",
        "-metadata",
        "artist=AI Generated",
        "-metadata",
        f"album=Generated {datetime.now(timezone.utc).year}",
        "-metadata",
        f"title={provenance['title']}",
        "-metadata",
        f"grouping={provenance['job_id']}",
        "-metadata",
        f"comment={compact_provenance}",
        str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise AiMediaError("ffmpeg is required to embed music provenance") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise AiMediaError(f"audio tagging failed: {detail.strip()}") from exc

    tags = {
        str(k).lower(): str(v)
        for k, v in _probe(destination).get("format", {}).get("tags", {}).items()
    }
    if (
        tags.get("artist") != "AI Generated"
        or not tags.get("title")
        or not tags.get("album")
    ):
        raise AiMediaError(
            f"audio container did not retain required tags: {destination.suffix}"
        )
    embedded: dict[str, Any] | None = None
    for key in ("comment", "description"):
        try:
            candidate = json.loads(tags.get(key, ""))
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            embedded = candidate
            break
    if not embedded or any(
        embedded.get(key) != provenance[key]
        for key in (
            "job_id",
            "wangp_job_id",
            "media_id",
            "model",
            "prompt",
            "seed",
            "settings",
            "source_sha256",
        )
    ):
        raise AiMediaError(
            f"audio container did not retain provenance tags: {destination.suffix}"
        )


def _set_owner_mode(path: Path, mode: int) -> None:
    os.chmod(path, mode, follow_symlinks=False)
    uid = int(os.environ.get("AI_MEDIA_OWNER_UID", os.getuid()))
    gid = int(os.environ.get("AI_MEDIA_OWNER_GID", os.getgid()))
    try:
        os.chown(path, uid, gid, follow_symlinks=False)
    except PermissionError as exc:
        raise AiMediaError(f"cannot set archive ownership on {path}") from exc


def _existing_job_result(
    job_dir: Path, expected: list[dict[str, Any]], visual_tags: list[str]
) -> dict[str, Any]:
    media = []
    sidecars_updated = 0
    for item in expected:
        path = job_dir / item["filename"]
        if not path.is_file() or path.is_symlink():
            raise AiMediaError(f"archive job collision at {job_dir}", 5)
        sidecar = Path(str(path) + ".xmp")
        if item["media_type"] != "audio" and (
            not sidecar.is_file() or sidecar.is_symlink()
        ):
            raise AiMediaError(
                f"archive job collision has missing XMP sidecar: {path}", 5
            )
        if item["media_type"] != "audio" and _merge_xmp_tags(sidecar, visual_tags):
            sidecars_updated += 1
        media.append(
            {
                "media_id": item["media_id"],
                "media_type": item["media_type"],
                "path": str(path),
                "sidecar_path": str(sidecar) if sidecar.exists() else None,
                "sha256": _sha256(path),
            }
        )
    return {"created": False, "media": media, "sidecars_updated": sidecars_updated}


def archive(args: argparse.Namespace) -> dict[str, Any]:
    if not args.source:
        raise AiMediaError("archive requires at least one --source")
    sources = [_safe_source(item) for item in args.source]
    if len(set(sources)) != len(sources):
        raise AiMediaError("the same source cannot be archived twice in one job")
    inspected = [_validate_media(path) for path in sources]
    categories = {item[0] for item in inspected}
    if len(categories) != 1:
        raise AiMediaError("one archive invocation cannot mix visual and music outputs")
    category = categories.pop()
    if category == "music" and args.tag:
        raise AiMediaError("--tag is currently supported for visual archives only")
    wangp_job_id = _validate_wangp_job_id(args.wangp_job_id)
    settings = _parse_settings(args.settings_json)
    visual_tags = _visual_tags(args.model, args.tag) if category == "visuals" else []
    source_hashes = [_sha256(path) for path in sources]
    job_id = _stable_job_id(
        category,
        wangp_job_id,
        args.model,
        args.prompt,
        args.seed,
        settings,
        source_hashes,
    )
    expected: list[dict[str, Any]] = []
    for index, (source, source_hash, inspection) in enumerate(
        zip(sources, source_hashes, inspected, strict=True), start=1
    ):
        media_id = _media_id(job_id, source_hash, index)
        expected.append(
            {
                "source": source,
                "source_sha256": source_hash,
                "media_id": media_id,
                "media_type": inspection[1],
                "probe": inspection[2],
                "filename": media_id + source.suffix.lower(),
            }
        )

    destination = _category_root(category) / job_id
    if destination.exists():
        existing = _existing_job_result(destination, expected, visual_tags)
        return {
            "ok": True,
            "command": "archive",
            "job_id": job_id,
            "wangp_job_id": wangp_job_id,
            "category": category,
            "tags": visual_tags,
            **existing,
        }

    staging_root = _root() / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    _category_root(category).mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{job_id}-", dir=staging_root))
    archived_at = datetime.now(timezone.utc).isoformat()
    try:
        staged_media: list[dict[str, Any]] = []
        for index, item in enumerate(expected, start=1):
            output = stage / item["filename"]
            title = args.title or f"AI Generated {job_id}"
            if len(expected) > 1:
                title = f"{title} (variant {index})"
            provenance = {
                "job_id": job_id,
                "wangp_job_id": wangp_job_id,
                "media_id": item["media_id"],
                "model": args.model,
                "prompt": args.prompt,
                "seed": args.seed,
                "settings": settings,
                "source_sha256": item["source_sha256"],
                "archive_sha256": "",
                "archived_at": archived_at,
                "title": title,
            }
            if item["media_type"] == "audio":
                _tag_audio(item["source"], output, provenance)
            else:
                shutil.copyfile(item["source"], output, follow_symlinks=False)
            _validate_media(output)
            provenance["archive_sha256"] = _sha256(output)
            _set_owner_mode(output, 0o664)
            sidecar: Path | None = None
            if item["media_type"] != "audio":
                sidecar = Path(str(output) + ".xmp")
                _write_bytes(sidecar, _xmp_bytes(provenance, visual_tags))
                _set_owner_mode(sidecar, 0o664)
            staged_media.append(
                {
                    "media_id": item["media_id"],
                    "media_type": item["media_type"],
                    "path": str(destination / output.name),
                    "sidecar_path": str(destination / sidecar.name)
                    if sidecar
                    else None,
                    "sha256": provenance["archive_sha256"],
                }
            )
        _set_owner_mode(stage, 0o775)
        os.rename(stage, destination)
        return {
            "ok": True,
            "command": "archive",
            "job_id": job_id,
            "wangp_job_id": wangp_job_id,
            "category": category,
            "tags": visual_tags,
            "created": True,
            "media": staged_media,
        }
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _job_matches(job_id: str) -> list[Path]:
    if not JOB_ID_RE.fullmatch(job_id):
        raise AiMediaError(f"invalid job ID: {job_id}")
    matches = []
    for category in ("visuals", "music"):
        candidate = _category_root(category) / job_id
        if candidate.is_dir() and not candidate.is_symlink():
            matches.append(candidate)
    return matches


def _media_matches(media_id: str) -> list[Path]:
    if not MEDIA_ID_RE.fullmatch(media_id):
        raise AiMediaError(f"invalid media ID: {media_id}")
    matches: list[Path] = []
    for category in ("visuals", "music"):
        root = _category_root(category)
        if not root.exists():
            continue
        for job_dir in root.iterdir():
            if (
                not job_dir.is_dir()
                or job_dir.is_symlink()
                or not JOB_ID_RE.fullmatch(job_dir.name)
            ):
                continue
            for candidate in job_dir.glob(media_id + ".*"):
                if candidate.name.endswith(".xmp"):
                    continue
                if (
                    candidate.is_file()
                    and not candidate.is_symlink()
                    and candidate.stem == media_id
                ):
                    matches.append(candidate)
    return matches


def _require_one(matches: list[Path], identifier: str) -> Path:
    if not matches:
        raise AiMediaError(f"archive ID not found: {identifier}", 4)
    if len(matches) != 1:
        raise AiMediaError(f"archive ID is not unique: {identifier}", 5)
    return matches[0]


def find(args: argparse.Namespace) -> dict[str, Any]:
    if JOB_ID_RE.fullmatch(args.identifier):
        job = _require_one(_job_matches(args.identifier), args.identifier)
        files = sorted(
            str(path)
            for path in job.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and not path.name.endswith(".xmp")
        )
        return {
            "ok": True,
            "command": "find",
            "id": args.identifier,
            "id_type": "job",
            "path": str(job),
            "media_paths": files,
        }
    media = _require_one(_media_matches(args.identifier), args.identifier)
    sidecar = Path(str(media) + ".xmp")
    return {
        "ok": True,
        "command": "find",
        "id": args.identifier,
        "id_type": "media",
        "job_id": media.parent.name,
        "path": str(media),
        "sidecar_path": str(sidecar) if sidecar.is_file() else None,
    }


def delete(args: argparse.Namespace) -> dict[str, Any]:
    media = _require_one(_media_matches(args.media_id), args.media_id)
    sidecar = Path(str(media) + ".xmp")
    if sidecar.is_symlink() or (sidecar.exists() and not sidecar.is_file()):
        raise AiMediaError(f"refusing unsafe media sidecar: {sidecar}", 5)
    removed = [str(media)]
    media.unlink()
    if sidecar.is_file():
        removed.append(str(sidecar))
        sidecar.unlink()
    job_id = media.parent.name
    try:
        media.parent.rmdir()
    except OSError:
        pass
    return {
        "ok": True,
        "command": "delete",
        "media_id": args.media_id,
        "job_id": job_id,
        "removed": removed,
        "sync_pending": True,
    }


def delete_job(args: argparse.Namespace) -> dict[str, Any]:
    job = _require_one(_job_matches(args.job_id), args.job_id)
    for child in job.iterdir():
        if child.is_symlink() or not child.is_file():
            raise AiMediaError(
                f"refusing to delete job containing unexpected entry: {child}", 5
            )
    removed = [str(path) for path in sorted(job.iterdir())]
    shutil.rmtree(job)
    return {
        "ok": True,
        "command": "delete-job",
        "job_id": args.job_id,
        "removed": removed,
        "sync_pending": True,
    }


def backfill_tags(args: argparse.Namespace) -> dict[str, Any]:
    visual_root = _category_root("visuals")
    scanned = 0
    updated = 0
    unchanged = 0
    if visual_root.exists():
        for job_dir in sorted(visual_root.iterdir()):
            if (
                not job_dir.is_dir()
                or job_dir.is_symlink()
                or not JOB_ID_RE.fullmatch(job_dir.name)
            ):
                continue
            for sidecar in sorted(job_dir.glob("*.xmp")):
                if sidecar.is_symlink() or not sidecar.is_file():
                    raise AiMediaError(f"refusing unsafe XMP sidecar: {sidecar}", 5)
                media = sidecar.with_suffix("")
                if (
                    not media.is_file()
                    or media.is_symlink()
                    or not MEDIA_ID_RE.fullmatch(media.stem)
                ):
                    raise AiMediaError(
                        f"XMP sidecar has no safe archived media companion: {sidecar}",
                        5,
                    )
                try:
                    root = ET.parse(sidecar).getroot()
                except ET.ParseError as exc:
                    raise AiMediaError(f"invalid XMP sidecar {sidecar}: {exc}") from exc
                model = root.findtext(f".//{{{AI_NS}}}Model")
                if model is None:
                    raise AiMediaError(
                        f"XMP sidecar has no ai:Model provenance: {sidecar}"
                    )
                scanned += 1
                if _merge_xmp_tags(
                    sidecar, _visual_tags(model, []), dry_run=args.dry_run
                ):
                    updated += 1
                else:
                    unchanged += 1
    return {
        "ok": True,
        "command": "backfill-tags",
        "dry_run": args.dry_run,
        "scanned": scanned,
        "updated": updated,
        "unchanged": unchanged,
    }


def _parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="ai-media")
    subparsers = parser.add_subparsers(dest="command", required=True)

    archive_parser = subparsers.add_parser(
        "archive", help="archive final WanGP variants"
    )
    archive_parser.add_argument("--source", action="append", required=True)
    archive_parser.add_argument("--wangp-job-id", required=True)
    archive_parser.add_argument("--model", required=True)
    archive_parser.add_argument("--prompt", required=True)
    archive_parser.add_argument("--seed", required=True, type=int)
    archive_parser.add_argument("--settings-json", default="{}")
    archive_parser.add_argument("--title")
    archive_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="add an Immich XMP tag (visuals only)",
    )
    archive_parser.set_defaults(handler=archive)

    find_parser = subparsers.add_parser("find", help="find one exact media or job ID")
    find_parser.add_argument("identifier")
    find_parser.set_defaults(handler=find)

    delete_parser = subparsers.add_parser("delete", help="delete one exact media ID")
    delete_parser.add_argument("media_id")
    delete_parser.set_defaults(handler=delete)

    delete_job_parser = subparsers.add_parser(
        "delete-job", help="delete one exact job ID"
    )
    delete_job_parser.add_argument("job_id")
    delete_job_parser.set_defaults(handler=delete_job)

    backfill_parser = subparsers.add_parser(
        "backfill-tags",
        help="merge default Immich tags into existing visual XMP sidecars",
    )
    backfill_parser.add_argument("--dry-run", action="store_true")
    backfill_parser.set_defaults(handler=backfill_tags)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        result = args.handler(args)
        print(
            json.dumps(
                result, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
        )
        return 0
    except AiMediaError as exc:
        print(f"ai-media: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "exit_code": exc.exit_code},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return exc.exit_code
    except KeyboardInterrupt:
        print("ai-media: interrupted", file=sys.stderr)
        print('{"error":"interrupted","exit_code":130,"ok":false}')
        return 130
    except Exception as exc:
        print(f"ai-media: unexpected failure: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {"ok": False, "error": "unexpected internal failure", "exit_code": 1},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
