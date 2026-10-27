# Flash-Next IQ2_XS / Strata als Kandidat für Qwen3.8 27B

Gemessen am 3./4. Oktober 2026 auf `ailab-ubuntu`: beide Profile auf den zwei
RTX 3090, GPU2/5060 Ti unbenutzt. Embedding, ASR und TTS blieben geladen.
Keine realen Geräte-/Listenaktionen; alle Tool-Ergebnisse sind feste Testdaten.
ComfyUI-Queue leer, Wolf/ComfyUI bleiben aktiv.

## Entscheidung

**Ein Kandidat für lange Textkontexte, aber aktuell keine Empfehlung, den
27B-Standard vollständig zu ersetzen.** Die Textqualität ist in dieser kleinen
Suite insgesamt ähnlich. Flash ist besser bei einigen Fakten-/Nullwert-Tests,
27B im ausgewählten mehrstufigen Rechnen. Vollständige Tool-Runden funktionieren
bei beiden. Für kurze Home-Assistant-/Hermes-Anfragen ist das bestehende
27B/vLLM häufig schneller; Flash gewinnt bei längeren Textausgaben und Kontexten.

Das getestete Flash-Profil hat 131072 Tokens Kontext, deaktivierte Vision und
serielle Engine-Verarbeitung im [Servercode](https://github.com/Niko1221/Strata/blob/99f3dbd0b21d1401b3769e0c0d963913607f380b/serve/server.py#L1450).
Das bestehende 27B-Profil ist auch `home-vision`, hat 262144 Tokens und
`--max-num-seqs 3`. Gleichzeitige Benutzerlast und die tatsächlichen HA-/Hermes-
Agentenwege wurden hier nicht getestet. Die bestehenden Modellrouten bleiben auf 27B.

## Profile und Methode

| Profil | Modell / Quantisierung | Backend | Kontext | Thinking |
| --- | --- | --- | ---: | --- |
| Qwen3.8 27B Produktion | Frozenlock 27B INT4 AutoRound | vLLM 0.27.1, TP2, FP8 KV | 262144 | aus |
| Flash 2GPU | ISTA-DASLab GSQ-RCO IQ2_XS | Strata-Engine 0.1.38, Commit 99f3dbd0b21d, mmap, MTP 4, INT8 KV, 28 GiB RAM-Limit | 131072 | aus |

**87 verschiedene Aufgaben pro Modell:** 81 automatisch prüfbare Fälle und
sechs freie Antworten. 70 kurze Aufgaben laufen einmal mit Greedy und einmal
mit den üblichen Sampling-Werten (Temperatur 0,7; top-p 0,8; top-k 20;
Presence-Penalty 1,5). Greedy: Temperatur 0, top-p 1, top-k 0, keine Penalties.
Seed 20261004 bei beiden APIs. Die Engines müssen dadurch nicht denselben
Zufallsverlauf haben. Neun lange Abrufaufgaben und zwei JSON-Schema-API-Tests
laufen einmal mit Greedy; freie Antworten ebenfalls einmal.

Die **151 automatischen Durchläufe** pro Modell verwenden vorab festgelegte
Sollantworten. Vollständiges JSON mit richtigen Schlüsseln/Typen/Werten wird
verlangt; gleichwertige JSON-Zahlen sind erlaubt, Boolean und Zahl bleiben
verschiedene Typen. Kein Markdown bei JSON-Aufgaben. Alle Antworten, Fehler,
Tokenzahlen, Requestzeiten und Prompt-Hashes sind gespeichert. Ausgabegrenze
256 Tokens, freie Antworten 384. Warmup/Startzeit sind nicht enthalten.

20 fest per Seed ausgewählte Aufgaben aus dem offiziellen
[GSM8K-Testdatensatz](https://github.com/openai/grade-school-math) ergänzen die
selbst erstellten deutschen Aufgaben. Revision, Dateihash und Indices stehen
in [den Testfällen](../experiments/strata/quality-cases-2026-10-04.json).
Das ist **kein offizieller GSM8K-Benchmarkscore**: kleine bekannte Stichprobe,
kein Thinking und nur direkte JSON-Endantwort. Die zwei Sampling-Modi derselben
Aufgabe sind korreliert. Auch die handgeschriebenen Fälle sind eine begrenzte
synthetische Suite, keine Sammlung realer Haushaltsanfragen.

## Automatische Ergebnisse

| Kategorie | 27B Greedy | Flash Greedy | 27B übliche Werte | Flash übliche Werte |
| --- | ---: | ---: | ---: | ---: |
| Deutsch: Rechnen | 6/8 | 7/8 | 5/8 | 5/8 |
| Deutsch: Logik | 7/8 | 8/8 | 6/8 | 7/8 |
| Deutsch: Faktenextraktion | 7/8 | 8/8 | 7/8 | 8/8 |
| Python-Code verstehen | 5/6 | 6/6 | 5/6 | 3/6 |
| Ausgabevorgaben | 4/6 | 5/6 | 4/6 | 5/6 |
| Tool-Aufrufe im ersten Turn, streng | 8/8 | 7/8 | 8/8 | 6/8 |
| Einfache vollständige Tool-Runden | 4/4 | 4/4 | 4/4 | 4/4 |
| Gesprächskorrektur / Erinnerung | 2/2 | 2/2 | 2/2 | 2/2 |
| GSM8K-Ausschnitt | 11/20 | 8/20 | 10/20 | 7/20 |
| JSON-Schema-API | 2/2 | 2/2 | — | — |
| Abruf 16K/64K/128K | 9/9 | 9/9 | — | — |

Originale strenge Erstbewertung: **27B 116/151, Flash 113/151**.
Zwei Tool-Szenarien (`two_lights`, `shopping_exact_ids`, jeweils beide Modi)
bewerten in dieser Erstbewertung nur den allerersten Modell-Turn. Damit werden
gleichwertige serielle Tool-Aufrufe und eine zusätzliche lesende Bestätigung
nicht fair als vollständige Aufgaben beurteilt. Diese vier Beobachtungen werden
bei **beiden** Modellen aus dem vergleichbaren Gesamtwert ausgeschlossen:
**112/147 bei beiden**. Die Originalwerte bleiben unverändert in den Rohdaten;
die vollständigen Zusatzrunden stehen separat unten.

In der verbleibenden Stichprobe ist keine klare allgemeine Qualitätsüberlegenheit
erkennbar. Relevante Unterschiede:

- Flash extrahiert vorhandene **0,0 °C** korrekt und gibt bei unbekanntem
  Akkustand `null` zurück. 27B ließ den Nullwert weg bzw. erfand Akkustand 0.
- 27B löst im GSM8K-Ausschnitt mehr Aufgaben: 11/20 gegenüber 8/20 mit Greedy,
  10/20 gegenüber 7/20 mit den üblichen Sampling-Werten. Beide machen auch
  einfache Rechenfehler; daraus folgt keine isolierte Aussage über IQ2 allein.
- Flash gibt bei drei Python-Ausgabeaufgaben im Sampling-Modus korrekte
  Listendarstellungen **als String statt als JSON-Array** zurück. Das sind
  Typ-/Formatfehler, keine drei falschen berechneten Listen.
- Bei `latest_revision` liefert 27B den richtigen Datensatz mit zusätzlichen
  Worten statt nur dem verlangten Feldwert. Der strenge Vertragstest zählt
  dies als Fehler; das ist kein falsch ausgewählter Datensatz.

## Vollständige Tool-Runden

Einfache Abfrage-, Erfolgs- und Fehler-Runden: jeweils **8/8** über beide Modi.
Zusatzprobe für zwei Lichtaktionen und Einkauf (je zwei Modi):
**4/4 bei 27B und 4/4 bei Flash**, keine unerwünschte Mutation.
Flash kann Aktionen seriell abarbeiten und zusätzliche Abfragen einfügen;
27B führt die zwei Lichtaktionen hier in einem Turn aus. Beide beenden korrekt.
Der Zustand des Mock-Tools wird nach jeder erfolgreichen Änderung fortgeschrieben.

Der erste Zusatzlauf von Flash hatte einen Fehler im Simulator: Einkaufs-
Snapshots enthielten nach Änderungen noch den ursprünglichen Zustand. Dieser
Lauf ist ausdrücklich ausgeschlossen und als
`flash-iq2-tool-sequence-invalid-stale-state.jsonl` aufbewahrt. Der korrigierte
Zustand und erneute Läufe beider Modelle liefern die obigen Ergebnisse.
Parser-/Reducer-Checks prüfen unter anderem gelöschte/abgehakte IDs,
unzulässige zusätzliche Aktionen und voreilige Erfolgsbehauptungen.

## Freie deutsche Antworten

Sechs Antworten mit je fünf vorab definierten Kriterien: **28/30 bei beiden**.
Die Modellnamen wurden pro Antwortpaar vor der Bewertung zufällig verdeckt.
Bewertet hat derselbe Assistant, der die Suite erstellt hat; das ist keine
unabhängige externe Beurteilung. Verdeckte Antworten, Kriterien, Bewertungen
und anschließend aufgelöste Zuordnung sind in den Rohdaten enthalten.

Beide schreiben gut verständliches Deutsch, erklären Synchronisation/Backup
und liefern einen plausiblen minimalen Python-Fix. Beide antworten bei einem
unbekannten Fensterzustand zu bestimmt mit „Nein“, statt nur die fehlende
Bestätigung aller geschlossenen Fenster zu benennen. Der hohe Sprachwert
bedeutet daher keine fehlerfreie Unsicherheitsbehandlung.

## Geschwindigkeit direkt gegen 27B

Der frühere große Vorteil gegenüber llama.cpp Q3 ist **kein 27B-Vergleich**.
Hier wurden beide mit identischen Prompts und jeweils 512 Output-Tokens geprüft,
zwei Messungen bei 4K und 64K; vorher eine kurze und eine 64K-Aufwärmgeneration.
Client-Decode misst `(output_tokens-1)/(Streamende-erster nichtleerer Token)`.

| Kontext / Messgröße | 27B/vLLM | Flash IQ2_XS/Strata |
| --- | ---: | ---: |
| 4K: Decode tok/s | 51.21 | 73.98 |
| 4K: erster Token, s | 2.21 | 3.55 |
| 4K: Prompt + 512 Tokens, s | 12.22 | 10.46 |
| 64K: Decode tok/s | 53.43 | 76.59 |
| 64K: erster Token, s | 40.55 | 30.33 |
| 64K: Prompt + 512 Tokens, s | 50.11 | 37.01 |

Flash erreicht hier etwa **1,44× Decode-Durchsatz** gegenüber 27B.
Bei den 68 kurzen Textaufgaben, die beide korrekt lösten, dauert die vollständige
Antwort dagegen im Median **0,22 s mit 27B, 0,73 s mit Flash**. Die Ergebnisse
beziehen sich auf neue Testpräfixe und diese direkten Backend-Anfragen; sie sind
keine Messung eines wiederverwendeten Agentenpräfixes oder der Zeit bis zur
realen HA-Aktion.

Median der drei Abrufaufgaben pro Kontextlänge, komplette JSON-Antwort:

| Textkontext | 27B/vLLM, s | Flash/Strata, s |
| ---: | ---: | ---: |
| 16384 | 8.52 | 10.79 |
| 65536 | 41.11 | 30.38 |
| 128000 | 100.86 | 54.76 |

Die Abrufaufgaben enthalten zusammengehörige Ticket-/Node-Dokumente und
widersprechende alte Revisionen zwischen gemeinsamem synthetischem Fülltext.
Das Ticket steht jeweils am Anfang, in der Mitte oder am Ende. Gemessene
Korrektheit betrifft diesen Zwei-Schritt-Abruf, keine allgemeine 128K-Qualität.

## Ressourcen und Abschluss

| Profil | Cgroup-Peak GiB | Container-Swap GiB | Min. freier VRAM GPU0/1/2 MiB | Max. Temperatur GPU0/1/2 °C |
| --- | ---: | ---: | --- | --- |
| qwen27b-vllm | 30.07 | 0.00 | 3676/3166/15203 | 91/93/49 |
| flash-iq2-2gpu | 28.00 | 0.00 | 4268/4224/15203 | 91/96/51 |

Peak enthält Dateicache und umfasst die Containerlaufzeit, einschließlich
Modellstart bei Flash. Keine OOMs/OOM-Kills. Strata hat Dateicache-Reclaim am
28-GiB-Limit, aber keinen Container-Swap. Beide Reihen zeigen thermische
Drosselung; die Ergebnisse gelten für bestehende Kühlung und 250/250/180 W.

Produktion über LlamaSwap wiederhergestellt: vLLM antwortet `42`, Embedding
1024 Dimensionen, TTS `de-host` gültige WAV mit
109404 Bytes, ASR transkribiert „Das ist ein kurzer Funktionstest.“.
Alle vier Backends `ready`, Flash entladen, GPU2 frei für seine üblichen Dienste.
Keine Modellroute wurde umgestellt.
[Restoration-Nachweis](../experiments/strata/quality-results-2026-10-04/restoration.json).

[Rohdaten und Auswertung](../experiments/strata/quality-results-2026-10-04/),
[zusammengefasste Werte](../experiments/strata/quality-results-2026-10-04/summary.json),
[Reproduktion](../experiments/strata/README.md).
Die Qualitäts-/Tool-Parser-Checks, bestehenden Benchmark-Parser-Checks und
`git diff --check` bestanden. Image-/Client-/Corpus-/Testfall-Hashes sind gespeichert.
