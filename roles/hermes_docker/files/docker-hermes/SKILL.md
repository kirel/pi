---
name: docker-hermes
description: Install or update tools and dependencies in the managed Docker Hermes environment. Use when setting up projects, choosing persistent paths, encountering command-not-found, missing Python modules, permission or PATH problems, or repairing tools after a container update. Applies to Docker Hermes, not the bare-metal agent.
---

# Docker Hermes environment

You run as the unprivileged Hermes user. Install tools needed for the user's task
yourself using the package managers below; no sudo or runtime apt is needed.

## Choose the package manager

- Native CLIs: `brew install <formula>`. Homebrew lives at
  `/home/linuxbrew/.linuxbrew` in your own persistent mount.
- Python CLIs: `uv tool install <package>`; `uvx <package>` for a temporary run.
  Installed tools live under `/opt/data/.local`.
- Python projects: use `uv init`, `uv add <package>`, `uv run` inside the project.
  For an existing venv: `uv pip install --python .venv/bin/python <package>`.
  For standalone scripts use `uv run --no-project --with <package> python script.py`.
  Do not run project commands from `/opt/hermes`: uv would discover Hermes's own
  pyproject and try to install it. Set the terminal workdir to your project.
- JavaScript projects: local `npm install`; standalone CLIs: `npm install -g`.
  The global npm prefix is `/opt/data/npm-global`.

For scanned PDFs, `brew install ocrmypdf tesseract-lang` supplies OCR with German
language data, but brings a sizeable dependency tree. For image OCR alone,
`brew install tesseract tesseract-lang` is sufficient.
`brew install poppler` supplies `pdftotext` and `pdftoppm`.
Check `tesseract --list-langs`; OCR to a new output file, preserving the source.
Prefer existing text extraction first and Vision for ambiguous pages or layouts.

## Paths and runtime boundaries

- Keep projects and durable outputs under `/opt/data`; scratch files go under
  `/opt/data/cache/scratch` and may be cleaned. `/tmp` is disposable.
- Brew, uv tools and npm globals survive container replacement. They are private
  to this agent; other agents' installations do not affect yours.
- `/opt/hermes/.venv` belongs to the Hermes runtime. Do not install application
  packages there, modify Hermes PM environments, or change the Hermes launcher
  to solve project dependencies. Use a project venv instead.
- Login shells can use a different Python from the gateway. Diagnose with
  `command -v python`, `python -c 'import sys; print(sys.executable)'`,
  `command -v brew` and `uv tool list`; use explicit project interpreters.
- Brew bins are appended to PATH so they do not replace the runtime's tools.
  If a system command shadows a desired Brew version, invoke it through
  `/home/linuxbrew/.linuxbrew/bin/<command>` or a project-scoped PATH.
  Do not globally prepend Brew's Python or run `brew shellenv` in startup files.

## Updates and failures

Verify a new tool with a small real operation, not just its installation status.
Brew auto-update/cleanup are disabled to avoid unrelated upgrades during a task.
If formula metadata is stale, run `brew update` then retry the requested install.
Upgrade only the needed formula with `brew upgrade <formula>`; broad maintenance
is separate work. Brew installs consume disk space; inspect `df -h` and
`du -sh /home/linuxbrew/.linuxbrew` if installation fails for lack of space.

Image updates do not update your persistent tools. After a base OS/Python change,
check the affected command and repair/reinstall only what fails. A `Brewfile`
from `brew bundle dump --file=/opt/data/Brewfile --force` records desired formulae
for recovery, not exact versions or a backup of installed packages.

For publishing an app, use the existing `caddy-proxy` skill and `hermes-service`.
