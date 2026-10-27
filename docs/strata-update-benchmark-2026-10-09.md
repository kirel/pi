# Strata 0.1.41: Update und Geschwindigkeitsvergleich

Am 9. Oktober wurde [Strata 0.1.41](https://github.com/Niko1221/Strata/releases/tag/v0.1.41) ausgerollt. Revision: `fb58e0dbc8399662c0e47c76578c6e878b14f6cf`, Image: `kirelabs/strata:fb58e0dbc839-sm86-sm120-vision`. Auf ausdrücklichen Wunsch bleibt diese Version aktiv.

Q3 IQ3_XXS bleibt auf beiden RTX 3090s mit Low Reasoning, automatischem Layer-Split, mmap, 131072 Kontexttokens, int8-KV, GPU-Vision, 4608 MiB Reserve je Karte und 2-GiB-Gesprächscache mit vier Slots. Containerlimit: 28 GiB ohne zusätzlichen Container-Swap. GPU2 wurde nicht für LLMs verwendet. Die neue Batch-/Peer-/Resident-Konfiguration wurde nicht aktiviert.

## Ergebnis

Die Hauptreihe zeigt kürzeren Prefill bei 4K und fast vollständig gecachten Wiederholungen. 16K bleibt praktisch gleich. 64K ist unter der neuen Version langsamer; die kühlere Gegenprobe bestätigt diese Richtung. Das Update bringt auf unserem Profil keinen allgemeinen Speedup.

| Messung | Prefill 0.1.40.3 | Prefill 0.1.41 | Zeitänderung | Sichtbare Antwort alt / neu |
| --- | ---: | ---: | ---: | ---: |
| 4K kalt | 22,11 s | 19,11 s | -13,55 % | 22,65 / 19,74 s |
| 16K kalt | 41,80 s | 41,87 s | 0,18 % | 42,30 / 42,54 s |
| 64K kalt | 135,76 s | 163,10 s | 20,14 % | 136,44 / 163,76 s |
| 16K warm, identische Wiederholung | 0,55 s | 0,41 s | -26,06 % | 1,11 / 0,85 s |

Jeweils Median aus drei Läufen. Negative Zeitänderung bedeutet schneller. Die warme Wiederholung nutzt 16.480 Tokens wieder und bildet keine beliebige neue Assist-Anfrage ab. Sichtbare Antwortlatenz enthält das Low-Reasoning.

| Decode nach Kontext | 0.1.40.3 | 0.1.41 | Änderung |
| --- | ---: | ---: | ---: |
| 4K | 49,80 tok/s | 51,60 tok/s | 3,61 % |
| 64K | 51,30 tok/s | 43,70 tok/s | -14,81 % |

Decode jeweils ein Lauf mit exakt 1024 Ausgabetokens und `length`-Ende. Der am Stream gemessene Durchsatz stimmt eng mit dem nativen Wert überein. Die kurzen Rechenantworten werden nicht als Decode-Benchmark verwendet.

## Kühlere 64K-Gegenprobe

Beide Versionen wurden frisch gestartet, Embedding, ASR und TTS geladen und identische Warmups ausgeführt. Vor jeder Anfrage kühlten beide Karten auf höchstens 55 °C ab. Danach lief derselbe kalte 64K-Prompt, jeweils einmal.

| Version | Prefill | Sichtbare Antwort | Start GPU0 / GPU1 |
| --- | ---: | ---: | ---: |
| 0.1.40.3 | 113,58 s | 114,34 s | 55 °C / 52 °C |
| 0.1.41 | 135,15 s | 135,95 s | 55 °C / 53 °C |

Die neue Version benötigt hier 18,99 % mehr Prefill-Zeit. In beiden Gegenproben wurde kein `sw_thermal_slowdown` aufgezeichnet. Die Zähler zeigen keine zusätzlichen Anfragen: jeweils 1 → 4 für drei eigene Requests. Die Peaks im gemessenen alten/neuen Lauf waren GPU0 85/81 °C und GPU1 76/80 °C. Die langsamere neue Version lässt sich daher nicht allein mit thermischer Drosselung erklären. Ein Sample je Version ist trotzdem kein Beleg für eine allgemeine Leistungsänderung.

## Ablauf und Grenzen

Je Version wurden 20 native Anfragen in der Hauptreihe geprüft: zwei Warmups, neun kalte Prefill-Läufe, zwei Decode-Läufe, ein Cache-Prime und drei warme Wiederholungen mit je einer anderen kurzen Anfrage dazwischen. Q3, Embedding, ASR und TTS waren gleichzeitig geladen. Low-Denktext war in allen 40 Hauptrequests vorhanden.

Beide Versionen verwendeten denselben Corpus, dieselben Seeds und Sampling-Parameter (Temperatur 0). Die Requests umgehen LiteLLM und dessen Antwortcache. Pro Messfenster muss der native Request-Zähler exakt um eins steigen; Promptlänge, Cache-Reuse und Antwortende müssen mit der Streaming-Antwort übereinstimmen. Alle 40 Hauptrequests bestanden diese Prüfungen. Kalt bedeutet kein KV-Prompt-Reuse, nicht einen kalten OS-Datei-/Expertencache.

Die alte Hauptreihe wurde vollständig vor der neuen gemessen; keine ABBA-Reihenfolge. Vor den Hauptrequests wurde auf höchstens 70 °C gewartet. Beide Versionen wurden unter langer Last thermisch gedrosselt (aufgezeichnete Peaks: GPU0 90 °C, GPU1 93 °C). Die alte Temperaturaufzeichnung begann erst während der Reihe; die neue deckt sie vollständig ab. Drosselungssamplezahlen sind deshalb nicht direkt vergleichbar.

Auf 0.1.41 zeigen die Gesamtzähler elf zusätzliche native Anfragen außerhalb der einzeln geprüften Hauptmessfenster. Ihre Herkunft wurde nicht zugeordnet. Die Hauptreihe ist deshalb kein vollständig isolierter Softwarevergleich. Die zusätzliche Gegenprobe hatte keine solchen Anfragen.

Die automatische Expertencache-Aufteilung änderte sich trotz identischer Einstellungen: insgesamt 20.297 → 20.245 MiB, primär 10.552 → 10.962 MiB; Slots 12.371 → 12.910. Das ist ein dokumentierter Laufzeitunterschied, keine belegte Erklärung für die Geschwindigkeit.

Das Release nennt 32–68 % höheren Multi-GPU-Gesamtdurchsatz bei mehreren gleichzeitigen Clients mit `--batch`. Unser Profil bedient eine Anfrage gleichzeitig und aktiviert diese Option nicht. Diese Release-Werte gelten daher nicht für unsere einzelne Assist-Anfrage.

## Deployment und Funktion

Zuerst `strata-build`, anschließend `strata-test --limit ailab-ubuntu`. Vor jedem Versionswechsel wurde `activity.in_flight == 0` geprüft. Für die Gegenprobe wurde die alte Revision nur vorübergehend per Ansible-Extra-Variable gesetzt; anschließend wurde 0.1.41 wiederhergestellt. Das alte Image bleibt erhalten. Der abschließende Ansible-Check hatte keine Änderungen.

Die finale Engine meldet 0.1.41. Docker-GPU-Zuordnung, Memory/MemorySwap und die geprüften Profilfelder stimmen mit dem alten Profil überein. `setup.py` und `serve/server.py` stimmen per SHA256 mit dem gepinnten Checkout überein.

- Alle Prefill-Rechentests liefern `42`; Decode erfüllt Länge und Format.
- Echte HA- und Local-Hermes-Assist-Routen bestehen jeweils zwei frische Rechenanfragen, anhand neuer nativer Strata-Requests überprüft.
- GPU-Vision erkennt Formen/Farben; OCR liefert `4827`.
- Embedding: 1024 endliche Werte. TTS: gültige WAV-Datei. ASR: synthetischer Testsatz erkannt.
- Abschließend sind Q3, Embedding, ASR und TTS gemeinsam bereit; `oom=0`, `oom_kill=0`.

Diese Funktionsproben ersetzen den früheren HA-Qualitätsbenchmark nicht. Geräteaktionen wurden nicht angefordert. Allgemeiner Qualitätsgewinn, Fehlaktionsrate und neuer Vergleich gegen Q2/27B wurden hier nicht gemessen. Gleichzeitig geladene Begleitdienste sind kein Benchmark gleichzeitiger ASR-/TTS-Verarbeitung.

## Rohdaten und Wiederholung

[Rohdaten und interaktiver Vergleich](../experiments/strata/update-0141-results-2026-10-09/): `old.jsonl`, `new.jsonl`, `confirm-*.jsonl`, `thermal-*.csv`, `summary.json`, `comparison.html` und finale Funktions-/Laufzeitproben. Die Summary enthält auch Minima und Maxima.

```bash
python3 experiments/strata/benchmark_update.py \
  --label LABEL --version VERSION \
  --corpus experiments/strata/reasoning-results-2026-10-06/prefill-corpus.json \
  --output /tmp/strata-LABEL.jsonl
# Gegenprobe: zusätzlich --confirm-only --cooling-limit-c 55
python3 experiments/strata/test_update_benchmark.py
python3 scripts/test_benchmark_flash_prefill.py
```
