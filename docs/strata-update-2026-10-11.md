# Strata-Update auf 0.1.43 ohne Benchmark

Strata wurde vom bisherigen Stand 0.1.42 auf die zum Updatebeginn neueste
stabile Version [0.1.43](https://github.com/Niko1221/Strata/releases/tag/v0.1.43)
aktualisiert. Engine und Build-Metadaten melden 0.1.43. Gepinnter Quellstand:
`7695859aa13afb248bdb4d36f9b2e95707db079d`.
Image: `kirelabs/strata:7695859aa13a-sm86-sm120-vision`.

Das bestehende Q3-IQ3_XXS-Profil mit Low Reasoning bleibt erhalten: beide
RTX 3090s, automatischer Layer-Split, mmap, 131072 Tokens Kontext, int8-KV,
GPU-Vision und 2-GiB-Gesprächscache mit vier Slots. Container-RAM und
MemorySwap bleiben jeweils 28 GiB. GPU2 wird nicht verwendet.
Das Dashboard bleibt unter [strata.kirelabs.org](https://strata.kirelabs.org)
erreichbar; seine Hostfreigabe und die Inferenzhost-Freigabe werden erhalten.

## Vorgehen

```bash
uv run ansible-playbook setup.yml --tags strata-build --limit ailab-ubuntu
# Vor dem Umschalten erneut activity.in_flight = 0 prüfen.
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu --check
```

Das neue Image wurde gebaut, während der bisherige Backend-Prozess weiterlief.
Vor dem Umschalten meldete der native Status `activity.in_flight=0`.
Syntaxcheck, Build und Deployment waren erfolgreich; der abschließende
Ansible-Check meldet `changed=0`, `failed=0`.
Es wurden nur kurze Funktionsprüfungen durchgeführt. Weder die bisherigen
Kontext-/Decode-Vergleiche noch das neue Upstream-Benchmark-Werkzeug wurden
ausgeführt. Auch der neue optionale Benchmark am Ende von `setup.py` ist beim
bestehenden nichtinteraktiven `--yes`-Start ausgeschlossen.

## Ergebnis der Funktionsprüfungen

- Native Low-Reasoning-Anfrage: `42`, nichtleerer Denktext, Antwortende `stop`.
- Home Assistant und Local-Hermes-Assist: je eine korrekte Rechenantwort über
  eine frische Anfrage an Strata 0.1.43. Die geprüfte Hermes-Sitzung verwendet
  `home-hermes`, Reasoning Low und keine Werkzeugaufrufe.
- GPU-Vision: drei Formen/Farben erkannt; OCR liefert exakt `4827`.
- Embedding: 1024 endliche Werte. TTS liefert eine gültige WAV-Datei; ASR
  erkennt den Testsatz „Das ist ein kurzer Funktionstest.“.
- Dashboard, seine sechs direkt eingebundenen CSS-/JS-/SVG-Dateien sowie
  Health und Monitor-Daten antworten über HTTPS mit HTTP 200.
- `STRATA_ROUTE_TAIL_SKIP=7 is ON (default)` ist im Engine-Log bestätigt;
  tatsächlich übersprungene Experten werden protokolliert.
- Image, Quellstand und Build-Version stimmen mit dem Pin überein;
  `setup.py` und `serve/server.py` stimmen per SHA256 mit dem Checkout überein.
- Docker-Gerätefreigaben, Speicherlimits, geprüfte Konfigurationsfelder,
  Kontext/KV/Vision und Gesprächscache entsprechen dem Snapshot vor dem Update.
  Die native CUDA-Sicht bleibt `0,1`; Q3, ASR, TTS und Embedding sind gleichzeitig
  bereit. `oom=0`, `oom_kill=0`.

Es wurde kein Geschwindigkeitsgewinn gemessen und kein neuer vollständiger
HA-Aktionsqualitätstest durchgeführt. Die bisherigen Benchmark-Ergebnisse
bleiben unverändert als historische Messungen erhalten.

Rohdaten:
[`experiments/strata/update-0143-results-2026-10-11`](../experiments/strata/update-0143-results-2026-10-11).
