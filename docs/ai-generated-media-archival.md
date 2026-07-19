# AI-generated media archival

WanGP publishes every technically successful final output through `ai-media`
into two host-backed roots on AI Lab:

- `/home/daniel/wan2gp/generated/visuals`
- `/home/daniel/wan2gp/generated/music`

`/home/daniel/wan2gp/generated/.staging` and `.stversions` are deliberately
outside the two Syncthing folders. Previews, intermediates, failed outputs,
in-progress archives, and recoverable deletions therefore stay outside the
media sync.

On the NUC, the receiving paths are:

- `/tank/medien/Bilder/Generated` (mounted read-write in Immich at
  `/external/ai-generated`)
- `/tank/medien/Musik/Generated` (already below the Jellyfin/Navidrome music
  mount)

## Deployment and one-time live configuration

Ansible owns the two AI-media Syncthing folders through each instance's local
REST API. It resolves the already-paired peer by name, creates or updates only
the deterministic folder IDs `ai-generated-visuals` and
`ai-generated-music`, and leaves every other device and folder untouched.
Deploy the directory owners before the Syncthing configuration:

```bash
uv run ansible-playbook setup.yml \
  --tags storage,immich \
  --limit homelab

uv run ansible-playbook setup.yml \
  --tags wan2gp,syncthing \
  --limit ailab_ubuntus
```

Both folders use **Send & Receive** and enable Trash Can versioning with 30-day
cleanup on both peers. Syncthing versions only changes received from another
device: NUC versioning therefore protects Hermes deletions, while AI Lab
versioning protects Immich deletions. The NUC custom version paths are
`/Medien/.stversions/ai-generated/visuals` and
`/Medien/.stversions/ai-generated/music`. They resolve to
`/tank/medien/.stversions/ai-generated` on the same filesystem as the media,
but outside the Immich, Jellyfin, and Navidrome scan roots. AI Lab uses
`/home/daniel/wan2gp/generated/.stversions/visuals` and `music`, outside both
shared folders.

The inspected NUC configuration has only narrower `/Medien/comfy-output`,
`/Medien/Sync`, and `/Medien/yuzu/nand` folders, so neither new media root nor
`.stversions` overlaps an existing Syncthing folder. Do not later add
`/Medien` itself as a Syncthing folder without excluding `.stversions` and
reviewing all nested-folder overlap.

The only remaining UI configuration is Immich database state. In Immich,
create an external library using `/external/ai-generated`, assign its owner,
and scan it. Keep the library writable so intentional Immich UI deletions
propagate through Syncthing. Do not point Immich at `/tank/immich/library` for
these files.

Syncthing propagation and downstream library scans are asynchronous. A
successful `ai-media archive`, `delete`, or `delete-job` reports only the local
filesystem operation.

## CLI contract

Run `ai-media` inside the WanGP container. Every command prints exactly one JSON
object to stdout and sends human-readable failures to stderr.

```bash
ai-media archive \
  --source /workspace/outputs/final-1.png \
  --source /workspace/outputs/final-2.png \
  --wangp-job-id '<original WanGP job ID>' \
  --model krea2_turbo \
  --prompt 'full generation prompt' \
  --seed 12345 \
  --settings-json '{"resolution":"1024x1024","num_inference_steps":8}' \
  --title 'Optional library title' \
  --tag 'Project/Optional'

ai-media find media-0123456789abcdefabcd
ai-media find job-0123456789abcdef
ai-media delete media-0123456789abcdefabcd
ai-media delete-job job-0123456789abcdef
ai-media backfill-tags --dry-run
ai-media backfill-tags
```

Archive all technically successful final variants from one generation in one
`archive` invocation, including aesthetically rejected variants. Only corrupt
or failed outputs, previews, and intermediates are excluded.
Visual and music outputs cannot be mixed in one job. IDs are deterministic,
filesystem-safe, include the original WanGP job identity in their derivation,
and are present in directory/file names; lookup and deletion use exact IDs only.
Visual provenance is stored in adjacent XMP sidecars. Each new visual sidecar
also exposes Immich-compatible `XMP-digiKam:TagsList` values `AI Generated`,
`WanGP`, and `Model/<model>`; repeatable `--tag` arguments add deliberate
project or subject tags. Tags do not affect deterministic archive IDs, and a
repeated archive call merges missing tags into the existing sidecar.
`backfill-tags` performs the same additive merge for existing visual sidecars;
it preserves existing XML metadata such as Immich ratings and user-created
tags. Run its `--dry-run` form first.
After a one-time backfill has reached the NUC, run Immich's Sidecar `DISCOVER`
and `SYNC` admin jobs so already-imported assets are re-read. Normal external
library scans associate sidecars for newly archived media.

Music is stream-copied
through ffmpeg to add embedded Artist, Album, Title, archive/WanGP job IDs,
model, prompt, seed, settings, and source-hash provenance without transcoding.

The existing Hermes JSONL/CSV generation log remains the attempt telemetry
source. The archive does not create a second log, manifest, database, watcher,
queue, control file, or tombstone state.
