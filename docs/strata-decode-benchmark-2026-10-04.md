# Strata gegen llama.cpp Flash-Next: sustained Decode auf 2 und 3 GPUs

Nachtrag: [Qualität und direkter Geschwindigkeitsvergleich gegen das 27B/vLLM-Produktionsprofil](strata-quality-benchmark-2026-10-04.md).

Gemessen in der Nacht vom 3. auf den 4. Oktober 2026 auf `ailab-ubuntu`.
Dieselbe Hardware, Power-Limits und Profile wie im
[Prefill-Vergleich](strata-prefill-benchmark-2026-10-03.md): i5-12500,
46,9 GiB nutzbarer RAM, zwei RTX 3090 und eine RTX 5060 Ti.
Embedding, ASR und TTS blieben geladen; ComfyUI-Queue leer, Wolf/ComfyUI aktiv.
Die zusätzliche Nutzung der 5060 Ti war für diesen Benchmark ausdrücklich freigegeben.

## Methode und Grenzen

Das vorhandene Benchmarkskript wurde um `--decode-tokens` erweitert. Derselbe
synthetische Corpus und frische Systempräfixe wie beim Prefill-Test; diesmal
fordert die identische Abschlussanweisung einen ausführlichen deutschen Artikel
über Datenbank-Backups. Greedy Sampling, Thinking aus, genau **512 Output-Tokens**.
Drei Messungen bei 4096 und 65536 Texttokens, eine bei 128000.
Vor jedem Profil eine kurze 512-Token-Generation und eine ungewertete
64K-Generation. Reihenfolge: Strata 2GPU, Strata 3GPU, llama.cpp.
Modellstart und Aufwärmläufe sind außerhalb der Tabellen.

Alle **21** gewerteten Requests lieferten 512 Tokens mit `finish_reason=length`,
null wiederverwendeten Prompt-Tokens und mindestens 100 Textwörtern.
Stichproben der gespeicherten Antworten waren plausible deutsche Artikel;
das ist keine Bewertung der Modellqualität oder des Long-Context-Retrievals.
Die tatsächlichen Prompt-Zählungen stimmen zwischen allen drei Backends überein
und enthalten gegenüber dem Rohtext zusätzlich 108–109 Tokens.

Primärer Decode-Wert ist die Clientmessung
`(completion_tokens - 1) / (stream_end - first_nonempty_token)`.
Sie schließt Prefill/TTFT aus und enthält Stream-Chunking sowie Abschlussaufwand.
Die nativen Engine-Timings sind ebenfalls gespeichert und bestätigen die Werte.

| Profil | Quantisierung | GPUs / Schichten | Kontextbudget | Speculative Decode |
| --- | --- | --- | ---: | --- |
| bestehendes llama.cpp | Unsloth UD-Q3_K_XL | 3090 / 3090 / 5060 Ti, 28/12/8; erste 20 MoE-Blöcke und 20/40/47 auf CPU | 262144 | **aus**, Default `--spec-type none` |
| Strata 2GPU | ISTA-DASLab GSQ-RCO IQ2_XS | beide 3090, auto 25/23 | 131072 | MTP 4 |
| Strata 3GPU | dieselbe IQ2_XS | 3090 → 3090 → 5060 Ti, 16/16/16 | 131072 | MTP 4 |

Das llama.cpp-Image enthält MTP-Unterstützung, aber das bestehende Profil
aktiviert sie weder per CLI noch per `LLAMA_ARG_SPEC_TYPE`. Es wurde unverändert
getestet. Strata erreicht hier etwa 49–55 % Draft-Akzeptanz. Unterschiedliche
Quantisierung, Expertenplatzierung, MTP, RAM- und Kontextbudgets gehören zu diesem
Vergleich der konkreten Setups; aus ihm lässt sich kein isolierter Engine-Vorteil
oder gleichwertige Modellqualität ableiten. Output-Inhalt und MTP-Akzeptanz können
bei anderen Aufgaben abweichen.

## Decode: Tokens pro Sekunde

Median bei 4K/64K; **128K ist eine Einzelmessung**.

| Texttokens | llama.cpp Q3, 3GPU | Strata IQ2_XS, 2GPU | Strata IQ2_XS, 3GPU |
| ---: | ---: | ---: | ---: |
| 4096 | 18.75 | 87.58 | 72.06 |
| 65536 | 12.56 | 77.17 | 68.69 |
| 128000 | 9.21 | 76.03 | 68.40 |

Strata 2GPU erreicht damit den 4.67-fachen Durchsatz bei 4K,
den 6.14-fachen bei 64K und den 8.26-fachen bei 128K.
Auch beim Decode ist das Zwei-3090-Profil schneller als das getestete
Drei-GPU-Profil. Gegenüber 4K verliert Strata 2GPU bei 128K rund
13.2 % Decode-Durchsatz.

## Gesamtzeit für Prompt plus 512 Output-Tokens

Sekunden ab Requestbeginn bis Streamende; Median/Einzelmessung wie oben.

| Texttokens | llama.cpp Q3, 3GPU | Strata IQ2_XS, 2GPU | Strata IQ2_XS, 3GPU |
| ---: | ---: | ---: | ---: |
| 4096 | 39.98 | 9.23 | 11.12 |
| 65536 | 242.17 | 35.83 | 44.20 |
| 128000 | 512.06 | 60.53 | 76.11 |

Der Prefill-Vorteil bleibt dabei erhalten. TTFT, reine Decode-Dauer,
native Prefill-/Decode-Raten, Streuung und Draft-Akzeptanz stehen im
[aggregierten JSON](../experiments/strata/decode-results-2026-10-04/summary.json).

## Ressourcen und Wiederherstellung

1-Hz-GPU-Telemetrie einschließlich Warmup. Cgroup-Peak enthält Dateicache und die
gesamte Containerlaufzeit; die Swap-Spalte zeigt den Wert am Reihenende.

| Profil | Cgroup-Peak GiB | Container-Swap GiB | Min. freier VRAM GPU0/1/2 MiB | Max. Temperatur GPU0/1/2 °C |
| --- | ---: | ---: | --- | --- |
| llamacpp-q3-3gpu | 42.74 | 0.23 | 2018/2348/2527 | 91/94/66 |
| strata-iq2-2gpu | 28.00 | 0.00 | 4280/4238/15203 | 91/92/49 |
| strata-iq2-3gpu | 28.00 | 0.00 | 2044/5158/4215 | 91/94/68 |

Keine OOMs/OOM-Kills. Beide Strata-Profile liefen erneut mit 28 GiB RAM-Limit
und ohne Container-Swap. Alle 3090-Messreihen hatten thermische Drosselung;
die Werte gelten für die bestehende Kühlung und Power-Limits 250/250/180 W.

Anschließend Produktion über die echte LlamaSwap-API wiederhergestellt:
Qwen3.8-27B/AutoRound-vLLM antwortet `42`, Embedding liefert
1024 Dimensionen, Qwen3-TTS mit `de-host` erzeugt eine
WAV mit 109404 Bytes, und ASR transkribiert den Funktionstest korrekt.
Alle vier Backends sind `ready`, beide Strata-Container und der Flash-Next-Container
entladen. Wolf/ComfyUI laufen weiter, ComfyUI-Queue leer.
[Restoration-Nachweis](../experiments/strata/decode-results-2026-10-04/restoration.json).

[Alle Rohdaten](../experiments/strata/decode-results-2026-10-04/): Antworten,
SSE-Timings, Engine-/Containerlogs, tatsächliche Runtime-Konfigurationen,
Image-IDs, Corpus-Hash, Cgroup-Werte und GPU-Telemetrie.
[Reproduktion](../experiments/strata/README.md).
Die beiden bestehenden Benchmark-Parser-Checks und `git diff --check` bestanden.
