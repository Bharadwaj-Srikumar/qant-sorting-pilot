# Results retained for the thesis comparison

The canonical algorithms are Bitonic and full N×N rank sorting, including
independent directed cells and self-comparisons. The following are recorded
simulation and CPU integration results. The Gaussian noise and signed
quantization are declared assumptions, detailed in [METHOD.md](METHOD.md).

## 1. Whole-array correctness

Each cell is **Bitonic / Rank** (%), from 1,000 saved inputs per setting.
Source: [`results/reference/accuracy.csv`](../results/reference/accuracy.csv).

| Setting | η=0 | .05 | .10 | .15 | .20 | .25 |
|---|---:|---:|---:|---:|---:|---:|
| 4-bit, N=16, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 97.9 | 95.5 / 82.1 | 84.3 / 49.5 |
| 4-bit, N=16, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 97.7 | 95.1 / 75.5 | 87.9 / 35.2 |
| 8-bit, N=256, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 93.9 / 81.2 | 44.7 / 3.5 | 5.9 / 0.0 |
| 8-bit, N=256, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 95.5 / 72.4 | 54.8 / 1.2 | 10.4 / 0.0 |

The sweep contains **288 configurations and 288,000 sorts**, reusing 24,000
input arrays. At η=0, all 48,000 sorts are valid, correct and stable. Full outputs,
95% Wilson intervals, diagnostics and example failures remain available; the
table above is only a selection. “Duplicates allowed” means sampling with
replacement. Distinct inputs at maximum N cover the complete key domain.

## 2. Validity, stability and useful partial rankings

At **8 bits, N=256 and η=.25**, counts per 1,000 trials are:

| Inputs | Algorithm | Valid | Correct | Stable |
|---|---|---:|---:|---:|
| Distinct | Bitonic | 1,000 | 59 | 59 |
| Distinct | Rank | 0 | 0 | 0 |
| Duplicates allowed | Bitonic | 1,000 | 104 | 5 |
| Duplicates allowed | Rank | 0 | 0 | 0 |

Bitonic preserves records through swaps even when ordering fails. Rank failures
here are invalid rank permutations, retained without repair. Correct key order
and stable record order are different requirements when keys tie.

For the same condition, Bitonic's means over valid outputs are:

| Inputs | τ-b | τ-b ceiling | Key-normalized τ | Stable-ID Recall@10 | Tie-neutral Recall@10 |
|---|---:|---:|---:|---:|---:|
| Distinct | 0.999826 | 1.000000 | 0.999826 | 0.9988 | 0.9988 |
| Duplicates allowed | 0.997888 | 0.998046 | 0.999841 | 0.9978 | 0.9985 |

Mean inversion counts are 2.847 and 2.584, respectively. High partial ordering
quality can coexist with low whole-sort accuracy. Standard τ-b has a lower
ceiling with tied keys; the separately reported normalization makes this
explicit. Sources: [`summary.csv`](../results/ranking_quality/summary.csv)
and [`recall.csv`](../results/ranking_quality/recall.csv).

Rank has no valid outputs in either of these settings, so its conditional τ and
recall are undefined, shown as blank CSV fields. Both recall variants with
`mean_all_invalid_zero` are zero. For Bitonic here, conditional and all-trial
recall coincide because every output is valid. Recall selects the largest keys;
Recall@N checks record preservation only. The formulas and denominators are in
[METHOD.md](METHOD.md).

## 3. Evidence and reproduction

| Recorded directory | What it supports | Command |
|---|---|---|
| [`results/reference/`](../results/reference/) | 288,000 synthetic full-sort outcomes, counts and uncertainty | `python -m qant_sorting.run` |
| [`results/ranking_quality/`](../results/ranking_quality/) | Independent rescoring of every saved outcome; τ, inversions, key-distance errors and both Recall@k variants | `python -m qant_sorting.quality` |
| [`results/sdk/`](../results/sdk/) | Official CPU SDK check: 65,792 ordered pairs and 48,000 correct, stable full sorts | `python -m qant_sorting.sdk` |
| [`results/resources/`](../results/resources/) | Pair/call counts, logical bytes and conditional capacity trade-offs | `python -m qant_sorting.resources` |

Quality evaluation performs no new sorts. Its validation checks complete
coverage and agreement with every saved flag and accuracy count. To score a
fresh main run, use `--results-dir results/reproduced` and a fresh `--output-dir`.
The SDK control adds neither Gaussian noise nor the simulation's extra signed
quantizer; setup and its execution boundary are in [HARDWARE.md](HARDWARE.md).

At N=256, rank uses 65,536 pair differences against Bitonic's 4,608. A sufficiently
large submission can contain the rank matrix; Bitonic has 36 dependent layers.
Capacity, data movement and electronic work therefore matter to any physical
comparison. These logical counts and the SDK CPU check establish no measured
photonic speed or energy advantage.

New runs write to separate reproduction directories. Retained metadata keeps
its original generation environment and source hashes; historical source paths
can differ from the simplified code layout. The main-run duration records
simulation execution time, not a hardware latency benchmark.
