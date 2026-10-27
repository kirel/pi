# Strata Flash Q2/Q3: Low Reasoning versus NoThink, 2026-10-06

## Ergebnis

Low verbessert in dieser Suite die inhaltliche Aufgabenerfüllung: Q3 von
90/104 auf 97/104, Q2 von 79/104 auf 93/104. Fälle mit ungefragten
Aktionsversuchen sinken bei Q3 von sechs auf drei, bei Q2 von 17 auf sechs.
Der Nutzen liegt vor allem bei Rückfragen und mehrdeutigen Aufträgen.
Einfache Aktionen werden nicht allgemein besser; einzelne Zustandsfragen
werden mit Denken sogar schlechter.

Nach Abschluss des Benchmarks wurde der Alltagstest mit Q3 Low ausdrücklich
freigegeben und am 6. Oktober für `home-ha` und `home-hermes` ausgerollt.
Die [Aktivierung und tatsächlichen Assist-Latenzen](strata-q3-multimodal-home-test-2026-10-05.md)
sind gesondert dokumentiert; die folgenden Benchmarkdaten beschreiben den
vorangegangenen kontrollierten Vergleich.

## Versuchsaufbau

Verglichen werden die bestehenden Profile IQ2_XS und IQ3_XXS auf denselben
zwei RTX 3090, jeweils mit `reasoning_effort: none` und `low`.
Die RTX 5060 Ti bleibt außerhalb des Benchmarks. Die bisherigen
Home-Assistant- und Hermes-Aliase werden nicht geändert.

Strata läuft für alle vier Arme auf Version 0.1.39, Commit
`6f32ec070f23ced9f50e704d854d775da52591ab`, im bereits gebauten Image
`kirelabs/strata:6f32ec070f23-sm86-sm120-vision`.
Die Profile behalten 131072 Kontexttokens, int8-KV, mmap-Experten,
28 GiB Container-RAM ohne zusätzlichen Container-Swap und ihre GPU-Reserven.
Embedding, ASR und TTS bleiben geladen.
Q3 behält den GPU-Bildencoder und seinen 2048-MiB-Konversationscache mit vier
Slots; Q2 bleibt das bisherige reine Textprofil ohne diesen Zusatzcache.
In den Qualitäts- und HA-Latenzvergleichen unterscheiden sich die Arme
innerhalb einer Quantisierung nur im angeforderten Thinking-Modus. Der Vergleich Q2 gegen Q3 umfasst dagegen diese
unterschiedlichen Deployment-Einstellungen.

`low` ist die kleinste aktivierte Stufe. Requests enthalten dazu
`reasoning_effort: low` und `chat_template_kwargs.enable_thinking: true`;
NoThink enthält `none` und `false`.
Eine sichtbare Reasoning-Ausgabe wurde im Vorlauf nachgewiesen.
Es wird kein zusätzliches hartes Reasoning-Tokenbudget gesetzt.
Die native Stufe ist eine Anweisung an das Modell, kein festes Tokenlimit.
Siehe [Upstream-Protokoll](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/serve/frontend.py).

## Betriebsbedingungen und Grenzen

Die native Telemetrie meldete vor den Qualitätssuiten 86 °C und danach bis
91 °C als GPU-Maximaltemperatur. Während der ergänzenden Geschwindigkeitsläufe
meldete `nvidia-smi` an beiden 3090 explizit aktive Software-Thermaldrosselung
bei 88–89 °C; Hardware-Thermaldrosselung war nicht aktiv. Die Beobachtung ist in
`thermal-speed-observation.csv` gespeichert. Lüfter, Power-Limits und
Kühlung wurden für diesen Test nicht verändert.

Das sind Messungen des aktuellen Homelab-Betriebszustands. Temperatur und
Experten-/Dateicache sind keine vollständig kontrollierten Variablen; kleine
Durchsatzdifferenzen sind deshalb kein sauberer kausaler Reasoning-Vergleich.
Die umgekehrte Reihenfolge reduziert den systematischen Reihenfolgeeffekt,
entfernt diese Einflüsse aber nicht. Die Qualitätsergebnisse beruhen weiterhin
auf tatsächlich abgeschlossenen Antworten und protokollierten Toolversuchen.

## Geschwindigkeit: Methode

Alle Arme verwenden denselben vorhandenen synthetischen Textkorpus.
Vor jedem Arm laufen eine kurze und eine kalte 64K-Aufwärmanfrage.
Low und NoThink wechseln bei den kalten Messungen ihre Reihenfolge,
um den Einfluss warmer Expertengewichte zu begrenzen.
Neue Systempräfixe verhindern Promptwiederverwendung; mehr als 32
wiederverwendete Tokens invalidieren eine kalte Messung.
Der RAM-Dateicache und der GPU-Expertencache bleiben davon verschieden und
werden durch diesen Test nicht in einen exakt gleichen Zustand versetzt.

Die Rechenaufgabe am Ende jeder Eingabe muss exakt `42` ergeben.
Für diese kurze Speed-Aufgabe sind maximal 32 Ausgabetokens ohne Denken
und 2048 mit Low erlaubt; beide Modi beenden ihre gemessenen Antworten
regulär mit `stop`, ohne das jeweilige Limit zu erreichen. Die HA-
Qualitätskontrolle verwendet dagegen in beiden Modi dasselbe 2048-Tokenlimit.
Bei Q3 gibt es bei 4K, 16K und 64K drei Proben, bei 128K eine Probe.
Bei Q2 wird als Ergänzung zur vollständigen Qualitätssuite jeweils eine
Probe bei 4K, 16K und 64K gemessen. Die Stichprobenzahlen werden in den
Tabellen angegeben; die Geschwindigkeitstests sind eine technische Ergänzung,
kein gleich großer quantisierungsübergreifender Vergleich.
Die native Prefill-Zeit und der erste gestreamte Token werden von der Zeit
bis zum ersten sichtbaren Antworttext getrennt. Unter Low kann der erste
Token ausschließlich zur Denkphase gehören.

Der Decode-Test verwendet dieselbe Aufgabe wie der bisherige Benchmark:
einen langen deutschen Artikel über Datenbank-Backups. Dieses Mal werden
1024 Ausgabetokens einschließlich eventueller Reasoning-Tokens erzeugt.
Jede Probe muss mit dem Längenlimit enden und mindestens 100 sichtbare Wörter
enthalten. Für den vollständigen Low/NoThink-Vergleich wird pro Arm eine
4K-Probe ausgewertet. Eine zuvor bereits abgeschlossene 64K-Q3-Low-Probe
bleibt als ergänzende Rohmessung erhalten, ohne passenden NoThink-Kontrollarm.
Decode-Durchsatz bezeichnet `(completion_tokens - 1) / Zeit ab erstem Token`;
unter Low umfasst er Denken und Antwort, keinen isolierten sichtbaren Text.

Warme 16K-Messungen wiederholen unmittelbar dasselbe Präfix dreimal,
nach einer ungewerteten Prime-Anfrage. Dies prüft Wiederverwendung derselben
Unterhaltung, nicht die Wiederaufnahme zwischen verschiedenen Gesprächen.

## Home-Assistant-Qualität: Methode

Die bestehende Suite enthält 52 synthetische deutsche Aufgaben,
46 gespeicherte offizielle HA-Toolschemas und 19 simulierte Geräte.
Jeder Arm läuft mit beiden bisherigen Seeds 20261004 und 20261005,
also 104 Beobachtungen pro Arm. Alle Werkzeuge werden lokal simuliert;
keine realen Haushaltsgeräte werden geschaltet.
Der tatsächliche Hermes-Agent, dessen Tool-Suche und die Assist-Audiokette
sind nicht Teil dieses Modellbenchmarks.

Pro Aufgabe startet ein frischer simulierter Haushalt. Die Reihenfolge
Low/NoThink wird zwischen den Seeds umgedreht.
Sampling ist in allen Qualitätsarmen gleich: Temperatur 0,7, top-p 0,8,
top-k 20, Presence-Penalty 1,5, Frequency-Penalty 0 und Repetition-Penalty 1.
Alle Arme erhalten 2048 Ausgabetokens pro Modellrunde statt der früheren 384,
damit die Denkphase Platz hat. Maximal sechs Modellrunden bleiben erlaubt.
Der neue NoThink-Kontrollarm verwendet ebenfalls 2048 Tokens.
Die HA-Zeiten enthalten gemeinsame Promptpräfixe. Q3 wechselte die Modi
pro Aufgabe; Q2 wurde nach einem ausgeschlossenen Mischmodus-Pilot in
Modusblöcken getestet. Ein separater Latenztest verwendet deshalb für beide
Quantisierungen dieselbe Blockmethode mit Prime-Anfrage und umgekehrter
Modusreihenfolge bei der Wiederholung. Hierfür laufen zwölf ausgewählte
Aufgaben mit Seeds 20261006 und 20261007, also 24 Beobachtungen pro Arm.
Die Auswahl umfasst sechs Lichtaufträge, drei kombinierte/bedingte Aufträge,
zwei Zustandsfragen und einen Folgeauftrag. Modelllatenzen für typische
Anfragen werden aus
diesem zweiten Test abgeleitet, nicht aus dem Unterschied der Hauptsuite.
Die erste Aktionszeit bezeichnet den ersten vom Simulator erkannten
Aktionsversuch; Abschlusszeit umfasst alle Modellrunden bis zur finalen
Antwort. Beides schließt ASR, TTS und echte Geräteausführung aus.

Ein Aufgabenpass erfordert die gewünschten Aktionsbelege oder eine korrekte
Rückfrage/Zustandsauskunft, keine ungewollte Änderung und eine korrekte
Abschlussantwort. Korrigierte Schemafehler werden separat gezählt.
Ungefragte Aktionsversuche scheitern auch dann, wenn der Simulator sie
blockiert. Für angebotene Hausdurchsagen, Timerlöschungen und Fan-Steuerung
wird zusätzlich die Rohspur geprüft: Diese nie angeforderten Nebenwirkungen
sind im Simulator nur als „Unsupported action“ modelliert und dürfen deshalb
nicht als reine Protokollfehler durchrutschen.
Bloße Erfolgsmeldungen ohne erforderlichen Werkzeugaufruf bestehen nicht.
Freie Antworten werden gegen die vorhandenen Rubriken von demselben
Codex-Assistant bewertet; das ist keine unabhängige, blinde Bewertung.
Die beiden Seeds sind Wiederholungen derselben Aufgaben und korreliert.

## Vollständige Qualitätsmatrix

Jede Zelle bezieht sich auf 104 Beobachtungen. „Inhaltlich korrekt“ ignoriert
lediglich Emoji/Markdown-Verstöße gegen die gewünschte schlichte Sprachausgabe.
Der strenge Pass zählt diese ebenfalls als Fehler. Handlungserfolg muss in
beiden Fällen belegt sein. Die letzte Spalte zählt Fälle mit mindestens einem
ungefragten Aktionsversuch, nicht die Anzahl einzelner Aufrufe.

| Profil | Inhaltlich korrekt | Strenger Pass | Ungefragte Aktionen: Fälle / Aufrufe |
| --- | ---: | ---: | ---: |
| Q3 NoThink | 90 / 104 (86,5 %) | 90 / 104 | 6 / 17 |
| Q3 Low | 97 / 104 (93,3 %) | 93 / 104 | 3 / 9 |
| Q2 NoThink | 79 / 104 (76,0 %) | 76 / 104 | 17 / 29 |
| Q2 Low | 93 / 104 (89,4 %) | 91 / 104 | 6 / 8 |

Alle 208 Low-Beobachtungen enthalten echte `reasoning_content`-Ausgabe;
alle 208 NoThink-Beobachtungen enthalten keine. Die mediane gesamte
Ausgabetokenzahl je Aufgabe steigt bei Q3 von 74,5 auf 164, bei Q2 von
84,5 auf 171. Dies umfasst alle Modellrunden und die Denkphase; die API
liefert keinen separaten Reasoning-Tokenzähler.

Keine Beobachtung erreichte das Ausgabetokenlimit. Korrigierbare Protokoll- bzw.
Fixturefehler: Q3 NoThink neun, Q3 Low zwei, Q2 NoThink 21, Q2 Low sieben.
Diese Zählung kann sich mit ungefragten, vom Simulator nicht unterstützten
Nebenwirkungen überschneiden.

| Kategorie | Q3 NoThink → Low | Q2 NoThink → Low |
| --- | ---: | ---: |
| Einfache Aktionen (24) | 24 → 24 | 23 → 21 |
| Kombinierte/bedingte Aufträge (16) | 15 → 16 | 11 → 14 |
| Zustandsauskunft (24) | 23 → 21 | 23 → 22 |
| Rückfragen/unklare Aufträge (16) | 9 → 13 | 5 → 15 |
| Folgeaufträge (4) | 0 → 4 | 2 → 2 |
| Fehler/Teilresultate (8) | 7 → 7 | 3 → 7 |
| Rauschen/Stopp (12) | 12 → 12 | 12 → 12 |

Dies sind inhaltliche Passzahlen. Q3 Low gewinnt zehn zuvor gescheiterte
Beobachtungen, verliert aber drei zuvor korrekte; Q2 Low gewinnt 22 und verliert
acht. Die Wiederholungen sind korreliert und stammen aus einer kleinen
synthetischen Suite, deshalb sind die Prozentwerte kein allgemeines
Zuverlässigkeitsversprechen für den Haushalt.

Konkrete Unterschiede:

- Q3: „Nein, die im Wohnzimmer“ und „Etwas heller“ mit vorheriger Lampe im
  Gespräch funktionieren unter Low in 4/4 Fällen, unter NoThink in 0/4.
  NoThink behauptet beispielsweise 60 Prozent Helligkeit ohne Werkzeugaufruf.
- Q2: Bei unklaren Befehlen helfen Rückfragen deutlich. Ohne Denken werden
  zusätzlich nach Gerätefehlern ungefragte Hausdurchsagen versucht; Low zeigt
  diese konkrete Nebenwirkung nicht.
- Q3 und Q2: „Mach es gemütlicher“ bleibt mit Low teilweise ein Auslöser für
  ungefragte Änderungen. Bei Q2 Low kommen zudem beide Male ungefragte
  Zusatzaktionen beim einfachen Wohnzimmer-Deckenlichtauftrag vor.
- Mit Low werden Fensterfragen gelegentlich mit Rollostellungen beantwortet.
  Beim Personenstatus behauptet Q2 Low einmal, vorhandene Personen seien
  nicht verfügbar. Denken ersetzt keine korrekte Tool-Abfrage.

## Zusatzlatenz

Der gezielte warme Vergleich umfasst 24 Beobachtungen pro Arm, jeweils
zwölf Aufgaben mit zwei Seeds und umgekehrter Modusreihenfolge. Bei jedem
gewerteten Erstrequest wurden 6262–6303 Tokens wiederverwendet. Die Startzeit
des Containers und die Prime-Anfrage sind ausgeschlossen.

Die Latenzvergleiche verwenden nur Aufgaben, die **beide** Modi inhaltlich
korrekt abschließen. Der Folgeauftrag mit falscher Erfolgsmeldung ohne Aktion
wird dadurch nicht als vermeintlich besonders schneller NoThink-Erfolg gewertet.
Emoji/Markdown alleine schließen eine ansonsten korrekte Messung nicht aus.

| Profil | Gepaarte korrekte Aufgaben / davon mit Aktion | Median Mehrzeit bis erste Aktion | Median Mehrzeit bis finale Antwort | P95 Mehrzeit finale Antwort | Größte Mehrzeit finale Antwort |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q3 Low gegenüber NoThink | 22 / 16 | +0,38 s | +1,08 s | +2,65 s | +4,62 s |
| Q2 Low gegenüber NoThink | 19 / 13 | +0,53 s | +0,76 s | +1,54 s | +1,54 s |

Das sind Mediane der **fallweisen Differenzen**, nicht die Differenz zweier
Mediane. P95 verwendet den Rang `ceil(n × 0,95)`; bei diesen kleinen
Stichproben ist es kein stabil geschätzter Produktionstail. Die größte
zusätzliche Wartezeit vor der ersten Aktion betrug +3,51 s bei Q3 und +1,89 s
bei Q2.

Auf denselben korrekten Paaren lag die mediane finale Antwortzeit bei Q3 bei
2,12 s ohne Denken und 3,10 s mit Low; bei Q2 bei 1,45 und 2,09 s. Diese
absoluten Mediane lassen sich nicht zur obigen medianen Differenz subtrahieren.
Die warmen Kontrollaufgaben waren bei Q3 in 22/24 NoThink- und 24/24 Low-Fällen
korrekt; bei Q2 in 21/24 beziehungsweise 22/24 Fällen.

Ausreißer bleiben: Q2 Low brauchte für „Wohnzimmerlicht aus, Leselampe
unverändert“ einmal 11,58 s. Dieser Fall war zwar korrekt, sein NoThink-Paar
versuchte aber eine ungefragte Aktion und ist daher vom korrekten Paarvergleich
ausgeschlossen. Die Paartabelle beschreibt korrekt erledigte Aufgaben und
verschweigt solche Nicht-Paare nicht.

Die vollständige Qualitätssuite enthält komplexere Wünsche und längere
Reparaturketten. Dort lag die P95 der zusätzlichen Abschlusszeit bei Q3 bei
+5,80 s und bei Q2 bei +3,56 s; wegen der unterschiedlichen Modusreihenfolge
sind diese Werte ergänzend zu lesen, nicht als gleich kontrollierte Warmmessung.

**Einschätzung:** Q3 Low ist einen gezielten Alltagstest wert, wenn rund eine
Sekunde mehr bis zur gesprochenen Bestätigung akzeptabel ist. Der messbare
Gewinn bei Folgeaufträgen und Rückfragen rechtfertigt diesen Aufschlag für
mich eher als bei einfachen Schaltbefehlen, die bereits ohne Denken sehr gut
funktionieren. Q2 Low verbessert sich stärker gegenüber seiner eigenen
schwächeren Basis, erreicht aber weder die Qualität noch die niedrige Zahl
ungefragter Aktionen von Q3 Low. Das getestete Q2-Profil bietet außerdem keine
Bildverarbeitung. Der tatsächliche Assist/Hermes-Pfad muss separat geprüft
werden; Denken allein behebt keine fehlenden oder falsch transportierten
Werkzeugkontexte. Die Produktionsvorgabe wurde für diesen Benchmark nicht
auf Low umgestellt.

## Prefill und Decode

Alle gewerteten kalten Rechenanfragen meldeten **null wiederverwendete
Prompttokens** und antworteten korrekt mit `42`. Die native Prefill-Rate und
Zeit bis zur sichtbaren Antwort sind unterschiedliche Messgrößen.

| Quantisierung / Eingabe | Proben je Modus | Native Prefill-Rate NoThink → Low (Tokens/s) | Erster sichtbarer Text NoThink → Low |
| --- | ---: | ---: | ---: |
| Q3 / 4K | 3 | 986 → 896 | 4,25 → 5,10 s |
| Q3 / 16K | 3 | 1057 → 954 | 15,75 → 18,07 s |
| Q3 / 64K | 3 | 1213 → 1176 | 54,44 → 56,65 s |
| Q3 / 128000 | 1 | 1806 → 1332 | 71,32 → 97,19 s |
| Q2 / 4K | 1 | 1220 → 1245 | 3,44 → 3,73 s |
| Q2 / 16K | 1 | 1744 → 1734 | 9,48 → 9,93 s |
| Q2 / 64K | 1 | 2269 → 2260 | 29,03 → 29,50 s |

Q3s einzelne 128K-Probe ist **kein Nachweis für 26 Sekunden Denkaufwand**.
Die native Promptzeit betrug bereits 70,91 s ohne Denken und 96,17 s mit Low.
Die Denk-/Ausgabephase unter Low dauerte dagegen nur rund 0,62 s. Strata
meldete unterschiedliche Expertencache-Trefferraten (0,993 gegenüber 0,985)
und `file_mb` (33,6 gegenüber 958,5). Das ist eine Expertentransfermetrik,
kein Beleg für genau diese Menge physischer Datenträger-I/O.
Bei nur einer Probe und verschiedenem Cachezustand lässt sich der große
Prefill-Unterschied nicht eindeutig dem angeforderten Denkmodus zuschreiben.
Die ergänzenden Q3-64K-Aufwärmungen nach dem Q2-Profilwechsel dauerten sogar
106,82 beziehungsweise 116,27 s bis zum sichtbaren Text und zeigen die
Streuung durch den Betriebs-/Cachezustand. Aufwärmungen sind nicht in den
Medianen der Tabelle enthalten.

### Warmer 16K-Präfix

Nach dem Prime wird dreimal unmittelbar derselbe Prompt wiederholt. Die
folgenden Werte sind Mediane; die Rechenantwort ist in allen Fällen korrekt.

| Profil | Wiederverwendete Tokens NoThink / Low | Erster Token NoThink → Low | Erster sichtbarer Text NoThink → Low |
| --- | ---: | ---: | ---: |
| Q3 | 16453 / 16480 | 0,155 → 0,190 s | 0,155 → 0,667 s |
| Q2 | 16452 / 16477 | 0,085 → 0,078 s | 0,085 → 0,440 s |

Die Differenz zwischen erstem Denk-Token und sichtbarer Antwort bleibt mit
warmem Prompt bestehen. Q2s zusätzlicher Konversationscache ist deaktiviert,
aber auch dieses Profil kann den zuletzt verwendeten Präfix wiederverwenden.
Die Tabelle prüft unmittelbare Wiederholung, nicht vier wechselnde Gespräche
oder die komplexere Tool-Rundenkette des HA-Latenztests.

### Decode mit 1024 Ausgabetokens

Jeweils eine kalte 4K-Probe, langer deutscher Artikel, exakt 1024 Ausgabetokens
und `finish_reason: length`. Unter Low zählen Denk- und sichtbare Tokens zum
Durchsatz. In allen Proben wurden mindestens 100 sichtbare Wörter erzeugt.

| Profil | Decode NoThink → Low | Erster sichtbarer Text NoThink → Low |
| --- | ---: | ---: |
| Q3 | 61,94 → 63,35 Tokens/s | 4,52 → 11,52 s |
| Q2 | 82,27 → 90,53 Tokens/s | 3,42 → 4,24 s |

Die einzelne zusätzliche Q3-Low-64K-Probe ergab 57,77 Tokens/s. Für sie wurde
kein neuer passender NoThink-Kontrollarm erhoben.

Die höhere beobachtete Low-Rate ist kein Nachweis, dass Denken das Decoding
beschleunigt: Text und Tokenfolge unterscheiden sich, die Stichprobe ist klein
und Temperatur/Cache sind nicht vollständig kontrolliert. Für kurze
HA-Antworten erklärt die größere Tokenzahl die Mehrlatenz besser als eine
allgemeine Verschlechterung der reinen Generierungsrate. Die Langkontext-
Rechenaufgabe verifiziert das Serving und die korrekte Endantwort, keine
Langkontext-Suche oder HA-Qualität bei 64K.

## Wiederherstellung und Artefakte

Das vor dem Test laufende Profil
`Qwen3.8-Flash-Next-IQ3_XXS-Strata` wurde nach jeder Stufe und zum Abschluss
wieder geladen. Der finale echte Chatrequest mit NoThink ergab `42` ohne
Reasoning-Ausgabe. Der Bildencoder meldet `enabled: true, available: true`;
das Containergerätelimit enthält ausschließlich die beiden 3090-UUIDs.
`oom`, `oom_kill` und Dockers `OOMKilled` sind null beziehungsweise falsch.

Embedding, Qwen3-TTS und Whisper/CrispASR stehen weiterhin auf `ready`.
Eine tatsächliche Embedding-Anfrage über LlamaSwap lieferte einen
1024-dimensionalen Vektor. ASR/TTS wurden nicht gestoppt oder umkonfiguriert;
eine neue Audiokettenmessung war nicht Teil dieses Tests. GPU2 wurde nicht dem
LLM-Container zugewiesen. Die Home-/Hermes-Aliase behalten ihre vorhandenen
NoThink-Vorgaben. Kein Deployment und kein Wechsel des Produktionsdefaults
auf Low wurde vorgenommen.

- [Rohdaten und Bewertungsledger](../experiments/strata/reasoning-results-2026-10-06/):
  vier `*-ha.jsonl` mit jeweils 104 Aufgaben, vier `*-latency.jsonl` mit jeweils
  24 Aufgaben, Geschwindigkeitsspuren und Runtime-Snapshots.
- [Qualitäts-/Geschwindigkeitsübersicht](../experiments/strata/reasoning-results-2026-10-06/summary.json)
  und [warme Latenzpaare](../experiments/strata/reasoning-results-2026-10-06/warm-summary.json).
- [Explizite Textbewertungen](../experiments/strata/reasoning-results-2026-10-06/text-reviews.json),
  [Methoden-/Ablaufmetadaten](../experiments/strata/reasoning-results-2026-10-06/method.json)
  und [finale Funktionsprüfung](../experiments/strata/reasoning-results-2026-10-06/final-verification.json).
- [Runner](../experiments/strata/benchmark_reasoning.py) und
  [Auswertung](../experiments/strata/summarize_reasoning.py).

Die Module `benchmark_flash_prefill.py`, `benchmark_qwen_serving.py`,
`benchmark_ha_tool_quality.py` und `evaluate_flash_quality.py` müssen neben
dem Runner liegen oder über `PYTHONPATH` erreichbar sein. Die verwendeten
Toolschemas, Cases und der Systemprompt sind im Artefaktordner gespeichert;
der gemeinsame Textkorpus ist als `prefill-corpus.json` im Artefaktordner
archiviert, liegt zusätzlich auf dem GPU-Host unter
`/tmp/strata-prefill-corpus.json` und wird über `--corpus` angegeben.
Neue Qualitätsläufe brauchen ein neues Ausgabe-Verzeichnis.
Die Latenzstufe ist mit `--stage latency --latency-seed 20261006` und danach
`20261007` reproduzierbar. Die ergänzende Geschwindigkeitsstufe verwendet
`--stage speed --speed-repetitions 1 --speed-lengths 4096,16384,65536
--decode-lengths 4096`; bereits gemessene Q3-Proben werden beim Wiederaufnehmen
übersprungen. Der Runner stellt das zuvor laufende Profil im `finally` wieder
her; er setzt dafür ein bereits laufendes Q2- oder Q3-Profil voraus.

Prüfungen: Streaming-Zeit-/Reasoning-Regressionen,
HA-Selektor-/Aktionsregressionen, protokollierte ungefragte Hausdurchsage,
vollständige Bewertungszuordnung, Python-Kompilierung und `git diff --check`.


