# Sortierqualität auf vorhandenen Ausgaben

Stand: 7. Oktober 2026. Dieser Sprint ergänzt Kendall-τ, Fehler nach
Schlüsselabstand und Recall@k. Es wurden **keine neuen Sortierläufe** ausgeführt.

## Zentrales Ergebnis

Eine niedrige Quote vollständig korrekter Arrays kann mit einer fast korrekten
Reihenfolge und hoher Auswahlqualität einhergehen. Das bisherige Kriterium
bleibt für exaktes Sortieren richtig, beschreibt aber nicht die Schwere eines
Fehlers. Die zusätzlichen Kennzahlen machen diesen Unterschied sichtbar.

Beispiel aus den vorhandenen Upstream-Ausgaben: 8-Bit-Schlüssel, N=256,
unterschiedliche Schlüssel, η=0,25; jeweils 1.000 Versuche.

| Kennzahl | Bitonic | Rangsortierung |
|---|---:|---:|
| Gültige Ausgaben | 1.000 / 1.000 | 984 / 1.000 |
| Vollständig korrekt, bezogen auf alle Versuche | 5,9 % | 4,0 % |
| Mittleres Kendall-τ-b, nur gültige Ausgaben | 0,999826 | 0,999823 |
| Mittlere Zahl falsch geordneter Paare, nur gültige Ausgaben | 2,847 | 2,889 |
| Recall@10, nur gültige Ausgaben | 99,880 % | 99,878 % |
| Recall@10 mit ungültigen Ausgaben als Nullnutzen | 99,88 % | 98,28 % |

Bei 256 verschiedenen Schlüsseln gibt es 32.640 ungeordnete Paare. Im Mittel
sind bei Bitonic nur 2,847 davon falsch geordnet. Trotzdem reicht bereits
ein einziges falsch geordnetes Paar, damit ein Array nicht vollständig korrekt
ist. Hoher Recall@10 besagt hier lediglich, dass die zehn größten Schlüssel
meist ausgewählt werden; er belegt keine korrekte vollständige Sortierung.

Die Rangsortierung zeigt zugleich, warum ungültige Ausgaben separat sichtbar
bleiben müssen: Ihr bedingter Recall ist hoch, berücksichtigt aber die 16
ungültigen Ergebnisse nicht. Der ausdrücklich definierte Nullnutzen dieser
Versuche senkt den über alle Versuche gemittelten Wert auf 98,28 %.

## Wo liegen die Fehler?

Gezählt werden Paare, deren Reihenfolge in der **fertigen Ausgabe** falsch ist.
Der Abstand ist der Betrag der Differenz der ursprünglichen ganzzahligen
Schlüssel. Gleiche Schlüssel sind aus dieser Fehlerzählung ausgeschlossen.

Für das obige Beispiel:

| Mapping | Abstand 1: falsch / vorhandene Paare | Abstand 2: falsch / vorhandene Paare | Abstände ab 3 |
|---|---:|---:|---:|
| Bitonic, 1.000 gültige Ausgaben | 2.834 / 255.000 | 13 / 254.000 | 0 falsch geordnete Paare |
| Rangsortierung, 984 gültige Ausgaben | 2.843 / 250.920 | 0 / 249.936 | 0 falsch geordnete Paare |

Bei Bitonic liegen damit 99,54 % der beobachteten Paarinversionen zwischen
benachbarten Schlüsseln; bei Rangsortierung sind es in diesen gültigen Ausgaben
100 %. Die Fehlerquote bei Abstand 1 beträgt etwa 1,11 % beziehungsweise 1,13 %
der **Paare dieses Abstands**. Der Nenner ist weder die Zahl aller Vergleiche
im Algorithmus noch die Zahl der Arrays.

Diese Auswertung misst keine internen Komparatorfehler. Eine interne
Fehlentscheidung kann die spätere Reihenfolge mehrerer Paare beeinflussen.

## Definition von Kendall-τ und Gleichständen

Für jeden ursprünglichen Datensatz wird sein wahrer Schlüssel mit seiner
Position in der ausgegebenen Reihenfolge verglichen. Dies entspricht
`scipy.stats.kendalltau(original_keys, output_positions, variant="b")`.

Seien I die Zahl falsch geordneter ungleicher Schlüsselpaare, M die Zahl aller
ungleichen Schlüsselpaare und C=N(N−1)/2 die Zahl sämtlicher Paare. Dann gilt:

\[
\tau_b = \frac{M-2I}{\sqrt{CM}}.
\]

Ohne gleiche Schlüssel ist M=C und die Formel wird zu 1−2I/C. Bei gleichen
Schlüsseln hat die wahre Ordnung Gleichstände, die ausgegebene Permutation
jedoch eindeutige Positionen. Deshalb liegt selbst für eine korrekte Ausgabe
die erreichbare Obergrenze bei:

\[
\tau_{b,\max}=\sqrt{M/C}.
\]

Diese Obergrenze wird mitberichtet. Zusätzlich steht eine ausdrücklich getrennt
bezeichnete, auf die Schlüsselordnung normierte Variante zur Verfügung:

\[
\tau_{\mathrm{key,norm}}=\tau_b/\tau_{b,\max}=1-2I/M.
\]

Sie erreicht bei korrekter Schlüsselreihenfolge 1 und behandelt unterschiedliche
Anordnungen gleicher Schlüssel gleich. Sie wird **nicht als Standard-τ-b**
bezeichnet. Die Stabilität der Originaldatensätze bleibt ein eigenes Kriterium.
Bei M=0, also ausschließlich gleichen Schlüsseln, sind beide τ-Werte nicht
definiert und werden leer ausgegeben. `tau_defined_outputs` gibt ihren Nenner
an; `constant_key_valid_outputs` zählt die ausgeschlossenen konstanten Listen.
Ungültige Ausgaben erhalten ebenfalls keinen erfundenen τ-Wert.

Grundlage: [SciPy-Dokumentation zur Definition von Kendall-τ-b](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kendalltau.html).

## Definition von Recall@k

Top-k bedeutet hier die **k größten Schlüssel**. Da unsere Ausgaben aufsteigend
sortiert sein sollen, wird deren Suffix der Länge k ausgewählt. Vorab festgelegt
wurden k∈{1,5,10,32}, soweit k≤N, sowie k=N als vollständige Mengenkontrolle.
Recall@N ist für jede gültige Permutation 1 und kein Nachweis guter Sortierung.

Es werden zwei Varianten angegeben:

1. **Stabile Datensatzauswahl:** Schnittmenge zwischen den ausgewählten
   Originalindizes und den letzten k Indizes der korrekten stabilen Sortierung,
   geteilt durch k. Bei einem Gleichstand am Auswahlrand gehören in dieser
   Suffix-Konvention die späteren Originalindizes zur Referenzmenge.
2. **Gleichwertige Schlüssel am Rand zulassen:** Alle Schlüssel strikt oberhalb
   des k-ten Grenzwerts sind erforderlich. Für die verbleibenden Plätze darf
   jeder Datensatz mit genau diesem Grenzwert ausgewählt werden. Gezählt werden
   die ausgewählten erforderlichen Datensätze plus höchstens die zulässige
   Anzahl von Grenzwert-Datensätzen, geteilt durch k.

Beispiel: Beim bisherigen Output-Szenario mit 8 Bit, N=256, gleichen Schlüsseln
und η=0,25 sind sämtliche 1.000 Bitonic-Ausgaben nach Schlüsselwert korrekt,
aber keine ist vollständig stabil. Der stabile Recall@10 beträgt 97,76 %,
die zweite Variante 100 %. Der Unterschied betrifft die Auswahl gleichwertiger
Datensätze am Rand. Standard-τ-b erreicht hier seine Obergrenze von im Mittel
0,998046; die normierte Schlüsselordnung beträgt 1.

Für dieselbe Konfiguration der Rangsortierung ist keine Ausgabe eine gültige
Permutation. Bedingtes τ und bedingter Recall bleiben daher undefiniert;
der über alle Versuche gemittelte Nullnutzen-Recall beträgt 0.

In `recall.csv` bedeutet `*_mean_valid` den Mittelwert auf gültigen Ausgaben.
`*_mean_all_invalid_zero` ist eine zusätzlich definierte Bewertung, in der
ungültige Ausgaben Nullnutzen erhalten. Sie wird nicht als nachträglich
reparierte Ausgabe interpretiert.

Die Auswahlperspektive unterstützt die Abgrenzung zu einer näherungsweisen
Ranking-/Auswahlaufgabe wie PRISM. Sie ist kein PRISM-Benchmark: Es werden
weder dessen Scores und KV-Blöcke noch dessen nachgelagerte Inferenzgüte geprüft.

## Abdeckung und fehlende Daten

| Quelle | Erwartete Konfigurationen | Ausgewertet | Gespeicherte Ausgaben ausgewertet |
|---|---:|---:|---:|
| Direkte Referenz | 288 | 288 | 288.000 |
| Periodisch: Upstream und Output | 576 | 576 | 576.000 |
| Periodisch: Toleranzbereich | 288 | 283 | 283.000 |
| Gesamt | 1.152 | 1.147 | 1.147.000 |

Die 288 Upstream-Konfigurationen sind in Flags und Originalindizes exakt mit
der direkten Referenz identisch. Sie sind ein kontrollierter Doppelbericht,
keine unabhängigen neuen Versuche. Insgesamt werden dieselben 24.000 Eingaben
über verschiedene Bedingungen wiederverwendet. Von den 864.000 periodischen
Ausgaben sind 859.000 vollständig lesbar.

Die gespeicherte Datei `results/periodic_deadband/trial_outcomes.npz` besitzt
kein abgeschlossenes ZIP-Zentralverzeichnis. Aus ihren lokalen ZIP/ZIP64-Headern
sind 567 vollständige Mitglieder lesbar; deren Größen und CRC32 wurden geprüft.
Das sind 283 vollständige Paare aus Flags und Originalindizes plus ein weiterer
Flags-Eintrag. Die Datei wurde nicht verändert. Auch die geprüfte frühere
Archivkopie enthält denselben unvollständigen Datenstand.

Für **8 Bit, N=256, duplicates_allowed** fehlen vollständige Originalindizes in:

- η=0,15: Rangsortierung;
- η=0,20: Bitonic und Rangsortierung;
- η=0,25: Bitonic und Rangsortierung.

Die vorhandene Genauigkeitstabelle enthält auch diese fünf Konfigurationen.
Daraus lassen sich ihre Kendall-, Abstands- und Recall-Werte jedoch nicht
rekonstruieren. Die 5.000 fehlenden Ausgaben werden als Datenlücke ausgewiesen,
nicht als algorithmische Fehlsortierungen gezählt. Ein späterer Wiederholungslauf
müsste als neue Reproduktion mit eigener Herkunft dokumentiert werden; in diesem
Sprint wurde keiner ausgeführt.

## Prüfung und Reproduktion

- Neun gezielte Tests bestehen, einschließlich aller 240 Permutationen zweier
  kleiner Eingaben, Gleichständen, falschen Indizes und 8-Bit-Grenzwerten.
- 40 unabhängige SciPy-Kontrollen bestätigen die implementierte τ-b-Formel.
- Alle verfügbaren Gültigkeits-, Korrektheits- und Stabilitätsflags sowie die
  zugehörigen Anzahlen der bisherigen CSV-Tabellen wurden reproduziert.
- 192 verfügbare rauschfreie Konfigurationen erreichen die korrekte stabile
  Ausgabe, die τ-b-Obergrenze und normierte Schlüsselordnung 1.
- 3.911 Recall-Zeilen bestehen die Prüfungen für Nenner, Nullnutzen und k=N.
- Hashes sämtlicher Quelldateien blieben vor und nach der Auswertung gleich.

```bash
python -m pip install -r requirements/analysis.txt
python -m unittest discover -s tests -p test_ranking_quality.py -v
python -m qant_sorting quality --allow-incomplete --output-dir results/ranking_quality_reproduced
```

Der Runner benötigt den bisherigen Korpus und die gespeicherten Dateien
`accuracy.csv`, `metadata.json` und `trial_outcomes.npz` in `results/reference`,
`results/periodic` und `results/periodic_deadband`. Falls sie im lokalen Checkout
fehlen, müssen sie aus dem vorhandenen Ergebnisarchiv übernommen werden.
Das Zielverzeichnis muss leer sein. Ohne `--allow-incomplete` wird eine
unvollständige ZIP-Datei abgewiesen. Mit der Option werden ausschließlich
prüfbare vollständige Mitglieder verwendet und fehlende Fälle aufgelistet.

| Datei in `results/ranking_quality_20261007/` | Inhalt |
|---|---|
| `summary.csv` | Korrektheit, Gültigkeit, Stabilität, τ und Inversionszahlen |
| `recall.csv` | Alle k, beide Gleichstandsregeln und explizite Nenner |
| `distance.csv.gz` | 195.738 Zeilen mit exakten Schlüsselabständen und Paaranzahlen |
| `coverage.csv` | Sämtliche 1.152 erwarteten Konfigurationen einschließlich der Lücken |
| `metadata.json` | Definitionen, Versionen, Archivstatus und Quell-/Codehashes |
| `validation.json`, `checks.json` | Kontrollen und vollständig bezeichnete Datenlücken |

Die Auswertung verändert das Komplexitätsmodell C=(T,S,H,D) nicht. Sie ergänzt
Qualitätsmetriken. Die bisherigen Rausch- und Quantisierungsszenarien bleiben
physikalisch unterschiedlich skaliert. Dieser Sprint verbessert ihre
Beschreibung; ein fairer physikalischer Vergleich ist Aufgabe des nächsten
Sprints zum gemeinsamen Rauschmodell.
