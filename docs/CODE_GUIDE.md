# Reading the thesis code

## Start with one four-key example

```python
from qant_sorting.comparison import Precision, NoisyDifference, validate_keys
from qant_sorting.sorters import bitonic_sort, rank_sort
from qant_sorting.evaluation import reference_flags

keys = validate_keys([[3, 1, 3, 0]], key_bits=4)
precision = Precision(4, 4, 4)
for sorter in (bitonic_sort, rank_sort):
    difference = NoisyDifference(precision, eta=0)
    options = {"bias_step": precision.delta_in} if sorter is rank_sort else {}
    result = sorter(keys, difference, **options)
    print(result[0])                 # [[0, 1, 3, 3]]
    print(result[1])                 # [[3, 1, 0, 2]]: original record IDs
    print(reference_flags(keys, result))  # [[True, True, True]]
```

One row is one sorting trial. The sorters move the original keys and IDs using
measured comparison scores. The digital reference is used afterwards to score
the output; it never supplies sorting decisions.

## Read in this order

| File | Functions to follow | Question answered |
|---|---|---|
| `qant_sorting/comparison.py` | `validate_keys`, `Precision`, `NoisyDifference.__call__` | How does a pair of keys become a noisy comparison? |
| `qant_sorting/sorters.py` | `compact_bitonic_layers`, `bitonic_sort`, `rank_sort`, `place_ranks` | How do comparison results determine the output order? |
| `qant_sorting/evaluation.py` | `reference_flags`, `wilson_interval`, `prepare_keys`, `score_saved_order` | How are validity, accuracy, stability, tau and Recall@k calculated? |
| `qant_sorting/run.py` | Settings, `evaluate_case`, `run`, `main` | How are the datasets, noise levels and sorters evaluated? |
| `qant_sorting/quality.py` | `statistics`, `run`, `main` | How are detailed metrics generated from saved orders? |
| `qant_sorting/sdk.py` | `SdkDifference`, `backend_identity`, `main` | How is subtraction submitted through the Q.ANT CPU SDK? |
| `qant_sorting/resources.py` | `counts`, `main` | What work and logical data movement does each mapping require? |

The first four files explain the main experiment. The final three produce its
detailed quality analysis, software mapping evidence and resource comparison.

`qant_sorting/install_sdk.py` is a setup helper in the same folder. Run it as
`python -m qant_sorting.install_sdk --no-deps` after installing `requirements.txt`
when you want to use the official CPU SDK. It is not part of the sorting flow.

## Checks in the same files

Each core module ends with a **Self-tests** section containing its mathematical
examples and implementation checks. Read the main functions first, then use the
test names and comments to see which behaviours are checked. Normal experiment
commands do not execute these tests.

Run all checks with `python -m qant_sorting.run --self-test`. To check only one
module, use e.g. `python -m unittest qant_sorting.comparison -v`. The SDK checks
skip when the official toolkit is not installed.

## Keep these conventions in mind

- Keys use 4 or 8 bits. The matched input/output step is delta = 2**(-bits).
- Main noise has standard deviation eta * delta. Output rounding is nearest-even;
  signed clipping limits are [-1/2, 1/2-delta].
- Bitonic uses dependent compare/exchange layers. Rank evaluates N² directed
  cells, including the diagonal, before bias, threshold and column sums.
- Invalid rank placements remain failures with `-1` markers.
- Kendall metrics and conditional recall require valid output. Always report
  validity alongside them. Top-k selects the largest k keys.
- The simulation assumes independent errors. The CPU SDK is a separate software
  integration check. Neither establishes a physical noise distribution.

Use [METHOD.md](METHOD.md) for equations and the rank example,
[RESULTS.md](RESULTS.md) for findings, and [HARDWARE.md](HARDWARE.md) for the
mapping boundary and conditional costs. The [README](../README.md) lists commands.
