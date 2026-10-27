# Strata 0.2.2: offizielles CUDA-Image

Am 22. Oktober 2026 von Strata 0.2.1 / Engine 0.1.46 auf
[Strata 0.2.2](https://github.com/Niko1221/Strata/releases/tag/v0.2.2)
mit **Engine 0.1.47** aktualisiert.

Offizieller Tag: `ghcr.io/niko1221/strata:0.2.2-cuda13`.
Ansible pinnt den geprüften Digest
`sha256:17e96f76fb85ee47b445b38ebfe9e4190b96ebde522e109d40efa2f2404a4503`.
Die Build-Metadaten nennen CUDA 13.0, GPU-Vision und Architekturen 75/86/89/120.

Der Ansible-Diff enthielt ausschließlich den Image-Digest der drei vorhandenen
Strata-Profile. Aktiv bleibt IQ3_XXS auf den beiden RTX 3090. Der Launcher,
vorbereitete Modelldaten und die persistente Modellkonfiguration bleiben erhalten.
GPU2 wird nicht verwendet. Keine neuen GPU-Rollen oder Tuningparameter gesetzt.
Der Wechsel erfolgte bei `activity.in_flight=0`.

Für diesen Einsatz sind vor allem die Tool-Call-Erkennung und die
Fehlerbehandlung bei langen Prompts relevant. Upstreams beworbene
NVIDIA-Beschleunigung betrifft Gyro; daraus folgt kein vermessener Gewinn
für unser IQ3_XXS-Profil.

## Verifikation

- Live-Engine 0.1.47, Container `healthy`, keine OOM-Kills.
- Native Low-Reasoning-Anfrage korrekt mit `42` beantwortet.
- Beide echten HA-Agenten (`conversation.home_nano_ai_agent` und
  `conversation.local_hermes_hermes_local_ai_agent`) antworten korrekt mit `42`;
  jeweils eine frische Strata-Anfrage an Engine 0.1.47 nachgewiesen.
- Bildtest über HTTPS: roter Kreis, blaues Rechteck und grünes Dreieck korrekt;
  OCR exakt `4827`. Beide Tests bestanden.
- Dashboard/Health HTTP 200; Strata, Embedding, ASR und TTS `ready`.
- Docker-Freigabe nur für die beiden RTX 3090; Engine-Prozess weiterhin mit
  `CUDA_VISIBLE_DEVICES=0,1`. GPU2 bleibt ausgeschlossen.
- Persistente Modellkonfiguration per SHA256 unverändert:
  `285538011720f61546c7f0b55fd7821bf7ecbda3ec3b17a7978e0e6ff3468863`.
- Abschließender Ansible-Check: `changed=0`, `failed=0`.

Nachweise: [Update-Ergebnisse](../experiments/strata/update-022-results-2026-10-22/).
Kein Geschwindigkeitsbenchmark durchgeführt.
