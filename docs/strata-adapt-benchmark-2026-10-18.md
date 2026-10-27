# Strata 0.1.45: adapt-every 4 gegen 6 auf zwei RTX 3090

## Ergebnis und Entscheidung

**Standardwert 4 beibehalten.** Der Reddit-Tipp liefert auf diesem Setup keinen
reproduzierbaren Decode-Gewinn. Bei 4K steigt der Median um 1,3 %, bei 64K
bleibt er gleich. In beiden Größen gewinnt Wert 6 nur eines von drei Paaren.
Alle sechs 64K-Messungen zeigen am Ende thermische Drosselung auf GPU1;
sie sind kein sauberer Nachweis für einen isolierten Parametereffekt.
Die ursprüngliche native Konfiguration wurde nach dem Experiment wiederhergestellt.

Anlass war der [Reddit-Bericht](https://www.reddit.com/r/LocalLLaMA/s/It3fBZl3T3)
über 9–55 % mehr Decode-Durchsatz beim Wechsel von 1 auf 6 auf einer
RTX 4070 Ti Super mit Q4-Quantisierungen. Hier war zuvor kein Override gesetzt:
Der Quellcode der installierten 0.1.45 verwendet `adapt_every = 4`.
Getestet wurde deshalb 4 gegen 6, nicht die Reddit-Hardware oder deren Ausgangswert 1.

## Aufbau

- Strata 0.1.45, Quellstand `477ac13cbe8e582c20484871ce459d20d82df09d`,
  Image `kirelabs/strata:477ac13cbe8e-sm86-sm120-vision`.
- Bestehendes Profil `Qwen3.8-Flash-Next-IQ3_XXS-Strata`, IQ3_XXS,
  zwei RTX 3090, automatischer Layer-Split, mmap, int8-KV,
  131072 Kontext, GPU-Vision und 2 GiB Gesprächscache. GPU2 unbenutzt.
- Containerlimit unverändert 28 GiB RAM/MemorySwap; Begleitdienste bleiben aktiv.
- Blockfolge **4, 6, 6, 4, 4, 6**. Pro Paar identische Prompts und Seeds.
  Reihenfolge 4K→64K, dann 64K→4K, dann wieder 4K→64K.
- Neustart desselben Backends pro Block; `--adapt-every` im echten Engine-Prozess
  geprüft. Identischer ungewerteter 4K-/1024-Token-Aufwärmlauf vor jedem Block.
- Vor jedem Speed-Lauf beide Karten höchstens 70 °C. GPU-Zustände vor und nach
  jeder Anfrage erfasst; keine kontinuierliche thermische Aufzeichnung.
- Derselbe synthetische Zahlenkorpus und derselbe deutsche Backup-Artikelauftrag
  wie bei bisherigen Decode-Tests, 4K/64K Rohtexttokens, genau 1024 Ausgabetokens,
  Low Reasoning, Temperatur 0, Abschluss `length`. Kein Codeverständnistest.
- Drei Messungen pro Wert und Kontextgröße, insgesamt zwölf gewertete Anfragen.
  Alle mit **0 wiederverwendeten Prompt-Tokens**. Native Request-Zähler,
  Promptlänge, Finish und Cache-Nutzung gegen die Clientantwort abgeglichen.
- Kein Flush des globalen OS-Dateicaches. Neustarts setzen Engine-/KV-Zustand
  zurück, garantieren aber keinen identischen Dateicache. Die Blockfolge ist
  paarweise wechselnd, jedoch kein vollständig balanciertes großes Experiment.

## Geschwindigkeit

Mediane; Decode ist die native Engine-Messung, TTFT die erste nichtleere
Streaming-Ausgabe einschließlich Denktext. Gesamtdauer ist clientseitig.

| Kontext | Messgröße | Wert 4 | Wert 6 | Änderung 6 gegenüber 4 |
| --- | --- | ---: | ---: | ---: |
| 4K | Decode, Tokens/s | 70,6 | 71,5 | +1,3 % |
| 4K | TTFT, s | 13,03 | 13,21 | +1,3 % |
| 4K | Gesamtdauer, s | 27,51 | 27,50 | −0,1 % |
| 64K | Decode, Tokens/s | 57,9 | 57,9 | 0,0 % |
| 64K | TTFT, s | 84,92 | 69,32 | −18,4 % |
| 64K | Gesamtdauer, s | 102,52 | 87,58 | −14,6 % |

Die kürzere 64K-TTFT mit 6 trat in allen drei Paaren auf und ist als Beobachtung
interessant. Wegen Dateicache, thermischer Einflüsse und nur drei Paaren wird sie
hier nicht als gesicherter Parametergewinn oder Grund für eine Produktionsänderung
gewertet. Sie erklärt die kürzere Gesamtdauer, nicht ein schnellerer Decode.

| Paar | Promptreihenfolge | 4K Tokens/s: 4 → 6 | Änderung | 64K Tokens/s: 4 → 6 | Änderung |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | 4K, 64K | 70,6 → 71,5 | +1,3 % | 55,7 → 59,6 | +7,0 % |
| 2 | 64K, 4K | 67,9 → 65,5 | −3,5 % | 58,2 → 57,9 | −0,5 % |
| 3 | 4K, 64K | 71,6 → 71,5 | −0,1 % | 57,9 → 56,0 | −3,3 % |

Bei keinem 4K-Nachher-Snapshot war thermische Drosselung aktiv, bei allen sechs
64K-Snapshots dagegen schon. Bereits im ersten langen Lauf wurden 93 °C auf
GPU1 erfasst. Der niedrigere 4K-Durchsatz nach 64K tritt bei beiden Werten auf;
Expertenzustand und thermische Vorgeschichte sind mögliche Einflussgrößen.
Alle sechs Ressourcenprüfungen melden `oom=0`, `oom_kill=0`.

## HA-Werkzeuge und Textprüfung

Je Wert fünf vorhandene HA-Simulatorfälle mit demselben Seed und Low Reasoning:
Licht ausschalten, zwei Aktionen, Rolloposition, Rauschen und ein unerreichbares
Gerät. Beide Werte bestehen **5/5 Aktions-/Abschlussprüfungen**. Es wurden keine
realen Geräteaktionen ausgeführt. Das ist ein Smoke-Test, keine Wiederholung
der vollständigen früheren HA-Qualitätssuite.

Manuelle Sichtung der Abschlussantworten: Ziele und Rolloposition stimmen,
Rauschen endet ohne Aktion, beide Varianten melden das unerreichbare Gerät.
Bei Wert 6 ergänzt die Antwort im Fehlerfall allerdings, das Deckenlicht
funktioniere. Die Erreichbarkeit dieses anderen Geräts wurde nicht getestet;
diese Zusatzbehauptung ist nicht durch den Aktionstest gedeckt. Die automatische
Wertung prüft die Aktionen, nicht jede Aussage des Abschlusstextes. Beide
Varianten spekulieren außerdem über die Ursache der Nichterreichbarkeit.

Die langen Artikelantworten und Denktexte bleiben vollständig in den Rohdaten.
Die Ausgabeprüfung erzwingt 1024 Tokens und mindestens 100 sichtbare Wörter,
ist aber keine fachliche Qualitätsbewertung der Backup-Artikel. Gleiche Seeds
bedeuten bei adaptiver Expertenplatzierung keine identischen Antworttokens.

## Reproduktion und Artefakte

[Runner](../experiments/strata/benchmark_adapt.py),
[Auswertung](../experiments/strata/summarize_adapt.py),
[Rohdaten und Methodenmetadaten](../experiments/strata/adapt-results-2026-10-18/).
Der Runner verwendet die bestehenden Timing-/Validierungshelfer und den
HA-Simulator. Er sichert die native Konfiguration exklusiv, ändert nur
`--adapt-every` und stellt die Sicherung im `finally`-Block wieder her.
Ein erneuter Versuch benötigt einen neuen Ausgabeordner; bestehende Daten
werden absichtlich nicht überschrieben.

```bash
python3 experiments/strata/benchmark_adapt.py
python3 experiments/strata/summarize_adapt.py
```

Geprüft wurden die bestehenden Timing-/Cache-/Output-Tests und der HA-Simulator,
zusätzlich Änderung und bytegenaue Wiederherstellung einer temporären
Konfigurationsdatei sowie die Paarberechnung der Auswertung mit synthetischen Daten.

## Wiederhergestellter Betrieb

Die Konfiguration stimmt nach dem Lauf bytegenau mit der Sicherung überein
(SHA256 `285538011720f61546c7f0b55fd7821bf7ecbda3ec3b17a7978e0e6ff3468863`).
Der laufende Engine-Prozess hat wieder keinen `--adapt-every`-Override,
also den Standardwert 4. Strata meldet 0.1.45, Docker `healthy` und
`OOMKilled=false`.

Die tatsächlichen HA-Agenten `conversation.home_nano_ai_agent` und
`conversation.local_hermes_hermes_local_ai_agent` beantworten nach der
Wiederherstellung je eine Rechenfrage korrekt mit `42`. Für beide wurde eine
frische native Strata-Anfrage nachgewiesen; keine reale Geräteaktion.
Nachweise: `restored.json`, `original-config.sha256`, `restored-config.sha256`
und `client-checks.jsonl` im Ergebnisordner.
