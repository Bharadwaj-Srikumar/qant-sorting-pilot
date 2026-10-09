# Periodischer Vergleich: Datenweg und endliche Präzision

Stand: 9. Oktober 2026. Begrenzte CPU-Machbarkeitsstudie, keine Hardwaremessung.

## Ergebnis und Bedeutung

Der bisherige Pfad liefert die Differenz bereits an den Host. Ihre elektronische
Vorzeichenentscheidung genügt; der anschließende periodische Aufruf hat dort
keinen nachgewiesenen Nutzen. Eine mathematisch äquivalente affine Phasenbildung
lässt sich in `linear_fprop` verlagern. Die öffentliche Schnittstelle liefert
aber auch dabei das Zwischenergebnis als NumPy-Array zurück. Das ist noch kein
hostfreier Datenweg.

Zusätzlich ist diese konkrete affine Umsetzung bei 8 Bit numerisch ungeeignet:
**40 von 65.536 geordneten Paaren werden ohne Zusatzrauschen fälschlich gleich**.
Bei 4 Bit sind alle 256 Paare korrekt. Direkte SDK-Differenzentscheidung und
der bestehende Pfad mit Host-Phasenbildung bleiben bei beiden Breiten korrekt.
Das negative Ergebnis gilt für die gewählten Koeffizienten und die offizielle
CPU-Arithmetik, nicht für sämtliche affinen Codierungen oder die reale NPU.

## Welche Arbeit wird wohin verlagert?

Für ganzzahlige Schlüssel a,b mit Schlüsselbreite w und Werten von 0 bis
2^w−1 werden zunächst x=a/2^w und y=b/2^w codiert. Mit u0=α=π/2 gilt im exakten Modell:

`u = u0 − α(x−y) = [x, y, 1] · [−α, α, u0]`.

Die zusätzliche konstante Eingabe bildet den Bias ab. Der CPU-Kosinus liefert
ideal `cos(u)=sin(α(x−y))` und damit das gesuchte Vorzeichen. Eine einzelne
gleiche Eingabe (0,0) legt die CPU-Nullreferenz fest. Der endgültige Schwellwert,
die Gleichstandsregel und alle Datensatzbewegungen bleiben elektronisch.

| Datenweg | Sichtbare Schritte | Einordnung |
|---|---|---|
| Elektronischer Vergleich | Host vergleicht Originalschlüssel | Digitale Baseline; keine Nichtlinearität nötig |
| Direkte SDK-Differenz | MVM → Host sign(d) | Kontrolle mit einem SDK-Aufruf |
| Bisherige periodische Variante | MVM → Host d und Phase → tcos → Host Schwelle | Zwei Aufrufe; korrekt im rauschfreien CPU-Test |
| Affine CPU-Variante | Affine MVM → Host Phase → tcos → Host Schwelle | Zwei Aufrufe; 8-Bit-Informationsverlust |
| Angestrebte interne Verbindung | Affine MVM → residenter Zwischenwert → Nichtlinearität | Vom Hersteller zu bestätigen; nicht ausgeführt |

Für P Paare pro Software-Aufrufgruppe betragen die logischen BF16-Puffermengen
ohne Kalibrierung und ohne angenommenes Caching: direkte Differenz `6P+4` Byte,
bisheriger periodischer Pfad `12P+4` Byte, affine Variante `14P+6` Byte.
Gezählt werden Eingaben, Gewichte und Ausgaben an jeder öffentlichen API-Grenze;
es sind weder gemessene PCIe-Bytes noch interne Wandlungen. Die affine Variante
spart Host-Phasenarithmetik, aber im gezeigten API-Pfad weder einen Aufruf noch
die Rückgabe eines Zwischenwerts. Sie benötigt sogar eine dritte Eingabespalte.
Diese Buchführung ergänzt die Evaluierung; C=(T,S,H,D) bleibt unverändert.

## Was das SDK tatsächlich belegt

Geprüft wurde Version 2.3.1, Quellcommit
`72a2d99f10240b6df3c6d0f636dfa0e2b5d38902`. Acht lokal gelesene Quelldateien
stimmen mit den Blob-Hashes des offiziellen Git-Baums überein; Einzeldateien
und dauerhafte Quelllinks stehen in
[`sdk_source_audit.json`](../results/affine_periodic_20261009/sdk_source_audit.json).

- `_wrapper.py` dokumentiert NumPy-BF16-Eingaben und -Ausgaben für `linear_fprop`
  sowie den getrennten periodischen Aufruf; `_utils.py` prüft NumPy-Arrays.
- `qant_driver_import/mod.rs` reserviert getrennte Ausgabepuffer und ruft
  getrennte Treiberfunktionen für MVM und periodische Verarbeitung auf.
- `backend_cpu.rs` rundet **jedes Produkt auf BF16**, akkumuliert in FP32 und
  rundet das MVM-Ergebnis wieder auf BF16. Die Nichtlinearität verwendet Kosinus.
- Die KAN-Komposition in `non_linear.rs` enthält ausdrücklich eine Addition
  des Phasenoffsets auf der CPU zwischen Treiberaufrufen. Ein höherstufiger
  Funktionsaufruf ist deshalb kein Nachweis einer hostfreien Kaskade.
- Der verknüpfte Hardwaretreiber bleibt hinsichtlich interner Verarbeitung
  und Caching undurchsichtig. Aus dem öffentlichen Vertrag folgt keine Aussage,
  dass jede Hardwareversion eine solche Verbindung grundsätzlich ausschließt.

Eine hostfreie interne Ausführung wäre zudem nicht automatisch rein optisch
oder frei von Regeneration. Eine Einsparung physischer Wandlungen oder eine
Änderung der optischen Tiefe D müsste gesondert belegt werden.

## Reproduzierbare Paarprüfung

`check_affine_periodic.py` prüft alle geordneten 4-/8-Bit-Paare und speichert
Scores und affine Phasen. Es gibt kein Zusatzrauschen, keine zusätzliche
Festkommarundung, keinen Toleranzbereich und keine wahrheitsabhängige Reparatur.

| Breite | Paare je Pfad | Direkte Differenz: Fehler | Host-Phase: Fehler | Affine Phase: Fehler |
|---|---:|---:|---:|---:|
| 4 Bit | 256 | 0 | 0 | 0 |
| 8 Bit | 65.536 | 0 | 0 | 40 |

Alle 40 Fehler sind falsche Gleichstände; kein Vorzeichen wird umgekehrt und
alle echten Gleichstände bleiben erhalten. Beim Paar (165,166) sind die drei
gerundeten Produkte `[-1.015625, +1.015625, 1.5703125]`. Die ersten beiden
heben sich auf. Es folgt dieselbe Phase 1.5703125 wie bei (0,0) und somit nach
Referenzabzug der Score null. Auch das umgekehrte Paar ist nicht unterscheidbar.
Die exakt codierbaren Eingangsschlüssel verhindern diesen Produktfehler nicht.

Die kleinste affine Scoregröße über **alle ungleichen 8-Bit-Paare ist null**.
Die kleinste *von null verschiedene* Größe 0.007808685302734375 ist deshalb
keine nutzbare Mindestreserve. Referenzabzug oder eine größere Toleranzzone
können bereits verlorene Information nicht wiederherstellen.

## Auswirkungen in beiden Sortermappings

Vor der Auswertung festgelegte Stichprobe: jeweils die ersten 100 gespeicherten
Listen aus sechs Datensätzen, zwei Mappings und drei Vergleichspfade. Das sind
3.600 vollständige CPU-Sortierläufe, davon 1.200 mit der affinen Variante.
Eingaben: beide Schlüsselfamilien bei (4 Bit,N=16), (8 Bit,N=16) und (8 Bit,N=256).
Die Stapelgröße beträgt 10. Es wurden keine Laufzeit- oder Energiemessungen erhoben.

| Affine Variante | Bitonic: korrekt und stabil / 100 | Rang: korrekt und stabil / 100 |
|---|---:|---:|
| 4 Bit, N=16, verschieden | 100 | 100 |
| 4 Bit, N=16, Duplikate erlaubt | 100 | 100 |
| 8 Bit, N=16, verschieden | 95 | 95 |
| 8 Bit, N=16, Duplikate erlaubt | 97 | 97 |
| 8 Bit, N=256, verschieden | 0 | 0 |
| 8 Bit, N=256, Duplikate erlaubt | 0 | 0 |

Alle Ausgaben bleiben in dieser Stichprobe gültige Permutationen. Falsche
Gleichstände lösen die Originalindexregel aus, obwohl unterschiedliche Schlüssel
vorliegen. Gültigkeit allein bedeutet daher keine korrekte Ordnung. Beide
Kontrollpfade sortieren jeweils alle 1.200 Listen korrekt und stabil. Die
beobachteten Stichprobenquoten sind keine Aussage über jede mögliche Liste.

## Reproduktion und gespeicherte Evidenz

Linux x86_64, Python 3.12.14, offizieller CPU-SDK 2.3.1;
NumPy 2.3.5, ml-dtypes 0.6.0, cffi 2.1.1, pycparser 3.0.
Die historischen Abhängigkeiten und Ergebnisse werden nicht ersetzt.
Eine eigene Umgebung lässt sich mit Python 3.12 wie folgt einrichten:

```bash
python3.12 -m venv .venv-affine
. .venv-affine/bin/activate
python -m pip install -r requirements-affine-control.txt
sha256sum vendor/qant-native-computing-toolkit-wheels-cpu-backend-v2.3.1.zip
wheel_dir=$(mktemp -d)
python -m zipfile -e vendor/qant-native-computing-toolkit-wheels-cpu-backend-v2.3.1.zip "$wheel_dir"
python -m pip install --no-deps "$wheel_dir/qant_native_computing_toolkit-2.3.1-cp312-cp312-linux_x86_64.whl"
python check_affine_periodic.py --output-dir results/affine_periodic_reproduced
```

Der ZIP-Hash muss
`99b4669d3256d92cc35efc1a2d6d59deef7a033d78397d71150333011eb93898`
betragen. Auch der Runner prüft diesen sowie den bestehenden Eingabekorpus-Hash
und die tatsächlich gemeldete CPU-Treiberidentität. Ein vorhandenes Ziel wird
nicht überschrieben. Kein automatischer Hardwaremodus ist enthalten.

Unter `results/affine_periodic_20261009/` liegen `summary.json` mit vollständigen
Zählungen und Umgebungs-/Quellhashes, `outputs.npz` mit allen Paarscores und
Sortierausgaben sowie `sdk_source_audit.json`. Die Paarachsen im Archiv sind
direkt die Schlüssel a,b. Sortierausgaben tragen Datensatz, Mapping und Pfad
im Namen; Flags sind `[valid, correct, stable]`. Drei gezielte Regressionstests
ergänzen die exhaustive Prüfung und die bestehenden Tests.

## Konsequenz und nächste Entscheidung

Die affine Variante wird **nicht** als korrekter 8-Bit-Komparator übernommen.
Die periodische Funktion bleibt eine begrenzte Machbarkeitsstudie mit einem
konkreten negativen Präzisionsbefund. Zunächst sind interner Datenweg,
Biasdarstellung und tatsächliche Rechen-/Signalpräzision zu klären. Erst ein
bestätigter Datenweg rechtfertigt eine gezielte Anpassung der Codierung und
einen Vergleich von Genauigkeit, Wandlungen und Gesamtaufwand gegen die
direkte Entscheidung. Eine blinde Parametersuche ist kein Ersatz dafür.

Der [Q.ANT-Anfrageentwurf](QANT_FEEDBACK_INQUIRY_DE.txt) enthält diese Fragen.
Er ist nicht versendet; Herstellerantwort und Hardwarevalidierung stehen aus.
