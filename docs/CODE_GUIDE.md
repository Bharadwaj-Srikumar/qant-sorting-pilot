# Reading the thesis code

Start with one workload at a time:

1. `input_validation.py`: valid integer keys, shapes and unsigned-key ranges.
2. `comparison.py`: normalization, Gaussian noise, nearest-even rounding and clipping.
3. `sorting_schedules.py`: read `rank_sort` with the [Louri worked example](LOURI_REFERENCE.md),
   then `place_ranks` immediately below it to follow validation and record placement.
   Read Bitonic's layers and record exchanges in the same file.
4. `metrics.py`: separate validity, sorted keys and stable record order.
5. `ranking_quality.py`: inversions, Kendall-τ-b and Recall@k on valid outputs.
6. `sdk_mapping.py`: pack every requested pair into the official linear API.

The inspectable matrices in `louri_reference.py` are a reference for the same
full-matrix algorithm, not a competing rank adaptation. In particular, `rank_sort`
submits **N² entries**, keeps both directions separate, and does not restore noisy
diagonals. `bias_step` is required explicitly and must match the difference units.

Both `rank_sort` and the equation-level reference use `place_ranks` from
`sorting_schedules.py`. The operational sorter therefore has no dependency on
`louri_reference.py`. The reference's `quantize_difference` stays alongside its
matrix equations: it selects no quantization or the matched quantizer. In the
operational sorter, the supplied `difference` callable owns quantization;
`rank_sort` does not apply a second quantizer.

## Commands

Run `python -m qant_sorting COMMAND --help` from the repository root.
Implementations are under `qant_sorting/experiments/` except `report`.

| Command | Purpose |
|---|---|
| `noise` / `verify` | Reproduce / verify the complete current Bitonic–Louri reference |
| `louri` | Verify source matrices, noiseless ranks and analytic threshold controls |
| `quality` | Independently score the complete saved reference outputs |
| `common-noise` | Compare declared signal stages and quantization assumptions |
| `sdk` | Official CPU integration of both complete sorters |
| `resources` | Count N² rank cells, calls and logical BF16 buffers |
| `cpu` | Measure a stable digital CPU baseline |
| `periodic-pairs` / `affine` | Separate nonlinear comparison feasibility studies |
| `nonlinearity` | CPU ReLU/min-max identities and source boundaries |
| `curve` | Acquire repeated API samples with explicit backend selection |
| `install-sdk` | Install the checksum-verified vendor CPU wheel |
| `report` | Build the sole current PDF from hash-checked evidence |

## Contracts

- Keys have shape `(trials,N)`; matrix pair inputs have shape `(trials,N*N)`.
- Flags are `[valid,correct,stable]`; invalid rank records have `-1` indices/values.
- No digital re-sort, rank clipping or silent fallback repairs invalid outputs.
- Conditional tau/recall require valid permutations; report the denominator.
- Recall means the largest k keys. Stable-ID and tie-neutral variants are distinct.
- Absolute trial IDs determine RNG streams, regardless of memory batching.
- `common_noise_model.py` is a Float64 sensitivity model. `sdk_mapping.py` executes
  official BF16 CPU arithmetic. Neither is measured physical analog precision.
- A periodic score is not in difference units and cannot be passed unchanged to
  the full-matrix rank implementation. Current nonlinear controls are pair-only.

## Equations and saved evidence

Use fenced `math` blocks for display equations in guides, with blank lines around
them. Use `\mathrm`, not GitHub-blocked `\operatorname`. The PDF source uses its
supported single-line dollar-delimited math and `\lbrace` / `\rbrace` for visible
braces. Check rendered output when changing formulas.

`paths.py` pins the corpus. `io.py` hashes files and writes CSV. Per-run metadata
identify code as it existed during execution; subsequent documentation edits do
not retroactively rewrite those snapshots. The current report checks all evidence
against `report_assets/evidence.json`.
