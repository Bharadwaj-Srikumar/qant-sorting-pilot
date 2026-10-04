# Noise sweep results

Full-sort accuracy, 1,000 saved input arrays per setting. Each cell is **bitonic / rank** (%).

| Setting | eta=0 | 0.05 | 0.10 | 0.15 | 0.20 | 0.25 |
|---|---:|---:|---:|---:|---:|---:|
| 4-bit, N=16, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 99.9 | 95.5 / 95.0 | 84.3 / 83.1 |
| 4-bit, N=16, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 99.7 | 95.1 / 95.2 | 87.9 / 80.2 |
| 8-bit, N=256, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 93.9 / 96.1 | 44.7 / 45.4 | 5.9 / 4.0 |
| 8-bit, N=256, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 95.5 / 94.7 | 54.8 / 38.3 | 10.4 / 3.1 |

All tested sizes—not only these maximum sizes—had 1,000/1,000 correct, stable sorts per configuration at eta <= 0.10. This is observed success under the stated input/noise model, not universal proof or measured Q.ANT accuracy.

The full sweep covers 24 saved datasets × 6 noise values × 2 mappings = **288 configurations and 288,000 sorting executions**. The 288 CSV rows include 95% Wilson intervals.

“Duplicates allowed” means uniform sampling with replacement, not a guarantee that every sampled array contains a repeated key. Distinct arrays at maximum N contain the complete key domain.

At larger N, more opportunities for a noisy decision can reduce whole-array success. Invalid or repeated ranks are failed outputs. Comparison diagnostics and stable-sort counts are distinct from the headline full-sort accuracy.

The documented cleanup reproduces every reference CSV row, all 576 saved flags/index arrays, and all first-failure examples exactly. Independent seeds between mappings and common streams across positive noise levels are unchanged.

Read [METHOD.md](METHOD.md) for the equations and [HARDWARE.md](HARDWARE.md) for the remaining hardware questions.
