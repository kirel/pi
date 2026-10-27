# Strata Q3 als multimodaler Home-Assistant-/Local-Hermes-Test

Strata IQ3_XXS ist für den lokalen Testbetrieb eingerichtet. Seit dem
6. Oktober zeigen `home-ha` und `home-hermes` auf das Basisprofil
`Qwen3.8-Flash-Next-IQ3_XXS-Strata` mit Low Reasoning. `home-vision` und
`home-smart` verwenden dessen explizite NoThink-Variante. Home Assistant verwendet diese
Aliase bereits; seine Integrationseinträge mussten nicht verändert werden.
Local Hermes bleibt beim Provider `custom:kirelabs-litellm`, erhält aber die
passende Kontextgrenze von 131072 Tokens. Die bisherigen 27B-Profile bleiben
als Rückweg verfügbar. `home` und `home-fast` zeigen weiterhin auf 27B;
Anfragen an diese Aliase können das LLM wechseln und den Strata-Cache verlieren.

Seit dem 11. Oktober läuft [Strata 0.1.43, aktualisiert ohne Benchmark](strata-update-2026-10-11.md).
Expert Tail Skip bleibt aktiv; das [Dashboard](https://strata.kirelabs.org)
wurde beim vorherigen [Update auf 0.1.42](strata-update-2026-10-10.md) eingerichtet.
Der [Geschwindigkeitsvergleich vom 9. Oktober](strata-update-benchmark-2026-10-09.md)
beschreibt den vorherigen Stand 0.1.41.
Der [Cache-Benchmark mit 0.1.40.1](strata-cache-benchmark-2026-10-07.md) bestätigt, dass
Tail-/Message-Boundary-Checkpoints den aktuellen Layer-Split ausschließen.
Der bestehende native Gesprächscache bleibt aktiv.

## Alltagstest mit Q3 Low ab 6. Oktober

Nach dem [Low/NoThink-Benchmark](strata-low-reasoning-benchmark-2026-10-06.md)
startet der vom Nutzer freigegebene Alltagstest mit der kleinsten aktivierten
Denkstufe. `group_vars/all/llms.yml` ordnet `home-ha` und `home-hermes` dem
Q3-Basisprofil zu und legt dessen native LiteLLM-Standardparameter fest:
`reasoning_effort: low`, `chat_template_kwargs.enable_thinking: true`,
Temperatur 0,7, top-p 0,8 und Presence-Penalty 1,5. Explizite Clientparameter
können die Standardwerte weiterhin überschreiben.

Local Hermes hatte bereits `agent.reasoning_effort: low`. Seine bisherige
NoThink-Modellzuordnung hatte das Denken dennoch ausgeschaltet. Die Änderung
benötigt daher weder einen neuen Hermes-Provider noch eine zusätzliche
LlamaSwap-Instanz. Der vorhandene Q3-Prozess, Bildencoder, 2-GiB-/Vier-Slot-
Cache und die auf beiden 3090 geladenen Begleitdienste bleiben bestehen.

Ausgerollt wurde nur die Proxy-Konfiguration:

```sh
uv run ansible-playbook setup.yml --tags llm-tools-config --limit homelab
```

Syntaxcheck und Check-Modus liefen erfolgreich, LiteLLM meldet nach dem Reload
`healthy` und `db: connected`. Die effektiv gerenderte Konfiguration setzt Low;
die explizite NoThink-Variante behält `none` und `enable_thinking: false`.
Anfragen mit den tatsächlichen eingeschränkten HA-/Hermes-Schlüsseln liefern
über `home-ha` und `home-hermes` Denktext. Ein expliziter NoThink-Request
über `home-ha` und die vorhandene NoThink-Variante liefern keinen Denktext.
Es wurden keine Modell- oder MCP-Berechtigungen erweitert.

Beide echten HA-Konversationsagenten wurden mit Rechenfragen geprüft:
`conversation.home_nano_ai_agent` und das bevorzugte Assist-Profil
`conversation.local_hermes_hermes_local_ai_agent`. Alle Antworten waren `42`.
Hermes protokolliert für den Test `model: home-hermes` und
`reasoning_config: {enabled: true, effort: low}`; die kontrollierte Testsitzung
enthält keine Werkzeugaufrufe. Die Testfragen verändern keine Geräte.

Die Anwendungslatenz ist nicht die Zusatzlatenz des Modellbenchmarks:
Die ersten kalten Anfragen benötigten 33,39 s direkt über HA beziehungsweise
47,65 s über Local Hermes. Warme Folgefragen lagen bei 2,70 s beziehungsweise
7,83–7,87 s. Bei Local Hermes wurden jeweils 16384 Tokens wiederverwendet,
aber noch 890 beziehungsweise 934 Tokens verarbeitet. Deren Prefill dauerte
6,68 beziehungsweise 7,07 s; die anschließende Denk-/Ausgabephase nur
0,53 beziehungsweise 0,27 s. Der verbleibende Prefill-Aufwand ist damit ein
konkreter Ausgangspunkt für die Alltagserprobung, kein gemessener
achtsekündiger Reasoning-Aufschlag. ASR und TTS sind in diesen Textzeiten
nicht enthalten. Die Bildfunktion blieb aktiviert; sie wurde bei dieser
reinen Reasoning-Umstellung nicht erneut geprüft.

Für den Nutzertest einen neuen Assist-Dialog beginnen, damit frühere falsche
Erfolgsmeldungen den Verlauf nicht beeinflussen. Zum Rückweg auf NoThink
`home-ha` und `home-hermes` wieder dem vorhandenen
`Qwen3.8-Flash-Next-IQ3_XXS-Strata-nothink` zuordnen und denselben scoped Deploy
ausführen. Das ist ein Request-Moduswechsel desselben GPU-Backends.

[Aktivierungsnachweis und Messwerte](../experiments/strata/reasoning-results-2026-10-06/everyday-low-activation.json).

## Update auf 0.1.39 am 5. Oktober

Strata wurde auf Release-Commit `6f32ec070f23ced9f50e704d854d775da52591ab`
aktualisiert und mit dem unveränderten Upstream-Dockerfile einschließlich
Bild-Encoder gebaut. Laufendes Image:
`kirelabs/strata:6f32ec070f23-sm86-sm120-vision`. Der Backendstatus bestätigt
Engine **0.1.39**, Vision verfügbar, 131072 Tokens und eine gleichzeitig
bediente Anfrage. Q3, NoThink, beide 3090, 28 GiB Containerlimit ohne
zusätzlichen Swap und 4608 MiB VRAM-Reserve bleiben die Grundlage.

Die native Gesprächsparkierung ist jetzt mit `--conversation-cache-mib 2048`,
`--conversation-cache-slots 4` und `--conversation-cache-min-free-mib 6144`
aktiviert. Der Launcher setzt diese Argumente aus den Q3-Profileinstellungen
idempotent in der persistenten JSON-Konfiguration. Die maximal 2 GiB Cache
liegen innerhalb des bestehenden Containerlimits; der physische RAM-Schutz
verwendet Host-Telemetrie. Snapshot-Evictions unter diesem kleinen Budget sind
erwartet. Es werden weder ein weiteres Modell noch zusätzliche GPU-Caches
angelegt. Die native [Gesprächsparkierung](https://github.com/Niko1221/Strata/blob/v0.1.39/docs/DETAILS.md)
ist hier der gewählte Weg; paralleles Decoding ist nicht aktiviert.

Zusätzlich setzt Ansible ausschließlich für Local Hermes
`auxiliary.title_generation.enabled: false`. Sitzungstitel werden weiter
sofort aus dem ersten Text abgeleitet, aber nicht durch eine zusätzliche
Hintergrundanfrage verfeinert. Das Verhalten wurde gegen die installierte
Hermes-Implementierung und nach dem Neustart verifiziert. Die bisher getestete
LiteLLM-Responses-to-Chat-Brücke bleibt aktiv; Stratas neue native Responses-API
wurde nicht zum Anwendungsweg gemacht. Cloud-Hermes wurde nicht verändert.

### Messungen und Funktionsprüfung nach dem Update

Alle Proben verwenden synthetische Eingaben. Die 16K-Probe wechselt zwischen
einem langen und einem kurzen, unabhängigen Gespräch. In der neuen Version
braucht der erste lange Prompt **19,89 s** bis zum ersten Text; nach dem
jeweiligen kurzen Gespräch dauern die Wiederholungen **0,207 / 0,179 s**.
Dabei werden jeweils **16421 von 16428 Prompttokens** wiederverwendet.
Der native Monitor meldet tatsächliche Parkierungen und Wiederherstellungen.
Eine zusätzliche Prüfung zweier verschiedener Testzahlen (`42` / `17`)
bestätigt korrekte Folgeantworten bei wechselnden, wiederhergestellten Kontexten.

Die Ausgangsprobe mit 0.1.38 las dieselben 16K-Prompts bei jedem Wechsel
vollständig und benötigte etwa 31 s. Während dieser Ausgangsprobe lief bereits
der Container-Build auf der CPU: Die Zeitdifferenz isoliert deshalb weder den
Versionsgewinn noch den Cache-Effekt. Der belastbare Cache-Beleg ist die
Wiederverwendung im neuen Backend und dessen eigener Kalt/Warm-Vergleich.
Neue einzelne kalte Proben: 4K **12,07 s**, 16K **12,86 s**, 64K **51,88 s**
bis zum ersten Text. Keine neue 128K- oder anhaltende Decode-Vergleichsmessung.

| Echter Anwendungsweg | Ergebnis nach dem Update |
| --- | --- |
| HA über `home-ha`, zwei unterschiedliche Mathematikfragen | korrekt `42`, 0,75 / 0,56 s; 8319 Präfixtokens wiederverwendet |
| HA über Local Hermes, zwei unterschiedliche Mathematikfragen | korrekt `42`, 2,93 / 2,73 s; 16384 Präfixtokens wiederverwendet |
| Hermes Bild: Formen/Farben/Positionen | korrekt, 46,13 s; erste Anfrage bleibt langsam |
| Hermes Bild: OCR | korrekt `4827`, 5,69 s |
| HA `ai_task.generate_data` mit Bild | korrekt `4827`, 5,62 s; temporäre Mediendatei entfernt |
| Embedding, direkt über LlamaSwap | 1024 Dimensionen, 0,095 s |
| TTS über LiteLLM | gültige WAV, 1,32 s |
| ASR über LiteLLM mit dieser WAV | korrekter Testsatz, 0,29 s |

Die unterschiedlichen Mathematikfragen verhindern die Interpretation einer
identischen, möglicherweise vollständig zwischengespeicherten Antwort als
Nachweis für Promptcache-Nutzung. Backend-Telemetrie bestätigt die angegebenen
Präfixtokens. Die zusätzlich gespeicherten identischen HA-Wiederholungen sind
Funktionstests, kein isolierter Promptcache-Benchmark. Die Zeiten betreffen
Textantworten, nicht hörbare Sprachausgabe oder ausgeführte Geräteaktionen.

Die sechs simulierten HA-Regressionsfälle erreichen die gewünschten Endzustände;
**5/6 bestehen die strenge Prüfung**. `compound-0` verwendet zunächst den
ungültigen `device_class`-Enumwert `light`, korrigiert diesen nach dem Toolfehler
und führt anschließend die gewünschte Aktion aus. Kein ungewollter
Änderungsversuch in dieser kleinen Stichprobe. Dies ist kein Beleg für die
Behebung der früheren falschen Aktionen und ersetzt den vollständigen
104-Beobachtungen-Vergleich nicht. Keine echten Geräte wurden durch diese
Regression geschaltet.

Abschlussstand **2026-10-05T19:48:22Z**: Q3, Embedding, ASR und TTS `ready`;
GPU0 19908 MiB, GPU1 20016 MiB, jeweils von 24576 MiB, etwa 4,56 / 4,45 GiB frei.
Der Q3-Container erreicht mit Dateicache und Gesprächsparkierung das 28-GiB-Limit;
Reclaim-Ereignisse sind vorhanden, OOM/OOM-Kill und Container-Swap bleiben null.
Der Gesprächscache ist aktiv, auf 2048 MiB begrenzt und weist 10 Restores aus.
GPU2 gehört nicht zum Docker-DeviceRequest; ihre laufende andere Last wurde
nicht verändert. Die Funktionsproben belegen Koexistenz, keinen Dauerlasttest.

[Rohdaten zum Update](../experiments/strata/update-results-2026-10-05/),
[reproduzierbare Prefill-/Wechselprobe](../experiments/strata/probe_update.py)
und [Launcher-Konfigurationscheck](../experiments/strata/test_launcher.py).
Die Ansible-Deploys verwenden weiterhin die unten dokumentierten scoped Tags.
Vorheriges Image und Ausgangskonfiguration bleiben für einen Rückweg erhalten.
`home`/`home-fast` können weiterhin 27B laden und dabei Stratas GPU-Kontext
verlieren; diese Alias-Zuordnung wurde beim Update nicht geändert.

## Einrichtung des ursprünglichen Tests (0.1.38)

- Strata-Revision bleibt `99f3dbd0b21d1401b3769e0c0d963913607f380b`, Engine 0.1.38.
- Native GSQ-RCO IQ3_XXS, mmap-Experten, INT8-KV, MTP 4, 128K Kontextgrenze.
- Neuer upstream Container mit `BUILD_VISION=1`, Image
  `kirelabs/strata:99f3dbd0b21d-sm86-sm120-vision`.
- Q3 verwendet `STRATA_VISION=gpu`; der native BF16-Projektor wird durch
  Stratas Setup installiert. Vision-Konfiguration und bisherige Textkonfiguration
  liegen getrennt im persistenten Datenverzeichnis.
- Zwei RTX 3090, 28 GiB Containerbudget ohne zusätzlichen Swap und
  `--vram-reserve-mib 4608`. Die RTX 5060 Ti wird nicht für diesen Test verwendet.
- Die native Host-Freigabe `STRATA_ALLOWED_HOSTS=ailab-ubuntu.lan` erlaubt den
  von LlamaSwap weitergereichten Hostnamen. Ohne diese Einstellung waren
  direkte Loopback-Anfragen erfolgreich, Anwendungsanfragen wurden mit 403
  abgewiesen. Es wurde kein Wildcard-Host freigegeben.
- Die gepinnte Strata-Version bietet Chat Completions, Hermes verwendet
  Responses. `use_chat_completions_api: true` aktiviert die vorhandene
  [LiteLLM-Brücke](https://github.com/BerriAI/litellm-docs/blob/main/docs/response_api.md).
  Die NoThink-Variante setzt `reasoning_effort: none` und
  `chat_template_kwargs.enable_thinking: false`.

Native [Strata-Bildunterstützung](https://github.com/Niko1221/Strata) wurde genutzt;
es gibt keine Änderungen an Strata oder Hermes. Sprache läuft weiterhin über
die separaten ASR-/TTS-Modelle, nicht als direkter Audio-Input in Q3.

## Funktion und Qualität

Als Bildfixture dienen ein roter Kreis oben links, ein blaues Rechteck unten
links, ein grünes Dreieck rechts und die Zahl **4827**. Alle Geräteaktionen
wurden simuliert; echte HA-Geräte wurden nicht geschaltet. Ein temporäres
Bild in HAs Media-Verzeichnis wurde nach dem AI-Task-Test entfernt.

| Prüfung | Ergebnis |
| --- | --- |
| Q3 direkt: Formen, Farben, Positionen | korrekt |
| Q3 direkt: OCR | exakt `4827` |
| Hermes API: Bildanhang | Formen/Farben/Positionen korrekt; zusätzliche Größenbehauptung falsch |
| Hermes API: OCR | exakt `4827` |
| HA Conversation über `home-ha`: sechs mal sieben | korrekt `42` |
| HA Conversation über Local Hermes: sechs mal sieben | korrekt `42` |
| Echter HA `ai_task.generate_data` mit Bildanhang über `home-vision` | exakt `4827` |
| Sechs simulierte HA-Aufträge, Seed 20261004 | 6/6; einschließlich Zielausschluss, Zeitangabe und Widerruf |
| Echter lesender Hermes-MCP-Auftrag, erster Lauf | beendet; `GetLiveContext` erreicht, ein Tool-Fehler und Wiederholungen |
| Derselbe lesende Hermes-Auftrag, zweiter Lauf | bestanden; ein `GetLiveContext`, keine Tool-Fehler |
| Embedding über LiteLLM | 1024 Dimensionen |
| TTS über LiteLLM, `de-host` | gültige WAV, 109404 Bytes |
| ASR mit der Test-WAV | „Das ist ein kurzer Funktionstest.“ |

Hermes beschrieb den Kreis fälschlich als flächengrößte Form. Tatsächlich ist
das Dreieck größer. Der automatische Bildcheck prüft nur die verlangten
Form-/Farbmerkmale und die Zahl; sein positives Ergebnis ist kein Nachweis,
dass alle zusätzlichen Aussagen stimmen.

Der erste echte MCP-Lauf dauerte **29,97 s** und hatte sechs Tool-Ereignisse.
Der Fehler war ein unzulässiger Batch im Hermes-Wrapper `tool_call`:
`Local tools require one entry per tool_call; mixed and multi-local batches are not supported.`
Das Modell erholte sich und lieferte eine Antwort. Der zweite Lauf dauerte
**11,38 s**, hatte genau einen erfolgreichen `GetLiveContext`-Aufruf und
keinen Tool-Fehler. Da sich die Anzahl der Modell-/Tool-Runden unterscheidet,
ist das kein isolierter Vergleich der Cache-Geschwindigkeit.

Die erfolgreichen Hermes-Bildproben dauerten **37,56 / 38,84 s**. Die beiden
HA-Conversation-Proben dauerten **21,52 / 28,13 s**, der HA-Bildauftrag
**12,88 s**. Einige Anfragen liefen zeitlich überlappend; Strata bedient in
dieser Revision jeweils eine Anfrage und stellt weitere an. Diese Werte sind
Funktionsmessungen, kein kontrollierter Geschwindigkeitsvergleich mit 27B.
Die erste direkte Bildanfrage einschließlich Backendwechsel/Setup dauerte
191,22 s; diese Zeit darf nicht als reine Bild-Inferenzzeit verwendet werden.

Die sechs simulierten Fälle ersetzen nicht den
[vollständigen Q2/Q3/27B-Vergleich](strata-q2-q3-27b-benchmark-2026-10-04.md).
Die dort beobachteten ungewollten Aktionen wurden durch diese Einrichtung
nicht behoben. Ebenso wurde der lange 64K-/128K-Benchmark nicht mit aktiviertem
Vision-Encoder wiederholt. Die 128K sind hier die konfigurierte Grenze.

## Ressourcen und Nachweise

Live-Snapshot: **2026-10-04T23:09:31Z**. Q3, Embedding, ASR und TTS melden
`ready`; Vision meldet `enabled=true`, `available=true`, ohne Fehler.
GPU0 nutzt 19846 MiB, GPU1 19952 MiB von jeweils 24576 MiB; frei sind
ungefähr **4,62 / 4,52 GiB**. GPU2 bleibt bei 527 MiB.
Der Q3-Cgroup-Peak liegt bei ungefähr **24,89 GiB**, Swap und OOM-Zähler bei null.
Das belegt Koexistenz und erfolgreiche Zusatzmodell-Anfragen, keinen
anhaltenden Lasttest mit allen Modellen gleichzeitig.

Die [Rohdaten](../experiments/strata/multimodal-results-2026-10-05/) enthalten
Bildfixture, direkte Antworten, echte Hermes-Bildantworten, HA-Routentests,
simulierte Tool-Tests, beide MCP-Läufe und den Ressourcen-Snapshot. Frühere
403-/404-Versuche liegen getrennt unter `exploratory/`.
Private HA-Zustandsantworten und Zugangsdaten wurden nicht abgelegt.
Der [Bild-Probe-Runner](../experiments/strata/probe_multimodal.py) prüft die
Antworten und liefert bei einem Fehlversuch einen Fehlerstatus.

## Deploy und Rückweg

Scoped Deploys verwenden die bestehenden Ansible-Rollen:

```sh
uv run ansible-playbook setup.yml --tags strata-test --limit ailab_ubuntus
uv run ansible-playbook setup.yml --tags llm-tools-config --limit homelab
uv run ansible-playbook setup.yml --tags hermes-config --limit ailab_ubuntus \
  -e '{"hermes_docker_deploy_services":["hermes-local"]}'
```

Für den Rückweg in `group_vars/all/llms.yml` `home-ha`/`home-hermes` wieder auf
`Qwen3.8-27B-Instruct-AutoRound-vLLM-nothink`, `home-smart`/`home-vision` auf
`Qwen3.8-27B-Instruct-AutoRound-vLLM` setzen. In `group_vars/ailab_ubuntus.yml`
Local Hermes wieder `context_length: "{{ llama_native_context_qwen38 }}"`
geben. Die drei scoped Deploys ausführen und Local Hermes neu starten, damit
sein Gateway die geänderte Kontextgrenze einliest. Danach tatsächliche
Completion, HA-/Hermes-Route sowie Embedding, ASR und TTS prüfen.

Q3 bleibt für den gewünschten Nutzertest geladen. Es wurde nicht automatisch
auf 27B zurückgestellt und nichts committet oder gepusht.
