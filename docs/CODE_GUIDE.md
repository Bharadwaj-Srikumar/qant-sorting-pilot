# Reading the thesis code

The main implementation has six Python modules. Start with one four-key example,
then follow the same operations inside the experiment runner. Supporting SDK and
hardware studies are in `studies/` and can be read later.

## 1. Follow one complete sort

Run this from the repository root after installing `requirements.txt`:

```python
from qant_sorting.comparison import validate_keys, Precision, NoisyDifference
from qant_sorting.sorters import bitonic_sort
from qant_sorting.evaluation import reference_flags

keys = validate_keys([[3, 1, 3, 0]], key_bits=4)
precision = Precision(4, 4, 4)
difference = NoisyDifference(precision, eta=0)
result = bitonic_sort(keys, difference)
flags = reference_flags(keys, result)

print(result[0])  # [[0, 1, 3, 3]]: sorted keys
print(result[1])  # [[3, 1, 0, 2]]: original record IDs
print(flags)      # [[True, True, True]]: valid, correct, stable
```

One row is one independent sort. The comparison object returns measured scores;
the sorter moves original keys and IDs according to those scores. The evaluation
code checks the completed output against an independent stable digital reference.

## 2. Read the main model and algorithms

1. **`qant_sorting/comparison.py`**: read `validate_keys`, `Precision`, then
   `NoisyDifference.__call__`. For matched b-bit settings, delta = 2**(-b).
   Subtract normalized inputs, add Gaussian noise with sigma = eta * delta,
   round to the nearest-even code and clip to [-1/2, 1/2-delta].
2. **`qant_sorting/sorters.py`**: read `bitonic_sort` and its layer generator,
   then `rank_sort` and `place_ranks`. Both receive the same kind of comparison
   callable. Bitonic evaluates dependent layers; the rank sorter evaluates N² directed
   cells, including the diagonal.
3. **`qant_sorting/evaluation.py`**: start with `reference_flags`. Validity,
   sortedness and stability are separate questions. Read `prepare_keys` and
   `score_saved_order` when studying inversions, Kendall metrics and Recall@k.
4. **`qant_sorting/run.py`**: parameters are near the top. `evaluate_case` runs
   batches of one setting; `run` loops over datasets, noise levels and sorters,
   evaluates outputs and saves the results. `validation.json` records the current
   run's comparison-count checks and noiseless validity, correctness and stability
   checks. File helpers stay in this module, without a separate utility package.

For the rank matrix orientation and worked example, use [RANK_SORTER.md](RANK_SORTER.md).
Cell (i,j) measures the normalized difference delta * (keys[j]-keys[i]). The host subtracts
one normalized key step below the diagonal, thresholds at >=0, sums columns and
subtracts one to obtain zero-based destinations. Collisions and invalid ranks
produce -1 markers; no hidden digital repair is applied.

## 3. Read the extended noise controls

5. **`qant_sorting/common_noise.py`**: read `NoiseConfig`, `evaluate_difference`,
   then `CommonNoiseComparison`. The signal passes through upstream noise/offset,
   optional rounding, clipping, direct or normalized-sine transfer, readout
   noise/offset, and output rounding. This model clips to [-1,1], so it is a
   separate study from the main reference channel.
6. **`qant_sorting/controls.py`**: `SETTINGS` defines the cases.
   `analytic_probabilities` gives theoretical sign/zero probabilities where
   supported; `run_pair_controls` checks sampled frequencies. `run_sort_controls`
   applies selected settings to complete sorts. `run` coordinates these two
   stages and saves their results. The analytical probabilities validate the
   model; they do not choose swaps or ranks.

## 4. Run only the question you are studying

```bash
python -m qant_sorting.run       # full main experiment
python -m qant_sorting.controls  # separate common-channel sensitivity controls
python -m studies.check_rank_sorter   # independent equation-level checks
python -m studies.ranking_quality  # score recorded simulation outputs
```

The ranking-quality command reads recorded simulations in `results/reference/`.

Each module supports `--help`. The optional commands and SDK setup are listed in
the [README](../README.md). The direct module commands replace the old command
dispatcher and `qant_sorting/experiments/` layout.

## Assumptions to remember

- Input arrays have shape `(trials, N)`; pair arrays have shape `(trials, pairs)`.
- Original IDs travel with records; a measured zero invokes the stated tie rule.
- Absolute trial IDs preserve random streams when a batch is split.
- Conditional ordering metrics require valid permutations. Report that denominator.
- Top-k means the largest k keys; stable-ID and tie-neutral recall are distinct.
- The shared Float64 noise model, official BF16 CPU SDK and physical hardware
  are separate sources of evidence. Synthetic noise levels are assumptions.
- Stored metadata describe the code at the time of a run. The consolidation does
  not rewrite historical hashes, measurements or results.

The report is stored as a PDF in `reports/`; report-generation code is outside
this repository. Keep code comments and research documentation in English.
