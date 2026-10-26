"""Build the single current English thesis report from saved evidence.

Reading guide
-------------
The authored narrative lives in report_assets/thesis_report.md. Dynamic table
markers select existing CSV/JSON evidence; they never run a sorting experiment.
references.json, sources.json and evidence.json document literature and evidence.
Missing or ambiguous result rows raise an error rather than being interpolated.

The parser deliberately supports only the small Markdown subset used here:
headings, paragraphs, bullets, tables, code blocks, display mathematics and
explicit report markers. This keeps the source editable without an HTML engine.
ReportLab lays out text and tables; Matplotlib renders exact math and charts.
All intermediate images are held in memory. Only the final PDF is published to
reports/, using a temporary sibling and atomic replacement after a successful
build.
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
DEFAULT_OUTPUT = ROOT / "reports/Masters_Thesis_Hybrid_Photonic_Sorting.pdf"
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
    """Format saved values with English separators; blanks remain undefined."""
    if value in (None, ""):
        return "–"
    result = f"{float(value):,.{digits}f}"
    return result


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
    quality = read_rows("results/ranking_quality/summary.csv")
    recall = read_rows("results/ranking_quality/recall.csv")
    common = read_rows("results/common_noise/sort_quality.csv")
    cpu = read_rows("results/cpu_baseline_20261007/summary.csv")
    pairs = json.loads((ROOT / "results/periodic/pair_checks.json").read_text())
    assert (len(reference), len(quality), len(common), len(cpu)) == (288, 288, 108, 192)
    assert sum(int(r["trials"]) for r in quality) == 288000
    tables = {}

    def add(key, title, rows, widths=None, note=""):
        """Register a named table; the renderer handles wrapping and pagination."""
        tables[key] = dict(title=title, rows=rows, widths=widths, note=note)

    add("evidence_overview", "Current status and limits of the evidence", [
        ["Area", "Available evidence", "Outstanding"],
        ["Literature and model", "Five architectures; C = (T,S,H,D); derived bounds", "No new universal complexity theory"],
        ["Implementation", "Bitonic, rank sorting, linear and periodic CPU SDK", "Useful cascade without a host round trip"],
        ["Quality and noise", "Reference, τ, distance errors, recall; shared controls", "Device-specific transfer characteristic, noise, and drift"],
        ["Performance", "Stable digital CPU baseline", "GPU, complete NPU timing, and energy"],
    ], [1, 2.0, 1.6])
    # New CPU feasibility evidence remains separate from historical pair results.
    affine = json.loads((ROOT / "results/affine/summary.json").read_text())
    pair_rows = [["Width", "Pairs per path", "Direct: errors", "Host phase: errors", "Affine: errors"]]
    for bits in (4, 8):
        chosen = {r["path"]: r for r in affine["pairs"] if r["bits"] == bits}
        pair_rows.append([f"{bits} bits", number(chosen["affine_phase"]["ordered_pairs"])] +
                         [number(chosen[path]["errors"]) for path in
                          ("direct_difference", "host_phase", "affine_phase")])
    add("affine_pairs", "Affine CPU phase compared with two controls", pair_rows,
        [.7, 1.1, 1.1, 1.2, 1.0], "Source D7: summary.json; all ordered pairs, including ties. SDK 2.3.1, no added noise.")
    for label, symbol, description in [("lower", "Ω", "Lower"), ("tight", "Θ", "Tight"), ("upper", "O", "Upper")]:
        def bound(expr):
            """Apply a bound symbol to the same architecture-specific scaling expression."""
            return f"{symbol}({expr})"
        add("bounds_" + label, f"{description} bounds of the specified architectures", [
            ["Architecture", "T", "S", "H", "D"],
            ["Pipelined Bitonic", bound("N log²N"), bound("N"), bound("N log²N"), bound("log²N") + " / " + bound("1")],
            ["Beyette, recirculating", bound("N log²N"), bound("N"), bound("N"), bound("1")],
            ["Desmulliez, shuffle", bound("N log²N"), bound("N"), bound("N"), bound("1")],
            ["Louri, materialized ranks", bound("N²"), bound("N²"), bound("N²"), bound("1")],
            ["Radix, fixed parameters", bound("N"), bound("N"), bound("1"), bound("1")],
        ], [1.65, 1.15, .63, 1.15, 1.22], "Our derivation under the definitions and assumptions in Chapter 4. Pipeline D: passive / regenerated after every stage.")
    add("architecture_focus", "Role of the five architectures in this thesis", [
        ["Architecture", "Adopted idea", "Use in the current experiment"],
        ["Stirk / Athale", "Fixed active C&E stages", "Functional Bitonic mapping"],
        ["Beyette", "Reused comparison array", "Resource and latency contrast"],
        ["Desmulliez", "Shuffle, masks, and bypass", "Source-based accounting, no separate NPU run"],
        ["Louri", "Wide pair phase and ranks", "Functional rank mapping"],
        ["Mizutani", "Photonic data movement", "Hybrid architectural contrast"],
    ], [1, 1.5, 1.75])
    add("pair_check", "Exhaustive periodic pair check in the official CPU backend", [
        ["Keys", "Ordered pairs", "Errors before reference", "Errors after reference", "Minimum margin m"],
        *[[str(r["bits"]) + " bits", number(r["ordered_pairs"]), number(r["raw_zero_threshold_errors"]), number(r["referenced_errors"]), number(r["minimum_cpu_score_margin"], 8)] for r in pairs["rows"]],
    ], [0.8, 1.1, 1.15, 1.15, 1.2], "Source: results/periodic/pair_checks.json. No added noise; no hardware execution.")
    add("noise_parameters", "Parameters and their evidence status", [
        ["Quantity", "Saved control", "Rationale / limitation"],
        ["Key grid Δ", "2⁻⁴ or 2⁻⁸", "Integer-corpus normalization"],
        ["σ_in / Δ; σ_out / Δ", "0 or 0.25", "Assumed sensitivity, not a measurement"],
        ["q_pre", "0 or Δ", "No or shared intermediate rounding"],
        ["q_out", "0; 0.5Δ; Δ; 2Δ", "Separate resolution assumption in pair cases"],
        ["β_out", "−0.25Δ; 0; +0.25Δ", "Fixed residual offset, no drift trajectory"],
        ["β_in; ε_g", "0; 0", "Supported effects disabled here"],
        ["Transfer function and range", "d or sin(πd/2)/(π/2); [−1,1]", "Ideal Float64 functions, not a tcos fit"],
        ["Noise distribution", "Independent Gaussian noise", "Heavy tails and correlations remain unresolved"],
    ], [1.1, 1.45, 1.8], "Source: results/common_noise/metadata.json and docs/COMMON_NOISE_MODEL.md. Not every combination is tested as a complete sort.")
    add("experiment_inventory", "Current experiment series", [
        ["Series", "Scope", "Purpose"],
        ["Bitonic / full rank matrix", "288 configurations; 288,000 sorts", "All outputs saved"],
        ["Linear CPU SDK", "48,000 noiseless sorts", "N² rank cells through the official API"],
        ["Louri source equations", "155,328 inputs; 400,000 boundary-case pairs", "Stable ranks and analytical noise controls"],
        ["Periodic pairs", "256 + 65,536 pairs", "Finite-domain CPU check"],
        ["Affine CPU phase", "3 × (256 + 65,536) pairs", "Precision limit against two controls"],
        ["Ranking metrics", "288,000 existing outputs", "Complete coverage; no new sorting run"],
        ["Shared model", "28 million pair decisions; 10,800 sorts", "Defined noise locations, scales, and quantization"],
        ["Digital CPU baseline", "192 configurations; 1,728 repetitions", "Stable reference with batch/type variants"],
    ], [1.3, 1.9, 1.7])
    refrows = [["Width / N", "Inputs", "η", "Bitonic correct", "Rank correct"]]
    for bits, n in [(4, 16), (8, 256)]:
        for family in ("distinct", "duplicates_allowed"):
            for eta in (.15, .20, .25):
                rr = [r for r in reference if int(r["key_bits"]) == bits and int(r["n"]) == n and r["family"] == family and float(r["eta"]) == eta]
                assert len(rr) == 2
                vals = {("bitonic" if "bitonic" in r["mapping"].lower() else "rank"): percent(r["accuracy"]) for r in rr}
                refrows.append([f"{bits} bits / {n}", "distinct" if family == "distinct" else "Duplicates allowed", number(eta, 2), vals["bitonic"], vals["rank"]])
    add("reference_maxn", "Complete correctness at the largest tested list size", refrows, [1.1, 1.4, .55, 1.1, 1.0], "Source: results/reference/accuracy.csv; 1,000 trials per cell. Invalid outputs count as failures.")
    qrows, crows = [], []
    for mapping in ("bitonic", "rank"):
        criteria = dict(dataset="b8_n256_distinct", eta=.25, mapping=mapping)
        qrows.append(select_one(quality, **criteria))
        crows.append(select_one(recall, **criteria, k=10))
    add("quality_case", "8 bits, N = 256, distinct keys, η = 0.25", [
        ["Metric", "Bitonic", "Rank sorting"],
        ["Valid outputs / 1,000", *[r["valid_outputs"] for r in qrows]],
        ["Completely correct", *[percent(r["whole_sort_accuracy"]) for r in qrows]],
        ["Mean τ_b, valid outputs", *[number(r["tau_b_mean"], 6) for r in qrows]],
        ["Mean inversions, valid outputs", *[number(r["inversions_valid_mean"], 3) for r in qrows]],
        ["Recall@10, valid outputs", *[percent(r["tie_neutral_mean_valid"], 3) for r in crows]],
        ["Recall@10, invalid outputs = 0", *[percent(r["tie_neutral_mean_all_invalid_zero"], 3) for r in crows]],
    ], [2.1, 1, 1], "Sources: results/ranking_quality/summary.csv and recall.csv. Both recall variants agree for distinct keys.")
    commonrows = [["Setting", "Mapping", "Valid / 100", "Correct / 100", "τ_b, valid", "Recall@10, all"]]
    for setting, label in [("prequantized_control", "Shared intermediate rounding"), ("combined", "Input and output noise"), ("coarse_output", "Coarse output grid 2Δ")]:
        for mapping in ("bitonic", "rank"):
            r = select_one(common, dataset="b8_n256_distinct", setting=setting, transfer="direct", mapping=mapping)
            commonrows.append([label, "Bitonic" if mapping == "bitonic" else "Rank", r["valid"], r["correct"], number(r["tau_b_mean_valid"], 6), percent(r["recall_tie_neutral_mean_all_invalid_zero"], 1)])
    add("common_noise_cases", "Shared model: selected complete sorts", commonrows, [1.65, .75, .75, .85, 1.0, 1.0], "Source: results/common_noise/sort_quality.csv. 8 bits, N = 256, distinct keys. The direct difference channel is shown; the rank variant uses the full matrix including its diagonal. “All” assigns zero to invalid outputs.")
    cpur = [["Type", "Lists per batch", "Batch time [µs]", "Amortized [µs/list]", "Rel. IQR"]]
    for dtype in ("int64", "uint8"):
        for batch in (1, 1000):
            r = select_one(cpu, dataset="b8_n256_distinct", storage_dtype=dtype, batch_size=batch)
            cpur.append([dtype, number(batch), number(float(r["median_mean_batch_s"]) * 1e6, 2), number(float(r["amortized_s_per_array"]) * 1e6, 2), percent(r["relative_iqr"], 1)])
    add("cpu_case", "Digital baseline: 8 bits, N = 256, distinct keys", cpur, [.7, 1.1, 1.1, 1.3, .8], "Source: results/cpu_baseline_20261007/summary.csv. Median of nine repetitions; see text for CPU and software environment. Not an NPU comparison.")
    resources = [["N", "Mapping", "Comparisons", "Linear calls", "Logical bytes"]]
    for n in (16, 64, 256):
        m = int(math.log2(n)); stages = m * (m+1)//2
        for label, count, calls in [("Bitonic", n*stages//2, stages), ("Louri", n*n, 1)]:
            resources.append([str(n), label, number(count), number(calls), number(6*count+4*calls)])
    add("resource_counts", "Direct linear mapping when each stage or rank batch fits in one call", resources, [.55, .9, 1.2, 1.25, 1.2], "Our accounting: 4 input bytes + 2 output bytes per BF16 pair; 4 weight bytes per call. Not measured driver or PCIe bytes.")
    add("module_map", "Code overview by task", [
        ["Files under qant_sorting/", "Function and limitation"],
        ["input_validation.py; comparison.py", "Integer domain and normalized difference channel"],
        ["sorting_schedules.py; louri_reference.py", "Bitonic and full Louri matrix; inspectable source equations"],
        ["metrics.py; ranking_quality.py", "Validity, correctness, stability, τ, recall, and distance errors"],
        ["sdk_mapping.py; periodic_comparison.py", "Linear SDK integration and separate periodic pair function"],
        ["common_noise_model.py", "Explained signal stages, quantization, and disturbance parameters"],
        ["experiments/", "Explicit experiment, verification, resource, and measurement commands"],
        ["report.py; report_assets/thesis_report.md", "Current complete report from sources and hash-verified evidence"],
        ["tests/", "Independent mathematical, API, and reproduction checks"],
    ], [2,2.6])
    add("hardware_plan", "Required manufacturer information and measurements", [
        ["Question", "Specific data collection", "Value for the mapping"],
        ["Allowable u/v ranges", "Versioned driver contract, units, and channel normalization", "Allowed phases and amplitudes"],
        ["Transfer characteristic and zero point", "Dense sweeps plus the difference codes used", "u₀, monotone interval, and minimum margin"],
        ["Resolution and rounding", "Code histograms, DAC/ADC settings", "Quantization distinguished from BF16"],
        ["Noise and correlation", "Repetitions per level/channel; raw distributions and tails", "Physical parameters replacing the assumed η"],
        ["Drift and calibration", "Time-stamped references, load/temperature sequences", "Shared errors and calibration interval"],
        ["Capacity and cascade", "Confirmed dimensions, buffer residency, and data path", "Call count and avoided host steps"],
        ["Time and energy", "Cold/warm runs, transfers, complete power traces", "Same task compared with CPU/GPU"],
    ], [1.05, 1.75, 1.55], "Basis: docs/QANT_MEASUREMENT_PLAN.md. Inquiry template available; no documented measurement access.")
    provenance = json.loads((ASSETS / "sources.json").read_text())
    add("source_inventory", "Supplied files reviewed", [
        ["ID", "Document", "Pages"],
        *[[s["id"], s["title"], str(s["pages"])] for s in provenance["supplied_sources"]],
    ], [.55, 4.0, .55], "IDs 01–25 correspond to the supplied research files. Original filenames and hashes are in sources.json.")
    add("data_inventory", "Current result collections used", [
        ["ID / directory", "Contents", "Evidence limitation"],
        ["D1: results/reference", "All Bitonic/Louri outputs, accuracy, seeds", "Assumed independent cell noise"],
        ["D2: results/sdk", "All noiseless SDK outputs and pair counts", "Official CPU backend, no hardware measurement"],
        ["D3: results/periodic", "Exhaustive periodic pair check", "Comparison function, not a matrix sorter"],
        ["D4: results/ranking_quality", "τ, recall, inversions by key distance", "Conditional ranking quality requires valid outputs"],
        ["D5: results/common_noise", "Pair and sorting controls in common units", "Synthetic Float64 models"],
        ["D6: results/cpu_baseline_20261007", "Measured CPU timings and environment", "Measurement platform of 7 October 2026"],
        ["D7: results/affine", "All scores and errors of the affine pair function", "No data path without a host round trip demonstrated"],
        ["D8: results/louri", "Source equations and threshold controls", "Isolated pair cases hold the diagonal exact"],
        ["results/resources", "Analytical call and logical-buffer counts; SDK count check", "No measured device capacities"],
        ["data/inputs.npz", "24 datasets with 1,000 lists each", "Unchanged shared input corpus"],
    ], [1.6,1.8,1.6])
    add("glossary", "Key terminology", [
        ["Term", "Meaning in this report"],
        ["APC / anbit", "Analog Programmable-Photonic Computation / two-component classical optical information unit"],
        ["MVM / GEMM", "Matrix-vector multiplication / general matrix-matrix multiplication"],
        ["C&E", "Compare-and-exchange: compare and, if necessary, exchange original records"],
        ["T / physical time", "Total scalar real-RAM-like work / separately measured or modelled seconds"],
        ["S / H / D", "Live logical words / installed processing positions / unregenerated optical depth"],
        ["Ω / Θ / O", "Lower / matching lower and upper / upper asymptotic bound"],
        ["Δ / η / σ", "Key or signal grid / dimensionless noise factor / standard deviation in signal units"],
        ["ADC / DAC / ENOB", "Analog-to-digital converter / digital-to-analog converter / effective bit count from a defined measurement"],
        ["BF16", "Bfloat16 storage/interface format; no guarantee of effective analog precision"],
        ["tcos / CPU cosine", "Device-specific periodic function / separately investigated CPU substitute"],
        ["Zero band / reference", "Tolerated tie interval / subtracted output value for d = 0"],
        ["Validity / stability", "Output every original record exactly once / preserve original order of equal keys"],
        ["Kendall-τ-b / Recall@k", "Tie-corrected rank agreement / fraction of correctly selected top-k elements"],
        ["RIN / O/E/O", "Relative intensity noise density / optical-electronic-optical transition"],
    ], [1.15, 3.4])
    return tables


def check_provenance():
    """Verify pinned result hashes; external reading copies need not exist in a clone.

    The authored text is intentionally editable. Its current hash is recorded
    in the build validation, while the consolidation manifest records the
    initially reviewed source edition. Scientific inputs must match that edition.
    """
    evidence = json.loads((ASSETS / "evidence.json").read_text())["repository_evidence"]
    for item in evidence:
        path = ROOT / item["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Current evidence hash mismatch: {item['path']}")


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
        caption = para(f"Table {count['table']}. {spec['title']}", "caption")
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
            for ax, family, title in zip(axes, ("distinct", "duplicates_allowed"), ("Distinct keys", "Duplicates allowed")):
                for bits, n, color in [(4,16,"#167D8D"), (8,256,"#C77629")]:
                    for mapping, line, marker in [("bitonic", "-", "o"), ("rank", "--", "s")]:
                        rr = sorted([r for r in rows if int(r["key_bits"])==bits and int(r["n"])==n and r["family"]==family and (("bitonic" in r["mapping"].lower()) == (mapping=="bitonic"))], key=lambda r:float(r["eta"]))
                        ax.plot([float(r["eta"]) for r in rr], [100*float(r["accuracy"]) for r in rr], line, marker=marker, markersize=3, color=color, label=f"{bits} bits, N={n}, {'B' if mapping=='bitonic' else 'R'}")
                ax.set_title(title, fontsize=9); ax.set_xlabel("η = σ / Δ"); ax.set_ylim(-2,103); ax.grid(alpha=.18)
            axes[0].set_ylabel("Completely correct lists [%]")
            axes[1].legend(fontsize=6.4, frameon=False, loc="lower left")
            title = "Reference model at the largest tested list size. B: Bitonic, R: rank sorting; 1,000 lists per point. Source: results/reference/accuracy.csv."
        elif key == "cpu_baseline":
            rows = read_rows("results/cpu_baseline_20261007/summary.csv")
            fig, ax = plt.subplots(figsize=(7.2, 3.0), layout="constrained")
            for dtype, color in [("int64", "#C77629"), ("uint8", "#167D8D")]:
                for batch, line in [(1, "--"), (1000,"-")]:
                    rr = sorted([r for r in rows if int(r["key_bits"])==8 and r["family"]=="distinct" and r["storage_dtype"]==dtype and int(r["batch_size"])==batch],key=lambda r:int(r["n"]))
                    ax.plot([int(r["n"]) for r in rr], [float(r["amortized_s_per_array"])*1e6 for r in rr], line, marker="o", markersize=3, color=color, label=f"{dtype}, batch {batch}")
            ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_xticks([2,4,8,16,32,64,128,256], [2,4,8,16,32,64,128,256])
            ax.set_xlabel("List length N"); ax.set_ylabel("Amortized time [µs / list]"); ax.grid(alpha=.18); ax.legend(fontsize=7, frameon=False)
            title = "CPU baseline for 8-bit inputs with distinct keys. Amortized batch times, not individual request latencies. Source: results/cpu_baseline_20261007/summary.csv."
        else:
            raise ValueError(f"Unknown figure {key}")
        buffer = io.BytesIO(); fig.savefig(buffer, format="png", dpi=220); plt.close(fig)
        count["figure"] += 1
        return [KeepTogether([Spacer(1, 8), image_from_buffer(buffer), para(f"Figure {count['figure']}. {title}", "note")])]

    def diagram(key):
        """Use compact explanatory tables to show paths without implying chip topology."""
        if key == "signal_path":
            spec = dict(title="Generic hybrid signal path", rows=[
                ["Step", "Operation", "System quantity to assess"],
                ["1. Electronic input", "Read, scale, and pack keys", "Memory and host time"],
                ["2. Electro-optic encoding", "Map values to phase / amplitude", "Resolution, modulation, and energy"],
                ["3. Photonic core", "Linear transformation / confirmed nonlinearity", "Transfer characteristic, loss, and disturbance"],
                ["4. Readout", "Detection, conversion, and transfer", "Noise, grid, and interface"],
                ["5. Electronic output", "Decide, exchange / accumulate, validate", "Complete sorting quality and time"],
            ], widths=[1.15, 1.8, 1.5], note="Our schematic, not a Q.ANT layout. Internal boundaries may differ in a confirmed cascade.")
        elif key == "mappings":
            spec = dict(title="The same comparison function in two complete execution paths", rows=[
                ["Phase", "Bitonic", "Rank sorting"],
                ["Prepare pairs", "N/2 pairs in the current stage", "All N² matrix entries, including the diagonal"],
                ["Difference and decision", "Parallel within a stage", "Separate decision for each directed cell"],
                ["Electronic postprocessing", "Exchange original records", "Subtract lower-triangular bias, threshold, sum columns"],
                ["Next step", "Next dependent stage, up to K", "One output from valid ranks"],
            ], widths=[1.2, 1.75, 1.75], note="The differences concern dependencies, resources, and data movement; both mappings use the same stable-output contract.")
        else:
            raise ValueError(f"Unknown diagram {key}")
        return render_table(spec)

    class ReportDocument(BaseDocTemplate):
        """Track headings for bookmarks, the table of contents and running headers."""
        def __init__(self, filename):
            """Create one printable A4 text frame with consistent page furniture."""
            super().__init__(str(filename), pagesize=(PAGE_W,PAGE_H), leftMargin=LEFT, rightMargin=RIGHT, topMargin=TOP, bottomMargin=BOTTOM, title="Hybrid photonic sorting - complete master's thesis documentation", author="Bharadwaj Srikumar", subject="Literature, models, code, and evaluation; research status as of 24 October 2026")
            self.chapter = "Complete master's thesis documentation"
            frame = Frame(LEFT,BOTTOM,CONTENT_W,PAGE_H-TOP-BOTTOM,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
            self.addPageTemplates(PageTemplate(id="report", frames=frame, onPage=self.decorate))

        def beforeDocument(self):
            """Reset per-pass headings so multiBuild produces stable page furniture."""
            self.chapter = "Complete master's thesis documentation"

        def decorate(self, canvas, doc):
            """Draw unobtrusive headers and page numbers outside the content frame."""
            canvas.saveState()
            if doc.page > 1:
                canvas.setStrokeColor(colors.HexColor("#CDDCE1")); canvas.setLineWidth(.5)
                canvas.line(LEFT,PAGE_H-40,PAGE_W-RIGHT,PAGE_H-40)
                canvas.setFont("Report",7); canvas.setFillColor(colors.HexColor(MUTED))
                canvas.drawString(LEFT,PAGE_H-31,"HYBRID PHOTONIC SORTING")
                canvas.drawRightString(PAGE_W-RIGHT,PAGE_H-31,"Research status · 24 Oct 2026")
                canvas.drawString(LEFT,30,"Bharadwaj Srikumar · Master's thesis")
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
    story = [Spacer(1,72), para("MASTER'S THESIS · RESEARCH AND IMPLEMENTATION STATUS", "note"), Spacer(1,16), Paragraph("Hybrid photonic<br/>sorting",title_style), Paragraph("Complete master's thesis documentation",sub_style), para("Literature review, mathematical models, implementation, and evaluation"), Spacer(1,30), para("**Bharadwaj Srikumar**"), para("M.Sc. Computer Science · Bochum University of Applied Sciences<br/>".replace("<br/>", "")), para("Supervisor: Prof. Dr. Henrik Blunck"), para("Research status: 24 October 2026"), Spacer(1,25), para("**Working title**"), para("Mapping Hybrid Optoelectronic Sorting Architectures onto Modern Photonic Accelerators: A Hardware-Aware Evaluation and Simulation"), Spacer(1,20), para("This document describes the current state of the thesis. It connects literature, mathematical derivations, executable code, and saved results. Physical hardware validation, photonic runtime advantages, and energy efficiency remain unresolved.","note"), PageBreak(), para("Contents","h1")]
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
                    block += [para("**Source basis:** " + ref["source"] + ". **Role:** " + ref["role"], "note"), Spacer(1,6)]
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
            table_title = {"Stage": "Bitonic example for [10,3,9,1]", "Pair": "Stable rank construction for [10,3,9,1]", "Function": "Verified SDK functions and their limits"}.get(rows[0][0], "Worked example")
            story += render_table(dict(title=table_title, rows=rows, note="Our illustration based on the derivation or sources cited in this section."))
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
