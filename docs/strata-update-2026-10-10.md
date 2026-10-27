# Strata-Update auf 0.1.42 mit Expert Tail Skip

Am 10. Oktober wurde Strata von 0.1.41 auf die zum Updatezeitpunkt neueste
stabile Version [0.1.42](https://github.com/Niko1221/Strata/releases/tag/v0.1.42)
aktualisiert. Gepinnter Quellstand:
`61b3fb5dd3f1e8ec09cf7e4e05208bc6d3c46406`.
Das laufende Image heißt `kirelabs/strata:61b3fb5dd3f1-sm86-sm120-vision`.
Engine und Build-Metadaten melden 0.1.42; `setup.py` und `serve/server.py`
stimmen per SHA256 mit dem gepinnten Checkout überein.

Wie gewünscht bleibt das neue Expert Tail Skip aktiv. Das native Engine-Log
bestätigt `STRATA_ROUTE_TAIL_SKIP=7 is ON (default)` und protokolliert bereits
tatsächlich übersprungene Experten. Ein expliziter Abschaltparameter wurde
nicht gesetzt. Die Option überspringt unter bestimmten Bedingungen fehlende
Experten ab Routing-Rang 7 während der Decode-Verifikation; Antworten können
dadurch gegenüber 0.1.41 abweichen. Das ist eine andere Funktion als die
Tail-/Message-Boundary-Checkpoints des früheren Gesprächscache-Tests.

Das bestehende Q3-IQ3_XXS-Low-Profil bleibt erhalten: beide RTX 3090s in
derselben UUID-Reihenfolge, automatischer Layer-Split, mmap, 131072 Tokens
Kontext, int8-KV, GPU-Vision, 4608 MiB VRAM-Reserve je GPU und
2-GiB-Gesprächscache mit vier Slots. Container-RAM und MemorySwap bleiben
jeweils 28 GiB; GPU2 wird nicht verwendet. Docker-Gerätefreigaben und die
geprüften Konfigurationsfelder stimmen mit dem Snapshot vor dem Update überein.

## Deployment

```bash
uv run ansible-playbook setup.yml --tags strata-build --limit ailab-ubuntu
# Vor dem Umschalten: activity.in_flight = 0.
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu --check
```

Der Build erfolgte während das alte Modell weiterlief. Syntaxcheck, Build und
Deployment waren erfolgreich; der abschließende Check meldet `changed=0`,
`failed=0`. Das vorherige Image und sein Checkout bleiben verfügbar.

## Funktionstests

- Native Low-Reasoning-Anfrage: `42`, nichtleerer Denktext, Antwortende `stop`.
- Echte HA- und Local-Hermes-Assist-Routen: jeweils zwei korrekte Rechentests.
  Jede Antwort wurde einer frischen Anfrage an Strata 0.1.42 zugeordnet.
  Die geprüfte Hermes-Sitzung verwendet `home-hermes`, Reasoning Low und
  keine Werkzeugaufrufe.
- GPU-Vision erkennt die drei Formen/Farben; OCR liefert exakt `4827`.
- Embedding: 1024 endliche Werte; TTS: gültige WAV-Datei mit 2,24 Sekunden.
- ASR erkennt den TTS-Testsatz „Das ist ein kurzer Funktionstest.“.
- Q3, Embedding, ASR und TTS sind gleichzeitig bereit; kein Container-OOM.

Die warmen Assist-Folgeanfragen benötigten in diesen Einzeltests 3,59 s
(HA) und 15,49 s (Local Hermes); die ersten Anfragen 30,53 beziehungsweise
54,89 s. Diese Zeiten sind keine kontrollierte Messung des Versionsunterschieds.

Dies sind Funktionstests. Ein neuer kontrollierter Geschwindigkeitsvergleich
oder ein vollständiger HA-Aktionsqualitätstest wurde bei diesem Update nicht
durchgeführt. Die bisherigen Messungen mit 0.1.41 bleiben als historische
Ergebnisse erhalten.

Rohdaten:
[`experiments/strata/update-0142-results-2026-10-10`](../experiments/strata/update-0142-results-2026-10-10).

## Dashboard unter strata.kirelabs.org

Die eingebaute Strata-Weboberfläche mit Chat, Monitor und Einstellungen ist
unter [strata.kirelabs.org](https://strata.kirelabs.org) erreichbar. Der Eintrag
`services.strata` in `group_vars/all/services.yml` veröffentlicht das bestehende
Q3-Profil über LlamaSwap: Caddy ergänzt den konfigurierten `upstream_path`
vor der ursprünglichen URI, einschließlich Query-String. Die Oberfläche kann
ihre Dateien und API-Endpunkte dadurch direkt unter der neuen Domain laden.
Die Domain ist ausdrücklich in `STRATA_ALLOWED_HOSTS` zugelassen; die
bestehende Freigabe des Inferenzhosts bleibt erhalten.

Caddy und beide Pi-hole-Instanzen wurden ausgerollt. Auf beiden DNS-Servern
zeigt der CNAME auf `homelab-nuc.lan` beziehungsweise `192.168.50.5`.
Der Zugriff verwendet HTTPS und die bestehende Beschränkung auf LAN/Tailscale.
Die Homepage enthält unter „AI“ den statischen Strata-Link. Ihr neuer
`homepage-config`-Tag rendert die Konfiguration und startet den bestehenden
Container neu, ohne dabei ein neues Homepage-Image zu ziehen.

```bash
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu
uv run ansible-playbook setup.yml --tags caddy,homepage-config --limit homelab
uv run ansible-playbook setup.yml --tags pihole --limit nameserver,homelab -e pihole_pull_policy=never
```

Die Hostfreigabe erforderte einen Neustart; davor war `activity.in_flight=0`.
Danach bestanden eine native Low-Anfrage und eine gestreamte Low-Chat-Anfrage
mit `Origin: https://strata.kirelabs.org` (jeweils `42` und Denktext).
Fremde Origins erhalten weiterhin HTTP 403. Die sechs direkt eingebundenen
CSS-/JS-/SVG-Dateien, Health und Monitor-Daten liefern HTTP 200, auch mit
Query-String. ASR, TTS und Embedding wurden erneut geprüft und stehen zusammen
mit Q3 bereit. Die sieben Katalogtests und der Ansible-Syntaxcheck bestehen.
Die vorhandenen Tests wurden dabei an den bereits entfernten
`hermes-local-webui`-Eintrag angepasst.
Der abschließende Check für `strata-test,caddy,homepage-config` meldet auf
beiden Hosts `changed=0`, `failed=0`. Q3 bleibt auf beiden 3090s mit
2-GiB-/Vier-Slot-Gesprächscache und aktivem Expert Tail Skip; kein Container-OOM.

Eine visuelle Browserprüfung war nicht möglich: Der T3-Browser meldet fehlende
Systembibliotheken; der alternative `agent-browser` ist auf diesem Controller
nicht installiert. Die genannten Prüfungen erfolgten über HTTP und die API.
Rohdaten liegen unter
[`experiments/strata/dashboard-results-2026-10-10`](../experiments/strata/dashboard-results-2026-10-10).
