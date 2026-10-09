# Q.ANT sorting pilot

Reproducible research code for **pipelined-bitonic versus rank sorting** under
the agreed equal-step quantizer and Gaussian noise sweep. The bitonic mapping
is an active-layer adaptation motivated by Stirk and Athale; the rank mapping
is adapted from Louri. Neither is a device-level replica of the historical sorter.

**The numerical sweep is not a measurement of Q.ANT hardware.** An optional,
separate control exercises the official Q.ANT **CPU backend**.

## Current complete thesis report

[**Hybride photonische Sortierung – Gesamtdokumentation der Masterarbeit**](reports/Masterarbeit_Hybride_Photonische_Sortierung.pdf)
is the single current report, in German, dated **9 October 2026**. It connects
the literature and both earlier presentations to the complexity model, five
architectures, mathematical mappings, current code, noise/quality evaluation,
CPU baseline and remaining hardware questions. It documents the current thesis
state, not a completed physical hardware validation.

`reports/` contains only this PDF. Earlier reports, the old presentation copy
and standalone figures remain recoverable through Git history. The editable
narrative, bibliography and source inventory live in `report_assets/`.

To regenerate the report from saved results in a separate report environment:

```bash
python -m pip install -r requirements-report.txt
python build_reports.py
```

The builder verifies the pinned evidence hashes and does not rerun experiments.
See [report provenance](report_assets/report_provenance.json) and
[consolidation validation](validation/report_consolidation_20261007.json).
Historical periodic sort archives are **not included in this Git tree**; their
derived ranking-quality tables are retained, with five explicitly documented
missing output configurations. The report does not claim full raw-data coverage.

## New readers: code guide

Start with the [code reading guide](docs/CODE_GUIDE.md) for the execution paths,
array contracts and distinction between historical and current experiments.
All project-owned Python definitions and HTML/JavaScript behavior have detailed
source comments. The documentation update preserves the executable logic and
existing numerical evidence.

## Feedback sprint: periodic feasibility, 9 October 2026

Moving phase formation into an affine SDK MVM does not establish a host-free
cascade. The tested BF16 implementation produces **40 false ties among all
65,536 ordered 8-bit pairs**, even without noise; all 4-bit pairs pass.
The direct-difference and existing host-phase controls remain correct.
A fixed sample of 3,600 complete CPU sorts documents the consequence in both
mappings. No physical hardware or performance result is claimed.

See [the feasibility analysis and reproduction instructions](docs/PERIODIC_FEASIBILITY.md),
`check_affine_periodic.py`, and `results/affine_periodic_20261009/`.
The separate candidate does not replace the existing comparator. The Q.ANT
inquiry draft is updated but has not been sent.
The [validation record](validation/affine_feasibility_20261009.json) documents
37 passing tests, retained historical evidence and the PDF checks.

## Feedback sprint: common noise model, 7 October 2026

The old upstream/output accuracy contrast uses different decision margins and
quantization rules. It does not establish a physical noise advantage. The new
[common model and controls](docs/COMMON_NOISE_MODEL.md) separate upstream noise,
readout noise, rounding and residual offsets, with explicit source/assumption
labels and locally matched signal units. This is a Float64 sensitivity model,
not a Q.ANT calibration or an SDK hardware execution.

Run `python run_common_noise_controls.py` using `requirements-common-noise.txt`.
Saved pair controls, selected full sorts and quality metrics are in
`results/common_noise_20261007/`. Historical sweeps below remain unchanged.

## Hardware evidence update: 5 October 2026

The official SDK exposes a **native periodic nonlinearity**, but its **ReLU
runs on the host CPU**. The existing experiment uses only the linear difference
API, followed by electronic decisions and routing. No optical min/max kernel
or unregenerated cascade has been demonstrated.

Read [the source audit and mathematical consequences](docs/QANT_NONLINEARITY.md).
The new `check_sdk_nonlinearity.py` independently verifies the exact numerical
min/max identity on the official CPU backend, including every 4/8-bit pair.
It does not alter the noise sweep, routing, saved inputs or reference results.

After installing the optional SDK, run `python check_sdk_nonlinearity.py`.
Results go to `results/nonlinearity_reproduced/checks.json`; the saved result is
`validation/nonlinearity_check.json`. This check has **no extra noise or
sign-only clipping** and is not a photonic or full-sort experiment.

## Start in VS Code

Open this folder, open its terminal, and use Python **3.12**:

```bash
python -m venv .venv
```

Activate the environment:

| Terminal | Command |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows Command Prompt | `.venv\Scripts\activate.bat` |
| Linux/macOS | `source .venv/bin/activate` |

In VS Code, choose **Python: Select Interpreter → .venv**. Then:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_noise_sweep.py
```

The main sweep requires only NumPy. It writes `results/reproduced/`, leaving
`results/reference/` unchanged, and automatically checks **all 288 result rows
and all 576 saved trial arrays** against the previous experiment.

## Read the code in this order

| File | What it explains |
|---|---|
| `comparison.py` | The three precision settings, normalization, Gaussian noise, rounding and saturation |
| `sorting_schedules.py` | Bitonic comparison/exchange layers; rank comparisons, sums and output placement |
| `metrics.py` | Record preservation, full-sort correctness and stability |
| `run_noise_sweep.py` | Saved inputs, reproducible seeds, batching and result files |
| `verify_results.py` | Exact comparison against the previously reported results |
| `sdk_mapping.py`, `run_sdk_control.py` | Optional BF16 difference operation through the official CPU SDK |
| `hardware_conditions.py` | Operation counts, logical data transfers and conditional execution costs |
| `check_sdk_nonlinearity.py` | Separate CPU-only ReLU/min-max identity check |

Start with [the mapping explanation](docs/METHOD.md),
[the results](docs/RESULTS.md), and [the hardware boundary](docs/HARDWARE.md).

## Agreed experiment

| Setting | Value |
|---|---|
| Key/input/output bits | Separate fields; tested as `(4,4,4)` and `(8,8,8)` |
| Integer key ranges | 0–15 and 0–255, inclusive |
| Array sizes | Powers of two, from 2 through 16 or 256 |
| Input families | Distinct keys; uniform sampling with replacement (“duplicates allowed”) |
| Trials | 1,000 saved arrays per width, size and family; 24,000 inputs total |
| Normalization | Fixed declared range: `x / 2**bits` in these matched-width cases |
| Quantization steps | `delta_in = delta_out = 1 / 2**bits` |
| Output | Signed nearest-even rounding, then saturation |
| Noise | Gaussian; `sigma = eta * delta_out` |
| Eta values | 0, 0.05, 0.10, 0.15, 0.20, 0.25 |
| Routing and rank sums | Exact electronic operations on original integer records |
| Measured-zero tie rule | Earlier original record index is treated as smaller |
| Digital repair | None; invalid ranks count as failed sorts |

No new numerical assumptions were introduced in this cleanup. Unequal bit
widths are rejected because they are outside this agreed experiment. The key
validator accepts integral numeric values, including `3.0`, but rejects strings,
booleans, fractions and out-of-range values with their zero-based location.

## Outputs

`results/reference/` contains the original six-level sweep. Its metadata and
source hashes describe the **earlier code snapshot**, not the cleaned code.
`results/sdk_reference/` retains the earlier noiseless controls. New runs write
fresh provenance separately; `validation/current_checks.json` records the
verification performed for this project update.

| Output | Meaning |
|---|---|
| `accuracy.csv` | Counts, accuracy, Wilson intervals and comparison diagnostics |
| `trial_outcomes.npz` | Flags `[valid, correct, stable]` and output record indices |
| `failures.json` | First failed input/output example in each failing condition |
| `metadata.json` | Settings, seeds, input/source hashes and environment |
| `validation.json` | Exact reproduction check |

To repeat verification or change the **batch size only**:

```bash
python verify_results.py results/reproduced
python run_noise_sweep.py --batch-size 32 --output-dir results/reproduced
```

Batch size groups independent trials for memory use. It does not change the
model, trial seeds or results. Runtime is not a hardware timing benchmark.

## Optional Q.ANT CPU integration

The unchanged official 2.3.1 CPU release and its licenses are in `vendor/`.
Installation checks the archive checksum and uses a platform-matching wheel.

```bash
python install_sdk.py
python run_sdk_control.py
```

This executes 48,000 noiseless sorts and compares their output records with the
previous CPU results. BF16 API arithmetic is kept separate from the fixed-point
noise model. The runner rejects a non-CPU backend; it does not silently run on
an NPU or infer physical capabilities from software acceptance.

For source-constrained accounting, with an optional SDK chunking check:

```bash
python hardware_conditions.py
python hardware_conditions.py --verify-sdk
```

## Previous code cleanup (reference results unchanged)

- One documented noise-sweep entry point; no mandatory SDK import.
- Rank accumulation visits each pair once instead of repeatedly scanning all
  pairs. It retains the same decisions and uses quadratic accumulation work.
- Rank validity uses occupancy counts; it neither sorts nor clips the ranks.
- Redundant copies in bitonic exchanges were removed; advanced indexing already
  returns copies.
- Comments explain mathematical steps, physical boundaries, seeds and metrics.
- Saved input arrays, noise streams, quantization and reported results remain
  unchanged. Old Beyette/Desmulliez dispatch is absent from the current mapping.

Only project code, data and evaluation evidence are included. Research-paper
PDFs are not redistributed. The vendor license files apply to the bundled SDK;
this update does not assign a new license to the thesis project.

## Earlier repository snapshot

The root files `model.py`, `sorting.py`, `evaluate.py`, `validate.py` and
`config.json`, plus historical assets and top-level result files, remain for
traceability. The former report builder is now
[`tools/build_legacy_reports.py`](tools/build_legacy_reports.py); it writes to
`tmp/legacy_reports/`, never to the current `reports/` folder.
They use the **superseded two-step output quantizer and three-architecture scope**.
Use `run_noise_sweep.py` and `results/reference/` for the current study.
The [legacy instructions](docs/LEGACY_README_20261002.md) and
`requirements-legacy.txt` document the older environment; install it separately.
The root `MANIFEST.json` describes a historical snapshot. Current report sources
and evidence are identified in `report_assets/report_provenance.json`.

## This delivered revision

See [CHANGELOG.md](CHANGELOG.md) for the exact changes and evidence boundary.
The repository includes current research and explicitly marked historical code.
Historical root-level code is not needed to reproduce the current matched-step
reference or the newer shared-noise and CPU-baseline evaluations.

