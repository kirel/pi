# Strata 0.2.0-beta: Update des LlamaSwap-Backends

Am 19. Oktober 2026 von 0.1.45 auf den Release
[0.2.0-beta](https://github.com/Niko1221/Strata/releases/tag/v0.2.0-beta)
aktualisiert. Die separate Engine-Version ist **0.1.45.3**.
Quellstand: `3d1fb48090e8f2cefc22d7b5845fb7f5b71f33fa`.
Image: `kirelabs/strata:3d1fb48090e8-sm86-sm120-vision`.

## Docker-Kompatibilität

Der neue Upstream-Dockerfile verwendet ein anderes Terminal-/Komponentenlayout.
Der vorhandene LlamaSwap-Launcher benötigt dagegen `/opt/strata/.venv`,
`setup.py`, `engine/` und die bestehenden nativen Konfigurationen.
`roles/llm_inference/files/strata-Dockerfile` übernimmt deshalb das serverseitige
Buildlayout des Upstream-Releases 0.1.45 für den neuen Quellstand. Die weggefallene
alte Entrypoint-Datei wird nicht mehr benötigt; die separaten Build-Abhängigkeiten
werden explizit installiert. Ansible verwaltet diesen Dockerfile und baut auch
bei dessen Änderung neu. Engine- und Serverquellcode bleiben ungepatcht.

Das Image wurde bei weiterlaufendem altem Backend gebaut. Vor dem Wechsel
meldete Strata `in_flight=0`. Der geprüfte LlamaSwap-Diff enthielt ausschließlich
die Image-Tags der Strata-Profile. Deployment und anschließender Check waren
erfolgreich (`changed=0`, `failed=0` im Check).

## Verifiziert

- Build-Metadaten und Engine: 0.1.45.3, Architekturen 86/120, GPU-Vision;
  Engine-Quellhash entspricht dem Build.
- Live-Chat über `https://strata.kirelabs.org`: Low Reasoning, Antwort `42`,
  Abschluss `stop`.
- Vision: roter Kreis, blaues Rechteck, grünes Dreieck korrekt beschrieben;
  OCR exakt `4827`.
- Dashboard und Health: HTTP 200; Docker `healthy`, keine OOMs/OOM-Kills.
- Native Modellkonfiguration unverändert per SHA256
  `285538011720f61546c7f0b55fd7821bf7ecbda3ec3b17a7978e0e6ff3468863`.
  Docker-GPU-Freigaben unverändert auf beiden 3090s; GPU2 nicht verwendet.
- `adapt-every` bleibt beim Standardwert 4. Kontext 131072, int8-KV,
  mmap, GPU-Vision und 2-GiB-Gesprächscache bleiben erhalten.
- Das Engine-Log bestätigt die neun neuen sm_86-Performance-Schalter und
  weiterhin `STRATA_ROUTE_TAIL_SKIP=7`.
- Strata, Embedding, ASR und TTS nach dem Wechsel gleichzeitig `ready`.

Kein Benchmark: Ein Geschwindigkeitsgewinn auf den beiden 3090s wurde nicht
vermessen. Der Release trägt weiterhin die Bezeichnung Beta. Die neuen
Desktop-/Terminal-Oberflächen wurden nicht separat ausgerollt.

Nachweise: [Update-Ergebnisse](../experiments/strata/update-020-beta-results-2026-10-19/).

Die echten HA-Agenten `conversation.home_nano_ai_agent` und
`conversation.local_hermes_hermes_local_ai_agent` antworteten beide korrekt mit
`42`. Für beide wurde eine frische Anfrage an Strata 0.1.45.3 nachgewiesen
(`client-checks.jsonl`). Es wurden keine Geräteaktionen ausgelöst.
