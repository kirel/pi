# Strata 0.2.1: offizielles Docker-Image

Am 20. Oktober 2026 vom lokalen Build `kirelabs/strata:3d1fb48090e8-sm86-sm120-vision`
(Engine 0.1.45.3) auf das offizielle Image
[`ghcr.io/niko1221/strata:0.2.1-cuda13`](https://github.com/Niko1221/Strata/blob/v0.2.1.3/docs/DOCKER.md)
umgestellt. Ansible pinnt dessen Digest:
`sha256:a0398afb7a60253f1442ec149326aa7d80e0137e9f1ffe304bb0e84a6939ee8e`.
Das tatsächlich ausgelieferte CUDA-Image enthält **Engine 0.1.46**;
die nachträglichen Terminal-Hotfix-Tags 0.2.1.1–0.2.1.3 sind keine
abweichenden Versionsnummern dieser CUDA-Engine.

## Betrieb

Ansible zieht das fertige Image; Git-Checkout, eigener Dockerfile und lokaler
CUDA-Build entfallen. Der bereits begonnene Quellbuild wurde beendet.
`--tags strata-build` bereitet weiterhin nur Image und Launcher vor;
`--tags strata-test` rendert zusätzlich LlamaSwap und aktiviert Änderungen.

Der kleine LlamaSwap-Launcher startet den unveränderten API-Server und die
Engine aus dem offiziellen Paket. Die vorgelagerte interaktive Terminal-
Einrichtung wird für unsere bereits vorbereiteten Profile nicht benötigt.
Er prüft die Engine-Komponente mit Upstreams Integritätsprüfung und passt
Engine-, Bibliotheks-, Vision- und Expert-Profile-Pfade im temporären
`/tmp/strata-runtime.json` an. Die bestehende native Konfiguration, GGUFs,
Packs und MTP-Dateien bleiben erhalten. Fehlende Profile werden ausdrücklich
gemeldet; neue Modelle müssen vor ihrer Nutzung vorbereitet werden.

Die bestehende Auswahl der beiden RTX 3090 per UUID, Layer-Split auto,
131072 Kontext, int8-KV, mmap, GPU-Vision, 4608 MiB VRAM-Reserve,
28 GiB RAM-Limit und 2-GiB-Gesprächscache mit vier Slots bleiben erhalten.
`adapt-every` bleibt beim Standard 4. GPU2 wird nicht verwendet.

## Task board

Das [Task board aus den Release Notes](https://github.com/Niko1221/Strata/releases/tag/v0.2.1)
ist eine Ansicht in der Strata-Desktop-App für geplante Aufgaben und
wiederkehrende Läufe, laufende Jobs, ausstehende Freigaben und Fehler.
Es gehört zur Agentenoberfläche und wird für unseren Inferenzserver hinter
LlamaSwap, Home Assistant und Hermes nicht benötigt.

## Verifikation

- Wechsel jeweils bei `activity.in_flight=0`; offizieller Container `healthy`,
  Engine 0.1.46 und ausschließlich die beiden 3090-UUIDs nachgewiesen.
- Native Low-Reasoning-Anfrage: Antwort `42`, regulärer Abschluss `stop`.
- Beide echten HA-Agenten (`conversation.home_nano_ai_agent` und
  `conversation.local_hermes_hermes_local_ai_agent`) antworteten mit `42`;
  jeweils frische Backend-Anfrage an Engine 0.1.46 nachgewiesen.
- Vision über die öffentliche HTTPS-Adresse: alle drei Farben/Formen korrekt,
  OCR exakt `4827`, beide Prüfungen bestanden.
- Dashboard und Health HTTP 200; Strata, Embedding, ASR und TTS `ready`.
- Keine OOMs/OOM-Kills. SHA256 der persistenten Konfiguration unverändert:
  `285538011720f61546c7f0b55fd7821bf7ecbda3ec3b17a7978e0e6ff3468863`.
- Launcher-Test prüft Komponentenpfade, GPU-Reihenfolge, Vision,
  Cache-Optionen und Erhalt der Quelldatei; Shell-Syntaxprüfung bestanden.
- Abschließender Ansible-Check: `changed=0`, `failed=0`.


Nachweise: [Update-Ergebnisse](../experiments/strata/update-0213-results-2026-10-20/).
Kein Geschwindigkeitsbenchmark durchgeführt.
