# Strata-Update auf 0.1.40.3

Am 7. Oktober wurde Strata von 0.1.40.1 auf die zum Updatezeitpunkt neueste
stabile Version [0.1.40.3](https://github.com/Niko1221/Strata/releases/tag/v0.1.40.3)
aktualisiert. Gepinnter Quellstand:
`d5ea7133741e67743c0e886bb426c0ce8d69cf6c`.
Das laufende Image heißt `kirelabs/strata:d5ea7133741e-sm86-sm120-vision`;
Engine und Build-Metadaten melden 0.1.40.3. `setup.py` und `serve/server.py`
stimmen per SHA256 mit dem gepinnten Checkout überein.

Q3 IQ3_XXS läuft weiter auf beiden RTX 3090s mit Low Reasoning, mmap,
131072 Tokens Kontext, GPU-Vision, 4608 MiB VRAM-Reserve je GPU und dem
2-GiB-Gesprächscache mit vier Slots. Das Containerlimit bleibt 28 GiB,
zusätzlicher Container-Swap ist ausgeschlossen. GPU2 wird nicht verwendet.
Tail-/Message-Boundary-Optionen wurden nicht zusätzlich aktiviert.

## Deployment und Rückweg

Das Image wurde zuerst gebaut, während das alte Modell weiterlief:

```bash
uv run ansible-playbook setup.yml --tags strata-build --limit ailab-ubuntu
# Vor dem Umschalten: /v1/status meldete activity.in_flight = 0.
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu --check
```

Build und Deployment waren erfolgreich; der abschließende Check hatte keine
Änderungen. Der neue Tag `strata-build` trennt die Vorbereitung vom Rendern
der LlamaSwap-Konfiguration und ihrem Neustart. Das vorherige Image und sein
Checkout bleiben erhalten. Für einen Rückweg den Revisionspin auf
`82f46a8c8f475f001ad76d92f58f4a4f8ffb0253` setzen und `strata-test` deployen.

## Funktionstests

- Native Textantwort mit Low Reasoning: korrekt, reguläres Antwortende.
- Echte HA- und Local-Hermes-Assist-Routen: jeweils zwei korrekte Rechentests;
  frische Strata-Anfragen anhand der nativen Request-Metadaten nachgewiesen.
  Die geprüfte Hermes-Sitzung verwendet `home-hermes`, Reasoning Low und keine Tools.
- GPU-Vision: drei Formen/Farben korrekt erkannt, OCR liefert `4827`.
- Embedding: 1024 endliche Werte; TTS: gültige WAV-Datei; ASR: Testsatz korrekt erkannt.
- Q3, Embedding, ASR und TTS abschließend gleichzeitig bereit; kein Container-OOM.

Nach dem Laden der Begleitdienste dauerten die abschließenden Assist-Aufrufe
3,57 s (HA) und 9,57 s (Hermes). Die ersten Aufrufe mit kaltem Kontext lagen
bei 32,57 beziehungsweise 43,09 s. Das sind einzelne Funktionstests, kein
kontrollierter Geschwindigkeitsvergleich mit 0.1.40.1.

Der RAM-Snapshot zeigt rund 28 GiB gesamten Containerverbrauch, davon etwa
22,6 GiB regulären Dateicache und 5,4 GiB anonymen Speicher, Shared Memory
und Kernel-Speicher. Dateicache ist rückgewinnbar; die 28 GiB sind keine
permanente private RAM-Reservierung. Auf dem Host waren rund 25,6 GiB
verfügbar. Die Container-Speichergrenze wurde beim Befüllen des Caches erreicht,
ohne OOM oder OOM-Abschuss.

Die Rohdaten liegen unter
[`experiments/strata/update-01403-results-2026-10-07`](../experiments/strata/update-01403-results-2026-10-07).
Der frühere Cache-Benchmark bleibt unverändert als Messung von 0.1.40.1 erhalten.
