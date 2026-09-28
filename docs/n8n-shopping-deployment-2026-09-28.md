# Optimierte Einkaufslisten-Tools: Deployment und Benchmark

`shopping_snapshot` und `shopping_apply` laufen in n8n und sind über LiteLLM als MCP-Server `shopping` eingebunden. Beide Server — `shopping` und der weiterhin verfügbare offizielle `todoist` — gehören zur bestehenden Capability-Gruppe `shopping`. Die bisherigen n8n-Einkaufslisten-Agenten bleiben deaktiviert.

## Deployment

- MCP-Katalog: `roles/llm_tools/defaults/main.yml`, Server `shopping`, HTTP-Endpunkt `https://n8n.kirelabs.org/mcp/shopping-experiment`. Kein neuer Container oder Proxy-Service.
- Authentifizierung: dediziertes n8n-Bearer-Credential, Client-Geheimnis verschlüsselt in `group_vars/all/shopping_mcp.yml`. Kein Credential-Inhalt im Workflow-Export.
- Tool-Profil: `hermes_mcp_tool_profiles.shopping.shopping` erlaubt nur `shopping_snapshot` und `shopping_apply`; die sieben offiziellen Todoist-Tools bleiben erhalten.
- Ein eingeschränkter Schlüssel mit `shopping` sah beide Tools und konnte lesen. Ein Schlüssel nur mit `photos` sah keines und wurde auch bei direktem Aufruf abgewiesen. Temporäre Testschlüssel wurden gelöscht. Local Hermes wurde mit seinem echten Schlüssel getestet.
- Workflow-Code und reproduzierbarer Publisher: `scripts/shopping/logic.js`, `scripts/shopping/deploy.py`. Export der tatsächlich publizierten Konfiguration: `scripts/shopping/workflows.json`.
- Der Publisher aktualisiert ausschließlich die drei bekannten Einkaufslisten-Workflows über den bestehenden n8n-MCP. IDs und Credential-Referenzen gelten für diese Instanz; beim Umzug müssen sie angepasst werden.

```bash
node scripts/shopping/test_logic.js
python3 scripts/shopping/deploy.py
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab
```

Katalogänderungen werden mit Ansible deployt. Reine Workflow-Änderungen benötigen nur den Publisher; sie erfordern keinen LiteLLM-Image-Build. Bei geändertem Tool-Katalog muss Hermes gegebenenfalls seine MCP-Verbindung neu laden. Ein nötiger Container-Neustart erfolgt mit `sudo docker compose -f /opt/hermes-agents/docker-compose.yml restart hermes-local`, nicht mit einem unvollständig parametrisierten `docker_container`-Aufruf.

Workflows: [MCP-Endpunkt](https://n8n.kirelabs.org/workflow/iwne0jSsKHaOLMj0), [Snapshot](https://n8n.kirelabs.org/workflow/DvIUXUvO0fGnXseG), [Apply und Verifikation](https://n8n.kirelabs.org/workflow/woGpVPKNAKntvUJY).

## Verhalten

Hermes entscheidet anhand eines vollständigen Snapshots über Produkte, Varianten, Sektionen und Dubletten. Ein strukturierter Apply-Aufruf führt bis zu 25 betroffene Aufgaben aus. Unterstützt sind `add`, `update`, `move`, `complete` und `merge`. Sprache und semantische Zuordnung bleiben beim Modell; n8n enthält keinen weiteren LLM-Agenten.

Das Projekt ist fest auf `6Jhc7FCRmrMQPgW7` beschränkt. Aktuelle Aufgaben werden vor dem Schreiben gegen die mitgelieferten erwarteten Werte geprüft. Sektionen werden anhand ihres aktuellen Namens aufgelöst. Wiederkehrende Aufgaben, Unteraufgaben, Eltern mit Unteraufgaben und organisatorische Überschriften werden abgewiesen und können bei entsprechender Nutzerabsicht über die offiziellen Tools bearbeitet werden. Endgültiges Löschen ist kein optimiertes Tool.

Jeder Snapshot liefert eine eindeutige `request_id`, die Hermes für den anschließenden Apply-Aufruf übernimmt. Dieselbe ID darf nur für eine identische Wiederholung verwendet werden.

Änderungen nutzen [Todoists Sync-API](https://developer.todoist.com/api/v1/) mit stabilen Command-IDs aus Anfrage-ID und Operationsindex. Es gibt keine blinden HTTP-Schreibwiederholungen. Danach wird die Liste vollständig gelesen und der tatsächliche Zustand pro Artikel geprüft. Bei Dubletten werden zuerst sämtliche Beschreibungen am Überlebenden gespeichert und verifiziert; erst dann werden die Dubletten abgehakt und erneut geprüft. Gemischte Add/Merge-Batches behalten die ID-Zuordnung aus dem ersten Schreibschritt.

Ein atomar angelegtes Verzeichnis `/tmp/data/shopping-apply-lock` serialisiert Schreibvorgänge dieses Workflows. Ein zweiter Aufruf erhält `busy`. Bei einem Prozessabbruch bleibt die Sperre absichtlich bestehen: zuerst den gespeicherten n8n-Execution-Owner prüfen und sicherstellen, dass er beendet ist; erst dann die Sperre entfernen. Es gibt keine unsichere zeitbasierte Übernahme. Direkte Todoist-Clients nehmen an dieser Sperre nicht teil: Prüfungen und Readback sind keine globale Transaktion und verhindern nicht jede externe Race Condition.

Ergebnisse: `verified`/`already_present` dürfen bestätigt werden. `conflict` vor dem ersten Schreibschritt bedeutet keine Änderungen aus dieser Anfrage. `uncertain`, `partial` oder `failed` benötigen Zustandsabgleich; erfolgreiche Teiloperationen dürfen nicht wiederholt werden. Ein unbekannter Ausgang darf nicht durch einen Wechsel zum offiziellen MCP blind erneut geschrieben werden.

Der gemeinsame Skill `/home/daniel/projects/agent-skills/skills/family/einkaufsliste/SKILL.md` ist auf Version 4.0.1 aktualisiert und im lokalen Container sichtbar. Der normale Weg lädt nur den Hauptskill. `references/official-todoist.md` enthält die bisherige Anleitung für explizite Sonderfälle oder fehlende optimierte Tools vor einem Schreibversuch. Der Patches-Skill bleibt unverändert.

## Gemessene Werkzeuglaufzeit

Drei Durchläufe je Szenario und Variante, Reihenfolge pro Zyklus gewechselt. Beide Wege liefen aus `hermes-local` über denselben LiteLLM-Endpunkt mit demselben Schlüssel. Gemessen wurden Lesen, Schreiben und Verifikation; keine Modellzeit, STT oder TTS. Bereits vorhandene Artikel benötigen in beiden Varianten keinen Schreibaufruf. Der offizielle Ablauf folgt dem bisherigen Skill einschließlich Fetch. Titel und Beschreibung werden aus dem Fetch-Text, Projekt und Sektion aus dessen Metadaten geprüft. Nur bei fehlenden Prüfdaten ist ein weiterer Listen-Read erforderlich.

| Fall | n8n Median | Offizieller MCP Median | Tool-Aufrufe n8n / offiziell |
| --- | ---: | ---: | ---: |
| Ein Artikel hinzufügen | 3.94 s | 12.21 s | 2 / 4 |
| Bereits vorhanden | 0.81 s | 6.97 s | 1 / 2 |
| Details ergänzen | 5.65 s | 9.64 s | 2 / 3 |
| Sektion ändern | 9.93 s | 12.50 s | 2 / 4 |
| Drei Artikel hinzufügen | 3.39 s | 20.21 s | 2 / 6 |
| Zwei Artikel abhaken | 3.45 s | 10.72 s | 2 / 3 |
| Dubletten zusammenführen | 6.04 s | 16.10 s | 2 / 5 |

Alle 42 Messungen wurden erfolgreich verifiziert. Verwendet wurden ausschließlich eindeutig markierte synthetische Testartikel in der echten Einkaufsliste. Sie wurden anschließend gelöscht; die übrigen Aufgaben wurden vor und nach dem Lauf verglichen und waren unverändert. Zwischen den Zyklen blieben einige Testartikel bis zur abschließenden Bereinigung bestehen; die Listengröße war daher nicht in jedem Einzelversuch identisch. Kleine Stichprobe, kein P95/SLA-Nachweis.

[Rohdaten](n8n-shopping-write-benchmark-2026-09-28.json), [Benchmark](../scripts/shopping/benchmark.py), [Live-Sicherheitsprüfung](../scripts/shopping/safety_check.py).

## Rollout-Zwischenfall

Ein Ad-hoc-Aufruf von `community.docker.docker_container` mit nur Name, Status und Restart erzeugte Local Hermes neu ohne seine bisherigen Bind-Mounts und Umgebungswerte. Der falsch konfigurierte Container wurde entfernt und aus der bereits vorhandenen Compose-Datei mit `up -d --no-deps --no-build --pull never hermes-local` wiederhergestellt. Das ursprüngliche Host-Datenverzeichnis wurde nicht ersetzt. Danach: korrekter `/opt/data`-Bind-Mount, Zugangsdaten vorhanden, API erreichbar, Skill 4.0.0 sichtbar, SQLite `quick_check=ok`, 598 vorhandene Sitzungen. Dadurch entstand eine kurze Unterbrechung; der Gateway-Benchmark war davor bereits vollständig abgeschlossen.

## Sicherheitsprüfung

Live bestanden: unveränderte Wiederholung erzeugt keine Dublette; vorhandener Artikel bleibt ohne Schreibvorgang; veralteter Änderungsplan wird abgewiesen; erneute Sync-Command-ID erzeugt auch nach Abschluss keinen neuen Artikel; zwei gleichzeitige Hinzufüge-Anfragen erzeugen genau einen Artikel; gemischtes Hinzufügen und Zusammenführen liefert für beide Operationen verifizierte Ergebnisse. Zusätzlich nach dem letzten Deployment: Snapshot-Anfrage-ID formal gültig, Apply damit erfolgreich verifiziert, Skill 4.0.1 im laufenden Hermes sichtbar. Testartikel entfernt, übrige Aufgaben unverändert. [Prüfergebnisse](n8n-shopping-safety-2026-09-28.json).

## Assist-Praxistest

Bevorzugte HA-Pipeline `Local Hermes`, Modell `home-hermes`, Beginn bei Intent (ohne Mikrofon, Wake Word oder STT), Ende bei TTS. Audio wurde per HTTP konsumiert, nicht auf einem Lautsprecher abgespielt. Skill-Version 4.0.0 (vor Ergänzung der vom Snapshot gelieferten Anfrage-ID). Je ein explizit auf den jeweiligen Werkzeugweg beschränkter Test mit eindeutigem Testartikel; danach beide Testartikel entfernt.

| Weg | Verifizierte Aktion | Erstes Bestätigungs-Audio | Modellaufrufe |
| --- | ---: | ---: | ---: |
| n8n über LiteLLM | 18,12 s | 19,11 s | 5 |
| Offizieller Todoist-MCP über LiteLLM | 29,76 s | 30,28 s | 9 |

Beide Antworten lauteten „Testartikel eingetragen.“. Die Werkzeugwege wurden anhand der Hermes-Sitzungsdaten verifiziert. Reihenfolge n8n vor offiziell, je nur eine Messung, mögliche Cache-/Aufwärmeffekte; keine statistische End-to-End-Aussage. Der n8n-Lauf lud den Hauptskill einmal, suchte Werkzeuge einmal und nutzte Snapshot + Apply. Der offizielle Lauf lud zusätzlich die Referenz und beschrieb die offiziellen Werkzeuge, bevor er vier Todoist-Aufrufe ausführte. [Messwerte](n8n-shopping-voice-benchmark-2026-09-28.json).

Der erste reine Werkzeugbenchmark suchte die Beschreibung fälschlich nur in Fetch-Metadaten und führte redundante Listen-Reads aus. Diese Messreihe wurde verworfen und mit Prüfung des Fetch-Textes vollständig wiederholt; die Assist-Messung selbst war davon nicht betroffen.

## HA-Systemprompt mit vorgeladenem Skill

Der Conversation-Subentry von `Local Hermes` (`local_openai`) wurde über den nativen Reconfigure-Flow angepasst. Der bisherige Ladehinweis ist durch den eingebetteten Hauptskill 4.0.1 ersetzt; der veraltete Hinweis auf separate Präzisierungen entfällt. Andere Sprach-/Smart-Home-Regeln bleiben bestehen. Neue Pflichtfelder des Konfigurationsdialogs wurden mit ihren bisherigen effektiven Standardwerten gespeichert (`always_continue_conversation=false`, leere `request_body_parameters`); native HA-Tools bleiben deaktiviert.

[Prompt-Kopie](ha-local-hermes-system-prompt-2026-09-28.md). Es handelt sich um eine statische Kopie: bei Skill-Änderungen muss dieser Block aktualisiert werden. Der Originalprompt wurde vor dem Eingriff im HA-Container unter `/tmp/ha-local-hermes-prompt-before-shopping.txt` gesichert. Gespeicherten Prompt, Modell und deaktivierte native HA-Tools nach dem Update geprüft.

Read-only-Test über HA `conversation/process`: Anzahl offener Artikel, Antwort nach 11,40 s. Hermes-Trace: `tool_search` → `shopping_snapshot` → Antwort, kein `skill_view`. Kein TTS-Test und kein direkter Zeitvergleich mit dem vorherigen Schreibbenchmark. Die Tool-Schemas sind weiterhin dynamisch gesucht; ihre direkte Bereitstellung wurde durch diese Prompt-Änderung nicht eingerichtet.

### Korrektur der Home-Assistant-Werkzeugregeln

Die zuvor übernommenen Smart-Home-Regeln waren veraltet: sie verlangten den inoffiziellen `hamcp`-Server und verboten sogar Namen des offiziellen Servers. Live-Discovery mit dem Local-Hermes-Schlüssel bestätigt stattdessen `home_assistant` (Gruppe `home_control`) und dessen `GetLiveContext`-/Intent-Werkzeuge. Der HA-Prompt wurde über Reconfigure korrigiert: offizielle Werkzeuge erlauben, echte Schemas und `name`/`domain`/`area` verwenden, keine `ha_search`-/`ha_call_service`-Anweisungen. Einkaufsblock unverändert. Read-only-HA-Test „Welche Lampen sind gerade eingeschaltet?“ erfolgreich; Trace enthält den offiziellen `GetLiveContext`-Aufruf und keine Schaltaktion.

### Skill und HA-Prompt 4.0.2

Nach dem realen Gouda-Formatfehler wurden Hauptskill und eingebetteter HA-Block gemeinsam angepasst: explizites JSON-Array-Beispiel, keine Stringifizierung von `operations`/`expected_candidates`/`expected`, und `tool_describe` nur bei fehlendem oder unklarem Schema. Der sonstige HA-Prompt einschließlich der offiziellen MCP-Regeln blieb unverändert. JSON-Beispiel, Gleichheit des Skill-Inhalts mit dem eingebetteten Block und persistierte HA-Version geprüft.

Ein Assist-Test ab Intent mit normaler Hinzufügen-Formulierung verwendete `tool_search` → `tool_describe` → `shopping_snapshot` → `shopping_apply`. Kein Skill-Nachladen, `operations` beim ersten Versuch als Array, Ergebnis `verified`. Intent-Ende 15,69 s, erster heruntergeladener Audio-Chunk 16,19 s. Einzeltest, keine garantierte Fehlerfreiheit oder messbare Beschleunigung daraus ableiten. Das schwach typisierte n8n-Schema wurde hierbei nicht verändert.
