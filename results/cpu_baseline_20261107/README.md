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

The retained timing metadata keeps the exact source hash from the measurement run. The code was subsequently relocated into `qant_sorting/cpu_baseline.py`; the timed NumPy operation and benchmark protocol are unchanged, while the integrated module adds convenient repository-default paths and an explicit canonical NPZ hash guard.

## Retained files

- `summary/b*_n*.csv`: all 192 configuration summaries, split by bit-width and N.
- `metadata.json`: environment, benchmark settings, timing boundary and limitations.
- `validation.json`: complete correctness/stability checks and per-dataset hashes.

The benchmark also generates the repeated raw `samples/` files on reproduction via `python -m qant_sorting.cpu_baseline`.
The committed thesis evidence retains the complete 192-row summary together with
validation and provenance rather than adding the larger raw timing trace to the
main result history.

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
