# Gemeinsames Signal-, Rausch- und Quantisierungsmodell

Stand: 7. Oktober 2026 · Sprint 3

## Ergebnis und Zweck

Der bisherige Vergleich „5,9 % vs. 100 % korrekt“ vergleicht unterschiedliche
Störstellen, Signalabstände und Rundungsregeln. Er ist **kein Nachweis eines
photonischen Rauschvorteils**. Das neue Modell macht diese Unterschiede einzeln
sichtbar. Es erklärt, wann eine Vergleichsentscheidung kippt, einen falschen
Gleichstand erzeugt oder einen echten Gleichstand aufbricht.

Die gemeinsamen Kontrollen liefern bei gleicher Störung und Rundung vor der
Transformation **identische Entscheidungen für direkten und idealen periodischen
Vergleich**. Bei einheitlicher Ausgangsquantisierung sind die Ergebnisse der
ausgewählten 8-Bit-Kontrollen ebenfalls sehr ähnlich. Daraus folgt keine
allgemeine Gleichwertigkeit realer Geräte: Kennlinie, Wandlung, Rauschen,
Kalibrierung und Kosten fehlen weiterhin als Hardwaredaten.

Dies ist **ein Modell mit gezielt veränderten Einstellungen**. Es ersetzt keine
alten Dateien oder Messergebnisse. Die Implementierung rechnet in Float64 und
ruft das SDK nicht auf. Das Komplexitätsmodell **C = (T, S, H, D)** bleibt
unverändert; die folgenden Größen sind Signal- und Evaluierungsgrößen.

## 1. Ein Signalweg für beide Varianten

Für ganzzahlige Schlüssel a,b im Bereich 0 bis 2^b−1 gilt

\[
\Delta=2^{-b},\qquad x_a=a\Delta,\quad x_b=b\Delta,
\qquad d=x_a-x_b=(a-b)\Delta.
\]

`bits` bezeichnet im Code die Schlüsselbreite. Die verwendeten Eingaben liegen
bereits exakt auf diesem Raster. Eine Eingangsrundung auf Δ verändert sie nicht.
Für andere Eingabewerte wäre sie ausdrücklich zu modellieren.

Der gemeinsame Ablauf lautet:

\[
z=\operatorname{clip}_{[-1,1]}
  Q_{q_{\rm pre}}(d+b_{\rm in}+\sigma_{\rm in} Z_{\rm in}),
\]
\[
y=\operatorname{clip}_{[-1,1]}Q_{q_{\rm out}}
  \big((1+\epsilon_g)g(z)+b_{\rm out}+\sigma_{\rm out}Z_{\rm out}\big).
\]

Die Elektronik entscheidet anhand `sign(y)` und behandelt y=0 mit der bisherigen
Regel nach Originalindex. Originalschlüssel bleiben unverändert; fehlerhafte
Ränge werden nicht repariert.

- **σ_in:** effektive Störung der Differenz vor der Übertragungsfunktion.
  Sie fasst vorerst Fehler der Eingabe/MVM zusammen; sie ist kein gemessener
  Einzelmodulatorwert. Bei getrennten Eingabefehlern gilt
  Var(e_a−e_b)=Var(e_a)+Var(e_b)−2Cov(e_a,e_b).
- **σ_out:** zusätzliche Auslesestörung nach der Übertragungsfunktion, in der
  unten festgelegten normierten Ausgangseinheit.
- **b_in, b_out:** verbleibende feste Offsets während eines Durchlaufs, etwa
  nach einer Kalibrierung. Das ist eine Drift-Sensitivität, kein zeitliches
  Driftmodell. Ein Offset wird nicht für jeden Vergleich neu gezogen.
- **ε_g:** relativer Verstärkungsfehler; im vorliegenden Lauf auf null gesetzt.
  Eine Implementierungsoption ist noch kein experimenteller Nachweis ihrer Wirkung.
- **Z_in, Z_out:** unabhängige Standardnormalvariablen, neu pro Vergleich.
  Zeit-/Kanalkorrelationen sind im aktuellen Sweep nicht kalibriert oder simuliert.

Die Begrenzung auf [−1,1] hält den idealen Sinus auf einem monotonen Ast und
verhindert Vorzeichenumkehr durch periodisches Zurückfalten bei Übersteuerung.
Sie ist eine **angenommene Modellgrenze**, keine bestätigte Hardwarefunktion.
Überschreitungen vor der Begrenzung werden gezählt. Die frühere signed-b-bit-
Begrenzung [−1/2,1/2−Δ] bleibt nur in den alten Experimenten bestehen.

## 2. Signalabstände und Normierung

Es werden zwei Funktionen verglichen:

\[
g_{\rm direkt}(d)=d,\qquad
g_{\rm periodisch}(d)=\frac{\sin(\alpha d)}{\alpha},
\qquad \alpha=\pi/2.
\]

Beide haben am Vergleichspunkt d=0 die Steigung 1. Die Division durch α ist
eine Wahl der **Ausgangseinheit**. Damit dieselbe Zahl σ_out vergleichbar ist,
muss auch reales Ausgangsrauschen durch dieselbe Verstärkung geteilt werden.
Das setzt weder einen kostenlosen Verstärker noch identische Geräte voraus.
Gleiche normierte σ_out sind hier eine ausdrücklich angenommene Kontrollbedingung.

Für Schlüsselabstand m=|a−b| beträgt der Abstand des idealen Signals zur
Nullentscheidung mΔ beziehungsweise sin(αmΔ)/α. Allgemein ist der Abstand
benachbarter Signalstufen g((m+1)Δ)−g(mΔ); er ist beim Sinus nicht konstant.
Für die Vergleichsentscheidung ist insbesondere der Abstand von ±Δ zu 0 relevant.

| Größe | 4 Bit | 8 Bit |
|---|---:|---:|
| Schlüsselabstand Δ | 0,0625 | 0,00390625 |
| Direkt: Abstand für m=1 zur Null | 0,0625 | 0,00390625 |
| Normierter Sinus: Abstand für m=1 zur Null | ca. 0,0623996 | ca. 0,00390623 |
| Angenommene Standardabweichung 0,25Δ | 0,015625 | 0,0009765625 |

Eine Nichtlinearität verstärkt auch bereits vorhandenes Eingangsrauschen.
Für kleine Störungen ohne wirksame Quantisierung/Begrenzung gilt näherungsweise

\[
\operatorname{Var}(y\mid d)\approx
 (1+\epsilon_g)^2[g'(d)]^2\sigma_{\rm in}^2+\sigma_{\rm out}^2,
\]

sofern die beiden Störungen unabhängig sind. Das unnormierte sin(αd) hat nahe
null ungefähr α-fachen Signalabstand **und** α-faches Eingangsrauschen.
Die größere Steigung allein verbessert daher dieses Verhältnis nicht.
Gegen festes, später hinzugefügtes Ausleserauschen kann Verstärkung helfen;
dafür müssen reale Verstärkung, Bereich, Rauschposition und Kosten bekannt sein.

## 3. Quantisierung ist eine Entscheidungsregel

\[
Q_q(v)=q\,\operatorname{roundToEven}(v/q),\qquad Q_0(v)=v.
\]

Bei q_out=Δ gehört [−Δ/2,+Δ/2] zum Nullcode. Exakte Halbwerte gehen zum geraden
Code; insbesondere werden ±Δ/2 null. Ein positiver Nachbarschlüssel d=Δ hat
damit nur **Δ/2 Abstand zum falschen Gleichstand**, obwohl sein Abstand zu
null Δ beträgt. Ein groberes Raster schützt echte Gleichstände besser, kann
aber ungleiche Schlüssel zusammenfallen lassen.

Die Quantisierer werden deterministisch ausgewertet. Es wird **kein zusätzliches
unabhängiges „Quantisierungsrauschen“ q²/12** hinzuaddiert: Diese Näherung ist an
den hier entscheidenden Schwellen nicht allgemein gerechtfertigt.

q_pre=0 ist der Standard ohne Zwischenrundung. q_pre=Δ, q_out=0 wird nur als
Kontrolle verwendet: sign(g(Q_Δ(d+e)))=sign(Q_Δ(d+e)) für beide monotonen,
vorzeichenerhaltenden Funktionen. Das modelliert keine nachgewiesene hostfreie
Q.ANT-Kaskade. q_out=0 bedeutet keine zusätzliche feste Ausgangsrundung und
kein Toleranzband. Bei kontinuierlichem Rauschen wird dann d=0 mit
Wahrscheinlichkeit 1 als ungleich behandelt.

**Rasterweite ist nicht Hardwareauflösung:** Schlüsselbreite, simuliertes
Quantisierungsraster, BF16-Datentyp und physikalische ENOB sind verschiedene
Angaben. Der symmetrische Modellbereich [−1,1] mit Schritt Δ enthält mehr als
2^b Codes; daraus wird keine b-bit-ADC-Aussage abgeleitet. Die reale Codezahl,
Asymmetrie, Übersteuerung und Wandlung müssen separat belegt werden.

## 4. Was den alten Unterschied erklärt

Für den alten direkten/upstream-Pfad, d=Δ und σ=0,25Δ:

\[
P(\text{falscher Gleichstand})=
\Phi(-2)-\Phi(-6)\approx 2{,}275\%,
\]
\[
P(\text{Vorzeichenumkehr})=\Phi(-6)\approx9{,}87\cdot10^{-10}.
\]

Für echte Gleichstände beträgt die Wahrscheinlichkeit des Aufbrechens nach
dieser Rundung 2Φ(−2)≈4,550 %. Ein falscher Gleichstand ist noch nicht in jedem
Fall eine falsche binäre Sortierentscheidung: Das hängt vom Originalindex ab.
Ein Array benötigt viele solche Entscheidungen; Einzelpaarwahrscheinlichkeiten
dürfen nicht ohne Abhängigkeitsmodell zu einer Arrayquote hochgerechnet werden.

Im alten Output-Szenario kam σ=0,25Δ **nach** dem unnormierten periodischen
Signal hinzu, ohne nachgeschaltetes festes Raster. Für 8 Bit gilt:

| Alter Pfad | Abstand / jeweiliges σ | Bedeutung |
|---|---:|---|
| Direkte Differenz zur Null | 4 | σ in Differenzeinheiten |
| Direkte Differenz zur Rundungsgrenze | 2 | Eintritt in den falschen Nullcode |
| Idealer unnormierter Sinus zur Null | ca. 6,283 | σ in unnormierten Score-Einheiten |
| Gespeichertes offizielles CPU-Ergebnis zur Null | ca. 7,996 | kleinster ungleicher Score nach BF16 und Referenzkorrektur |

Der letzte Wert folgt aus `results/periodic/pair_checks.json`:
0,007808685302734375 / 0,0009765625. Er ist ein **CPU-Softwarewert**, kein
Hardwareabstand. BF16-Phasenrundung macht die Kennlinie stufig; eine glatte
Sinusableitung beschreibt diese CPU-Schritte nicht. Das neue Float64-Modell
isoliert die Modellannahmen und ersetzt diese SDK-Prüfung nicht.

Damit ist der Einwand des Betreuers bestätigt und präzisiert. „Etwa 6σ“
beschreibt den idealen alten Sinusfall; die konkret gespeicherte CPU-Implementierung
hat einen anderen Abstand. Beide sind mit der 2σ-Rundungsgrenze nicht unmittelbar
vergleichbar.

## 5. Belege und ausdrücklich angenommene Parameter

| Parameter / Aussage | Verwendung / Wert | Evidenzstatus |
|---|---|---|
| Schlüsselbreite und Normierung | b=4/8, Δ=2^−b | Festgelegter Versuch; gespeicherter Korpus |
| Ideale periodische Funktion | sin(πd/2)/(π/2) | Mathematische Kontrollfunktion; keine gemessene tcos-Kennlinie |
| Native API und CPU-BF16 | periodische tcos-API; CPU berechnet Kosinus | Belegter SDK-Quellstand 2.3.1 [2]; kein ENOB-Nachweis |
| σ_in/Δ, σ_out/Δ | jeweils 0 oder 0,25 | Angenommene Sensitivitätswerte, Anschluss an alten η-Endpunkt |
| q_pre/Δ | 0 oder 1 | Angenommener Schalter zur Trennung der Zwischenrundung |
| q_out/Δ | 0; 0,5; 1; 2 | Angenommene Auflösungssensitivität; keine DAC/ADC-Spezifikation |
| b_out/Δ | −0,25; 0; +0,25 | Angenommene feste Restoffsets |
| b_in, ε_g | 0 im gespeicherten Lauf | Ausgeschlossene Effekte dieses Laufs; Code erlaubt spätere Variation |
| Gaussianität, Unabhängigkeit | unabhängige Samples pro Vergleich/Stufe | Kontrollannahme, keine belegte Q.ANT-Verteilung |
| Signalgrenzen | [−1,1], symmetrische Begrenzung | Kontrollannahme; reale zulässige Bereiche unbekannt |
| Referenzunsicherheit | bislang nicht separat geschätzt | Im Offset-/Auslesebudget explizit zu ergänzen, sobald Daten vorliegen |
| RIN/Shot/Thermal, Fehlerfortpflanzung | strukturgebende Modellgrundlage | López-March et al. [1], Abschnitt 2, Gl. 6–9, S. 6–8 |
| RIN −145 dB/Hz, 1550 nm, 400 kHz Laserlinienbreite | nur als Kontext der Quelle genannt | Messaufbau aus [1], S. 8; **nicht in die Sortiersimulation übernommen** |
| Q.ANT-Bandbreite, Photoströme, thermische PSD, Kovarianzen | unbekannt; kein Zahlenwert eingesetzt | Herstellerdaten/Messungen erforderlich |

### Anschluss an ein physikalisches Modell

[1] trennt Rauschquellen und propagiert Photostromschwankungen über die
Übertragungsfunktion. Die Arbeit untersucht eine andere Silizium-PIP-Anordnung;
ihre normierten Varianzdiagramme liefern kein universelles absolutes σ für
unseren Sortervergleich. Übernommen wird die **Modellstruktur**, nicht eine
scheinbar gerätespezifische Rauschzahl.

Für eine einzelne Photodiode und weiße, einseitige spektrale Dichten lautet
eine passende Parametrisierung:

\[
\operatorname{Var}(\delta I)=B_{\rm eq}
 \left(S_{I,\rm th}+2q_e I+10^{\mathrm{RIN}_{\rm dB/Hz}/10} I^2\right).
\]

I: Ampere; B_eq: äquivalente Rauschbandbreite in Hz; S_I,th: A²/Hz;
10^(RIN/10): 1/Hz; q_e: Elementarladung. Ergebnis: A².
`receiver_current_variance` implementiert diese Formel nur mit explizit
übergebenen Werten. Sie wird mangels belegter Geräteparameter **nicht** zur
Parametrierung der aktuellen Sortierläufe benutzt. Laserlinienbreite ist nicht
die elektrische Rauschbandbreite; RIN pro Hz allein ist keine Varianz.

Für die Abbildung in unsere Signalgröße gilt in erster Ordnung
Var(s)≈JΣ_IJᵀ; der Jacobian J enthält Empfängertransfer und Normierung.
`projected_variance` erhält die gesamte Kovarianz. Bei einem Differenzempfänger
sind positive Zweigströme und deren Korrelationen nötig: Der Shot-Term darf
nicht mit einem vorzeichenbehafteten Differenzstrom berechnet werden. Ein
gemeinsamer RIN-Anteil kann sich abhängig vom Aufbau teilweise aufheben.
Zusätzliche Kanal-/Phasenfehler und Kalibrierfehler müssen ohne Doppelzählung
ergänzt werden. Die Kleinsignalnäherung gilt nicht pauschal nahe Singularitäten,
Sättigung oder starken Störungen.

Eine gemessene Referenz ist ebenfalls verrauscht:
Var(y−y_ref)=Var(y)+Var(y_ref)−2Cov(y,y_ref). Bei einer einmalig gespeicherten
Referenz ist ihr Fehler zwischen Vergleichen gemeinsam, kein jedes Mal neu
unabhängig gezogenes Rauschen. Eine Zeitserie ist nötig, um das zu trennen.

## 6. Durchgeführte Kontrollen und Ergebnisse

Der Lauf `results/common_noise_20261007/` enthält:

- 280 Paarfälle mit jeweils 100.000 Stichproben: 4/8 Bit, zwei Funktionen,
  zehn Einstellungen und Abstände 0, ±1, ±2, ±(2^b−1).
- 182 analytisch prüfbare Wahrscheinlichkeitsfälle bestanden die dokumentierte
  Monte-Carlo-Toleranz (6 Standardfehler plus 5/n und gegebenenfalls eine
  explizite Schranke für die ausgelassene Clipping-Wahrscheinlichkeit).
  Für nichtlineare kombinierte Störungen wird keine exakte Gaussianität behauptet.
- 1.400.000 gepaarte Entscheidungen der Zwischenrundungs-Kontrolle waren identisch.
- 144 Sortierfälle / 14.400 Sortierläufe: jeweils die ersten 100 vorhandenen
  Eingaben aus sechs Datensätzen (4 Bit N=16; 8 Bit N=16/256; beide Familien),
  sechs Einstellungen, beide Funktionen und beide Sortermappings.
- Alle 24 rauschfreien Sortierfälle waren korrekt und stabil. Die 1.200 gepaarten
  Sortierausgaben der Zwischenrundungs-Kontrolle waren exakt identisch.

Der kleine Lauf dient der Modellprüfung, nicht einer abgeschlossenen statistischen
Hardwarebewertung. Beide Funktionen nutzen dieselben Zufallszahlen als Kontrolle;
die zwei Varianten sind deshalb **keine unabhängigen Wiederholungen**. Bitonic
und Rangsortierung erhalten getrennte Streams. Ergebnisse aus 100 Eingaben sind
nicht die alten 1.000er-Ergebnisse unter neuer Beschriftung.

Beispiel: 8 Bit, N=256, unterschiedliche Schlüssel, je 100 Eingaben. In diesen
Zeilen stimmen direkte und ideale periodische Variante überein:

| Einstellung | Mapping | gültig | vollständig korrekt | mittleres τ-b, gültige Ausgaben | Recall@10, gültig / ungültig=0 |
|---|---|---:|---:|---:|---:|
| σ_in=0,25Δ; σ_out=0; q_out=Δ | Bitonic | 100/100 | 8/100 | 0,999814 | 0,998 / 0,998 |
| dieselbe Einstellung | Rang | 100/100 | 4/100 | 0,999819 | 0,998 / 0,998 |
| σ_in=σ_out=0,25Δ; q_out=Δ | Bitonic | 100/100 | 0/100 | 0,999371 | 0,993 / 0,993 |
| dieselbe Einstellung | Rang | 72/100 | 0/100 | 0,999384 | 0,997222 / 0,718 |
| σ_in=σ_out=0,25Δ; q_out=2Δ | Bitonic | 100/100 | 0/100 | 0,996376 | 0,973 / 0,973 |
| dieselbe Einstellung | Rang | 0/100 | 0/100 | nicht definiert | nicht definiert / 0 |

Diese Fälle zeigen den Einfluss von Rauschkombination und Quantisierung sowie
die Bedeutung der Gültigkeitsquote bei Rangsortierung. Ein hoher bedingter
Recall darf ungültige Ausgaben nicht verdecken. Der konstante positive Offset
kann einzelne Quoten durch die asymmetrische Gleichstands-/Originalindexregel
auch verbessern; das ist kein Argument für absichtlich erzeugte Hardwaredrift.

`sort_quality.csv` enthält zusätzlich getrennte Fehler und Nenner für
Schlüsselabstand 1, 2 und ≥3. Die Indizes und Flags sind gespeichert und können
mit `ranking_quality.py` genauer ausgewertet werden. Recall meint die größten
k Schlüssel und ist hier gleichstandsneutral; τ-b und normalisiertes τ_key
bleiben getrennt (Definitionen in [RANKING_QUALITY.md](RANKING_QUALITY.md)).

## 7. Reproduktion und nächster Evidenzschritt

```bash
python -m pip install -r requirements/analysis.txt
python -m unittest discover -s tests -p 'test_common_noise_model.py' -v
python -m qant_sorting common-noise --output-dir results/common_noise_reproduced
```

Die Ausgabe muss in ein leeres Verzeichnis erfolgen. Metadaten enthalten
Versionen, Seeds, Einstellungen, Ein-/Ausgabehashes und die unveränderte
Korpusidentität. Der neue Lauf benötigt keine fehlenden alten Deadband-Ausgaben
und rekonstruiert diese auch nicht. Die in Sprint 2 dokumentierte Datenlücke
bleibt bestehen.

Für eine **Q.ANT-bezogene** Bewertung benötigen wir als Nächstes eine gemessene
oder belegte Kennlinie mit Einheit/Normierung, zulässige Eingangsbereiche,
Wandlungsraster/-grenzen, wiederholte Ausgaben je Signalniveau, Bandbreite,
Kalibrierverfahren und Zeit-/Kanalkorrelationen. Der
[Messplan](QANT_MEASUREMENT_PLAN.md) beschreibt diese Abfrage.
Bis dahin bleiben die Zahlen Sensitivitätsannahmen. Ein größerer Sweep sollte
erst auf einem begründeten Parameterbereich aufbauen. Laufzeit-/Energieaussagen
erfordern zusätzlich den tatsächlichen Datenweg und Messungen.

## Quellen

[1] R. López-March et al., *Noise in analog programmable-photonic computation*,
arXiv:2604.24541v1, 27.04.2026. Abschnitt 2, Gl. 6–9 sowie Abschnitt 3.
https://arxiv.org/abs/2604.24541v1
Die vorhandene lokale PDF wurde gelesen; SHA256:
`3c982697860af379e2bf08dda78f89dbf45b1d74631ecfd92ad06298e6411874`.

[2] Q.ANT SDK 2.3.1, Commit `72a2d99f10240b6df3c6d0f636dfa0e2b5d38902`.
`python/qant_native_computing_toolkit/_wrapper.py`, Funktion
`calc_scaled_periodic_nl_fprop`, und
`src/qant_driver_import/backend_cpu.rs`, Funktion
`qant_driver_scaled_periodic_nl_npu`. Quellstand lokal geprüft am 07.10.2026.
https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/tree/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902

[3] Eigene unveränderte CPU-Paarprüfung: `results/periodic/pair_checks.json`;
alte Signalpfade: `comparison.py`, `periodic_comparison.py`.
Neue Modellgleichungen, Normierung und Sensitivitätswerte sind eigene explizite
Festlegungen; sie werden keiner der Quellen als Gerätespezifikation zugeschrieben.
