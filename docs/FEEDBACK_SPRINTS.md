# Arbeitsplan nach dem Feedback vom 7. Oktober 2026

Ziel: Eine belastbare, zeitlich begrenzte Evaluierung von Bitonic- und
Rangsortierung. Die Anmeldung der Masterarbeit kann parallel erfolgen.
Die Arbeit muss ohne photonischen Hardwarezugang tragfähig bleiben.

## Arbeitsweise

Jeder Sprint endet mit einer konkreten Frage, einer dokumentierten Antwort,
reproduzierbarem Code beziehungsweise einer Rechnung und einer kurzen Übersicht
der verbleibenden Unsicherheiten. Zahlen werden erst nach Prüfung in die Folien
übernommen. Das bestehende Hochschuldesign bleibt erhalten.

Das Komplexitätsmodell bleibt **C = (T, S, H, D)**. T zählt weiterhin skalare
Schritte einer vollständigen Sortierung im sequenziellen real-RAM-artigen Modell.
Gemessene Sekunden und Durchsatz sind Implementierungsergebnisse, keine neue
Definition von T und keine zusätzlichen Kernparameter.

## Sprint 1 – Digitale CPU-Baseline (zuerst)

**Frage:** Wie lange benötigt eine etablierte digitale Implementierung für
dieselben stabil zu sortierenden Datensätze?

- Unveränderte 24.000 gespeicherte Eingaben verwenden.
- Sortierte Schlüssel und Originalindizes ausgeben, einschließlich stabiler
  Behandlung gleicher Schlüssel.
- NumPy `argsort(kind="stable")` plus Anordnung der Werte messen.
- Einzellisten und Stapelgrößen 10, 100 und 1.000 untersuchen.
- Originalspeicherung `int64` und passende `uint8`-Speicherung getrennt zeigen.
  Die 4-/8-Bit-Schlüsselbereiche ändern sich dadurch nicht.
- Aufwärmen, Wiederholungen, Rohzeiten, Streuung, Softwareversionen und Hardware
  dokumentieren. Laden und Ergebnisprüfung aus dem Zeitfenster heraushalten;
  Ausgabeallokation und Anordnung der Werte einschließen.

**Abschluss:** Ausführbarer Benchmark, unabhängige Korrektheitsprüfung,
Ergebnistabelle und ausdrückliche Grenze der Übertragbarkeit. Ein erster Lauf
in einer geteilten Umgebung ist eine Baseline für genau diese Umgebung; vor
abschließenden Leistungsbehauptungen auf einer kontrollierten Maschine prüfen.

**Planungsgröße:** 0,5–1 Arbeitstag. Ergebnis: `CPU_BASELINE.md` und
`results/cpu_baseline_20261007/`.

## Sprint 2 – Aussagekräftige Sortierqualität

**Stand 7. Oktober 2026:** Implementiert und auf den vorhandenen Ausgaben
ausgeführt. 1.147 von 1.152 Konfigurationen sind auswertbar, einschließlich
der zur Upstream-Variante identischen direkten Referenz. Fünf Konfigurationen
der Toleranzbereich-Variante haben keine vollständigen gespeicherten Ausgaben.
Die Quelle wurde nicht verändert und keine Sortierung neu ausgeführt.
Definitionen, Ergebnisse und Datenlücke: [RANKING_QUALITY.md](RANKING_QUALITY.md).

**Frage:** Wie stark sind fehlerhafte Ergebnisse tatsächlich gestört?

- Vorhandene gespeicherte Ausgaben auswerten, bevor Sortierungen neu ausgeführt werden.
- Vollständige Korrektheit und Stabilität beibehalten.
- Kendall-tau-b mit definiertem Umgang mit gleichen Schlüsseln ergänzen.
  Bei konstanten Listen ist tau nicht definiert; diese Fälle separat berichten.
  Da die Ausgabe eindeutige Positionen und die Schlüssel Gleichstände haben,
  wird zusätzlich die erreichbare tau-b-Obergrenze angegeben. Die auf diese
  Obergrenze normierte Schlüsselordnung wird getrennt bezeichnet.
- Vertauschte ungleiche Schlüsselpaare nach ursprünglichem Schlüsselabstand
  auswerten. Diese Ausgabequalität nicht mit der Fehlerrate einzelner interner
  Komparatoraufrufe verwechseln.
- Recall@k für vorab festgelegte k und eine erklärte Regel für Gleichstände
  am Auswahlrand ergänzen. Die Aufgabe vollständiger Sortierung bleibt von
  PRISMs anwendungsbezogener näherungsweiser Auswahl abgegrenzt.
- Ungültige Rang-Ausgaben gesondert zählen. Metriken auf gültigen Permutationen
  ausdrücklich als bedingt berichten, niemals ungültige Versuche still entfernen.

**Abschluss:** Eine kompakte Qualitätstabelle mit geprüften Beispielpermutationen
und eindeutigem Nenner für jede Kennzahl.

**Planungsgröße:** 0,5–1 Arbeitstag.

## Sprint 3 – Gemeinsames Rauschmodell

**Stand 07.10.2026: Modell und erste Kontrollen abgeschlossen.**
Siehe [COMMON_NOISE_MODEL.md](COMMON_NOISE_MODEL.md). Getrennte Störstellen,
gemeinsame Normierung, explizite Quantisierer und Quellen-/Annahmenregister sind
implementiert. 182 analytische Kontrollen und 144 ausgewählte Sortierfälle
(14.400 Läufe) sind ausgewertet; Ergebnisse unter `results/common_noise_20261007/`.
Q.ANT-spezifische Rauschparameter bleiben unbekannt. Kein Hardwarevorteil abgeleitet.

**Frage:** Welche Unterschiede bleiben bei nachvollziehbaren physikalischen
Annahmen, Signalabständen und Quantisierung bestehen?

- Zuerst ein gemeinsames Signalflussmodell mit Rauschquellen, Einheiten,
  Quantisierern und Entscheidungsgrenzen definieren.
- Direkte Differenzentscheidung und periodische Transformation unter derselben
  zugrunde gelegten Störung vergleichen. Die Nichtlinearität verändert die
  Rauschverteilung; dieselbe Zahl fuer sigma an zwei Schnittstellen stellt
  noch keinen physikalisch gleichen Versuch dar.
- Eingangsrauschen, Ausgangs-/Ausleserauschen, Quantisierung und Drift anhand
  ihrer Position unterscheiden. Keine Kennliniensteigung als kostenloses
  Signal-Rausch-Verhältnis interpretieren.
- Literaturwerte nur mit Architektur, Bandbreite und Betriebsbedingungen
  übertragen. López-March ist eine Modellgrundlage, keine Q.ANT-Kalibrierung.
- Unbekannte Hardwarewerte als Annahmen kennzeichnen und über nachvollziehbare
  Bereiche variieren. Erst einfache Paartests und Grenzfälle rechnen, danach
  ausgewählte vollständige Sortierfälle auswerten.

**Abschluss:** Kurze mathematische Spezifikation, Einheitenprüfung und kleine
reproduzierbare Kontrollfälle. Erst danach einen größeren Sweep freigeben.

**Planungsgröße:** 1–2 Arbeitstage für das Modell und erste Kontrollen;
Herstellerantworten können später einfließen.

## Sprint 4 – Rolle der periodischen Funktion und Q.ANT-Anfrage

**Frage:** Kann die Funktion einen nützlichen Teil des Sortierablaufs übernehmen?

- Mathematische Möglichkeit `u = u0 - alpha*a + alpha*b` von belegter
  Hardwareausführung unterscheiden; den konstanten Anteil ausdrücklich beachten.
- Direktes MVM-Ergebnis plus elektronische Vorzeichenentscheidung als Kontrolle.
- Q.ANT nach MVM/Nichtlinearität ohne Host-Rückkehr, internen Wandlungen,
  Puffern, Eingangsbereichen, Kennlinien, Auflösung, Rauschen und Drift fragen.
- Host-freie Verarbeitung ist nicht automatisch eine unregenerierte optische
  Kaskade. Aus ihr folgt kein gemessener D-Wert.
- Auch bei Kaskadierbarkeit den zusätzlichen Nutzen gegenüber dem direkten
  Vergleich nachweisen; der heutige tcos-Baustein ersetzt den letzten
  elektronischen Schwellwertvergleich nicht.

**Abschluss:** Dokumentierter möglicher Datenweg oder klare technische Grenze;
begrenzte Machbarkeitsstudie bleibt auch bei negativem Ergebnis verwertbar.

**Parallel starten:** Anfrageentwurf vorbereiten. Keine Nachricht ist versendet.
Kennlinienmessungen und Hardwarezugang hängen von externer Rückmeldung ab.
Vorbereitung: etwa eine kurze Arbeitssitzung, Antwortzeit nicht planbar.

## Sprint 5 – GPU und zusammengeführte Bewertung

**Frage:** Wie ändern sich die digitalen Zielwerte mit einer GPU, und unter
welchen Bedingungen könnte das hybride Mapping diese überhaupt erreichen?

- GPU-Zugang und gegebenenfalls eine empfohlene Vergleichsplattform mit dem
  Betreuer klären. Keine GPU ist in der aktuellen Ausführungsumgebung sichtbar.
- Etablierte stabile GPU-Sortierung mit gleichen Eingaben/Ausgaben verwenden.
- Bereits auf dem Gerät liegende Daten und Host-zu-Host-Gesamtzeit einschließlich
  Hin-/Rücktransfer getrennt messen. GPU-Fertigstellung korrekt synchronisieren.
- Im selben Benchmark-Protokoll Einzellisten und Stapel betrachten.
- Ohne NPU-Messungen nur bedingte Laufzeitanforderungen an das vollständige
  hybride Mapping ableiten. CPU-Simulationszeit ist keine photonische Laufzeit.
- Erst danach die betroffenen Ergebnisfolien und den Bericht aktualisieren.

**Abschluss:** Digitaler CPU/GPU-Vergleich, klar markierte Hardwareannahmen,
kurze Ergebnisdarstellung und offene Fragen.

**Planungsgröße:** 1–2 Arbeitstage nach verfügbarem GPU-Zugang, zuzüglich einer
kurzen Sitzung zur konsistenten Darstellung in Folien und Bericht.

## Korrektur der bisherigen Bestandsaufnahme

Ein früherer lokaler Prototyp enthielt bereits CPU-Mikromessungen
(`cpu_benchmarks.csv`): NumPy-Wertesortierung, neu erzeugte uint16-Eingaben,
N=8..128 und Stapelgrößen 1/256. Diese decken den aktuellen Korpus und die
Ausgabe stabiler Originalindizes nicht ab. Die Aussage, es habe noch gar keine
CPU-Zeitmessungen gegeben, war deshalb zu weitgehend. Es fehlte eine zum
aktuellen Versuch passende dokumentierte Leistungsbaseline. Die alte Datei
wird nicht als neue Baseline umetikettiert.

Der bisherige Vergleich „5,9 % vs. 100 %“ bleibt ein Ergebnis unterschiedlicher
synthetischer Rausch-/Quantisierungsbedingungen; er belegt keinen physikalischen
Vorteil. Die neuen Sprints sollen die Vergleichbarkeit herstellen.
