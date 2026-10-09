# Reading the sorting research code

The Python files now start with a reading guide and explain each function,
method and class at its definition. Comments describe array shapes, units,
returned values, state changes, assumptions and failure behavior. Existing
docstrings remain intact. Comments are in English to match the code and thesis.

## Start with one comparison and one array

1. Read [input_validation.py](../input_validation.py): accepted keys are copied
   to signed integer arrays before any normalization.
2. Read [comparison.py](../comparison.py): a pair becomes a noisy, rounded score.
   This module is the established matched-step reference, not the old `model.py`.
3. Read [sorting_schedules.py](../sorting_schedules.py): only the score's sign
   and equality status guide the exchange or rank decision. Original records
   remain electronic and travel with their original indices.
4. Read [metrics.py](../metrics.py): record validity, complete key ordering and
   stability are checked independently after sorting.
5. Read [run_noise_sweep.py](../run_noise_sweep.py): the runner supplies saved
   inputs and per-trial seeds, batches work and saves auditable outputs.

For example, a pair `[10,9]` at 8 bits has normalized difference `1/256`.
The comparator returns a measured score; the sorter then routes the original
integers. It does not reconstruct key values from a clipped analog magnitude.
If the measured score is zero, original indices decide the order. A false zero
can therefore produce a wrong order even when no score reverses its sign.

## Choose the correct model before interpreting a result

| Code path | Purpose | Numerical boundary |
|---|---|---|
| `model.py`, `sorting.py`, `evaluate.py`, `validate.py` | Historical initial experiment and source examples | Output step `2/2**output_bits`; includes fixed-shuffle bypass stages |
| `comparison.py`, `sorting_schedules.py`, `run_noise_sweep.py` | Matched-step reference and exact reproduction | Input/output steps `1/2**bits`; six synthetic noise levels |
| `sdk_mapping.py`, `run_sdk_control.py` | Official CPU linear API integration | BF16 API, no added reference-sweep quantizer/noise |
| `periodic_comparison.py`, `run_periodic_evaluation.py` | Historical periodic CPU comparison | BF16 phase/output; upstream and output noise have different boundaries/units |
| `check_affine_periodic.py` | Affine phase feasibility, exhaustive pairs and bounded full sorts | CPU-only BF16 products; known 8-bit false ties retained as evidence |
| `common_noise_model.py`, `run_common_noise_controls.py` | Shared signal/noise sensitivity controls | Float64 identity/normalized ideal sine, explicit stage noise and quantizers |

These paths coexist to preserve evidence. They must not be swapped without
changing the declared experiment. In particular, a successful old quantizer
test can deliberately predict adjacent-key ties that the newer model avoids
without noise. BF16 is an interface format, not a measured analog ENOB.

## Follow the evaluation question

| Question | Read these files |
|---|---|
| How is quality measured beyond complete-array correctness? | `ranking_quality.py`, `evaluate_ranking_quality.py` |
| How is a damaged archive inspected without inventing outputs? | `saved_output_reader.py` |
| How do we check exact reference reproduction? | `verify_results.py` |
| What does the digital CPU timing include? | `run_cpu_baseline.py` |
| Can an affine MVM form the phase without changing precision behavior? | `check_affine_periodic.py`, `docs/PERIODIC_FEASIBILITY.md` |
| How are the periodic reference and margins obtained? | `check_periodic_pairs.py` |
| Why does min/max reconstruction need an unclipped magnitude? | `check_sdk_nonlinearity.py` |
| What do logical call/transfer counts mean? | `hardware_conditions.py`, `summarize_periodic_results.py` |
| How would repeated actual API outputs be collected? | `measure_periodic_curve.py` |
| How is the optional pinned CPU SDK installed? | `install_sdk.py` |
| How is the current complete thesis report generated? | `build_reports.py`, `report_assets/thesis_report.md`, `report_assets/references.json` |
| How were the historical PDF/HTML reports generated? | `tools/build_legacy_reports.py`, `report_assets/report_template.html` |
| Where are independent examples and edge cases? | The modules in `tests/` |

The [current complete German report](../reports/Masterarbeit_Hybride_Photonische_Sortierung.pdf)
is the only file in `reports/`. Its builder reads authored Markdown and saved
evidence, verifies evidence hashes, lays out tables and equations, and writes
the PDF only after a successful build. Imports have no file-writing side effects.
Use `requirements-report.txt` in a separate environment.

The earlier generated HTML/PDF reports and standalone figures have been removed
from `reports/`; Git history retains them. The old editable HTML template remains
with its historical claims. Running the explicitly named legacy builder writes
to `tmp/legacy_reports/` and cannot recreate obsolete files in `reports/`.

## Important contracts

- **Shapes:** original keys are usually `(trials,N)`; comparison arrays are
  `(trials,pairs)`. The SDK flattens pairs into a matrix and restores the shape.
- **Record identity:** index `i` always refers to input record `i`. Schedule wire
  labels are different from record indices. Keeping them separate makes stable
  equal-key handling possible.
- **Invalid ranking:** colliding ranks produce `-1` output markers. They are not
  digitally re-sorted. Kendall/conditional recall are undefined for such outputs.
- **Flag order:** current flags are `[valid,correct,stable]`. The historical
  `evaluate.py` archive uses `[correct,stable,valid]`; inspect source provenance.
- **Noise:** preserve absolute trial IDs when splitting batches. Paired random
  streams across conditions are controls, not independent repeated evidence.
- **Top-k:** select the largest k keys, the suffix of an ascending output.
  Stable-ID and tie-neutral recall answer different questions at tied boundaries.
- **Complexity:** C=(T,S,H,D) remains the thesis framework. T counts scalar
  real-RAM-like full-sort steps; measured seconds are separate evaluation data.
- **Hardware:** CPU execution, assumed signal limits and logical API buffers do
  not establish physical tcos, optical depth, measured bus traffic or a speedup.

## Running and preserving evidence

Use the requirements file belonging to the selected experiment. The SDK is
optional for NumPy/SciPy controls. A quick test run from the repository root is:

```bash
python -m unittest discover -s tests -v
```

The optional SDK tests explicitly skip when the package is absent. A skip is
not a pass on the SDK. Script comments describe required input files and output
locations. Some historical scripts overwrite their target filenames; use fresh
output paths when reproducing an experiment. Other runners require an empty
directory or protect their reference path explicitly.

Importing `tools/build_legacy_reports.py` loads historical evidence and constructs
dated report descriptions. The new `build_reports.py` is import-safe.
Importing `summarize_periodic_results.py` also writes summary files. Read their
module guides before importing them as if they were passive helper libraries.

The earlier comments-only update preserved Python syntax trees and executable tokens,
including original docstrings, for all 32 Python files. Both HTML files preserve
their noncomment content and pass JavaScript syntax checks. All 148 Python
function/method/class definitions have a dedicated explanation. The available
unit run passed 32 tests and explicitly skipped the two optional SDK tests.
These counts describe that dated update, not a new measurement of the report
renderer. The report consolidation has its own validation record in
`validation/report_consolidation_20261007.json`.

Adding comments changes source-file hashes. Existing result metadata correctly
continues to identify the source snapshot that originally generated the data;
those historical hashes must not be rewritten to make them match new comments.
