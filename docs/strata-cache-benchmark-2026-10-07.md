# Strata 0.1.40.1: Cachevergleich auf zwei RTX 3090

Am 7. Oktober 2026 ist Strata **0.1.40.1** über Ansible aktualisiert und für
`home-ha` / `home-hermes` mit **Q3 Low** in Betrieb. Die neuen Optionen
`--prompt-cache-tail` und `STRATA_CACHE_MESSAGE_BOUNDARY=1` verkürzen den
verbleibenden Prefill dieses Profils nicht: Beide schließen den verwendeten
Layer-Split ausdrücklich aus. Der bestehende 2048-MiB-/Vier-Slot-Cache bleibt
aktiv; die zusätzlichen Test-Schalter sind nach dem Benchmark entfernt.

## Update und Betriebsprüfung

- Gepinnter Quellstand: `82f46a8c8f475f001ad76d92f58f4a4f8ffb0253`;
  Image `kirelabs/strata:82f46a8c8f47-sm86-sm120-vision`.
- Der Hotfix betrifft den Python-Server. Die native Engine meldet weiterhin
  **0.1.40**, wie im [Release 0.1.40.1](https://github.com/Niko1221/Strata/releases/tag/v0.1.40.1)
  vorgesehen. Die SHA256-Werte der laufenden `frontend.py` / `server.py`
  stimmen mit dem gepinnten Release überein.
- Zwei RTX 3090, Layer-Split `auto`, Kontext 131072, Low-RAM `mmap`,
  28 GiB Containerlimit und die bisherigen VRAM-Reserven bleiben erhalten.
  GPU2 wird nicht für Inferenz oder Benchmark verwendet.
- Deployment: `uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu`.
  Der Nachcheck meldet `changed=0`; Syntaxprüfung bestanden.
- Wegen der von Upstream neu geschriebenen Git-Historie liegen gepinnte
  Checkouts jetzt getrennt nach Revision. Der alte Checkout und das alte
  Image wurden erhalten; kein Hard-Reset angewandt.
- 31 mitgelieferte Regressionstests zu Tool-Aufrufen im Reasoning und
  wartenden Anfragen bei Neustarts bestanden. Sie verwenden Mock-Engines.
- Bildtest mit Formen und OCR (`4827`) bestanden. Embedding liefert 1024
  endliche Werte; TTS erzeugt ein WAV, ASR erkennt dessen synthetischen Satz
  korrekt. Nach dem letzten Neustart liefern beide echten HA-Agenten jeweils
  fünf korrekte Rechenantworten mit nachgewiesen frischen Strata-Aufrufen.
- In den 45 zugehörigen Hermes-Testsessions: `home-hermes`, Reasoning
  aktiviert mit `effort=low`, **0 Tool-Aufrufe**. Der Benchmark enthält keine
  Geräteaktionen als Testfälle.

## Warum die neuen Optionen hier nicht greifen

Der [Tail-Checkpoint](https://github.com/Niko1221/Strata/blob/v0.1.40.1/docs/PROMPT_CACHE_TAIL.md)
liegt an einer ohnehin erreichten Chunk-Grenze nahe dem Promptende.
Der [Message-Boundary-Checkpoint](https://github.com/Niko1221/Strata/blob/v0.1.40.1/docs/MESSAGE_BOUNDARY_CACHE.md)
liegt vor der letzten kurzen Nachricht und kann zusätzliche Chunk-Grenzen
setzen. Beide Selektoren verlangen im Release `!multi_gpu`.
Die Dokumentation schließt **Layer-Split** aus; die Anzahl physischer Karten
allein ist dabei nicht das Kriterium, etwa bei einem Haupt-GPU-/Helper-Aufbau.
Dieser Benchmark verwendet das bestehende Layer-Split-Profil.

Die positiven Testarme haben beide Schalter tatsächlich an den Engine-Prozess
übergeben: `--prompt-cache-tail` vorhanden, Environment-Wert `1`,
`CUDA_VISIBLE_DEVICES=0,1`, `--layer-split auto`. Die Kontrollarme haben
Flag und Environment-Wert ausgeschaltet. Das ist eine überprüfte Negativkontrolle
auf der produktiven Architektur, kein Geschwindigkeitstest der Features auf
einer unterstützten Architektur.

## Native lange Verläufe

Reihenfolge **aus → an → an → aus**, je sechs warme Beobachtungen pro
Kontextlänge und Einstellung. Gleiche synthetische Zahlenverläufe bei 16K/32K,
wechselnde letzte Rechenfrage, dazwischen eine separate kurze Anfrage.
Die Blockkennung im Systemtext unterscheidet die Blöcke. Native Requests
umgehen LiteLLM, verwenden Temperatur 0, `reasoning_effort=low`, aktiviertes
Thinking und höchstens 256 Ausgabetokens. Jeder Block startet den Container
neu; kalte Prime-Anfragen werden separat aufgezeichnet.

Alle Zeitangaben sind Mediane; pro Zelle **aus / an**. Die erste sichtbare
Antwort schließt verborgenes Reasoning ein. Native Promptzeit umfasst auch
Arbeit beim Wiederherstellen des Caches; sie ist keine isolierte Token-GEMM-Zeit.

| Verlauf | Native Promptzeit | Erste sichtbare Antwort | Wiederverwendete Tokens | Neu gelesene Tokens |
| --- | ---: | ---: | ---: | ---: |
| 16K | 3,91 / 5,62 s | 4,25 / 5,92 s | 16384 / 16384 | 97–98 / 97–98 |
| 32K | 5,53 / 5,43 s | 5,76 / 5,64 s | 32768 / 32768 | 97–98 / 97–98 |

Beide Einstellungen verwenden exakt denselben Umfang des Präfixes wieder.
Die Zeitdifferenzen zeigen keinen zusätzlichen Cache-Checkpoint. Eine kausale
Geschwindigkeitsänderung durch diese Schalter lässt sich daraus nicht ableiten;
der Code überspringt beide zusätzlichen Checkpoints beim Layer-Split.

## Echte Home-Assistant-Wege

Der erste Clientdurchlauf enthielt zehn HA-Anfragen mit Antworten aus dem
LiteLLM-Redis-Antwortcache, ohne neuen Strata-Aufruf. Ihre ausgelesenen nativen
Timings gehörten zur vorherigen Anfrage und dürfen nicht dieser HA-Antwort
zugeschrieben werden. Die ursprünglichen Daten sind erhalten, diese Werte
werden für die folgende Tabelle nicht verwendet. Zehn passende Cache-Hits
sind auch im read-only aggregierten LiteLLM-Spend-Log nachgewiesen.

Der Clientvergleich wurde vollständig in derselben ABBA-Reihenfolge wiederholt:
**40 Rechenanfragen**, darunter je acht warme Beobachtungen pro Agent und
Einstellung. Unterschiedliche Blockkennungen in der neuen Benutzernachricht
verhindern Wiederverwendung identischer vollständiger Antworten. Ein Vorher-/
Nachher-Vergleich des nativen Request-Zeitstempels erzwingt einen neuen
Strata-Aufruf für jede Messung. Der Runner fügt für spätere Wiederholungen
zusätzlich einen Zeitstempel an die Kennung an. Frühere Nachrichten des
jeweiligen Gesprächs werden dabei nicht geändert.

Mediane, pro Zelle **aus / an**; Gesamtzeit ab HA-REST-Aufruf bis Antwort.
Die ASR-/TTS-Latenz ist in dieser Tabelle nicht enthalten.

| Weg | Gesamte Antwortzeit | Native Promptzeit | Neu gelesene Tokens |
| --- | ---: | ---: | ---: |
| HA → LiteLLM → Strata | 2,46 / 2,83 s | 1,37 / 1,43 s | 68–71 / 68–71 |
| HA → Local Hermes → LiteLLM → Strata | 11,36 / 11,35 s | 10,48 / 10,45 s | 927–1120 / 927–1120 |

Local Hermes bleibt in allen warmen Beobachtungen bei **16384 wiederverwendeten
Tokens**. Beide Einstellungen verarbeiten pro Folgefrage exakt 927, 991,
1057 und 1120 Tokens neu. Der wesentliche Zeitanteil bleibt deren Verarbeitung.
Die neuen Schalter lösen diesen Engpass auf dem aktuellen Profil nicht.

## Fehler und Grenzen

Ein 16K-Folgefall mit ausgeschalteten neuen Optionen beantwortet **20 + 22 mit
44 statt 42**, nach einer separaten Zwischenanfrage. Das trat im abgebrochenen
letzten Block und bei der vollständigen Wiederholung desselben Blocks erneut
auf. Beide Fehler sind erhalten. Beim ersten Fehler fehlen Timing und
Reasoningtext, weil der ursprüngliche Runner vor dem Speichern auf Korrektheit
prüfte. Der Runner speichert falsche Antworten nun als solche und beendet
damit nicht mehr den ganzen Latenzvergleich.

Der Vergleich enthält 96 Antworten des vollständigen ersten Experiments,
40 Antworten des bereinigten Clientvergleichs sowie drei zusätzliche Resultate
des unterbrochenen Blocks: **137 von 139 Rechenantworten korrekt**, beide Fehler
betreffen denselben langen synthetischen Folgefall. Das ist kein allgemeiner
HA-Qualitätsscore. Es wurde kein passender Qualitätsvergleich gegen 0.1.39
oder 27B durchgeführt; die Ursache des Fehlers ist damit offen.
Die Zeitmediane enthalten alle normal beendeten Antworten, auch die falsche
Antwort des vollständigen Durchlaufs.

Die Temperaturen lagen bei GPU0 bei 81–90 °C und GPU1 bei 71–91 °C.
Ein Snapshot meldet Software-Thermal-Slowdown auf GPU0. GPU-Temperatur,
Expert-/Dateicache und unterschiedliche Kennungen begrenzen die Aussagekraft
kleiner Zeitdifferenzen. Kein aufgezeichneter Ressourcencheck meldet OOM
oder OOM-Kill. Es wurden keine Power-Limits verändert.

## Daten und Wiederholung

[Methodik](../experiments/strata/cache-results-2026-10-07/method.json),
[Zusammenfassung](../experiments/strata/cache-results-2026-10-07/summary.json),
[native/originale Clientdaten](../experiments/strata/cache-results-2026-10-07/observations.jsonl),
[bereinigte Clientdaten](../experiments/strata/cache-results-2026-10-07/ha-isolated/observations.jsonl),
[unterbrochener Block](../experiments/strata/cache-results-2026-10-07/interrupted-3-off.jsonl),
[erster Fehler](../experiments/strata/cache-results-2026-10-07/failed-observation.json),
[Antwortcache-Nachweis](../experiments/strata/cache-results-2026-10-07/response-cache-evidence.json).

Der [Runner](../experiments/strata/benchmark_cache_01401.py) nutzt die bestehende
Fixture und speichert das native Config-Backup auf dem GPU-Host mit Modus 0600.
Er stellt im `finally` die ursprüngliche Config wieder her und startet Q3 neu.
Für einen neuen Versuch ein unbenutztes Ausgabeverzeichnis wählen:

```sh
python3 experiments/strata/test_cache_config.py
python3 experiments/strata/benchmark_cache_01401.py \
  --corpus experiments/strata/reasoning-results-2026-10-06/prefill-corpus.json \
  --output /tmp/strata-cache-neuer-versuch
```

`--ha-only` wiederholt nur die Clientwege; `--blocks 3` ergänzt einen
unterbrochenen letzten Block. Gemischte/anlaufende Clientdaten erst nach
Prüfung frischer Backend-Aufrufe auswerten. Die Alltagseinstellungen sind
Q3 Low, Vision aktiv, native Gesprächscaches aktiv und beide neuen
Zusatz-Checkpoint-Schalter aus.
