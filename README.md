# Hybrid photonic sorting — thesis evaluation

This repository compares **Bitonic sorting** and **full-matrix rank sorting**
under a declared Gaussian comparison-noise and quantization model. It contains
the implementation and evidence needed to review that comparison.

The scope follows the thesis questions: establish reliable algorithm mappings,
measure numerical limits, distinguish optical arithmetic from electronic control,
and express unknown hardware costs parametrically. Q.ANT is the reference
platform. The official CPU SDK establishes software integration; there are no
physical NPU measurements or claims of a hardware speed or energy advantage.

## Run the evaluation

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m qant_sorting.run
python -m qant_sorting.quality --results-dir results/reproduced
python -m qant_sorting.resources
```

The main experiment uses the fixed corpus in `data/inputs.npz`: 24 datasets,
1,000 arrays each, six noise levels and two sorters. It produces **288 cases and
288,000 complete sorting runs**. Both algorithms use the same comparison model;
the rank sorter evaluates all N² directed cells, including noisy self-comparisons.
No invalid output is repaired by a digital sorter.

The quality command scores the saved record orders. It retains **validity,
correctness, stability, Kendall's tau, inversions and Recall@k / Top-k**, including
both stable-record and tie-neutral recall. Conditional quality is undefined for
invalid outputs; a separately named recall measure assigns those failures zero
utility. The definitions and denominators are in [METHOD.md](docs/METHOD.md).

New results go to `results/reproduced/`, `results/ranking_quality_reproduced/`
and `results/resources_reproduced/`. Each command accepts `--output-dir` and
refuses to overwrite a nonempty directory. The main command's `--batch-size`
changes memory use without changing a trial's noise stream. To score the
committed results directly, run `python -m qant_sorting.quality`.

## Code structure and reading order

| Order | File | Purpose |
|---|---|---|
| 1 | [comparison.py](qant_sorting/comparison.py) | Validate keys; normalize differences; add noise; round and clip |
| 2 | [sorters.py](qant_sorting/sorters.py) | Bitonic layers, full rank matrix and record placement |
| 3 | [evaluation.py](qant_sorting/evaluation.py) | Validity, correctness, stability, confidence intervals and ranking metrics |
| 4 | [run.py](qant_sorting/run.py) | Main experiment settings, execution and saved outputs |
| 5 | [quality.py](qant_sorting/quality.py) | Calculate detailed metrics from saved sorting outputs |
| 6 | [sdk.py](qant_sorting/sdk.py) | Map differences to the official Q.ANT CPU SDK and evaluate both sorters |
| 7 | [resources.py](qant_sorting/resources.py) | Count operations, submissions and logical data movement |

The setup helper [install_sdk.py](qant_sorting/install_sdk.py) is in the same
folder. It installs the bundled Q.ANT SDK and is separate from the seven
evaluation modules above.

Start with the four-key example in [CODE_GUIDE.md](docs/CODE_GUIDE.md).
The main flow is **inputs → noisy comparisons → sorting → quality metrics → results**.
There is one retained simulation noise model, in `comparison.py`.

## Q.ANT mapping

The pinned SDK and its licenses are included so that the linear mapping can be
reproduced. The setup above installs all shared Python dependencies from the
single `requirements.txt`. Add the bundled SDK wheel in the same Python 3.12
virtual environment:

```bash
python -m qant_sorting.install_sdk --no-deps
python -m qant_sorting.sdk
```

This checks every 4-/8-bit key pair and both sorters on the saved inputs, writing
to `results/sdk_reproduced/`. The differences are calculated by `linear_fprop`;
decisions, bias, sums and record routing remain on the host. The SDK run has no
added Gaussian noise or extra fixed-point quantizer. See
[HARDWARE.md](docs/HARDWARE.md) for the source-audited nonlinearity boundary,
resource formulas and unresolved physical parameters.

## Evidence included for review

| Folder | Contents |
|---|---|
| `data/` | Fixed input arrays |
| `results/reference/` | Main accuracy, complete output orders, failures and run metadata |
| `results/ranking_quality/` | Kendall metrics, inversion distances, Recall@k and their denominators |
| `results/sdk/` | Official CPU SDK integration results |
| `results/resources/` | Logical operation, submission and transfer counts |
| `vendor/` | Pinned SDK distribution and required license notices |

[RESULTS.md](docs/RESULTS.md) summarizes the retained findings. Saved results
retain their original metadata and hashes; historical source paths describe the
code at the time those runs were produced. The cleanup does not relabel them as
new measurements. Earlier exploratory code and drafts remain in Git history.

Each of the seven core files ends with a clearly marked **Self-tests** section.
These checks run only when requested. Run them all with:

```bash
python -m qant_sorting.run --self-test
```

To check just one module, for example the evaluation metrics:

```bash
python -m unittest qant_sorting.evaluation -v
```

The numerical simulation and quality evaluation use NumPy. The shared requirements
also include the SDK support packages; the official toolkit wheel is installed
separately as shown above. SDK self-tests skip until that toolkit is installed.
No report-generation code is included.
