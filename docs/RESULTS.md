# Current evaluation results

The canonical architectures are **Bitonic** and **Louri full-matrix rank sorting**. Each rank run evaluates N² directed cells, including the diagonal. Reverse decisions are not inferred.

## Whole-array correctness

Each cell is **Bitonic / Louri** (%), from 1,000 saved inputs per setting.

| Setting | η=0 | 0.05 | 0.10 | 0.15 | 0.20 | 0.25 |
|---|---:|---:|---:|---:|---:|---:|
| 4-bit, N=16, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 97.9 | 95.5 / 82.1 | 84.3 / 49.5 |
| 4-bit, N=16, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 97.7 | 95.1 / 75.5 | 87.9 / 35.2 |
| 8-bit, N=256, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 93.9 / 81.2 | 44.7 / 3.5 | 5.9 / 0.0 |
| 8-bit, N=256, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 95.5 / 72.4 | 54.8 / 1.2 | 10.4 / 0.0 |

The complete sweep contains **288 configurations and 288,000 sorts**. At η=0,
all 48,000 sorts are correct and stable. Each matrix cell receives independent
Gaussian difference noise with σ=ηΔ, followed by the specified signed quantizer;
Louri's exact host bias and inclusive threshold follow quantization. These are
simulation assumptions, not measured Q.ANT noise.

At 8 bits, N=256 and η=0.25, Louri has **no valid rank permutations** in either
input regime. Such failures are retained and are not repaired electronically.
Conditional Kendall-τ and recall are undefined when no valid outputs exist;
recall utility that assigns zero to invalid outputs is zero. Bitonic always
retains a permutation, which does not ensure sortedness. See
[RANKING_QUALITY.md](RANKING_QUALITY.md) for the separate denominators.

"Duplicates allowed" means sampling with replacement. Distinct inputs at the
maximum size cover the complete key domain. More cells create more opportunities
for noisy threshold errors; simple independent-array probability claims are not
made because outcomes also depend on the keys, thresholds and rank constraints.

## Independent checks and related evidence

| Evidence | Current scope | Result |
|---|---|---|
| Literal Louri equations and stable argsort | 155,328 noiseless arrays | Agreement, including ties and rank offset |
| Official CPU SDK | 65,792 pairs; 48,000 full sorts | Exact differences and correct stable orders |
| Rerun with different batch size | 288,000 main-sort outcomes | All CSV rows, flags, indices and failure examples identical |
| Ranking quality | All 288,000 main-sort outcomes | Complete coverage; τ, distance errors and Recall@k |
| Common-channel controls | 28 million pair decisions; 10,800 sorts | Analytic and noiseless checks passed |
| Periodic CPU pairs | All 65,792 ordered pairs | Correct after host reference correction |
| Affine BF16 phase | All 65,792 pairs per path | 40 false 8-bit ties; no hardware advantage established |
| Digital CPU baseline | 192 measured configurations | Dated platform-specific comparison; no GPU/NPU timing |

The full matrix uses 65,536 pair differences at N=256, against 4,608 for Bitonic.
One sufficiently large submission can contain the matrix; Bitonic requires 36
dependent layers. Capacity limits, logical bytes and host work all affect any
future timing comparison. See [HARDWARE.md](HARDWARE.md).

Current evidence is in `results/reference`, `sdk`, `louri`, `ranking_quality`,
`common_noise`, `resources`, `periodic`, `affine` and `cpu_baseline_20261007`.
The report's evidence manifest records file hashes. See [METHOD.md](METHOD.md)
for model equations and [THESIS_SCOPE.md](THESIS_SCOPE.md) for the research scope.
