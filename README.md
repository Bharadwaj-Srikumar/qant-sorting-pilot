# Hybrid photonic sorting — master's thesis

The thesis compares **Bitonic** with **Louri's full N×N rank matrix** on a
hybrid linear-computing path. Every directed rank comparison and self-comparison
is evaluated separately. The lower-triangular bias, threshold, column sums and
record placement are electronic. CPU verification is not evidence of a photonic
speed or energy advantage.

## Start here

- [Thesis scope and decisions](docs/THESIS_SCOPE.md)
- [Current complete thesis report, English](reports/Masters_Thesis_Hybrid_Photonic_Sorting.pdf)
- [Read the code one step at a time](docs/CODE_GUIDE.md)
- [Comparison model](docs/METHOD.md) and [Louri's equations](docs/LOURI_REFERENCE.md)
- [Current results](docs/RESULTS.md), [ranking quality](docs/RANKING_QUALITY.md),
  [noise assumptions](docs/COMMON_NOISE_MODEL.md), and [resource accounting](docs/HARDWARE.md)

## Run from the repository root

Use Python 3.12 and a virtual environment:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements/analysis.txt
python -m unittest discover -s tests -v
python -m qant_sorting noise
python -m qant_sorting louri
python -m qant_sorting quality
```

`noise` reproduces all **288 current configurations / 288,000 sorts** and compares
outputs with `results/reference/`. The source-equation check covers **155,328
noiseless arrays**. Absolute trial IDs preserve the experiment across batch sizes.
New runs write to separate reproduction directories; existing evidence is protected.

For the official CPU SDK:

```bash
python -m pip install -r requirements/sdk.txt
python -m qant_sorting install-sdk --no-deps
python -m qant_sorting sdk
python -m qant_sorting affine
```

The full-matrix/Bitonic integration checks **48,000 complete sorts**. The affine
periodic candidate is a separate pair feasibility study: it has 40 false 8-bit
ties and is not the thesis rank implementation. SDK tests skip explicitly if the
optional dependency is absent; no hardware backend is silently substituted.

To rebuild the report:

```bash
python -m pip install -r requirements/report.txt
python -m qant_sorting report
```

## Repository contents

| Directory | Purpose |
|---|---|
| `qant_sorting/` | Current algorithms, comparison models, quality metrics and report builder |
| `qant_sorting/experiments/` | Reproducible commands; run `python -m qant_sorting --help` |
| `data/` | One immutable input corpus |
| `results/` | Current evidence, including output indices required for independent rescoring |
| `docs/`, `report_assets/` | Explanations, literature, source audits and report text |
| `reports/` | One current complete PDF |
| `tests/`, `validation/` | Mathematical/API tests and current validation evidence |
| `requirements/`, `vendor/` | Environments and licensed, pinned official CPU SDK |

Superseded prototypes, reduced-rank outputs and earlier reports are absent from
the current tree. Git history preserves version comparisons. Stored NPZ outputs
and the SDK ZIP are necessary reproducibility data/dependencies, not old reports.

GPU timing, calibrated physical noise, a confirmed useful internal cascade,
complete NPU timing and energy measurements remain open.
