"""Digital CPU reference for the thesis sorting task.

Measures a conventional stable NumPy sort on the same fixed input corpus as the
photonic evaluation. No noise model, Q.ANT SDK, or hybrid mapping is used.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/inputs.npz"
INPUT_SHA256 = "79efbd1ee270242cc122d8f9e1848fe07a85077bcf310324b27dd60f8faf11da"

BATCH_SIZES = (1, 10, 100, 1000)
DTYPES = ("uint8", "int64")
REPEATS = 9
WARMUPS = 2
TARGET_MS = 15.0


def stable_sort(data):
    indices = np.argsort(data, axis=-1, kind="stable")
    return np.take_along_axis(data, indices, axis=-1), indices


def validate_sort(data, values, indices):
    n = data.shape[-1]
    if values.shape != data.shape or indices.shape != data.shape:
        raise AssertionError("wrong output shape")
    if not np.all(np.sort(indices, axis=-1) == np.arange(n)):
        raise AssertionError("output is not a record permutation")
    if not np.array_equal(values, np.take_along_axis(data, indices, axis=-1)):
        raise AssertionError("values and record indices disagree")
    if np.any(values[..., 1:] < values[..., :-1]):
        raise AssertionError("keys are not sorted")
    tied = values[..., 1:] == values[..., :-1]
    if np.any(tied & (indices[..., 1:] <= indices[..., :-1])):
        raise AssertionError("stable tie order was not preserved")


def measure(batches, passes):
    start = time.perf_counter_ns()
    for _ in range(passes):
        for batch in batches:
            stable_sort(batch)
    return (time.perf_counter_ns() - start) * 1e-9


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def cpu_model():
    info = Path("/proc/cpuinfo")
    if info.exists():
        for line in info.read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output directory must be empty")

    input_sha = hashlib.sha256(INPUT.read_bytes()).hexdigest()
    if input_sha != INPUT_SHA256:
        raise ValueError("input archive differs from the thesis corpus")

    cases = []
    with np.load(INPUT, allow_pickle=False) as corpus:
        if len(corpus.files) != 24:
            raise ValueError("expected 24 thesis datasets")

        for name in sorted(corpus.files):
            bit_tag, n_tag, family = name.split("_", 2)
            bits, n = int(bit_tag[1:]), int(n_tag[1:])
            original = np.asarray(corpus[name])

            if original.shape != (1000, n) or original.dtype.kind not in "iu":
                raise ValueError(f"unexpected dataset schema: {name}")
            if np.any(original < 0) or np.any(original >= 2**bits):
                raise ValueError(f"key outside {bits}-bit range: {name}")

            for dtype in DTYPES:
                data = np.ascontiguousarray(original, dtype=dtype)
                if not np.array_equal(data, original):
                    raise ValueError(f"dtype conversion changed values: {name}")
                validate_sort(data, *stable_sort(data))
                data.flags.writeable = False

                for batch_size in BATCH_SIZES:
                    batches = tuple(
                        data[i:i + batch_size] for i in range(0, len(data), batch_size)
                    )
                    cases.append((name, bits, n, family, dtype, batch_size, batches))

    samples, summary = [], []
    started = time.perf_counter()

    for name, bits, n, family, dtype, batch_size, batches in cases:
        for _ in range(WARMUPS):
            measure(batches, 1)

        calibration = measure(batches, 1)
        passes = max(1, math.ceil((TARGET_MS / 1000) / max(calibration, 1e-9)))
        times = []

        for repeat in range(REPEATS):
            elapsed = measure(batches, passes)
            mean_batch_s = elapsed / (passes * len(batches))
            times.append(mean_batch_s)
            samples.append({
                "dataset": name, "storage_dtype": dtype, "batch_size": batch_size,
                "repeat": repeat, "passes": passes, "elapsed_s": elapsed,
                "mean_batch_s": mean_batch_s,
            })

        q25, median, q75 = np.quantile(times, [0.25, 0.5, 0.75])
        summary.append({
            "dataset": name, "key_bits": bits, "n": n, "family": family,
            "storage_dtype": dtype, "batch_size": batch_size,
            "median_batch_s": float(median),
            "relative_iqr": float((q75 - q25) / median),
            "amortized_s_per_array": float(median / batch_size),
            "arrays_per_s": float(batch_size / median),
            "keys_per_s": float(batch_size * n / median),
        })

    write_csv(output / "summary.csv", summary)
    write_csv(output / "samples.csv", samples)

    (output / "validation.json").write_text(json.dumps({
        "all_passed": True,
        "datasets": 24,
        "unique_input_arrays": 24000,
        "stable_sort_verified": True,
        "input_sha256": input_sha,
    }, indent=2) + "\n")

    quota = Path("/sys/fs/cgroup/cpu.max")
    (output / "metadata.json").write_text(json.dumps({
        "run_id": output.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cpu_model": cpu_model(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "logical_cpus_visible": os.cpu_count(),
        "cgroup_cpu_max": quota.read_text().strip() if quota.exists() else None,
        "input_sha256": input_sha,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "baseline": "NumPy stable argsort + take_along_axis",
        "batch_sizes": BATCH_SIZES,
        "storage_dtypes": DTYPES,
        "repeats": REPEATS,
        "warmups": WARMUPS,
        "target_ms": TARGET_MS,
        "configurations": len(summary),
        "timing_samples": len(samples),
        "benchmark_elapsed_s": time.perf_counter() - started,
        "timed": "stable argsort, index allocation and value gathering",
        "excluded": "file loading, dtype conversion, validation and result writing",
        "limitations": [
            "platform-specific NumPy baseline",
            "no GPU, NPU, energy or photonic speedup measurement",
        ],
    }, indent=2) + "\n")

    print(f"Saved {len(summary)} configurations and {len(samples)} timing samples to {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "results/cpu_baseline_reproduced",
    )
    run(parser.parse_args().output_dir)


if __name__ == "__main__":
    main()
