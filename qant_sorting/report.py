"""Build the single current German thesis report from saved evidence.

Reading guide
-------------
The authored narrative lives in report_assets/thesis_report.md. Dynamic table
markers select existing CSV/JSON evidence; they never run a sorting experiment.
references.json and report_provenance.json document literature and provenance.
Missing or ambiguous result rows raise an error rather than being interpolated.

The parser deliberately supports only the small Markdown subset used here:
headings, paragraphs, bullets, tables, code blocks, display mathematics and
explicit report markers. This keeps the source editable without an HTML engine.
ReportLab lays out text and tables; Matplotlib renders exact math and charts.
All intermediate images are held in memory. Only the final PDF is published to
reports/, using a temporary sibling and atomic replacement after a successful
build. Historical report generation lives in tools/build_legacy_reports.py.
Importing this module does not read evidence, write reports or run experiments.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile

from qant_sorting.paths import ROOT
ASSETS = ROOT / "report_assets"
DEFAULT_OUTPUT = ROOT / "reports/Masterarbeit_Hybride_Photonische_Sortierung.pdf"
PAGE_W, PAGE_H = 595.276, 841.890
LEFT, RIGHT, TOP, BOTTOM = 54, 54, 58, 52
CONTENT_W = PAGE_W - LEFT - RIGHT
INK, ACCENT, PALE, MUTED = "#173247", "#167D8D", "#EDF4F6", "#566471"


def read_rows(relative_path):
    """Read a UTF-8 CSV as strings without changing its data or units."""
    with (ROOT / relative_path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_one(rows, **criteria):
    """Require one exact row; numeric keys accept CSV decimal formatting."""
    def matches(row):
        """Compare declared numeric criteria numerically and all others literally."""
        return all(float(row[k]) == v if isinstance(v, (int, float))
                   else row[k] == v for k, v in criteria.items())
    found = [row for row in rows if matches(row)]
    if len(found) != 1:
        raise ValueError(f"Expected one result for {criteria}, found {len(found)}")
    return found[0]


def number(value, digits=0):
    """Format saved numeric values in German notation; blanks remain undefined."""
    if value in (None, ""):
        return "–"
    result = f"{float(value):,.{digits}f}"
    return result.replace(",", "@TEMP@").replace(".", ",").replace("@TEMP@", ".")


def percent(value, digits=1):
    """Format fractions as percentages without converting an undefined value to zero."""
    return "–" if value in (None, "") else number(100 * float(value), digits) + " %"


def evidence_tables():
    """Assemble tables from recorded results and explicitly authored model assumptions.

    Values derived from architecture formulas are separate from empirical rows.
    Returned dictionaries contain captions, cells, optional column proportions,
    and a source note. Assertions protect the documented evidence inventory.
    """
    reference = read_rows("results/reference/accuracy.csv")
    quality = read_rows("results/ranking_quality_20261007/summary.csv")
    recall = read_rows("results/ranking_quality_20261007/recall.csv")
    common = read_rows("results/common_noise_20261007/sort_quality.csv")
    cpu = read_rows("results/cpu_baseline_20261007/summary.csv")
    pairs = json.loads((ROOT / "results/periodic/pair_checks.json").read_text())
    assert (len(reference), len(quality), len(recall), len(common), len(cpu)) == (288, 1147, 3911, 144, 192)
    assert sum(int(r["trials"]) for r in quality) == 1147000
    tables = {}

    def add(key, title, rows, widths=None, note=""):
        """Register a named table; the renderer handles wrapping and pagination."""
        tables[key] = dict(title=title, rows=rows, widths=widths, note=note)

    add("evidence_overview", "Erreichter Stand und Aussagegrenzen", [
        ["Bereich", "Vorhandene Evidenz", "Offen"],
        ["Literatur und Modell", "Fünf Architekturen; C = (T,S,H,D); hergeleitete Schranken", "Keine universelle neue Komplexitätstheorie"],
        ["Implementierung", "Bitonic, Rangsortierung, lineares und periodisches CPU-SDK", "Nützliche hostfreie Kaskade"],
        ["Qualität und Rauschen", "Referenz, τ, Abstandsfehler, Recall; gemeinsame Kontrollen", "Gerätespezifische Kennlinie, Rauschen und Drift"],
        ["Leistung", "Stabile digitale CPU-Baseline", "GPU, vollständige NPU-Zeit und Energie"],
    ], [1, 2.0, 1.6])
    # New CPU feasibility evidence remains separate from historical pair results.
    affine = json.loads((ROOT / "results/affine_periodic_20261009/summary.json").read_text())
    pair_rows = [["Breite", "Paare je Pfad", "Direkt: Fehler", "Host-Phase: Fehler", "Affin: Fehler"]]
    for bits in (4, 8):
        chosen = {r["path"]: r for r in affine["pairs"] if r["bits"] == bits}
        pair_rows.append([f"{bits} Bit", number(chosen["affine_phase"]["ordered_pairs"])] +
                         [number(chosen[path]["errors"]) for path in
                          ("direct_difference", "host_phase", "affine_phase")])
    add("affine_pairs", "Affine CPU-Phase im Vergleich zu zwei Kontrollen", pair_rows,
        [.7, 1.1, 1.1, 1.2, 1.0], "Quelle D7: summary.json; alle geordneten Paare, einschließlich Gleichständen. SDK 2.3.1, kein Zusatzrauschen.")
    sort_rows = [["Affine Variante", "Bitonic korrekt / stabil", "Rang korrekt / stabil"]]
    for dataset in affine["sample"]["datasets"]:
        bits, size, family = dataset.split("_", 2)
        label = f"{bits[1:]} Bit, N={size[1:]}, " + ("verschieden" if family == "distinct" else "Duplikate erlaubt")
        selected = [select_one(affine["sorts"], dataset=dataset, mapping=mapping, path="affine_phase")
                    for mapping in ("bitonic", "rank")]
        sort_rows.append([label] + [f"{r['correct']} / {r['stable']}" for r in selected])
    add("affine_sorts", "Vollständige Sortierkontrolle der affinen Variante", sort_rows,
        [2.0, 1.2, 1.2], "Quelle D7: je Zelle 100 gespeicherte Listen. Alle Ausgaben gültig. Beide Kontrollpfade: jeweils 100 korrekt und stabil in jeder Zelle.")
    for label, symbol, description in [("lower", "Ω", "Untere"), ("tight", "Θ", "Enge"), ("upper", "O", "Obere")]:
        def bound(expr):
            """Apply a bound symbol to the same architecture-specific scaling expression."""
            return f"{symbol}({expr})"
        add("bounds_" + label, f"{description} Schranken der spezifizierten Architekturen", [
            ["Architektur", "T", "S", "H", "D"],
            ["Pipeline-Bitonic", bound("N log²N"), bound("N"), bound("N log²N"), bound("log²N") + " / " + bound("1")],
            ["Beyette, rezirkulierend", bound("N log²N"), bound("N"), bound("N"), bound("1")],
            ["Desmulliez, Shuffle", bound("N log²N"), bound("N"), bound("N"), bound("1")],
            ["Louri, materialisierte Ränge", bound("N²"), bound("N²"), bound("N²"), bound("1")],
            ["Radix, feste Parameter", bound("N"), bound("N"), bound("1"), bound("1")],
        ], [1.65, 1.15, .63, 1.15, 1.22], "Eigene Ableitung unter den Definitionen und Annahmen in Kapitel 4. D der Pipeline: passiv / nach jeder Stufe regeneriert.")
    add("architecture_focus", "Rolle der fünf Architekturen in dieser Arbeit", [
        ["Architektur", "Übernommene Idee", "Umsetzung im aktuellen Versuch"],
        ["Stirk / Athale", "Feste aktive C&E-Stufen", "Bitonic-Funktionsmapping"],
        ["Beyette", "Wiederverwendete Vergleichsfläche", "Ressourcen- und Latenzkontrast"],
        ["Desmulliez", "Shuffle, Masken und Bypass", "Quellenbasierte Zählung, kein eigener NPU-Lauf"],
        ["Louri", "Breite Paarphase und Ränge", "Rang-Funktionsmapping"],
        ["Mizutani", "Photonische Datenbewegung", "Hybrider Architekturkontrast"],
    ], [1, 1.5, 1.75])
    add("pair_check", "Erschöpfende periodische Paarprüfung im offiziellen CPU-Backend", [
        ["Schlüssel", "Geordnete Paare", "Fehler vor Referenz", "Fehler nach Referenz", "Kleinster Abstand m"],
        *[[str(r["bits"]) + " Bit", number(r["ordered_pairs"]), number(r["raw_zero_threshold_errors"]), number(r["referenced_errors"]), number(r["minimum_cpu_score_margin"], 8)] for r in pairs["rows"]],
    ], [0.8, 1.1, 1.15, 1.15, 1.2], "Quelle: results/periodic/pair_checks.json. Kein Zusatzrauschen; keine Hardwareausführung.")
    add("noise_parameters", "Parameter und ihr Evidenzstatus", [
        ["Größe", "Gespeicherte Kontrolle", "Begründung / Grenze"],
        ["Schlüsselraster Δ", "2⁻⁴ oder 2⁻⁸", "Normierung des Integerkorpus"],
        ["σ_in / Δ; σ_out / Δ", "0 oder 0,25", "Angenommene Sensitivität, keine Messung"],
        ["q_pre", "0 oder Δ", "Keine oder gemeinsame Zwischenrundung"],
        ["q_out", "0; 0,5Δ; Δ; 2Δ", "Getrennte Auflösungsannahme in Paarfällen"],
        ["β_out", "−0,25Δ; 0; +0,25Δ", "Fester Restoffset, keine Drifttrajektorie"],
        ["β_in; ε_g", "0; 0", "Unterstützte Effekte hier deaktiviert"],
        ["Kennlinie und Bereich", "d bzw. sin(πd/2)/(π/2); [−1,1]", "Ideale Float64-Funktionen, kein tcos-Fit"],
        ["Rauschverteilung", "Unabhängiges Gaußrauschen", "Schwere Tails und Korrelationen noch offen"],
    ], [1.1, 1.45, 1.8], "Quelle: results/common_noise_20261007/metadata.json und docs/COMMON_NOISE_MODEL.md. Nicht jede Kombination wird als vollständige Sortierung getestet.")
    add("experiment_inventory", "Vorhandene Versuchsserien", [
        ["Serie", "Umfang", "Prüfzweck / Status"],
        ["Referenz, sechs η", "288 Konfigurationen; 288.000 Sortierungen", "Gespeicherte vollständige Ausgaben"],
        ["Lineares CPU-SDK", "48.000 rauschfreie Sortierungen", "Softwareintegration, kein Timing"],
        ["Periodische Paare", "256 + 65.536 geordnete Paare", "Vollständige endliche Domänenprüfung"],
        ["Affine CPU-Phase", "3 × (256 + 65.536) Paare; 3.600 Sortierungen", "Begrenzte Machbarkeitskontrolle mit zwei Kontrollpfaden"],
        ["Periodische Szenarien", "864 Konfigurationen; nominell 864.000 Sortierungen", "Historische Serie; Roharchive fehlen im Git-Stand"],
        ["Zusätzliche Rankingmetriken", "1.147 / 1.152 Konfigurationen; 1.147.000 Ausgaben", "Referenz + historische Szenarien; 5 Lücken"],
        ["Gemeinsames Rauschmodell", "28 Mio. Paarentscheidungen; 14.400 Sortierungen", "Synthetische Kontrollen, eigenes Protokoll"],
        ["CPU-Baseline", "192 Konfigurationen; 1.728 Zeitwiederholungen", "24.000 Eingaben; Batch- und Typvarianten"],
    ], [1.25, 1.9, 1.8])
    refrows = [["Breite / N", "Eingaben", "η", "Bitonic korrekt", "Rang korrekt"]]
    for bits, n in [(4, 16), (8, 256)]:
        for family in ("distinct", "duplicates_allowed"):
            for eta in (.15, .20, .25):
                rr = [r for r in reference if int(r["key_bits"]) == bits and int(r["n"]) == n and r["family"] == family and float(r["eta"]) == eta]
                assert len(rr) == 2
                vals = {("bitonic" if "bitonic" in r["mapping"].lower() else "rank"): percent(r["accuracy"]) for r in rr}
                refrows.append([f"{bits} Bit / {n}", "verschieden" if family == "distinct" else "Duplikate erlaubt", number(eta, 2), vals["bitonic"], vals["rank"]])
    add("reference_maxn", "Vollständige Korrektheit bei maximaler getesteter Listengröße", refrows, [1.1, 1.4, .55, 1.1, 1.0], "Quelle: results/reference/accuracy.csv; je Zelle 1.000 Versuche. Ungültige Ausgaben zählen als Fehler.")
    qrows, crows = [], []
    for mapping in ("bitonic", "rank"):
        criteria = dict(source="reference", scenario="direct", dataset="b8_n256_distinct", eta=.25, mapping=mapping)
        qrows.append(select_one(quality, **criteria))
        crows.append(select_one(recall, **criteria, k=10))
    add("quality_case", "8 Bit, N = 256, verschiedene Schlüssel, η = 0,25", [
        ["Kennzahl", "Bitonic", "Rangsortierung"],
        ["Gültige Ausgaben / 1.000", *[r["valid_outputs"] for r in qrows]],
        ["Vollständig korrekt", *[percent(r["whole_sort_accuracy"]) for r in qrows]],
        ["Mittleres τ_b, gültige Ausgaben", *[number(r["tau_b_mean"], 6) for r in qrows]],
        ["Mittlere Inversionen, gültige Ausgaben", *[number(r["inversions_valid_mean"], 3) for r in qrows]],
        ["Recall@10, gültige Ausgaben", *[percent(r["tie_neutral_mean_valid"], 3) for r in crows]],
        ["Recall@10, ungültige Ausgaben = 0", *[percent(r["tie_neutral_mean_all_invalid_zero"], 3) for r in crows]],
    ], [2.1, 1, 1], "Quellen: results/ranking_quality_20261007/summary.csv und recall.csv. Bei verschiedenen Schlüsseln stimmen die beiden Recall-Varianten überein.")
    commonrows = [["Einstellung", "Mapping", "Gültig / 100", "Korrekt / 100", "τ_b gültig", "Recall@10 alle"]]
    for setting, label in [("prequantized_control", "Gemeinsame Zwischenrundung"), ("combined", "Ein- und Ausgangsrauschen"), ("coarse_output", "Grobes Ausgaberaster 2Δ")]:
        for mapping in ("bitonic", "rank"):
            r = select_one(common, dataset="b8_n256_distinct", setting=setting, transfer="direct", mapping=mapping)
            other = select_one(common, dataset="b8_n256_distinct", setting=setting, transfer="ideal_sine", mapping=mapping)
            for key in ("valid", "correct", "tau_b_mean_valid", "recall_tie_neutral_mean_all_invalid_zero"):
                assert r[key] == other[key], (setting, mapping, key)
            commonrows.append([label, "Bitonic" if mapping == "bitonic" else "Rang", r["valid"], r["correct"], number(r["tau_b_mean_valid"], 6), percent(r["recall_tie_neutral_mean_all_invalid_zero"], 1)])
    add("common_noise_cases", "Gemeinsames Modell: ausgewählte vollständige Sortierungen", commonrows, [1.65, .75, .75, .85, 1.0, 1.0], "Quelle: results/common_noise_20261007/sort_quality.csv. 8 Bit, N = 256, verschiedene Schlüssel. Direkte und ideal-periodische Funktion stimmen in diesen ausgewählten Kennzahlen überein. „Alle“ zählt ungültige Ausgaben mit null.")
    cpur = [["Typ", "Listen je Batch", "Batchzeit [µs]", "Amortisiert [µs/Liste]", "Rel. IQR"]]
    for dtype in ("int64", "uint8"):
        for batch in (1, 1000):
            r = select_one(cpu, dataset="b8_n256_distinct", storage_dtype=dtype, batch_size=batch)
            cpur.append([dtype, number(batch), number(float(r["median_mean_batch_s"]) * 1e6, 2), number(float(r["amortized_s_per_array"]) * 1e6, 2), percent(r["relative_iqr"], 1)])
    add("cpu_case", "Digitale Baseline: 8 Bit, N = 256, verschiedene Schlüssel", cpur, [.7, 1.1, 1.1, 1.3, .8], "Quelle: results/cpu_baseline_20261007/summary.csv. Median aus neun Wiederholungen; CPU- und Softwareumgebung siehe Text. Kein NPU-Vergleich.")
    resources = [["N", "Mapping", "Vergleiche", "Lineare Aufrufe", "Logische Bytes"]]
    for n in (16, 64, 256):
        m = int(math.log2(n)); stages = m * (m+1)//2
        for label, count, calls in [("Bitonic", n*stages//2, stages), ("Rang", n*(n-1)//2, 1)]:
            resources.append([str(n), label, number(count), number(calls), number(6*count+4*calls)])
    add("resource_counts", "Direktes lineares Mapping bei vollständig passenden Chargen", resources, [.55, .9, 1.2, 1.25, 1.2], "Eigene Zählung: 4 Eingabebytes + 2 Ausgabebytes je BF16-Paar; 4 Gewichtsbytes je Aufruf. Keine gemessenen Treiber- oder PCIe-Bytes.")
    add("module_map", "Codeübersicht nach Aufgabe", [
        ["Dateien", "Funktion und Grenze"],
        ["input_validation.py", "Schlüsseltypen, Wertebereiche und Eingabeformen prüfen"],
        ["comparison.py; sorting_schedules.py; metrics.py", "Gleichschrittiger Komparator, aktive Bitonic-Stufen, Ränge, Gültigkeit, Ordnung und Stabilität"],
        ["run_noise_sweep.py; verify_results.py", "Referenzläufe, Seeds, gespeicherte Ausgaben und exakter Reproduktionsvergleich"],
        ["sdk_mapping.py; run_sdk_control.py; install_sdk.py", "Gepinnte CPU-SDK-Installation, BF16-Differenz und rauschfreie Integration"],
        ["periodic_comparison.py; run_periodic_evaluation.py", "Phasencodierung, Referenzkorrektur, historische Szenarien und Nullbereich"],
        ["check_periodic_pairs.py; check_sdk_nonlinearity.py", "Endliche Paarprüfung und getrennte ReLU-/Min-Max-Kontrolle"],
        ["check_affine_periodic.py", "Affine CPU-Phasenbildung, erschöpfende Paare und begrenzte vollständige Sortierkontrolle"],
        ["measure_periodic_curve.py", "Wiederholte API-Ausgaben, Codes und Zeiten; explizite Backendprüfung"],
        ["ranking_quality.py; evaluate_ranking_quality.py; saved_output_reader.py", "τ, Inversionen, Recall und CRC-geprüfte eingeschränkte Archivlesung"],
        ["common_noise_model.py; run_common_noise_controls.py", "Gemeinsame Einheiten, explizite Störstellen und analytische / Monte-Carlo-Kontrollen"],
        ["run_cpu_baseline.py", "Stabile digitale Sortierung, Kalibrierung, Batchzeit und Metadaten"],
        ["hardware_conditions.py; summarize_periodic_results.py", "Logische Ressourcen und historische Zusammenfassungen; keine physische Zeitmessung"],
        ["legacy/: model.py; sorting.py; evaluate.py; validate.py", "Historisches gröberes Ausgangsmodell und zugehörige Validierung"],
        ["qant_sorting/report.py; report_assets/thesis_report.md", "Aktueller Gesamtbericht aus Text, Quellen und gespeicherten Tabellen"],
        ["legacy/build_reports.py; report_assets/report_template.html", "Historischer Generator; Ausgabe nach tmp/legacy_reports"],
        ["tests/: Modell-, Metrik-, SDK- und Strukturtests", "Gezielte Modell-, Qualitäts-, Backend- und Benchmark-Vertragsprüfungen (alle unter tests/)"],
    ], [2, 2.6])
    add("hardware_plan", "Benötigte Herstellerinformationen und Messungen", [
        ["Frage", "Konkrete Erhebung", "Nutzen für das Mapping"],
        ["Zulässige u-/v-Bereiche", "Versionierter Treibervertrag, Einheiten und Kanalnormierung", "Legale Phasen und Amplituden"],
        ["Kennlinie und Nullpunkt", "Dichte Sweeps plus verwendete Differenzcodes", "u₀, monotones Intervall und Mindestabstand"],
        ["Auflösung und Rundung", "Codehistogramme, DAC-/ADC-Einstellungen", "Quantisierung getrennt von BF16"],
        ["Rauschen und Korrelation", "Wiederholungen je Pegel/Kanal; Rohverteilungen und Tails", "Physikalische Parameter statt η-Annahme"],
        ["Drift und Kalibrierung", "Zeitgestempelte Referenzen, Last-/Temperaturfolgen", "Gemeinsame Fehler und Kalibrierintervall"],
        ["Kapazität und Kaskade", "Bestätigte Dimensionen, Pufferspeicherung und Datenpfad", "Aufrufzahl und vermiedene Hostschritte"],
        ["Zeit und Energie", "Cold-/Warm-Läufe, Transfers, vollständige Leistungsspuren", "Gleiche Aufgabe gegen CPU/GPU"],
    ], [1.05, 1.75, 1.55], "Grundlage: docs/QANT_MEASUREMENT_PLAN.md. Anfragevorlage vorhanden; kein dokumentierter Messzugang.")
    provenance = json.loads((ASSETS / "report_provenance.json").read_text())
    add("source_inventory", "Ausgewertete bereitgestellte Dateien", [
        ["ID", "Dokument", "Seiten"],
        *[[s["id"], s["title"], str(s["pages"])] for s in provenance["supplied_sources"]],
    ], [.55, 4.0, .55], "Kennungen 01–25 entsprechen den bereitgestellten Recherchedateien; P1/P2 den Präsentationen, B1 dem ausführlichen Bericht. Dateinamen und vollständige Hashes stehen in report_provenance.json.")
    add("data_inventory", "Ergebnisdateien und Verfügbarkeit", [
        ["ID / Verzeichnis", "Inhalt", "Verfügbarkeit im Git-Stand"],
        ["D1: results/reference", "Sechs η; Accuracy, Ausgaben, Fehler und Metadaten", "Vollständige Referenzdateien"],
        ["D2: results/sdk_reference", "Rauschfreie lineare SDK-Ausgaben", "Ergebnisse und Metadaten"],
        ["D3: results/periodic/pair_checks.json", "Alle 4-/8-Bit-Paare nach Referenzkorrektur", "Paarprüfung vorhanden; ältere Sortier-Roharchive fehlen"],
        ["D4: results/ranking_quality_20261007", "summary, recall, distance, coverage, Prüfungen", "Abgeleitete Daten; fünf historische Ausgabelücken"],
        ["D5: results/common_noise_20261007", "Paarfälle, Skalen, Sortierausgaben und Qualität", "Vollständige gespeicherte Kontrollserie"],
        ["D6: results/cpu_baseline_20261007", "Einzelzeiten, Aggregation, Umgebung und Validierung", "Gemessene CPU-Baseline"],
        ["data/inputs.npz", "24 Datensätze mit je 1.000 Eingaben", "Gemeinsamer Korpus mit festem Datei-Hash"],
        ["D7: results/affine_periodic_20261009", "Alle Paarscores, 3.600 Sortierausgaben, Zählungen und SDK-Quellprüfung", "Neue CPU-Kontrolle; keine Hardwaremessung"],
        ["validation; docs", "Prüfprotokolle, Methoden und Hardwaregrenzen", "Versionsabhängige Belege; Zeitstempel beachten"],
    ], [1.55, 1.6, 1.65])
    add("glossary", "Zentrale Begriffe", [
        ["Begriff", "Bedeutung in diesem Bericht"],
        ["APC / Anbit", "Analog Programmable-Photonic Computation / zweikomponentige klassische optische Informationseinheit"],
        ["MVM / GEMM", "Matrix-Vektor-Multiplikation / allgemeine Matrix-Matrix-Multiplikation"],
        ["C&E", "Compare-and-Exchange: vergleichen und Originaldatensätze gegebenenfalls tauschen"],
        ["T / physische Zeit", "Skalare real-RAM-artige Gesamtarbeit / separat gemessene oder modellierte Sekunden"],
        ["S / H / D", "Lebende logische Wörter / installierte Verarbeitungspositionen / unregenerierte optische Tiefe"],
        ["Ω / Θ / O", "Untere / passende untere und obere / obere asymptotische Schranke"],
        ["Δ / η / σ", "Schlüssel- oder Signalraster / dimensionsloser Rauschfaktor / Standardabweichung in Signaleinheiten"],
        ["ADC / DAC / ENOB", "Analog-Digital-Wandler / Digital-Analog-Wandler / effektive Bitzahl einer definierten Messung"],
        ["BF16", "Bfloat16-Speicher-/Schnittstellenformat; keine Zusage effektiver Analogpräzision"],
        ["tcos / CPU-Kosinus", "Gerätespezifische periodische Funktion / separat untersuchter CPU-Ersatz"],
        ["Nullbereich / Referenz", "Toleriertes Gleichstandsintervall / abgezogener Ausgangswert für d = 0"],
        ["Gültigkeit / Stabilität", "Jeden Originaldatensatz genau einmal ausgeben / Originalreihenfolge gleicher Schlüssel bewahren"],
        ["Kendall-τ-b / Recall@k", "Bindungskorrigierte Rangübereinstimmung / Anteil korrekt ausgewählter Top-k-Elemente"],
        ["RIN / O/E/O", "Relative Intensitätsrauschdichte / optisch-elektronisch-optischer Übergang"],
    ], [1.15, 3.4])
    return tables


def check_provenance():
    """Verify pinned result hashes; external reading copies need not exist in a clone.

    The authored text is intentionally editable. Its current hash is recorded
    in the build validation, while the consolidation manifest records the
    initially reviewed source edition. Scientific inputs must match that edition.
    """
    manifest = json.loads((ASSETS / "report_provenance.json").read_text())
    additions = json.loads((ASSETS / "affine_evidence.json").read_text())
    for item in manifest["repository_evidence"] + additions["repository_evidence"]:
        path = ROOT / item["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Evidence changed since report consolidation: {item['path']}")


def build(output):
    """Render the authored report, keeping all experiments and evidence read-only."""
    # Defer optional rendering imports until an actual build is requested.
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "qant_report_mpl"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.mathtext import math_to_image
    from matplotlib.font_manager import FontProperties
    from PIL import Image as PILImage
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether, CondPageBreak
    from reportlab.platypus.tableofcontents import TableOfContents

    check_provenance()
    tables = evidence_tables()
    for name, filename in [("Report", "DejaVuSans.ttf"), ("ReportBold", "DejaVuSans-Bold.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(ASSETS / filename)))
    pdfmetrics.registerFontFamily("Report", normal="Report", bold="ReportBold", italic="Report", boldItalic="ReportBold")
    styles = {
        "body": ParagraphStyle("body", fontName="Report", fontSize=9.5, leading=14.2, textColor=colors.HexColor(INK), spaceAfter=8.0, allowWidows=0, allowOrphans=0),
        "h1": ParagraphStyle("h1", fontName="ReportBold", fontSize=19, leading=24, spaceAfter=17, textColor=colors.HexColor(INK), keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName="ReportBold", fontSize=11.4, leading=15.3, spaceBefore=13, spaceAfter=7, textColor=colors.HexColor(ACCENT), keepWithNext=True),
        "caption": ParagraphStyle("caption", fontName="ReportBold", fontSize=9, leading=12.4, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor(INK), keepWithNext=True),
        "note": ParagraphStyle("note", fontName="Report", fontSize=7.5, leading=10.6, spaceBefore=5, spaceAfter=12, textColor=colors.HexColor(MUTED)),
        "cell": ParagraphStyle("cell", fontName="Report", fontSize=7.7, leading=10.7, textColor=colors.HexColor(INK)),
        "headcell": ParagraphStyle("headcell", fontName="ReportBold", fontSize=7.7, leading=10.7, textColor=colors.white),
        "code": ParagraphStyle("code", fontName="Report", fontSize=7.25, leading=10.8, backColor=colors.HexColor(PALE), borderPadding=8, spaceBefore=4, spaceAfter=12),
        "bullet": ParagraphStyle("bullet", fontName="Report", fontSize=9.5, leading=14.2, leftIndent=12, firstLineIndent=-9, spaceAfter=5, textColor=colors.HexColor(INK)),
    }
    count = {"table": 0, "figure": 0}

    def rich(text):
        """Escape authored text and translate only bold/code spans, never raw HTML."""
        value = html.escape(str(text))
        value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
        value = re.sub(r"`([^`]+)`", r'<font color="#167D8D">\1</font>', value)
        # Typeset the fixed mathematical subscripts used in prose and tables.
        # This does not interpret arbitrary HTML or modify path/code identifiers.
        value = re.sub(r"([Δσβτ])_(in|out|key|b)\b", r"\1<sub>\2</sub>", value)
        return value

    def para(text, kind="body"):
        """Create a wrapped paragraph with the requested semantic style."""
        return Paragraph(rich(text), styles[kind])

    def render_table(spec):
        """Produce repeatable header rows and natural row-level page breaks."""
        count["table"] += 1
        caption = para(f"Tabelle {count['table']}. {spec['title']}", "caption")
        caption.keepWithNext = False
        widths = spec.get("widths") or [1] * len(spec["rows"][0])
        widths = [CONTENT_W * value / sum(widths) for value in widths]
        cells = [[para(value, "headcell" if row == 0 else "cell") for value in values] for row, values in enumerate(spec["rows"])]
        table = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(INK)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(PALE)]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, 0), .7, colors.HexColor(ACCENT)),
            ("LINEBELOW", (0, -1), (-1, -1), .4, colors.HexColor("#C9D7DC")),
        ]))
        # Keep compact tables intact. Long inventories may split by row and
        # repeat their header; this avoids wasting a whole introductory page.
        if len(spec["rows"]) <= 9:
            caption.keepWithNext = True
            return [caption, table, para(spec.get("note", ""), "note")]
        return [CondPageBreak(120), caption, table, para(spec.get("note", ""), "note")]

    def image_from_buffer(buffer, max_width=CONTENT_W, natural_points=None):
        """Retain an in-memory PNG buffer for all multi-pass PDF layout operations."""
        buffer.seek(0)
        width, height = PILImage.open(buffer).size
        shown = min(max_width, natural_points if natural_points else max_width)
        result = Image(buffer, width=shown, height=shown*height/width)
        result.hAlign = "CENTER"
        return result

    def equation(tex):
        """Render mathematical notation with mathtext, scaled only if width requires it."""
        buffer = io.BytesIO()
        math_to_image("$" + tex + "$", buffer, prop=FontProperties(size=11), dpi=240, format="png", color=INK)
        buffer.seek(0); width, _ = PILImage.open(buffer).size
        return KeepTogether([Spacer(1, 6), image_from_buffer(buffer, CONTENT_W-16, width*72/240), Spacer(1, 14)])

    def plot(key):
        """Draw saved numerical evidence; never smooth, fit or manufacture new data."""
        plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":9, "axes.spines.top":False, "axes.spines.right":False, "axes.labelcolor":INK, "text.color":INK})
        if key == "reference_accuracy":
            rows = read_rows("results/reference/accuracy.csv")
            fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), layout="constrained", sharey=True)
            for ax, family, title in zip(axes, ("distinct", "duplicates_allowed"), ("Verschiedene Schlüssel", "Duplikate erlaubt")):
                for bits, n, color in [(4,16,"#167D8D"), (8,256,"#C77629")]:
                    for mapping, line, marker in [("bitonic", "-", "o"), ("rank", "--", "s")]:
                        rr = sorted([r for r in rows if int(r["key_bits"])==bits and int(r["n"])==n and r["family"]==family and (("bitonic" in r["mapping"].lower()) == (mapping=="bitonic"))], key=lambda r:float(r["eta"]))
                        ax.plot([float(r["eta"]) for r in rr], [100*float(r["accuracy"]) for r in rr], line, marker=marker, markersize=3, color=color, label=f"{bits} Bit, N={n}, {'B' if mapping=='bitonic' else 'R'}")
                ax.set_title(title, fontsize=9); ax.set_xlabel("η = σ / Δ"); ax.set_ylim(-2,103); ax.grid(alpha=.18)
            axes[0].set_ylabel("Vollständig korrekte Listen [%]")
            axes[1].legend(fontsize=6.4, frameon=False, loc="lower left")
            title = "Referenzmodell bei maximaler getesteter Listengröße. B: Bitonic, R: Rangsortierung; je Punkt 1.000 Listen. Quelle: results/reference/accuracy.csv."
        elif key == "cpu_baseline":
            rows = read_rows("results/cpu_baseline_20261007/summary.csv")
            fig, ax = plt.subplots(figsize=(7.2, 3.0), layout="constrained")
            for dtype, color in [("int64", "#C77629"), ("uint8", "#167D8D")]:
                for batch, line in [(1, "--"), (1000,"-")]:
                    rr = sorted([r for r in rows if int(r["key_bits"])==8 and r["family"]=="distinct" and r["storage_dtype"]==dtype and int(r["batch_size"])==batch],key=lambda r:int(r["n"]))
                    ax.plot([int(r["n"]) for r in rr], [float(r["amortized_s_per_array"])*1e6 for r in rr], line, marker="o", markersize=3, color=color, label=f"{dtype}, Batch {batch}")
            ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_xticks([2,4,8,16,32,64,128,256], [2,4,8,16,32,64,128,256])
            ax.set_xlabel("Listenlänge N"); ax.set_ylabel("Amortisierte Zeit [µs / Liste]"); ax.grid(alpha=.18); ax.legend(fontsize=7, frameon=False)
            title = "CPU-Baseline für 8-Bit-Eingaben mit verschiedenen Schlüsseln. Amortisierte Batchzeiten, keine Einzelanfragelatenzen. Quelle: results/cpu_baseline_20261007/summary.csv."
        else:
            raise ValueError(f"Unknown figure {key}")
        buffer = io.BytesIO(); fig.savefig(buffer, format="png", dpi=220); plt.close(fig)
        count["figure"] += 1
        return [KeepTogether([Spacer(1, 8), image_from_buffer(buffer), para(f"Abbildung {count['figure']}. {title}", "note")])]

    def diagram(key):
        """Use compact explanatory tables to show paths without implying chip topology."""
        if key == "signal_path":
            spec = dict(title="Allgemeiner hybrider Signalweg", rows=[
                ["Schritt", "Operation", "Zu prüfende Systemgröße"],
                ["1. Elektronische Eingabe", "Schlüssel lesen, skalieren und packen", "Speicher und Hostzeit"],
                ["2. Elektrooptische Codierung", "Werte in Phase / Amplitude abbilden", "Auflösung, Modulation und Energie"],
                ["3. Photonischer Kern", "Lineare Transformation / bestätigte Nichtlinearität", "Kennlinie, Verlust und Störung"],
                ["4. Auslese", "Detektion, Wandlung und Übertragung", "Rauschen, Raster und Schnittstelle"],
                ["5. Elektronische Ausgabe", "Entscheiden, tauschen / akkumulieren, validieren", "Vollständige Sortierqualität und Zeit"],
            ], widths=[1.15, 1.8, 1.5], note="Eigene schematische Darstellung; kein Q.ANT-Layout. Bei einer bestätigten Kaskade können interne Grenzen anders liegen.")
        elif key == "mappings":
            spec = dict(title="Dieselbe Vergleichsfunktion in zwei vollständigen Abläufen", rows=[
                ["Phase", "Bitonic", "Rangsortierung"],
                ["Paare vorbereiten", "N/2 Paare der aktuellen Stufe", "Alle N(N−1)/2 ungeordneten Paare"],
                ["Differenz und Entscheidung", "Parallel innerhalb einer Stufe", "Unabhängige breite Paarphase"],
                ["Elektronisch weiterarbeiten", "Originaldatensätze tauschen", "Ränge summieren, Belegung prüfen"],
                ["Nächster Schritt", "Nächste abhängige Stufe bis K", "Einmalige Ausgabe aus gültigen Rängen"],
            ], widths=[1.2, 1.75, 1.75], note="Die Unterschiede betreffen Abhängigkeiten, Ressourcen und Datenbewegung; beide Mappings verwenden denselben stabilen Ausgabevertrag.")
        else:
            raise ValueError(f"Unknown diagram {key}")
        return render_table(spec)

    class ReportDocument(BaseDocTemplate):
        """Track headings for bookmarks, the table of contents and running headers."""
        def __init__(self, filename):
            """Create one printable A4 text frame with consistent page furniture."""
            super().__init__(str(filename), pagesize=(PAGE_W,PAGE_H), leftMargin=LEFT, rightMargin=RIGHT, topMargin=TOP, bottomMargin=BOTTOM, title="Hybride photonische Sortierung – Gesamtdokumentation der Masterarbeit", author="Bharadwaj Srikumar", subject="Recherche, Modelle, Code und Evaluierung; Stand 9. Oktober 2026")
            self.chapter = "Gesamtdokumentation der Masterarbeit"
            frame = Frame(LEFT,BOTTOM,CONTENT_W,PAGE_H-TOP-BOTTOM,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
            self.addPageTemplates(PageTemplate(id="report", frames=frame, onPage=self.decorate))

        def beforeDocument(self):
            """Reset per-pass headings so multiBuild produces stable page furniture."""
            self.chapter = "Gesamtdokumentation der Masterarbeit"

        def decorate(self, canvas, doc):
            """Draw unobtrusive headers and page numbers outside the content frame."""
            canvas.saveState()
            if doc.page > 1:
                canvas.setStrokeColor(colors.HexColor("#CDDCE1")); canvas.setLineWidth(.5)
                canvas.line(LEFT,PAGE_H-40,PAGE_W-RIGHT,PAGE_H-40)
                canvas.setFont("Report",7); canvas.setFillColor(colors.HexColor(MUTED))
                canvas.drawString(LEFT,PAGE_H-31,"HYBRIDE PHOTONISCHE SORTIERUNG")
                canvas.drawRightString(PAGE_W-RIGHT,PAGE_H-31,"Forschungsstand · 09.10.2026")
                canvas.drawString(LEFT,30,"Bharadwaj Srikumar · Masterarbeit")
                canvas.drawRightString(PAGE_W-RIGHT,30,str(doc.page))
            canvas.restoreState()

        def afterFlowable(self, flowable):
            """Publish only chapter-level entries; detailed subsections stay in the body."""
            if isinstance(flowable, Paragraph) and hasattr(flowable, "report_heading"):
                title, anchor = flowable.report_heading
                self.chapter = title
                self.canv.bookmarkPage(anchor)
                self.canv.addOutlineEntry(title, anchor, level=0, closed=False)
                self.notify("TOCEntry", (0, title, self.page, anchor))

    raw = (ASSETS / "thesis_report.md").read_text(encoding="utf-8")
    cover, body = raw.split("{{toc}}", 1)
    # The cover is typeset explicitly; its authored metadata remains in Markdown.
    title_style = ParagraphStyle("cover_title", fontName="ReportBold", fontSize=29, leading=35, textColor=colors.HexColor(INK), spaceAfter=20)
    sub_style = ParagraphStyle("cover_sub", fontName="Report", fontSize=15, leading=21, textColor=colors.HexColor(ACCENT), spaceAfter=15)
    story = [Spacer(1,72), para("MASTERARBEIT · FORSCHUNGS- UND IMPLEMENTIERUNGSSTAND", "note"), Spacer(1,16), Paragraph("Hybride photonische<br/>Sortierung",title_style), Paragraph("Gesamtdokumentation der Masterarbeit",sub_style), para("Recherche, mathematische Modelle, Implementierung und Evaluierung"), Spacer(1,30), para("**Bharadwaj Srikumar**"), para("Master Informatik · Hochschule Bochum<br/>".replace("<br/>", "")), para("Betreuung: Prof. Dr. Henrik Blunck"), para("Stand: 9. Oktober 2026"), Spacer(1,25), para("**Arbeitstitel**"), para("Mapping Hybrid Optoelectronic Sorting Architectures onto Modern Photonic Accelerators: A Hardware-Aware Evaluation and Simulation"), Spacer(1,20), para("Diese Dokumentation beschreibt den erreichten Stand der Masterarbeit. Sie verbindet Literatur, mathematische Herleitung, ausführbaren Code und gespeicherte Ergebnisse. Reale Hardwarevalidierung, photonische Laufzeitvorteile und Energieeffizienz sind noch offen.","note"), PageBreak(), para("Inhaltsverzeichnis","h1")]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("toc", fontName="Report", fontSize=9.3, leading=13.5, leftIndent=0, firstLineIndent=0, spaceBefore=6, textColor=colors.HexColor(INK))]
    story += [toc]
    lines = body.splitlines(); index = 0; heading_count = 0
    while index < len(lines):
        line = lines[index].strip(); index += 1
        if not line:
            continue
        if line.startswith("# "):
            heading_count += 1
            title = line[2:]
            heading = para(title,"h1"); heading.report_heading = (title, f"chapter_{heading_count}")
            story += [PageBreak(), heading]
        elif line.startswith("## "):
            story.append(para(line[3:],"h2"))
        elif line.startswith("{{"):
            marker = line[2:-2]
            if marker.startswith("table:"):
                story += render_table(tables[marker.split(":",1)[1]])
            elif marker.startswith("figure:"):
                story += plot(marker.split(":",1)[1])
            elif marker.startswith("diagram:"):
                story += diagram(marker.split(":",1)[1])
            elif marker == "bibliography":
                refs = json.loads((ASSETS/"references.json").read_text())
                assert [r["id"] for r in refs] == list(range(1,41))
                for ref in refs:
                    block = [para(f"[{ref['id']}] {ref['authors']} ({ref['year']}). **{ref['title']}**.")]
                    if ref["url"]:
                        label = re.sub(r"^https?://", "", ref["url"])
                        link = f'<link href="{html.escape(ref["url"], quote=True)}" color="{ACCENT}">{html.escape(label)}</link>'
                        block.append(Paragraph(link,styles["note"]))
                    block += [para("**Grundlage:** " + ref["source"] + ". **Einordnung:** " + ref["role"], "note"), Spacer(1,6)]
                    story.append(KeepTogether(block))
            else:
                raise ValueError(f"Unknown marker {marker}")
        elif line.startswith("$$") and line.endswith("$$"):
            story.append(equation(line[2:-2]))
        elif line.startswith("```"):
            code = []
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index]); index += 1
            if index == len(lines):
                raise ValueError("Unclosed code block")
            index += 1
            story.append(Paragraph("<br/>".join(html.escape(c) for c in code),styles["code"]))
        elif line.startswith("|"):
            rows = [[part.strip() for part in line.strip("|").split("|")]]
            while index < len(lines) and lines[index].strip().startswith("|"):
                pieces = [part.strip() for part in lines[index].strip().strip("|").split("|")]; index += 1
                if not all(re.fullmatch(r"[-: ]+", p) for p in pieces):
                    rows.append(pieces)
            table_title = {"Stufe": "Bitonic-Beispiel für [10,3,9,1]", "Paar": "Stabile Rangbildung für [10,3,9,1]", "Funktion": "Geprüfte SDK-Funktionen und ihre Grenzen"}.get(rows[0][0], "Ausgearbeitetes Beispiel")
            story += render_table(dict(title=table_title, rows=rows, note="Eigene Darstellung auf Grundlage der im Abschnitt angegebenen Herleitung oder Quellen."))
        elif line.startswith("- "):
            story.append(para("• " + line[2:], "bullet"))
        else:
            paragraph = [line]
            while index < len(lines) and lines[index].strip() and not re.match(r"^(#|\{|\$\$|\||```|- )", lines[index]):
                paragraph.append(lines[index].strip()); index += 1
            story.append(para(" ".join(paragraph)))
    output.parent.mkdir(parents=True, exist_ok=True)
    # A failed layout must not remove the previously valid current report.
    handle, temp_name = tempfile.mkstemp(prefix=".thesis-report-", suffix=".pdf", dir=output.parent)
    os.close(handle)
    try:
        document = ReportDocument(temp_name)
        document.multiBuild(story)
        os.replace(temp_name, output)
    finally:
        if Path(temp_name).exists():
            Path(temp_name).unlink()
    return {"output": str(output), "pages": document.page, "tables": count["table"], "figures": count["figure"], "source_sha256": hashlib.sha256(raw.encode()).hexdigest(), "pdf_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    """Expose one output option; stdout is a compact machine-readable build receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
