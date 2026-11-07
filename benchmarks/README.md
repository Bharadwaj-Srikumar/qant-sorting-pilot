# CPU baseline benchmark

This folder contains a **standalone digital baseline** for the thesis. It is
kept outside `qant_sorting/` so the CPU timing experiment is not mixed with the
photonic mapping, noise model, SDK integration or sorting-quality code.

## What is measured

The timed application call is:

```python
indices = np.argsort(data, axis=-1, kind="stable")
values = np.take_along_axis(data, indices, axis=-1)
```

It therefore returns both the sorted keys and the original record indices.
Allocation and gathering are included. File loading, dtype conversion, input
validation and writing result files are excluded from the timed region.

The benchmark tests the same 24 thesis datasets using:

- storage dtypes: `uint8`, `int64`;
- batch sizes: 1, 10, 100, 1000 lists per call;
- 9 repeated timing samples per case;
- 2 warm-up passes;
- a target timing interval of 15 ms per repeated sample;
- randomized case order with seed `20261107`.

The script checks the SHA-256 content hash of every dataset before measuring.
This is stronger than checking only the NPZ container because it verifies the
actual arrays consumed by the sort.

## Reproduce

From the repository root with NumPy installed:

```bash
python benchmarks/cpu_baseline.py \
  --input data/inputs.npz \
  --output-dir results/cpu_baseline_reproduced
```

The output directory must be empty so an earlier measurement cannot be silently
overwritten.

## Fresh run retained in the repository

`results/cpu_baseline_20261107/` is a fresh run performed on 7 November 2026.
It contains:

- `summary/b*_n*.csv` — all 192 configurations, split by bit-width and N;
- `samples/b*_n*.csv` — all 1,728 raw timing samples, split the same way;
- `validation.json` — correctness, stability and dataset-hash checks;
- `metadata.json` — machine/software environment and timing boundary.

Environment of the retained run:

- AMD EPYC 9V74 80-Core Processor;
- Python 3.13.5;
- NumPy 2.3.5;
- 5 visible logical CPUs, affinity CPUs 0–4;
- cgroup quota `400000 100000` (four CPU-time units).

For 8-bit distinct keys at `N=256`:

| Storage dtype | Lists per call | Median time per call | Amortized time per list | Relative IQR |
|---|---:|---:|---:|---:|
| int64 | 1 | 11.74 µs | 11.74 µs | 2.6% |
| int64 | 1,000 | 7.894 ms | 7.89 µs | 4.6% |
| uint8 | 1 | 5.44 µs | 5.44 µs | 8.6% |
| uint8 | 1,000 | 1.380 ms | 1.38 µs | 2.0% |

These values are platform-specific measurements, not a universal CPU lower
bound. Four of the 192 configurations have relative IQR above 20%; the raw
samples are retained rather than filtered. No GPU, Q.ANT NPU, photonic latency
or energy measurement is implied.
