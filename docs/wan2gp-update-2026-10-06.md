# Wan2GP update and MCP v2 migration, 2026-10-06

## Scope and deployed configuration

Work performed directly in the existing project root, without a worktree.
Unrelated tracked changes were compared against the initial diff and preserved.

- AI Lab: `daniel@ailab-ubuntu.lan`, container `wan2gp`.
- Upstream: `5e898b1ef15ed65910fb14f5f1f4a303957f2c60` →
  `ec9566a6593727a922e516fbd0919f9b9210c949` (runtime version 17.10, October 6).
- The new commit is pinned in `roles/wan2gp/defaults/main.yml`.
- MCP API v2, `--mcp-async`; trusted server-file reads retained for the existing
  dedicated SSH bridge and `/generated` archive workflow.
- Profile 5, SDPA, FP16, preload 0, reserved-memory fraction 0.2 retained.
- CUDA base 13.1.1, Python 3.11.14, PyTorch 2.10.0+cu130 retained.
- MMGP now comes from the upstream checkout rather than its old 3.7.12 package.
- Only GPU UUID `GPU-070fdafb-63c8-9e3e-635e-9c29ba36f82f` (RTX 5060 Ti)
  is exposed to WanGP. GPU0/1 were not used for these tests.
- LiteLLM server membership and key grants were unchanged; no Marian/Anna grant.

Deployment:

```sh
uv run ansible-playbook setup.yml --syntax-check
uv run ansible-playbook setup.yml --tags wan2gp --skip-tags syncthing-config --limit ailab_ubuntus
```

The skip avoids reconciling unrelated pending Syncthing configuration from this
dirty working tree. Archive mounts and existing synchronization remain in place.
The first run built the image; a second scoped run applied the user's subsequent
request for MCP v2. Both completed with `failed=0`, `unreachable=0`.

Before stopping WanGP, its process CPU time remained unchanged over repeated
samples, all threads waited, GPU use was only the resident context, no outputs
were recent, and logs showed discovery calls only. The old MCP API had no
list-queue tool. The idle service was stopped before replacing its bind-mounted
code, preventing mixed old-runtime/new-source jobs during the build.

## Hermes and transfer compatibility

The personal skill is a symlink to
`/home/daniel/projects/agent-skills/skills/daniel/wangp-media-generation/SKILL.md`
on `100.82.91.51`. Its existing uncommitted edits were preserved while updating
the primary workflow to v2 (`settings`, explicit `wait=false`, `wangp_session`
job actions), Gallery transfer instructions, and affected examples. The manual
Hermes configuration and Craft entry were not replaced. Historical reference
recipes remain; the main skill explains how to translate their v1 examples.
The directly linked `references/robust-mcporter-job-polling.md` was updated too.

The Codex skill validator rejects this existing Hermes skill's `author` and
`version` frontmatter extensions. They were preserved; YAML/frontmatter and
diff checks were performed separately.

Verified from the bare-metal Hermes host, using its existing restricted LiteLLM
credential resolved and consumed locally:

- All nine v2 tools and their schemas are discoverable through LiteLLM.
- `wangp_session(action="list_queue", arguments={})` succeeds.
- Native upload PUT and download GET round-trip 42,545 JPEG bytes with identical
  SHA-256; a second GET returns 404; lifetime is 600 seconds.
- Relative transfer URLs resolve against `http://192.168.50.10:7860`, not LiteLLM.
- The dedicated SSH key reaches `/workspace`; `ai-media` and both `/generated`
  archive directories remain available.

The gateway still held old v1 schemas. Its live control socket reported zero
active agents and no active work, checked again immediately before restarting
only `hermes-gateway.service` to refresh the tool catalog.
Afterward its actual schema cache contained all nine v2 tools, including
`wangp_generate.settings`; gateway state was running and Telegram connected.

## H3 history and comparison

H3 means **MiniMax H3**, confirmed in the August 4 T3 thread
`6ff8a784-fa08-49dd-abe1-9a5c8e7d80d6`.

Daniel's [upstream issue #2066](https://github.com/deepbeepmeep/Wan2GP/issues/2066)
reports playable FL2VA/Ref2VA outputs with unrelated content, while start-frame
I2V worked. The historical Python-wheel and CUDA-library failures are separate
from this semantic-conditioning problem.
[PR #2071](https://github.com/deepbeepmeep/Wan2GP/pull/2071) addresses INT8 embedding
dequantization and AWQ pre-quantization scales; it was still open/unmerged at
inspection. No local upstream model patch was added.

The original pruned-20B video and a historical PR-test output were recovered,
including embedded prompt and settings. Baseline: seed `32309735`, 832×480,
124 frames, 20 Euler steps, flow shift 12, NVFP4-AWQ text encoder, no input media.
Prompt: a cinematic jazz duo in a softly lit club, singer and pianist.
The original contact sheet shows unrelated anime characters outdoors; the
historical PR-test contact sheet shows a singer and pianist in a club.

One updated test was submitted through Hermes's LiteLLM route, job
`02397a493f494e83bdba4ee1ed839d0f`. Original prompt, seed and core settings were
retained, prompt enhancement disabled. Upstream now selects a rank8 INT8
checkpoint (`MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors`, 21,057,674,787
bytes), so this is an installation-level comparison, not an isolated code-only
or bit-identical checkpoint comparison. The new INT8 video VAE is
`minimax_h3_video_vae_int8_convrot.safetensors` (2,811,065,184 bytes), replacing
the old FP16 selection. Historical effective attention is not encoded in the
baseline metadata; the updated service uses the existing SDPA configuration.
ComfyUI's queue was verified empty
before releasing its resident model cache; its service was not stopped.

### Technical result

- One task completed successfully, zero failed tasks/errors; no reroll.
- 832×480, 124 frames, 24 fps, duration 5.166667 seconds.
- H.264 video plus two-channel AAC audio, 3,229,350 bytes.
- Full FFmpeg decode check succeeded.
- Embedded metadata records seed 32309735, 20 Euler steps, flow shift 12,
  NVFP4-AWQ configuration and the rank8 checkpoint.
- Embedded generation time: 243 seconds, excluding initial checkpoint download.
  This is not a controlled performance benchmark against the historical run.
- Existing Hermes JSONL/CSV attempt logger used; `ai-media` archive succeeded:
  `job-eb1d8841faa501e8` / `media-e28f004e18e9ef7451f8`.
- Archived path:
  `/generated/visuals/job-eb1d8841faa501e8/media-e28f004e18e9ef7451f8.mp4`.
- Archived file registered in Gallery and downloaded through v2 from Hermes;
  SHA-256 matches `7458a6e067292c8705420fba15457221c5d8e943e92a10c61224ccb44c93486c`.
- Final queue empty; container running with restart count zero.

### Visual assessment and limits

Sampled frames from the new clip show a singer at a microphone and a pianist
in a warmly lit club, with consistent composition. This clearly follows the
requested scene, unlike the unrelated anime scene in the original baseline.
The historical PR test already showed the intended scene too. The current
upstream installation therefore passes this recovered prompt-adherence
regression case without a local model-code patch.

This is one seed and one text-to-video prompt, with updated model weights/VAE.
It does not establish general aesthetic superiority, isolate a specific fix,
or validate Ref2VA, image-to-video, lip synchronization, or subjective audio
quality. Audio was technically validated, not perceptually scored.

Artifacts on the controller:

- `/home/daniel/artifacts/wan2gp-update-20261006/before.mp4`
- `/home/daniel/artifacts/wan2gp-update-20261006/after.mp4`
- `/home/daniel/artifacts/wan2gp-update-20261006/pr2071-historical.mp4`
- Matching `before.jpg`, `after.jpg`, `pr2071-historical.jpg` contact sheets.
- `baseline-settings.json`, `updated-request.json`, `updated-settings.json`,
  and `result.json` hold reproducibility/technical evidence.

### Observed v2 limitation

An unrelated Gallery upload performed while the generation was running appeared
in that job's `result.generated_files` alongside the actual generated MP4.
Only the MP4 matched the requested output filename and represented new output;
the uploaded baseline contact sheet was not archived as a new generation.
The skill now says to stage uploads before submission and distinguish actual
generated outputs from concurrently registered Gallery inputs. No upstream
patch or new issue was submitted.

## Rollback retained on AI Lab

- Stopped original container: `wan2gp-rollback-20261006`.
- Original image: `local/wan2gp:rollback-20261006`,
  `sha256:0a038edc439bad5835c0724d4d1119c3efa2d16053476404155260416e18fbe3`.
- Snapshot: `/home/daniel/wan2gp/rollback-20261006/` contains original source,
  local patch, Docker/entrypoint helpers, personal Hermes files, configuration,
  container inspection, and baseline settings. Checkpoints and generated archive
  are preserved in their existing directories.
- Skill backup on Hermes:
  `~/.hermes/backups/wan2gp-update-20261006/SKILL.md` and
  `robust-mcporter-job-polling.md`.

For an immediate rollback, first verify the new MCP queue is empty (or explicitly
resolve its jobs). Stop/remove only the new `wan2gp` container, restore the old
checkout and its backed-up runtime files, rename the retained original container
back to `wan2gp`, and start it. Restore the skill backup and refresh an idle Hermes
gateway. Do not overwrite later personal edits blindly. Revert this update's
Ansible hunks/pin before a later deployment; old upstream does not accept the new
MCP flags. No checkpoint or archive deletion is needed. The rollback was prepared,
not executed.

Immediate runtime rollback commands on AI Lab, **only after checking the queue**:

```sh
docker stop wan2gp
docker rm wan2gp
cd /home/daniel/wan2gp/app
git checkout --force 5e898b1ef15ed65910fb14f5f1f4a303957f2c60
tar -xzf ../rollback-20261006/local-files.tar.gz Dockerfile entrypoint.sh .dockerignore docker wgp_config.json
docker rename wan2gp-rollback-20261006 wan2gp
docker start wan2gp
```

The tar extraction deliberately does not overwrite personal Hermes inputs,
outputs, or helpers that may have changed since the backup. The retained old
container already contains the original command, mounts, GPU request and image.
