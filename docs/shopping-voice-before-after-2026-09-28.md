# Voice-Einkaufsliste: reale Anfragen vor und nach der Optimierung

Auswertung der HA-Pipeline-Debugdaten und Hermes-Sitzungen am 28.09.2026. Nur gelesen, keine Einkaufsliste oder Konfiguration verändert. Zeitbasis für den Vergleich: HA `intent-start` bis `intent-end` (erkannter Text bis vollständige Antwort). Die tatsächliche erste Audiowiedergabe am Satelliten ist in diesen Debugdaten nicht belegt; `tts-end` zeigt hier nur die Bereitstellung der Streaming-Ausgabe.

| Anfrage | Ergebnis | Text bis Antwort | Sprechende bis Antwort | Modellaufrufe |
|---|---|---:|---:|---:|
| Füge "Dinkel Flakes" zu meiner Einkaufsliste hinzu. | schon vorhanden | 31.22 s | 31.44 s | 5 |
| Füge "Bananen" zu meiner Einkaufsliste hinzu. | schon vorhanden | 9.34 s | 9.48 s | 3 |
| Füge "Eier" zu meiner Einkaufsliste hinzu. | schon vorhanden | 10.67 s | 10.81 s | 3 |
| Füge "Saft" zu meiner Einkaufsliste hinzu. | Rückfrage | 10.97 s | 11.09 s | 4 |
| Füge "35 Liter Müllbeutel" zu meiner Einkaufsliste hinzu. | schon vorhanden | 8.67 s | 8.81 s | 3 |
| Füge "Gouda-Käse" zu meiner Einkaufsliste hinzu. | hinzugefügt | 16.07 s | 16.19 s | 5 |

## Vergleich und Befunde

- Vergleichbare Leseentscheidungen: Dinkel-Flakes vor den Änderungen 31,22 s; jetzt Bananen 9,34 s, Eier 10,67 s, Müllbeutel 8,67 s. Neuer Median 9,34 s, rund 70 % unter diesem einzelnen historischen Vergleich. Unterschiedliche Produkte und Cache-/Lastzustände: kein kontrollierter A/B-Nachweis.
- Echtes Hinzufügen: Gouda 16,07 s bis Antwort; der Erfolg war bereits etwa 15,36 s nach Intent-Start verifiziert. Der frühere kontrollierte offizielle MCP-Test lag bei 30,28 s bis Intent-Ende, der n8n-Test vor Preload bei 18,64 s. Andere Prompts und je eine Messung erlauben keine isolierte Zuschreibung an das Preloading.
- Historische reale Schreibanfragen (nur Hermes-Zeit): Ingwer 42,62 s, Planen 48,67 s, Müllbeutel 51,41 s. Jetzt Gouda 15,94 s auf derselben Hermes-Zeitbasis. Müllbeutel vorher hinzugefügt, jetzt bereits vorhanden: nicht als identischer Arbeitsschritt vergleichen.
- Alle fünf neuen Anfragen nutzen shopping_snapshot, keine lädt einkaufsliste oder einkaufsliste-patches nach. Bananen/Eier/Müllbeutel vermeiden Schreibvorgänge; Saft führt zur Rückfrage wegen vorhandenem Orangensaft/saft. Nur Gouda ist ein tatsächlicher Schreibvorgang.
- Gouda: operations zunächst als JSON-String gesendet und vor der Workflow-Ausführung vom Schema abgewiesen. Danach als Array korrigiert, Apply verified. Vermeidbare Zusatzzeit vom ersten Apply-Aufruf bis Beginn des korrigierten Aufrufs: 4,75 s. Live-MCP-Schema enthält bei operations lediglich eine Beschreibung, keinen expliziten Array-Typ. Diese schwache Typinformation ist ein plausibler Mitverursacher, obwohl der Skill ausdrücklich ein Array verlangt.
- Werkzeugentdeckung bleibt: alle fünf Anfragen tool_search, Saft zusätzlich tool_describe. Search selbst benötigt nur rund 0,03–0,04 s; der vorgeschaltete Modellschritt etwa 1,5–1,7 s. Statische Bereitstellung der zwei Schemas wäre daher der nächste Ansatz, nicht eine schnellere Suchimplementierung.
- Snapshot-Laufzeit aus den Hermes-Traces: 0,90–4,74 s; deutliche Schwankung. Gouda erfolgreiches Apply inklusive interner Verifikation: 2,54 s. Der größte Teil der übrigen Zeit entfällt auf Modellschritte und Aufrufvorbereitung.
- STT nach erkanntem Sprechende bei den fünf aktuellen Anfragen: 0,12–0,15 s. Das erfasste VAD-Ende ist nicht zwingend das physische Ende der Sprache. Keine belastbare Messung der Lautsprecher-Pufferung oder ersten hörbaren Silbe.
- Hermes meldet Cache-Lesetokens bei allen fünf Anfragen; auch die historischen Anfragen hatten Cache-Treffer. Damit ist Cache-Nutzung belegt, aber kein isolierter Cache-Gewinn durch die Prompt-Änderung.

[Messdaten](shopping-voice-before-after-2026-09-28.json)
