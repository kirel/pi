# Strata gegen llama.cpp Flash-Next: Prefill auf 2 und 3 GPUs

Nachtrag: [Decode-Vergleich mit jeweils 512 Output-Tokens](strata-decode-benchmark-2026-10-04.md)
bei 4K, 64K und 128K Kontext.

Gemessen am 2026-10-03 auf `ailab-ubuntu`: i5-12500, 46,9 GiB nutzbarer
RAM, zwei RTX 3090 und eine RTX 5060 Ti. Treiber 590.48.01; bestehende
Power-Limits 250/250/180 W. Embedding, ASR und TTS blieben während der
Messreihen geladen. ComfyUI hatte keine laufenden/ausstehenden Jobs; seine
ungenutzten Modelle wurden vorher über `/free` entladen. Wolf und ComfyUI
blieben als Dienste aktiv. Keine zusätzlichen parallelen LLM-/Audio-Testanfragen.

Für diesen Test war die zusätzliche Nutzung der 5060 Ti ausdrücklich
freigegeben. Die Produktionsauswahl bleibt Qwen3.8-27B/vLLM.

## Profile und Methode

| Profil | Quantisierung | GPUs / Schichten | Konfigurierter Kontext |
| --- | --- | --- | ---: |
| Bestehendes llama.cpp Flash-Next | Unsloth UD-Q3_K_XL | 3 GPUs, bestehender Split 28/12/8; erste 20 MoE-Blöcke sowie 20/40/47 auf CPU | 262144 |
| Strata 2GPU | ISTA-DASLab GSQ-RCO IQ2_XS | beide 3090, auto ergibt 25/23 | 131072 |
| Strata 3GPU | dieselbe IQ2_XS-Quantisierung | 3090 → 3090 → 5060 Ti, manuell 16/16/16 | 131072 |

Strata: Commit `99f3dbd0b21d1401b3769e0c0d963913607f380b`, Engine 0.1.38,
upstream Dockerfile mit CUDA 86/120 und BuildKit. Native `--mmap-experts`,
28 GiB Containerlimit ohne zusätzlichen Container-Swap, INT8 KV, MTP 4,
`--prefill auto`, Vision und experimentelle Speed-Projektion aus.
Der VRAM-Reserveparameter beträgt 4608 MiB pro Karte; separat angelegte
Prefill-Puffer können den verbleibenden freien VRAM weiter verringern.
Die gesamte Experten-Datei ist 33,02 GiB groß und wird aus dem Dateicache gelesen.

Unveränderte gemeinsame Textprompts aus dem vorhandenen Benchmark-Generator:
4096, 16384, 32768, 65536 und 128000 Texttokens. Tatsächliche Chat-Prompts
enthalten zusätzlich 78–79 Tokens, identisch gezählt bei allen drei Backends.
Drei Messungen pro Länge bis 64K, jeweils eine bei 128K. Vor jedem Profil
kurzer Funktionstest und zwei ungewertete 64K-Aufwärmläufe. Modellstart,
Downloads, Kompilierung und Aufbereitung liegen außerhalb der Messungen.
Frische Systempräfixe, deaktiviertes Thinking, Temperatur 0 und kurze Antwort
`42`: alle 39 gewerteten Antworten korrekt, jeweils drei Output-Tokens und
**null wiederverwendete Prompt-Tokens**. Strata wurde zuerst auf 2 GPUs,
danach auf 3 GPUs und anschließend llama.cpp gemessen.

Die folgenden Werte vergleichen die konkreten Konfigurationen: Quantisierung,
CPU-Auslagerung, Kontextbudget und RAM-Limit unterscheiden sich. Modellqualität,
Long-Context-Retrieval und gleichzeitige Audio-/LLM-Last wurden nicht bewertet.
Alle 3090-Messreihen zeigten thermische Drosselung; Ergebnisse gelten für diese
bestehende Kühlung und diese Power-Limits.

## Engine-Prefill: Tokens pro Sekunde

Median der drei Wiederholungen; 128K ist eine Einzelmessung.

| Texttokens | llama.cpp Q3, 3GPU | Strata IQ2_XS, 2GPU | Strata IQ2_XS, 3GPU |
| ---: | ---: | ---: | ---: |
| 4096 | 407.3 | 1247.4 | 1028.4 |
| 16384 | 409.3 | 1737.2 | 1282.1 |
| 32768 | 385.9 | 2005.4 | 1585.2 |
| 65536 | 350.1 | 2258.3 | 1746.1 |
| 128000 | 295.2 | 2376.8 | 1852.5 |

## Zeit bis zum ersten nichtleeren Stream-Token

Sekunden, einschließlich Request- und First-Token-Aufwand.

| Texttokens | llama.cpp Q3, 3GPU | Strata IQ2_XS, 2GPU | Strata IQ2_XS, 3GPU |
| ---: | ---: | ---: | ---: |
| 4096 | 10.45 | 3.37 | 4.09 |
| 16384 | 40.49 | 9.52 | 12.88 |
| 32768 | 85.54 | 16.44 | 20.78 |
| 65536 | 188.00 | 29.16 | 37.69 |
| 128000 | 434.61 | 54.08 | 69.33 |

Bei 64K hat Strata 2GPU den 6,45-fachen Prefill-Durchsatz der bestehenden
llama.cpp-Konfiguration; bei 128K den 8,05-fachen. Strata 2GPU ist bei 64K
rund 29 % schneller als das getestete manuelle 3GPU-Profil. Für Prefill ist
hier das Zwei-3090-Profil die günstigere Wahl.

## RAM, VRAM und GPU-Reihenfolge

Cgroup-Peak enthält Dateicache und umfasst die gesamte Containerlaufzeit,
bei Strata 2GPU auch die Erstaufbereitung. Er ist kein RSS-Wert. Der Host hatte bereits
Swap-Belegung; die Swap-Spalte zeigt nur den jeweiligen LLM-Container.
VRAM-Minima und Temperaturen stammen aus 1-Hz-Samples einschließlich Warmup.

| Profil | Cgroup-RAM-Peak GiB | Container-Swap GiB | Min. freier VRAM GPU0/1/2 MiB | Max. Temperatur GPU0/1/2 °C |
| --- | ---: | ---: | --- | --- |
| llamacpp-q3-3gpu | 43.33 | 0.56 | 2078/2406/2527 | 91/94/66 |
| strata-iq2-2gpu | 28.00 | 0.00 | 4294/4244/15203 | 91/92/48 |
| strata-iq2-3gpu-balanced | 28.00 | 0.00 | 2112/5220/4217 | 92/94/68 |

Keine OOMs/OOM-Kills. Beide Strata-Container erreichten ihr 28-GiB-Limit;
`memory.events.max` und Dateicache-Refaults zeigen Reclaim. Trotzdem liefen
128K ohne Container-Swap. Zwei 3090 lassen in dieser Konfiguration rund
4,2 GiB pro Karte frei. Beim Drei-GPU-Profil bleiben auf GPU0 nur rund 2,1 GiB;
der Benchmark qualifiziert keine zusätzliche gleichzeitige Last.

Stratas `--gpus all` sortiert hier anders als die normale CUDA-Reihenfolge:
Es wählt die 5060 Ti zuerst. Die native CLI akzeptiert eine explizite Liste
von `nvidia-smi`-Indices. Der Ansible-Launcher löst die gewünschten UUIDs zur
Laufzeit auf und übergibt sie in der Reihenfolge 3090 → 3090 → 5060 Ti.
Zusätzlich ist eine manuelle Schichtverteilung erforderlich, um die kleinen
Prefill-Blöcke der Automatik zu vermeiden.

| Strata-3GPU-Diagnostik | Reihenfolge | Schichten | Auto-Prefill-Block | Prüfung |
| --- | --- | --- | ---: | --- |
| ursprüngliche Automatik | 5060 Ti / 3090 / 3090 | 2/24/22 | 1024 | 7 abgeschlossene Messungen; danach kontrolliert beendet |
| feste Reihenfolge, auto Split | 3090 / 3090 / 5060 Ti | 24/23/1 | 512 | ein vollständiger 64K-Warmup; danach kontrolliert beendet |
| finales Profil | 3090 / 3090 / 5060 Ti | 16/16/16 | 8192 | gesamte Messreihe einschließlich 128K bestanden |

Die abgebrochenen Diagnostik-Reihen sind separat gespeichert und gehen nicht
in die Haupttabellen ein. GPU-Auswahl und Split verwenden ausschließlich
[upstream CLI-Optionen](https://github.com/Niko1221/Strata/blob/99f3dbd0b21d1401b3769e0c0d963913607f380b/docs/MULTI_GPU.md).

Rohdaten, CUDA/GPU-Zuordnung, Image-IDs, Modellrevisionen, Corpus-SHA256,
Cgroup-Werte, Engine-Logs und GPU-Telemetrie:
[`experiments/strata/results-2026-10-03`](../experiments/strata/results-2026-10-03/).
Aggregierte Werte: [`summary.json`](../experiments/strata/results-2026-10-03/summary.json).
Reproduktion und Profilnamen: [`experiments/strata/README.md`](../experiments/strata/README.md).


## Kontrolllauf und Abschluss

Nach dem kompletten llama.cpp-Lauf wurde das finale Zwei-GPU-Profil erneut
über LlamaSwap gestartet: explizite UUID-Reihenfolge, automatischer Split
25/23 und 8192-Token-Prefill-Blöcke. Dieselben drei 64K-Prompts nach zwei
64K-Warmups: **2265.0 Tokens/s**, **29.08 s TTFT**, alle Antworten korrekt,
kein Prompt-Cache. Das entspricht +0,30 % gegenüber dem ersten Zwei-GPU-Lauf
und bestätigt sowohl den Rückwechsel als auch die stabile Leistung.

Produktion wiederhergestellt und über die echte LlamaSwap-API geprüft:

- `Qwen3.8-27B-Instruct-AutoRound-vLLM`: ready, Antwort `42`.
- `qwen3-embedding`: ready, 1024 Dimensionen.
- `qwen3-tts`, Stimme `de-host`: ready, gültige WAV mit 109404 Bytes.
- `whisper-large-v3-turbo-q8-crispasr`: ready; transkribiert diese WAV korrekt
  als „Das ist ein kurzer Funktionstest.“.
- Beide Strata-Container und der Flash-Next-llama.cpp-Container entladen;
  Wolf/ComfyUI bleiben aktiv, ComfyUI-Queue leer.

Ansible-Syntax, Shell-Syntax und beide Benchmark-Parser-Checks bestanden.
Abschließender `strata-test`-Ansible-Check: `changed=0`, `failed=0`.
Die zwei defekten Legacy-Builder-Testimages wurden entfernt. Das funktionierende
BuildKit-Image und die ca. 105 GiB Strata-Daten bleiben für weitere Tests erhalten.
Die beiden Strata-Profile sind deklarativ vorhanden; sie ändern die voreingestellte
Produktionsauswahl nicht. GPU2 wird nur bei ausdrücklicher Auswahl des
Drei-GPU-Profils genutzt.
