# Digitale CPU-Baseline – erster Lauf vom 7. Oktober 2026

## Ergebnis und Reichweite

Die Baseline wurde auf allen **24.000 gespeicherten Eingaben** aus 24 Datensätzen
geprüft. Alle Ausgaben erhalten die Datensätze, sind korrekt sortiert und stabil.
Es wurden **192 Konfigurationen** mit insgesamt **1.728 Zeitmessungen** erfasst:
24 Datensätze × 2 Speicherformate × 4 Stapelgrößen × 9 Wiederholungen.
Die drei gezielten Tests zur Ausgabesemantik und Stapelverarbeitung bestehen.

Dies sind erste Messungen in einer geteilten Ausführungsumgebung. Sie belegen
keinen NPU-Vorteil und keinen allgemeinen CPU-Bestwert. Vor abschließenden
Leistungsbehauptungen ist eine Messung auf einer kontrollierten Maschine sinnvoll.

## Messumfang

- NumPy `argsort(kind="stable")` erzeugt die Originalindizes;
  `take_along_axis` erzeugt die sortierten Werte.
- Ausgabe: sortierte Schlüssel **und** Indizes der Originaldatensätze.
- 4-Bit-Schlüssel 0–15 und 8-Bit-Schlüssel 0–255, einschließlich gleicher Schlüssel.
- `int64` entspricht dem gespeicherten Korpus. `uint8` enthält dieselben Werte in
  einem passenden kompakten Speicherformat. Beide Varianten bleiben getrennt.
  Der gültige Schlüsselbereich ist nicht mit der Speicherbreite gleichzusetzen.
- Stapelgrößen 1, 10, 100, 1.000; jede Liste wird unabhängig innerhalb ihrer Zeile
  sortiert. Es wird nicht der gesamte Stapel als eine lange Liste sortiert.
- Alle 1.000 Listen je Datensatz werden je gemessenem Durchlauf verwendet.
  Keine Zeile wird verworfen oder durch Padding ersetzt.
- Eingaben liegen bereits im CPU-Speicher. Datei-I/O, Typkonvertierung,
  Eingabevorbereitung und Korrektheitsprüfungen liegen außerhalb der Zeitmessung.
- Python-Aufruf, Ausgabeallokation, Sortierung, Anordnung der Werte und normale
  Freigabe der Ergebnisse liegen innerhalb der Messung.

## Messprotokoll

Pro Konfiguration erfolgen zwei vollständige Aufwärmdurchläufe und eine
Kalibrierung der Wiederholungszahl. Jede der neun Zeitproben umfasst mindestens
angestrebte 15 ms auf Basis dieser Kalibrierung. Die tatsächlichen Zeiten werden
unverändert gespeichert. Die Reihenfolge der Konfigurationen wird mit dem
festgehaltenen Seed 20261007 gemischt. Die Eingaben sind schreibgeschützt und
werden wiederholt verwendet; dies ist ein Benchmark mit aufgewärmten Caches.

Jede Probe liefert eine **mittlere Zeit pro Stapelaufruf**. Die Tabelle zeigt den
Median dieser neun Mittelwerte und deren Interquartilsabstand (IQR). Diese
Streuung ist weder eine Verteilung individueller Anfrage-Latenzen noch ein
Konfidenzintervall. Bei vier von 192 Konfigurationen überschreitet die relative
IQR 20 %; diese Fälle bleiben sichtbar und sollten auf kontrollierter Hardware
besonders überprüft werden. Es wurden keine langsamen Proben entfernt.

## Beispiel: 8 Bit, N = 256, unterschiedliche Schlüssel

| Speicherformat | Listen pro Aufruf | Zeit pro Aufruf | Amortisierte Zeit pro Liste | relative IQR |
|---|---:|---:|---:|---:|
| int64 | 1 | 11.90 µs | 11.90 µs | 5.4 % |
| int64 | 1000 | 8851.66 µs | 8.85 µs | 12.2 % |
| uint8 | 1 | 5.26 µs | 5.26 µs | 10.6 % |
| uint8 | 1000 | 1407.79 µs | 1.41 µs | 3.7 % |

Ein Aufruf mit 1.000 Listen liefert sämtliche 1.000 Ausgaben erst nach der
angegebenen Aufrufzeit. Die kleinere amortisierte Zeit ist eine Durchsatzgröße,
keine Antwortzeit einer einzelnen Liste. Selbst bei Stapelgröße 1 ist der
Tabellenwert eine aus wiederholten Durchläufen gemittelte Aufrufzeit.

## Umgebung und Reproduktion

Gemessen: AMD EPYC 9V74, Python 3.12.14, NumPy 2.3.5, Linux x86-64.
Der Container sieht neun logische CPUs; seine cgroup-Quote entspricht acht
CPU-Zeiteinheiten. Das bedeutet nicht, dass die NumPy-Sortierung acht Kerne nutzt.
Keine Prozessaffinität wurde festgesetzt. Vollständige relevante Metadaten stehen
in `results/cpu_baseline_20261007/metadata.json`.

Für diesen Benchmark eine separate Umgebung verwenden; die historischen SDK-
und Sweep-Abhängigkeiten werden nicht geändert:

```bash
python -m venv .venv-baseline
# Umgebung aktivieren, anschließend:
python -m pip install -r requirements-cpu-baseline.txt
python -m unittest discover -s tests -p test_cpu_baseline.py -v
python run_cpu_baseline.py --output-dir results/cpu_baseline_reproduced
```

Das Ausgabeverzeichnis muss leer sein. Der SHA-256 des Korpus wird vor dem Lauf
geprüft. Software- und Eingabehash, Rohzeiten sowie eine Korrektheitsprüfung
werden gespeichert. Laufzeiten sind maschinenabhängig und sollen bei Wiederholung
nicht bitgenau übereinstimmen.

| Datei | Inhalt |
|---|---|
| `summary.csv` | Median, IQR und Durchsatz für jede Konfiguration |
| `samples.csv` | Alle 1.728 Rohzeitproben und Zahl der Aufrufe |
| `validation.json` | Korrektheit, Stabilität und Datensatzerhaltung |
| `metadata.json` | Umgebung, Messgrenzen, Parameter und Hashes |

## Einordnung

Es wird eine Bibliotheksbaseline gemessen, keine speziell entwickelte schnellste
CPU-Sortierung. GPU-Messungen stehen noch aus. Die Zeit eines Q.ANT-CPU-Backends
darf nicht als NPU-Laufzeit in einen Beschleunigungsfaktor eingehen. Ohne reale
NPU-Messungen können die digitalen Zeiten als Zielwerte für eine ausdrücklich
bedingte Gesamtzeitrechnung dienen. Energie wurde hier nicht gemessen.

Das Komplexitätsmodell C=(T,S,H,D) bleibt unverändert. Diese Sekundenmessungen
ersetzen nicht die Definition von T als sequenzielle real-RAM-Schrittzahl.

Methodische Dokumentation: [NumPy argsort](https://numpy.org/doc/2.3/reference/generated/numpy.argsort.html)
und [take_along_axis](https://numpy.org/doc/2.3/reference/generated/numpy.take_along_axis.html).

Weitere Arbeit: siehe [Feedback-Sprints](FEEDBACK_SPRINTS.md).
