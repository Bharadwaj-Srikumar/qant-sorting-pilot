# Hybrid photonic sorting — thesis evaluation

This repository compares **Bitonic sorting** and **full-matrix rank sorting**
under a declared Gaussian comparison-noise and quantization model. It contains
the implementation and evidence needed to review that comparison.

The scope follows the thesis questions: establish reliable algorithm mappings,
measure numerical limits, distinguish optical arithmetic from electronic control,
and express unknown hardware costs parametrically. Q.ANT is the reference
platform. The official CPU SDK establishes software integration; there are no
physical NPU measurements or claims of a hardware speed or energy advantage.

Read [Documentation.md](Documentation.md) for the code guide, mathematical model,
hardware mapping and recorded results.

## Run the photonic sorting evaluation

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
utility. See the [method and noise model](Documentation.md#2-method-and-noise-model)
for definitions and denominators.

All commands write new files to `results/reproduced/` by default, using the
prefixes `simulation_`, `quality_`, `sdk_` and `resources_`. Each command accepts
`--output-dir` and stops if any file in its output group already exists; other
groups can share the directory. Choose another output directory to repeat a
group. The main command's `--batch-size` changes memory use without changing a
trial's noise stream. To score the committed results in `results/` directly,
run `python -m qant_sorting.quality`.

## Code structure and thematic separation

All executable thesis code is kept together in `qant_sorting/`, but it serves
two different evaluation themes.

### A. Photonic sorting evaluation

This is the main research path: **inputs → noisy comparisons → sorting → quality
metrics → Q.ANT software mapping/resource accounting**.

| Order | File | Purpose |
|---|---|---|
| 1 | [comparison.py](qant_sorting/comparison.py) | Validate keys; normalize differences; add noise; round and clip |
| 2 | [sorters.py](qant_sorting/sorters.py) | Bitonic layers, full rank matrix and record placement |
| 3 | [evaluation.py](qant_sorting/evaluation.py) | Validity, correctness, stability, confidence intervals and ranking metrics |
| 4 | [run.py](qant_sorting/run.py) | Main experiment settings, execution and saved outputs |
| 5 | [quality.py](qant_sorting/quality.py) | Calculate detailed metrics from saved sorting outputs |
| 6 | [sdk.py](qant_sorting/sdk.py) | Map differences to the official Q.ANT CPU SDK and evaluate both sorters |
| 7 | [resources.py](qant_sorting/resources.py) | Count operations, submissions and logical data movement |

The setup helper [install_sdk.py](qant_sorting/install_sdk.py) installs the
bundled Q.ANT SDK. It supports the software-integration check and is not part of
the sorting algorithm itself.

### B. Digital CPU reference baseline

[cpu_baseline.py](qant_sorting/cpu_baseline.py) is a separate measurement path
inside the same package. It does **not** use the photonic noise model, the Q.ANT
SDK, or the hybrid mappings. Its purpose is only to provide a reproducible
digital reference for complete stable sorting.

The timed application call is:

```python
indices = np.argsort(data, axis=-1, kind="stable")
values = np.take_along_axis(data, indices, axis=-1)
```

It therefore returns the same complete record contract used by the thesis:
sorted values plus original record indices. Allocation and gathering are inside
the timing boundary; file loading, dtype conversion, validation and result-file
writing are outside it.

The benchmark uses the same 24 thesis datasets and checks their SHA-256 content
before measuring. Its default protocol is:

- storage dtypes: `uint8` and `int64`;
- batch sizes: 1, 10, 100 and 1,000 lists per call;
- 9 timing repetitions per configuration;
- 2 warm-up passes;
- 15 ms target timing interval per repeated sample;
- randomized case order with seed `20261107`.

Run it from the repository root:

```bash
python -m qant_sorting.cpu_baseline
```

By default it reads `data/inputs.npz` and writes a new run to
`results/cpu_baseline_reproduced/`. The output directory must be empty.

The retained fresh run is
[`results/cpu_baseline_20261107/`](results/cpu_baseline_20261107/). It covers
**192 configurations** and generated **1,728 timing samples**. All outputs passed
record-preservation, sortedness and stability checks.

Environment of that retained run:

- AMD EPYC 9V74 80-Core Processor;
- Python 3.13.5;
- NumPy 2.3.5;
- 5 visible logical CPUs, affinity CPUs 0–4;
- cgroup quota `400000 100000` (four CPU-time units).

For 8-bit distinct keys at (N=256):

| Storage dtype | Lists per call | Median time per call | Amortized time per list | Relative IQR |
|---|---:|---:|---:|---:|
| int64 | 1 | 11.74 µs | 11.74 µs | 2.6% |
| int64 | 1,000 | 7.894 ms | 7.89 µs | 4.6% |
| uint8 | 1 | 5.44 µs | 5.44 µs | 8.6% |
| uint8 | 1,000 | 1.380 ms | 1.38 µs | 2.0% |

These are platform-specific CPU measurements, not a universal CPU lower bound.
They do not imply GPU/NPU performance, energy efficiency, or photonic speedup.
The GPU baseline remains open.

Start with the four-key example in the [code guide](Documentation.md#1-code-guide)
for the photonic evaluation. The CPU baseline is intentionally documented as a
different experimental question even though its code lives in the same package.

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
`sdk_` files to `results/reproduced/`. The differences are calculated by `linear_fprop`;
decisions, bias, sums and record routing remain on the host. The SDK run has no
added Gaussian noise or extra fixed-point quantizer. See
[hardware mapping and resource costs](Documentation.md#3-hardware-mapping-and-resource-costs)
for the source-audited nonlinearity boundary, resource formulas and unresolved
physical parameters.

## Evidence included for review

All retained result files are directly in `results/`; their prefixes identify
the evaluation that produced them.

| Location or filename prefix | Contents |
|---|---|
| `data/` | Fixed input arrays |
| `results/simulation_*` | Main accuracy, complete output orders, failures and run metadata |
| `results/quality_*` | Kendall metrics, inversion distances, Recall@k and their denominators |
| `results/sdk_*` | Official CPU SDK integration results |
| `results/resources_*` | Logical operation, submission and transfer counts |
| `qant_sorting/cpu_baseline.py` | Digital CPU reference baseline code; same package, separate evaluation theme |
| `results/cpu_baseline_20261107/` | Fresh 7 Nov 2026 CPU baseline summaries, validation and provenance |
| `vendor/` | Pinned SDK distribution and required license notices |

Each command has one `*_metadata.json` file for its run details, including
checks and failure examples where applicable.

The [results section](Documentation.md#4-results) summarizes the retained findings, including the [fresh CPU baseline](Documentation.md#43-fresh-cpu-baseline-7-november-2026).
Recorded metadata values and hashes are preserved; historical filenames and
source paths describe the original runs. The cleanup does not relabel them as
new measurements. Earlier exploratory code and drafts remain in Git history.

The [2026-11-04 reproduction check](Documentation.md#44-evidence-and-reproduction)
confirmed that all seven numerical result tables and both output archives
matched the retained files exactly after the optimizations.

Each of the seven core files contains `unittest` classes near the end.
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
