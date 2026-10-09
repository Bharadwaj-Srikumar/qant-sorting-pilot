# Reading and running the code

Start with four files; the experiment scripts can wait:

1. [input_validation.py](../qant_sorting/input_validation.py) checks and copies integer keys.
2. [comparison.py](../qant_sorting/comparison.py) defines the matched-step noisy comparison.
3. [sorting_schedules.py](../qant_sorting/sorting_schedules.py) uses its sign in bitonic or rank sorting.
4. [metrics.py](../qant_sorting/metrics.py) checks record preservation, order and stability.

A comparator returns negative, zero or positive scores for equally shaped pair
arrays. Original keys and indices stay electronic. The sorter never reconstructs
keys from analog magnitudes. A measured zero uses the original-index tie rule,
so a false zero can still produce an incorrect sort.

## Choose the model deliberately

| Module | Question and boundary |
|---|---|
| `comparison.py` | Matched input/output steps, six synthetic Gaussian noise levels |
| `common_noise_model.py` | Explicit noise locations, normalized ideal sine and quantizers; Float64 sensitivity model |
| `sdk_mapping.py` | Official BF16 linear CPU integration; logical buffer accounting |
| `periodic_comparison.py` | Historical host-phase CPU mapping; upstream/output scenarios have different scales |
| `experiments/check_affine_periodic.py` | Phase inside the MVM; known 8-bit false ties preserved as a negative result |
| `ranking_quality.py` | Kendall-τ-b, inversions by key distance and Recall@k |
| `saved_output_reader.py` | Complete or explicitly audited incomplete output archives |

All paths in this table are under `qant_sorting/`. These models are separate
because their assumptions differ. They are not interchangeable implementations
of one physical device. BF16 is an interface format, not measured analog ENOB.

## One command entry point

Run `python -m qant_sorting COMMAND --help` from the repository root.
Arguments pass through to the selected runner; no experiment runs on import.
SDK commands require the optional SDK environment. Top-level help needs only Python.

| COMMAND | Implementation in `qant_sorting/experiments/` | Purpose |
|---|---|---|
| `noise` | `run_noise_sweep.py` | Reproduce all matched-step reference results |
| `verify` | `verify_results.py` | Compare saved output with the reference |
| `common-noise` | `run_common_noise_controls.py` | Shared signal/noise controls |
| `quality` | `evaluate_ranking_quality.py` | Analyze saved indices; original archives required |
| `cpu` | `run_cpu_baseline.py` | Digital CPU timing with stable record outputs |
| `resources` | `hardware_conditions.py` | Conditional operation and buffer counts |
| `sdk` | `run_sdk_control.py` | Official linear CPU control |
| `periodic-pairs` | `check_periodic_pairs.py` | Exhaustive existing host-phase comparator |
| `affine` | `check_affine_periodic.py` | Affine CPU feasibility control |
| `nonlinearity` | `check_sdk_nonlinearity.py` | ReLU/min-max CPU identity |
| `periodic` | `run_periodic_evaluation.py` | Historical periodic scenarios |
| `periodic-summary` | `summarize_periodic_results.py` | Historical CSVs required; use `--project-dir` for external evidence |
| `curve` | `measure_periodic_curve.py` | Repeated API samples; explicit backend choice |
| `install-sdk` | `install_sdk.py` | Install the checksum-verified CPU wheel |
| `report` | `../report.py` | Build the sole current PDF from saved evidence |

For example, `python run_noise_sweep.py --batch-size 32` becomes
`python -m qant_sorting noise --batch-size 32`. Python imports now use the package:
`from qant_sorting.sorting_schedules import bitonic_sort`.
The complete old-to-new file map is [source_layout.json](source_layout.json).

## Shared plumbing and reproducibility

`paths.py` defines the repository root and input identity. `io.py` provides
streamed SHA-256, CSV writing and source inventory. `experiments/settings.py`
holds the existing sweep constants. These helpers do not decide scientific assumptions.

New provenance includes package paths and shared helpers. Historical result
metadata remain unchanged and identify the code that originally produced them.
The report checks saved evidence hashes; original source hashes remain in its
historical provenance record. Regenerated outputs use separate destinations.

The existing function explanations retain units, shapes, ties, seeds and
hardware boundaries. Repeated command-entry boilerplate has been removed.
No caching, precision change or altered RNG schedule is introduced by this reorganization.

## Contracts that matter

- Inputs are `(trials,N)`; comparator arrays are usually `(trials,pairs)`.
- Current flags are `[valid,correct,stable]`; the legacy archive has another order.
- Invalid rank outputs retain `-1` markers and count as failures. No digital repair.
- Invalid outputs have undefined conditional ranking metrics; report their count.
- Recall selects the largest k keys. Stable-ID and tie-neutral recall differ at ties.
- Preserve absolute trial IDs when batching. Batch size does not change random streams.
- C=(T,S,H,D) is unchanged; T counts real-RAM-like scalar work, not physical seconds.

The superseded prototypes and their instructions are isolated in [legacy/](../legacy/README.md).
They are unnecessary for current reference, quality, noise, CPU and affine work.
