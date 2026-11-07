# Fresh CPU baseline — 7 November 2026

This directory contains the retained evidence from a **fresh rerun** of the
standalone CPU sorting baseline. It is intentionally separate from the main
`simulation_*`, `quality_*`, `sdk_*` and `resources_*` result files.

## Run identity

- Run ID: `cpu_baseline_20261107`
- Input corpus SHA-256:
  `79efbd1ee270242cc122d8f9e1848fe07a85077bcf310324b27dd60f8faf11da`
- 24 datasets / 24,000 unique input arrays
- 2 storage dtypes × 4 batch sizes = 192 configurations
- 9 repeated timing samples per configuration = 1,728 measured samples
- All correctness, record-preservation and stability checks passed
- The content hash of every dataset matched the declared thesis corpus

The benchmark code is integrated into the main package at
[`qant_sorting/cpu_baseline.py`](../../qant_sorting/cpu_baseline.py). It remains a
separate digital-performance theme and does not call the photonic noise/SDK path.

The retained timing metadata keeps the exact source hash from the measurement
run. The current benchmark was subsequently simplified without changing the
measured operation or benchmark settings; the simplified code has also been
test-run successfully against the exact canonical input archive.

## Retained files

- `summary/b*_n*.csv`: all 192 configuration summaries, split by bit-width and N.
- `metadata.json`: environment, benchmark settings, timing boundary and limitations.
- `validation.json`: complete correctness/stability checks and per-dataset hashes.

A fresh reproduction writes `summary.csv`, `samples.csv`, `validation.json` and
`metadata.json` into a new output directory. The committed 7 November evidence
keeps the complete 192-row summary plus concise validation/provenance; the 1,728
raw timing samples are regenerated when the benchmark is rerun.

## Example: 8-bit, N=256, distinct keys

| Storage dtype | Lists per call | Median time per call | Amortized time per list | Relative IQR |
|---|---:|---:|---:|---:|
| int64 | 1 | 11.74 µs | 11.74 µs | 2.6% |
| int64 | 1,000 | 7.894 ms | 7.89 µs | 4.6% |
| uint8 | 1 | 5.44 µs | 5.44 µs | 8.6% |
| uint8 | 1,000 | 1.380 ms | 1.38 µs | 2.0% |

The retained environment was an AMD EPYC 9V74 host with Python 3.13.5 and
NumPy 2.3.5. These are platform-specific CPU measurements. They are not an NPU
measurement, not an energy benchmark, and not evidence of photonic speedup.
The GPU baseline remains open.
