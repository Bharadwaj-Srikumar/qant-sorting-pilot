# Hybrid photonic sorting - master's thesis

This project compares **Bitonic sorting** with a **full-matrix rank sorter**.
It studies how assumed comparison noise and quantization affect sorting quality.
The algorithms move original integer keys and record IDs; only their comparison
scores are disturbed.

The rank formulation follows the source paper cited in the
[rank-sorter reference and validation guide](docs/RANK_SORTER.md).

## Run the main evaluation

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m qant_sorting.run
```

This loads the fixed inputs from `data/inputs.npz`, runs both sorters at six noise
levels, and saves results in `results/reproduced/`. The sweep evaluates 288
configurations and 288,000 sorting trials. An existing output
directory is never overwritten. Use `--output-dir` to choose a fresh destination;
`--batch-size` changes memory use without changing a trial's random stream.

The main outputs are `accuracy.csv`, `trial_outcomes.npz`, `failures.json`,
`validation.json` and `metadata.json`. The NPZ contains original record IDs and
valid/correct/stable flags, so outputs can be checked independently.
`validation.json` records the current run's comparison-count checks and confirms
that noiseless outputs are valid, correctly sorted and stable.

## Six files to read

| File | Purpose |
|---|---|
| [comparison.py](qant_sorting/comparison.py) | Check inputs; normalize key pairs; add the main Gaussian noise; round and clip |
| [common_noise.py](qant_sorting/common_noise.py) | A separate model for upstream/readout noise, transfer shape and offsets |
| [sorters.py](qant_sorting/sorters.py) | Bitonic layers, full N² rank comparisons and record placement |
| [evaluation.py](qant_sorting/evaluation.py) | Validity, correctness, stability, uncertainty and partial ordering metrics |
| [run.py](qant_sorting/run.py) | Experiment settings, input loading, the main sweep and result files |
| [controls.py](qant_sorting/controls.py) | Pair-level and complete-sort checks of the common-noise model |

Follow [the short reading guide](docs/CODE_GUIDE.md) for a small worked example.
The main path is: **inputs → comparison model → sorting → evaluation → saved results**.
The reference and common models have different clipping contracts; both remain
explicitly named rather than silently sharing one changed model.

For the common-noise controls:

```bash
python -m qant_sorting.controls
```

This separate study writes to `results/common_noise_reproduced/`. Its defaults
check 28 million pair decisions and 10,800 complete sorts. It uses NumPy/SciPy,
not the Q.ANT SDK. Use `--help` on either module to see its few options.

## Supporting studies

The core evaluation works without these modules. Run a study when its question
is relevant to the thesis; the studies do not run automatically.

| Command | Question |
|---|---|
| `python -m studies.check_rank_sorter` | Does the implementation match the source equations and threshold controls? |
| `python -m studies.ranking_quality` | How good are the saved orders beyond complete-sort accuracy? |
| `python -m studies.check_sdk` | Do the mappings work through the official CPU SDK? |
| `python -m studies.check_periodic` | What does the periodic CPU operation do for every key pair? |
| `python -m studies.check_affine` | Does the affine phase candidate retain adjacent-key distinctions? |
| `python -m studies.check_nonlinearity` | Which nonlinear identities and SDK boundaries hold? |
| `python -m studies.measure_curve --help` | How can repeated API samples be collected with an explicit backend? |
| `python -m studies.resource_counts` | How many operations, submissions and logical bytes are required? |
| `python -m studies.cpu_baseline` | How long does stable sorting take on the chosen digital CPU? |

The ranking-quality study reads the recorded simulation outputs in
`results/reference/`, including noisy outcomes. It computes further quality
metrics without running new sorts.

SDK studies need the optional official CPU toolkit:

```bash
python -m pip install -r requirements/sdk.txt
python -m tools.install_sdk --no-deps
python -m studies.check_sdk
```

The installer checks the bundled archive before installing its platform wheel.
An SDK CPU result establishes software integration, not physical noise, optical
latency or energy efficiency. Keep benchmark environments and their dates explicit.

## Check the code

```bash
python -m unittest discover -s tests -v
```

Tests cover the equations, quantizer boundaries, invalid inputs, record routing,
random-stream reproducibility and quality metrics. Five SDK tests explicitly skip
when the optional toolkit is unavailable.

## Report and research evidence

- [Read the thesis report (PDF)](reports/Masters_Thesis_Hybrid_Photonic_Sorting.pdf).
  The repository stores the finished PDF only; it has no PDF-generation code,
  report template assets or report-rendering dependencies.
  The PDF retains its original research snapshot; use this README and the reading
  guide for the simplified layout and current commands.
- [Research scope](docs/THESIS_SCOPE.md), [model equations](docs/METHOD.md),
  [noise assumptions](docs/COMMON_NOISE_MODEL.md) and [current results](docs/RESULTS.md).
- `data/` contains the fixed input corpus; `results/` contains recorded evidence.
  New runs use separate directories. Existing results, validation receipts and
  the report retain their original dates and provenance.
- `studies/` holds the supporting investigations; `tools/` contains the SDK installer.
  `vendor/` contains the licensed CPU toolkit and its notices.

The rank sorter evaluates all N² directed cells, including noisy self-comparisons. Its
bias, threshold, column sums and placement are exact host operations. Invalid
rank outputs are retained as failures. Physical noise calibration, a useful
internal optical cascade, GPU comparison, and complete NPU timing/energy remain
open questions.
