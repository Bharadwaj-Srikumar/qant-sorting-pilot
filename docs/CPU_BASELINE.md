# Digital CPU baseline - first run on 7 October 2026

## Results and scope

The baseline was validated on all **24,000 saved inputs** from 24 datasets.
Every output preserves the records, is correctly sorted, and is stable.
The measurements cover **192 configurations** and **1,728 timing samples**:
24 datasets × 2 storage formats × 4 batch sizes × 9 repetitions.
The three targeted tests of output semantics and batch processing pass.

These are initial measurements in a shared execution environment. They establish
neither an NPU advantage nor a general best CPU performance. Measurements on a
controlled machine are advisable before making final performance claims.

## Measurement scope

- NumPy `argsort(kind="stable")` produces the original indices;
  `take_along_axis` produces the sorted values.
- Output: sorted keys **and** indices of the original records.
- 4-bit keys from 0–15 and 8-bit keys from 0–255, including equal keys.
- `int64` matches the stored corpus. `uint8` stores the same values in a suitable
  compact format. The two variants are reported separately. The valid key range
  must not be confused with the storage width.
- Batch sizes are 1, 10, 100, and 1,000; each list is sorted independently within
  its row. The entire batch is not sorted as one long list.
- Every measured pass uses all 1,000 lists in each dataset. No rows are discarded
  or replaced by padding.
- Inputs already reside in CPU memory. File I/O, type conversion, input
  preparation, and correctness checks are outside the timed region.
- The Python call, output allocation, sorting, gathering of values, and normal
  release of results are inside the timed region.

## Measurement protocol

Each configuration receives two complete warm-up passes and a calibration of
the repetition count. Based on this calibration, each of the nine timing samples
targets a minimum duration of 15 ms. Actual durations are stored unchanged.
Configuration order is shuffled with the recorded seed 20261007. Inputs are
read-only and reused; this is a benchmark with warm caches.

Each sample yields a **mean time per batch call**. The table reports the median
of these nine means and their interquartile range (IQR). This variation is
neither a distribution of individual request latencies nor a confidence
interval. The relative IQR exceeds 20% in four of the 192 configurations. These
cases remain visible and deserve particular attention in a controlled hardware
rerun. No slow samples were removed.

## Example: 8 bits, N = 256, distinct keys

| Storage format | Lists per call | Time per call | Amortized time per list | Relative IQR |
|---|---:|---:|---:|---:|
| int64 | 1 | 11.90 µs | 11.90 µs | 5.4% |
| int64 | 1000 | 8851.66 µs | 8.85 µs | 12.2% |
| uint8 | 1 | 5.26 µs | 5.26 µs | 10.6% |
| uint8 | 1000 | 1407.79 µs | 1.41 µs | 3.7% |

A call containing 1,000 lists returns all 1,000 outputs only after the stated
call duration. The smaller amortized time measures throughput, not the response
time for an individual list. Even at batch size 1, the tabulated value is a
call duration averaged over repeated passes.

## Environment and reproduction

Measured environment: AMD EPYC 9V74, Python 3.12.14, NumPy 2.3.5, Linux x86-64.
The container sees nine logical CPUs; its cgroup quota corresponds to eight
CPU-time units. This does not mean that NumPy sorting uses eight cores.
Process affinity was not fixed. Full relevant metadata are recorded in
`results/cpu_baseline_20261007/metadata.json`.

Use a separate environment for this benchmark; the historical SDK and sweep
dependencies remain unchanged:

```bash
python -m venv .venv-baseline
# Activate the environment, then run:
python -m pip install -r requirements/cpu.txt
python -m unittest discover -s tests -p test_cpu_baseline.py -v
python -m qant_sorting cpu --output-dir results/cpu_baseline_reproduced
```

The output directory must be empty. The corpus SHA-256 is checked before the
run. Software and input hashes, raw timings, and a correctness check are saved.
Timings depend on the machine and are not expected to match bit for bit on a rerun.

| File | Contents |
|---|---|
| `summary.csv` | Median, IQR, and throughput for each configuration |
| `samples.csv` | All 1,728 raw timing samples and call counts |
| `validation.json` | Correctness, stability, and record preservation |
| `metadata.json` | Environment, measurement boundaries, parameters, and hashes |

## Interpretation

This measures a library baseline, not a custom implementation of the fastest
possible CPU sorter. GPU measurements remain pending. Q.ANT CPU-backend timing
must not be treated as NPU runtime when calculating speedup. Without real NPU
measurements, the digital timings can serve as targets for an explicitly
conditional end-to-end timing estimate. Energy was not measured here.

The complexity model C=(T,S,H,D) remains unchanged. These measurements in seconds
do not replace the definition of T as a sequential real-RAM step count.

Method documentation: [NumPy argsort](https://numpy.org/doc/2.3/reference/generated/numpy.argsort.html)
and [take_along_axis](https://numpy.org/doc/2.3/reference/generated/numpy.take_along_axis.html).

Further work: see [Thesis scope and next steps](THESIS_SCOPE.md).
