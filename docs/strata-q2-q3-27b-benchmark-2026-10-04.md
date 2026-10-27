# Strata Q2 und Q3 gegen Qwen3.8 27B mit vLLM

Gemessen am 4. Oktober 2026 auf `ailab-ubuntu`. Der Vergleich umfasst
Flash-Next mit Strata IQ2_XS, Flash-Next mit Strata IQ3_XXS und den aktuellen
Qwen3.8 27B mit vLLM. Q2 wird ausschließlich mit Strata getestet.
Alle drei nutzen nur die beiden RTX 3090. Embedding, ASR und TTS bleiben geladen.
Die RTX 5060 Ti wird diesem Test nicht zugewiesen.

**Q3 passt auf zwei 3090 bis 128K und erreicht den höchsten HA-Aufgabenwert: 92/104. Q2 ist bei langen Eingaben deutlich schneller, versucht aber häufiger ungewollte Änderungen.** Ein vollständiger Ersatz des 27B-Standards ist damit nicht ausreichend begründet. Q2 ist vor allem ein Kandidat für lange Textkontexte; Q3 ist ein interessanter Kandidat für konkrete HA-Aufgaben mit warmem Präfix. Beide brauchen weitere Prüfung im tatsächlichen Agentenweg.

In dieser Suite sind die unerwünschten Änderungsversuche **12/104 bei Q2, 4/104 bei Q3 und 1/104 bei 27B**. Alle drei machen Fehler bei Gesprächsfortsetzungen. 27B erfindet dafür zweimal einen unbekannten Batteriestand und setzt mehrere klare zusammengesetzte Aufträge nicht um. Die Empfehlung berücksichtigt diese Unterschiede, nicht nur den Gesamtwert. Aktuelle Produktionsrouten bleiben auf 27B/vLLM.

## Getestete Profile

| Profil | Modell und Backend | Kontext | KV und Ausführung |
| --- | --- | ---: | --- |
| Strata Q2 | ISTA-DASLab Flash-Next GSQ-RCO IQ2_XS, Engine 0.1.38 | 131072 | INT8 KV, mmap-Experten, MTP 4, zwei GPUs |
| Strata Q3 | derselbe Flash-Next, GSQ-RCO IQ3_XXS, Engine 0.1.38 | 131072 | INT8 KV, mmap-Experten, MTP 4, zwei GPUs |
| 27B vLLM | Frozenlock Qwen3.8-27B-int4-AutoRound, vLLM 0.27.1 | 262144 | FP8 E4M3 KV, TP2, kein MTP, maximal drei Sequenzen |

Strata ist auf Commit `99f3dbd0b21d1401b3769e0c0d963913607f380b` gepinnt;
das unveränderte Upstream-Dockerfile wurde mit BuildKit für CUDA 86/120 gebaut.
Die zwei Testcontainer sehen ausschließlich die beiden 3090. Vision und die
experimentelle Speed-Projektion sind ausgeschaltet. Beide nutzen
`--prefill auto`, Kontext 131072, `--vram-reserve-mib 4608`, 28 GiB
Container-RAM und keinen zusätzlichen Container-Swap. Der Host hat einen
i5-12500 und 46,9 GiB nutzbaren RAM, Treiber 590.48.01 und 250 W pro 3090.

27B behält sein Produktionsprofil: GPU-Speicherbudget 0,755, Chunked Prefill,
8192 Tokens Scheduler-Budget, Long-Prefill-Schwelle 4096, Prefix Cache,
Qwen-Toolparser und deaktivierter Custom All-Reduce. Kein gleichzeitiger
LLM-Benchmark und keine zusätzlichen Audio-Testanfragen während der Messungen.
Thinking ist bei allen Requests ausgeschaltet.

## Qualität bei Home Assistant Anfragen

52 verschiedene, synthetische deutsche Szenarien laufen mit zwei festen Seeds:
104 Beobachtungen je Modell. Die beiden Wiederholungen derselben Aufgabe sind
korreliert. Das sind HA-nahe Anfragen, keine aufgezeichneten Haushaltsgespräche.
Die 46 Tool-Schemas stammen vom tatsächlich konfigurierten offiziellen
HA-MCP-Server. Alle Tool-Aufrufe werden lokal simuliert; es werden keine
realen Geräte geschaltet. Der tatsächliche Hermes-Agent und seine Tool-Suche
werden nicht durchlaufen.

Der deutsche Systemprompt übernimmt die bestehenden Regeln für kurze Antworten,
Zustandsabfragen, Rückfragen und das Abbrechen reiner Geräuscheingaben. Die
Tools sind direkt sichtbar. Jeder Fall startet mit einem frischen Haushalt:
Lampen, Rollos, Lautsprecher, Fenster, Temperatur- und Batteriesensoren,
Personen und Wetter. Auswahl nach Namen, Alias, Entity-ID, Bereich, Domain
und Geräteklasse folgt dem gelesenen HA-Quellcode. Antworten haben die Form von
GetLiveContext; Helligkeit wird mit 0–255 und Lautstärke mit 0–1 dargestellt.
Erfolgreiche Aktionen aktualisieren den nächsten simulierten Zustand.

Ein Fall besteht nur, wenn die gewünschten Zustände erreicht bzw. bereits
erfüllt sind, keine zusätzliche Änderung versucht wurde, die Abschlussantwort
korrekt ist und bei Geräuschen kein Tool aufgerufen wird. Seriell ausgeführte
Aktionen und zusätzliche erlaubte Leseaufrufe sind zulässig. „Helligkeit 0“
gilt als Ausschalten; positive Helligkeit erfüllt einen reinen Einschaltauftrag.
Eine korrekt gemeldete fehlgeschlagene Geräteaktion kann bestehen. Bloße
Erfolgsbehauptungen ohne erforderlichen Tool-Aufruf bestehen nicht.

Die strukturierten Aktionsbelege werden automatisch geprüft. Die freien
Antworten bewertet derselbe Codex-Assistant, der die Suite erstellt hat,
gegen die gespeicherten Rubriken; diese Bewertung ist nicht blind und nicht
unabhängig. Zusätzlich zählt ein Verstoß gegen den vorgegebenen Sprachstil,
etwa Emojis. Der Gesamtwert ist deshalb ein Aufgabenwert für diese Suite und
kein isolierter Intelligenz- oder Quantisierungs-Score.

Sampling ist explizit identisch angefordert: Temperatur 0,7, top-p 0,8,
top-k 20, min-p 0, Presence-Penalty 1,5, Frequency-Penalty 0,
Repetition-Penalty 1, Seeds 20261004/20261005, maximal 384 Ausgabetokens
und sechs Modellrunden. Identische Seeds bedeuten keine identischen
Zufallsverläufe zwischen Engines. Gemeinsam genutzte Promptpräfixe sind warm;
das Request-Feld `cache_prompt: false` deaktiviert Stratas native Wiederverwendung
nicht. Diese HA-Laufzeiten sind daher keine kalten Prefill-Messungen.

| Aufgabe | Strata Q2 | Strata Q3 | 27B vLLM |
| --- | ---: | ---: | ---: |
| Konkrete Licht-, Rollo-, Musik- und Scriptaktionen | 21/24 | 24/24 | 23/24 |
| Bedingungen, Ausschlüsse und mehrere Aktionen | 13/16 | 15/16 | 8/16 |
| Zustandsfragen | 24/24 | 23/24 | 20/24 |
| Mehrdeutigkeit, fehlende Funktionen und Widerruf | 5/16 | 9/16 | 9/16 |
| Geräusche abbrechen und klaren Stopp ausführen | 12/12 | 12/12 | 12/12 |
| Gespräch fortsetzen und Zuordnung korrigieren | 2/4 | 1/4 | 1/4 |
| Nicht erreichbare Geräte und Teilfehler | 8/8 | 8/8 | 7/8 |
| **Gesamt** | **85/104 (81.7 %)** | **92/104 (88.5 %)** | **80/104 (76.9 %)** |

| Zusätzliche Fehlerzählung | Strata Q2 | Strata Q3 | 27B vLLM |
| --- | ---: | ---: | ---: |
| Anfragen mit ungewolltem Änderungsversuch | 12 | 4 | 1 |
| Einzelne ungewollte Änderungsaufrufe | 23 | 11 | 3 |
| Sonstige Schema- oder Toolfehler, einschließlich korrigierter Versuche | 21 | 7 | 1 |

Die drei Q2-Fehler bei konkreten Aktionen betreffen Emojis bzw. sichtbare Selbstkorrekturen; die gewünschten Aktionen sind dort tatsächlich belegt. Fehlgeschlagene erlaubte Leseaufrufe werden nach erfolgreicher Korrektur nicht als ganze Aufgabe verworfen. Ungewollte Änderungen zählen auch dann als Fehler, wenn der Simulator sie blockiert oder anschließend die richtige Aktion erfolgt. Zwei Q2-Versuche schalten zusätzlich eine ausdrücklich ausgenommene, bereits ausgeschaltete Leselampe aus; nicht jeder gezählte Versuch hätte den Endzustand geändert.

Konkrete Unterschiede aus den gespeicherten Antworten:

- Bei „Wie voll ist die Batterie im Bad?“ sagen Q2 und Q3, dass kein Wert vorliegt. 27B antwortet mit **64 bzw. 87 Prozent**, obwohl der Sensor `unknown` meldet.
- Bei „Wenn es regnet, schließe das Rollo“ sowie Ausschlüssen wie „nur Arbeitslicht, Deckenlicht nicht“ ist Q3 zuverlässiger. Q2 versucht unter anderem zusätzliche Lichtänderungen; 27B bricht mehrere klare Aufträge mit „Abgebrochen.“ ab.
- Bei „Mach es gemütlicher“ versuchen alle drei in mindestens einem Durchlauf nicht beauftragte Änderungen. Q2 versucht außerdem in beiden Widerrufs-Fällen noch eine Lichtänderung; Q3 in einem, 27B in keinem.
- Bei Folgeaufträgen behaupten Q3 und 27B mehrfach eine ausgeführte Änderung, ohne den notwendigen Tool-Aufruf zu liefern. Auch Q2 löst nur zwei der vier Folgefälle korrekt.
- Q3 behauptet einmal zusätzlich einen geschlossenen Schlafzimmer-Fensterzustand, obwohl dafür kein Sensor angeboten ist. Gute Nullwertbehandlung bedeutet daher keine fehlerfreie Zustandsauskunft.

Aus dem [früheren allgemeinen Texttest](strata-quality-benchmark-2026-10-04.md): Q2 und 27B erreichten jeweils **112/147** in der vergleichbaren automatischen Stichprobe und **28/30** bei sechs freien Antworten. Im kleinen GSM8K-Ausschnitt war 27B besser: Greedy 11/20 gegenüber Q2 8/20, übliche Sampling-Werte 10/20 gegenüber 7/20. Beide bestanden neun lange Abrufaufgaben. Für Q3 wurden diese allgemeinen Textprüfungen nicht wiederholt; sein höherer HA-Wert belegt keine allgemeine Überlegenheit bei Mathematik, Code oder langen Abrufaufgaben.

## Prefill und Decode bis 128K Kontext

Alle Modelle erhalten denselben gespeicherten Textkorpus. Die drei Eingaben
haben tatsächlich 4205, 65645 und 128108 Prompttokens einschließlich
Chat-Template und Anweisung. Jede Messung generiert genau 512 Tokens eines
deutschen Artikels über Datenbank-Backups, mit Temperatur 0 und explizit
abgeschalteten Penalties. Die Ausgabe muss mindestens 100 Wörter enthalten
und mit dem Längenlimit enden. Vorher laufen eine kurze und eine separate
64K-Aufwärmgeneration.

Pro Modell und Kontext gibt es hier **eine** gemessene Probe. Damit lässt sich
die große Richtung beurteilen, aber keine belastbare Streuung oder kleine
Prozentdifferenz. Ein neuer System-Seed ganz vorne verhindert die Wiederverwendung
des langen Promptpräfixes. Strata meldet jeweils null wiederverwendete Tokens;
vLLM liefert in diesen Antworten keinen Cache-Zähler. Sein kaltes Präfix ist
über die Request-Konstruktion vorgesehen, nicht über einen gemeldeten
Nullwert belegt.

TTFT ist die Zeit bis zum ersten nichtleeren gestreamten Token einschließlich
Request und erstem Decode-Schritt. Der für alle Engines vergleichbare
Prefill-Näherungswert ist `Prompttokens / TTFT`; er liegt unter einem reinen
Engine-Prefill-Durchsatz. Stratas zusätzlich gespeicherte native Prompt-Timings
sind separat ausgewiesen. Decode misst
`(Ausgabetokens − 1) / (Streamende − erster Token)`.

Zeit bis zum ersten Token in Sekunden:

| Textkontext | Strata Q2 | Strata Q3 | 27B vLLM |
| --- | ---: | ---: | ---: |
| 4K | 3.52 | 11.23 | 1.96 |
| 64K | 30.01 | 87.75 | 40.64 |
| 128K (128000) | 54.73 | 179.78 | 100.05 |

Effektiver Prefill als Prompttokens pro TTFT Sekunde:

| Textkontext | Strata Q2 | Strata Q3 | 27B vLLM |
| --- | ---: | ---: | ---: |
| 4K | 1196 | 374 | 2145 |
| 64K | 2187 | 748 | 1615 |
| 128K (128000) | 2341 | 713 | 1280 |

Decode in Tokens pro Sekunde:

| Textkontext | Strata Q2 | Strata Q3 | 27B vLLM |
| --- | ---: | ---: | ---: |
| 4K | 82.63 | 71.85 | 59.18 |
| 64K | 79.14 | 65.78 | 54.00 |
| 128K (128000) | 76.27 | 63.02 | 46.07 |

Gesamtzeit für Prompt und 512 Ausgabetokens in Sekunden:

| Textkontext | Strata Q2 | Strata Q3 | 27B vLLM |
| --- | ---: | ---: | ---: |
| 4K | 9.70 | 18.34 | 10.59 |
| 64K | 36.47 | 95.52 | 50.10 |
| 128K (128000) | 61.43 | 187.88 | 111.15 |

Native Strata-Prefill-Timings bei 4K / 64K / 128K: Q2 **1204 / 2195 / 2349 tok/s**, Q3 **375 / 749 / 713 tok/s**. Ein direkt vergleichbares natives Timing liefert vLLM hier nicht.

Bei 64K ist Q2 bei der Zeit bis zum ersten Token ungefähr **1.35× schneller** als 27B, bei 128K ungefähr **1.83×**. Q3 braucht dagegen ungefähr **2.16× / 1.80×** so lange wie 27B. Beide Strata-Profile decodieren in diesen Proben schneller als 27B; Q3 ist dennoch wegen seines Prefills bei allen drei Kontextlängen insgesamt langsamer.

Diese Generierungsprobe prüft Ausgabelänge und plausiblen Text. Sie ist kein
Abruf- oder Verständnistest des langen Kontextes. Die früheren neun
16K/64K/128K-Abrufaufgaben für Q2 und 27B stehen im
[vorherigen Qualitätsbericht](strata-quality-benchmark-2026-10-04.md);
ein entsprechender Q3-Abrufscore wurde hier nicht erhoben.

## Latenz bei kurzen HA Aufgaben

Sechs vorab ausgewählte Aufgaben laufen mit zwei weiteren Seeds
20261006/20261007: Licht aus, Licht an, zwei Lichtaktionen, Rollo auf 25 Prozent,
Wohnzimmertemperatur und ein nicht erreichbares Fenster. Alle Profile sind
vorher durch die Qualitätssuite warm. Für einen fairen Geschwindigkeitsvergleich
werden nur diejenigen gepaarten Beobachtungen verwendet, die alle drei
Modelle korrekt abschließen. Zustandstexte werden zusätzlich gelesen.

**11 gepaarte korrekte Abschlüsse**, davon **7 mit Aktion**. Die Beobachtung „Leselampe an“ mit Seed 20261006 wird für alle drei Profile ausgeschlossen, weil Q2 mit einem Emoji antwortet. Die Geräteaktion selbst war korrekt.

| Median | Strata Q2 | Strata Q3 | 27B vLLM |
| --- | ---: | ---: | ---: |
| Bis zur ersten simulierten Aktion, s | 0.83 | 1.88 | 2.40 |
| Bis zur vollständigen Antwort, s | 2.60 | 2.09 | 2.89 |

Der Median über sämtliche 104, unterschiedlich schwierigen Qualitätsdurchläufe einschließlich Fehlantworten beträgt Q2 **1.52 s**, Q3 **1.71 s**, 27B **1.60 s**. Das ist keine Auswahl gleicher erfolgreicher Antworten und erlaubt keinen pauschalen Geschwindigkeitsgewinner. In den sechs ausgewählten warmen HA-Proben sind beide Strata-Profile schneller als 27B; die kleine Stichprobe belegt keine allgemeine Latenzgarantie.

Zeit bis zur Aktion bedeutet hier: Zeit bis der vollständige Modell-Toolaufruf
vorliegt und die simulierte Aktion ausgeführt werden kann, einschließlich
eventueller vorangegangener Zustandsabfragen. Das ist keine Messung bis zum
Schalten eines realen Geräts und keine vollständige HA/Hermes/Voice-Latenz.
Die kleine Auswahl ersetzt keinen Lasttest mit mehreren Benutzern.

## Speicher und GPU Reihenfolge

**Q3 passt in diesem Profil auf zwei 3090 bis 128K Kontext.** Möglich ist das
mit per mmap eingeblendeten Experten, Dateicache und einem begrenzten
GPU-Expertencache. Das gesamte Modell liegt weder vollständig im VRAM noch
vollständig im RAM. IQ3_XXS ist hier die native GSQ-RCO-Quantisierung;
das bestehende llama.cpp-Modell Unsloth UD-Q3_K_XL ist damit nicht austauschbar.

Q3 besteht aus zwei GGUF-Shards mit 47039860096 und 28800138432 Bytes.
Der identische zweite Shard ist mit Q2 hart verlinkt. Deshalb waren ungefähr
47 GB neue Download-Daten nötig, zusätzlich zum erzeugten Experten-Pack.
Der Q3-Experten-Pack umfasst ungefähr 40 GiB; Q2 ungefähr 33 GiB.
Das 28-GiB-Containerbudget umfasst auch Dateicache und ist keine feste
RAM-Reservierung. Q3 zeigt viele Dateicache-Neuladungen und Reclaims.
Das ist ein plausibler Grund für langsameren Prefill, aber keine isolierte
Ursachenmessung des Quantisierungsformats.

Messstand nach der 128K-Generierung; Cgroup-Peak umfasst die gesamte jeweilige Containerlaufzeit einschließlich Dateicache, keinen reinen Prozess-RSS:

| Profil | Cgroup-Peak GiB | Container-Swap GiB | OOM / Kill | Freier VRAM GPU0 / GPU1 MiB |
| --- | ---: | ---: | --- | --- |
| Strata Q2 | 28.00 | 0.00 | 0 / 0 | 4280 / 4234 |
| Strata Q3 | 28.00 | 0.00 | 0 / 0 | 4264 / 4184 |
| 27B vLLM | 29.25 | 0.00 | 0 / 0 | 3764 / 3304 |

Q2 nutzt im aktuellen Lauf den automatischen Split 25/23, Q3 26/22. Q3 wurde beim ersten Laden einschließlich einer korrekten Testantwort nach **37,87 Sekunden** bereit; spätere Qualitätsläufe verwenden ein schon aufbereitetes Modell. Diese Startprobe misst keinen erstmaligen Download oder Pack-Aufbau.

Die GPU-Reihenfolge lässt sich nativ mit `--gpus` einstellen. Der Launcher
übersetzt die geordneten UUIDs aus `STRATA_GPU_UUIDS` in die von NVML gemeldeten
Indizes und übergibt sie an Strata. In den gespeicherten Laufzeitkonfigurationen
steht `[0, 1]`; der Split wird zusätzlich über `--layer-split` gewählt.
Die Reihenfolge wurde in diesem Vergleich nicht vertauscht oder als eigener
Geschwindigkeitsfaktor getestet.

Die RTX 5060 Ti bleibt außerhalb der LLM-Testcontainer. Ihre unabhängige
Speicherbelegung änderte sich während der Sitzung; Wolf und ComfyUI blieben
aktiv. Die 3090 waren zeitweise thermisch gedrosselt. Die Werte beschreiben
diesen laufenden Host mit seinen bestehenden Limits, keine temperaturbereinigte
Laborleistung. Container-Swap von null bedeutet außerdem nicht, dass auf dem
Host kein bereits belegter Swap existiert.

## Reproduktion und wiederhergestellter Betrieb

Die deklarativen Profile stehen in `group_vars/all/llms.yml`; der Launcher
in `roles/llm_inference/files/strata-start.sh`. Das Q3-Profil lässt sich wie Q2
über LlamaSwap auswählen. Deployment der Versuchskonfiguration:

```sh
uv run ansible-playbook setup.yml --tags strata-test --limit ailab_ubuntus
```

Rohantworten, Fälle, Schemas, Rubriken, Ressourcen, native Logs, Timings und
Hash-Metadaten stehen unter
[`experiments/strata/ha-q3-results-2026-10-04`](../experiments/strata/ha-q3-results-2026-10-04/).
Der historische Verzeichnisname umfasst jetzt alle drei Modelle.
Vereinfachte frühe Selektoren sowie die Läufe vor der Korrektur gleichwertiger
Lichtaktionen sind dort ausdrücklich ausgeschlossen und archiviert.
Die Geschwindigkeitssamples haben denselben Prompt-/Decode-Vertrag und sind
von dieser Simulator-Korrektur unabhängig.

```sh
python3 scripts/test_benchmark_ha_tool_quality.py
python3 scripts/summarize_ha_tool_quality.py experiments/strata/ha-q3-results-2026-10-04
```

Nach Abschluss am **2026-10-04T17:36:25Z** wurde die echte LlamaSwap-Route geprüft: 27B beantwortet die Testfrage mit `42`, Embedding liefert **1024 Dimensionen**, TTS mit `de-host` liefert eine gültige WAV mit **109404 Bytes**, und ASR erkennt „Das ist ein kurzer Funktionstest.“ Alle vier Backends sind `ready`, Strata-Testcontainer sind entladen, Wolf und ComfyUI laufen. [Restoration-Nachweis](../experiments/strata/ha-q3-results-2026-10-04/restoration.json).

Die älteren [Prefill-Messungen mit drei GPUs und llama.cpp Flash-Next](strata-prefill-benchmark-2026-10-03.md)
und [Decode-Messungen](strata-decode-benchmark-2026-10-04.md) bleiben separat.
Der dortige llama.cpp-Arm ist Flash-Next mit drei GPUs und kein llama.cpp-27B.
Im früheren Versuch war die 5060 Ti ausdrücklich freigegeben. Dort war Strata Q2 auf zwei 3090 bei 64K schneller als das manuelle Drei-GPU-Profil: nativer Prefill **2258 gegenüber 1746 tok/s**, Decode **77,17 gegenüber 68,69 tok/s**. Ein eigener HA-Qualitätslauf für das Drei-GPU-Profil wurde nicht erhoben. Die aktuellen Produktionsrouten werden weiterhin auf 27B/vLLM belassen.
