# Reading guide: a digital PERFORMANCE baseline, independent of noise models.
# run validates the frozen corpus, prepares dtype/batch variants, checks output
# contracts, warms up, then records repeated timed calls to stable_records.
# The measured call produces BOTH sorted values and original indices; allocation
# and gather are included. Input loading/conversion and validation are excluded.
# The timer measures physical host seconds, not the real-RAM complexity T.
# An amortized batch time per array is not a single-request latency measurement.
# Run via the CLI into an empty output directory; importing helpers runs no sweep.

"""Stable digital CPU baseline on the unchanged 4/8-bit input corpus.

Measures an application call returning sorted keys AND original indices.
No Q.ANT SDK, simulated noise, or photonic timing is involved.
"""

from qant_sorting.io import source_hashes, write_csv

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import sys
import time

import numpy as np

from qant_sorting.paths import ROOT, INPUT_SHA256


# Input one key array or batch, with records along the last axis.
# Return (sorted_values, original_indices) using a stable argsort plus gather.
# Both outputs are allocated and equal-key indices preserve original order.
# This COMPLETE helper call is the timed baseline; timing only argsort would
# omit the required routed-value output and make the comparison inconsistent.
def stable_records(data):
    indices = np.argsort(data, axis=-1, kind="stable")
    return np.take_along_axis(data, indices, axis=-1), indices


# Check shape, integer index type, full permutation, value/index consistency,
# ascending keys and increasing original indices within equal-key runs.
# Raise AssertionError at the first violated property; return None on success.
# This checker is outside the timed scope and does not silently repair outputs.
# The permutation check precedes value gathering so invalid indices are rejected.
def validate_records(data, values, indices):
    """Check properties independently of the argsort implementation."""
    if values.shape != data.shape or indices.shape != data.shape:
        raise AssertionError("Wrong output shape")
    if indices.dtype.kind not in "iu":
        raise AssertionError("Indices must be integers")
    n = data.shape[-1]
    if not np.all(np.sort(indices, axis=-1) == np.arange(n)):
        raise AssertionError("Output is not a permutation of the input records")
    if not np.array_equal(values, np.take_along_axis(data, indices, axis=-1)):
        raise AssertionError("Keys and original indices disagree")
    if np.any(values[..., 1:] < values[..., :-1]):
        raise AssertionError("Keys are not sorted")
    tied = values[..., 1:] == values[..., :-1]
    if np.any(tied & (indices[..., 1:] <= indices[..., :-1])):
        raise AssertionError("Equal keys lost their original order")


# Input prebuilt batches and repetition count; return total measured seconds.
# The timed loop includes Python calls, stable sorting, allocation, gathering,
# and ordinary result release. Corpus loading and batch construction occur earlier.
# Temporarily disable cyclic garbage collection and restore its previous state
# even on failure. Reference-count-based result release still occurs in the loop.
# This measures warm repeated host work, not isolated hardware instruction latency.
def measure_passes(batches, passes):
    # Inputs/views were prepared before timing. Function calls, result allocation,
    # argsort, gather and ordinary result release remain inside the timed scope.
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        start = time.perf_counter_ns()
        for _ in range(passes):
            for batch in batches:
                stable_records(batch)
        elapsed = (time.perf_counter_ns() - start) * 1e-9
    finally:
        if was_enabled:
            gc.enable()
    return elapsed


# Collect runtime, CPU visibility/affinity, optional Linux quota, known thread
# environment variables and timer resolution into a JSON-ready dict.
# Missing platform-specific facilities yield absent/None observations rather
# than assumed hardware capacity. Visible logical CPUs are not exclusive cores;
# these fields help explain why shared-machine timings have limited portability.
def environment():
    cpu = platform.processor()
    info = Path("/proc/cpuinfo")
    if info.exists():
        cpu = next((line.split(":", 1)[1].strip() for line in info.read_text().splitlines()
                    if line.startswith("model name")), cpu)
    quota = Path("/sys/fs/cgroup/cpu.max")
    return dict(
        python=sys.version, numpy=np.__version__, platform=platform.platform(),
        cpu_model=cpu, logical_cpus_visible=os.cpu_count(),
        affinity_cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        cgroup_cpu_max=quota.read_text().strip() if quota.exists() else None,
        thread_environment={key: os.environ.get(key) for key in
                            ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        timer="time.perf_counter_ns", timer_resolution_s=time.get_clock_info("perf_counter").resolution,
        gpu_executed=False, photonic_hardware_executed=False,
    )


# Validate CLI settings and the exact corpus hash, then prepare storage/batch
# variants without changing key values. Require an empty output directory.
# Validate each dtype's stable output before timing and mark input buffers read-only.
# Randomize case order with a saved seed; warm up and calibrate the number of
# passes needed for the target duration. Save raw repeats and median/IQR summaries.
# The IQR is repeat variation of average batch times, not a tail-latency interval.
# Write validation and machine/protocol metadata; no SDK/GPU/NPU is executed.
def run(args):
    if args.repeats < 5 or args.target_ms <= 0 or not math.isfinite(args.target_ms):
        raise ValueError("Use at least 5 repetitions and a finite positive target duration")
    if args.warmup_passes < 1 or any(size < 1 for size in args.batch_sizes):
        raise ValueError("Warmup passes and batch sizes must be positive")
    if len(set(args.batch_sizes)) != len(args.batch_sizes) or len(set(args.dtypes)) != len(args.dtypes):
        raise ValueError("Duplicate settings would duplicate observations")
    input_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    if input_hash != INPUT_SHA256:
        raise ValueError("Input corpus differs from the saved agreed experiment")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Output directory must be empty; preserve previous measurements")

    # Preparation phase, outside timing: create equal-value storage variants and
    # batch views, validate stable output, then freeze the input buffers. No padding
    # or dropped remainder rows are permitted.
    cases, validation = [], []
    with np.load(args.input, allow_pickle=False) as corpus:
        for name in sorted(corpus.files):
            original = corpus[name]
            bit_tag, n_tag, family = name.split("_", 2)
            bits, n = int(bit_tag[1:]), int(n_tag[1:])
            if original.ndim != 2 or original.shape[1] != n or original.dtype.kind not in "iu":
                raise ValueError("Unexpected corpus schema")
            if np.any(original < 0) or np.any(original >= 2**bits):
                raise ValueError("Key outside the declared range")
            for dtype in args.dtypes:
                data = np.ascontiguousarray(original, dtype=dtype)
                if not np.array_equal(data, original):
                    raise ValueError("Storage conversion changed key values")
                before = data.tobytes()
                validate_records(data, *stable_records(data))
                if data.tobytes() != before:
                    raise AssertionError("Sorter modified its inputs")
                validation.append(dict(dataset=name, storage_dtype=dtype, arrays=len(data),
                                       valid=True, sorted=True, stable=True, input_unchanged=True))
                data.flags.writeable = False
                for batch_size in args.batch_sizes:
                    if len(data) % batch_size:
                        raise ValueError("Batch size must divide dataset size; no padding or dropped rows")
                    batches = tuple(data[start:start + batch_size]
                                    for start in range(0, len(data), batch_size))
                    cases.append(dict(dataset=name, key_bits=bits, n=n, family=family,
                                      storage_dtype=dtype, batch_size=batch_size, batches=batches))

    # Randomized, recorded order reduces systematic alignment with machine drift.
    rng = random.Random(args.seed)
    rng.shuffle(cases)
    raw, summaries = [], []
    for order, case in enumerate(cases):
        batches = case["batches"]
        for _ in range(args.warmup_passes):
            measure_passes(batches, 1)
        # Timing phase: estimate how many full-corpus passes give a measurable interval.
        # The calibration and warmup times are not themselves reported samples. Each
        # subsequent repetition produces a mean per batch call.
        calibration_s = measure_passes(batches, 1)
        passes = max(1, math.ceil(args.target_ms / 1000 / max(calibration_s, 1e-9)))
        fields = {key: value for key, value in case.items() if key != "batches"}
        samples = []
        for repeat in range(args.repeats):
            elapsed = measure_passes(batches, passes)
            calls = passes * len(batches)
            per_batch = elapsed / calls
            samples.append(per_batch)
            raw.append(dict(**fields, case_order=order, repeat=repeat, passes=passes,
                            batch_calls=calls, elapsed_s=elapsed, mean_batch_s=per_batch))
        # Aggregation phase: summarize repeated mean batch times. Dividing the median
        # by batch_size gives amortized cost per array, not latency of a single request
        # executed alone. Preserve raw timings so variation remains inspectable.
        q25, median, q75 = np.quantile(samples, [.25, .5, .75])
        summaries.append(dict(**fields, repeats=args.repeats, dataset_arrays=sum(map(len, batches)),
                              median_mean_batch_s=float(median), p25_mean_batch_s=float(q25),
                              p75_mean_batch_s=float(q75), relative_iqr=float((q75-q25)/median),
                              amortized_s_per_array=float(median / case["batch_size"]),
                              arrays_per_s=float(case["batch_size"] / median),
                              keys_per_s=float(case["batch_size"] * case["n"] / median)))
        if (order + 1) % 24 == 0:
            print(f"CPU cases complete: {order + 1}/{len(cases)}", flush=True)

    summaries.sort(key=lambda row: (row["key_bits"], row["n"], row["family"],
                                   row["storage_dtype"], row["batch_size"]))
    write_csv(output / "summary.csv", summaries)
    write_csv(output / "samples.csv", raw)
    (output / "validation.json").write_text(json.dumps(dict(
        all_passed=True, checks=validation, unique_input_arrays=24000,
        note="The same numerical arrays are checked once per storage dtype; these are not independent new inputs."
    ), indent=2) + "\n", encoding="utf-8")
    metadata = dict(
        created_at_utc=datetime.now(timezone.utc).isoformat(), environment=environment(),
        input_sha256=input_hash, source_sha256=source_hashes(),
        baseline="NumPy stable argsort + take_along_axis", input_storage_dtypes=args.dtypes,
        index_dtype=str(np.dtype(np.intp)), batch_sizes=args.batch_sizes,
        repeats=args.repeats, target_ms=args.target_ms, warmup_passes=args.warmup_passes,
        case_order_seed=args.seed, measured_cases=len(cases), raw_samples=len(raw),
        scope="CPU application calls returning sorted keys and original indices; allocations and gather included",
        excluded="File loading, dtype conversion, input preparation, validation and result-file writing",
        protocol="Warm-cache repeated full-corpus passes, immutable inputs, GC disabled only during timing",
        statistic="Median across repeated mean batch times. IQR is repeat variation, not a per-request tail latency or confidence interval.",
        limits=["Shared execution environment; timings apply to this software and machine only",
                "No GPU, photonic latency, device energy, or photonic speedup measured",
                "NumPy library baseline, not a claim of the fastest possible CPU implementation",
                "Amortized time per array in a batch is not single-array response latency"],
        units="Physical seconds and throughput; no redefinition of real-RAM T or of C=(T,S,H,D)",
    )
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(cases)} cases and {len(raw)} timing samples to {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/inputs.npz")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/cpu_baseline_reproduced")
    parser.add_argument("--batch-sizes", nargs="+", type=int, default=[1, 10, 100, 1000])
    parser.add_argument("--dtypes", nargs="+", choices=["uint8", "int64"], default=["uint8", "int64"])
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--target-ms", type=float, default=15)
    parser.add_argument("--warmup-passes", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261007)
    run(parser.parse_args())
