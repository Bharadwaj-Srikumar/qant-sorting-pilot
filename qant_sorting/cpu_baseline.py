"""Stable digital CPU baseline for the thesis input corpus.

This module lives beside the photonic evaluation code but remains a separate
measurement path: it uses NumPy only and does not call the noise model, Q.ANT
SDK, or photonic mapping. It measures stable argsort plus value gathering and
returns both sorted values and original record indices.
"""

from __future__ import annotations

import argparse
import csv
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

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_INPUT_ARCHIVE_SHA256 = "79efbd1ee270242cc122d8f9e1848fe07a85077bcf310324b27dd60f8faf11da"

EXPECTED_DATASET_HASHES = {
    "b4_n2_distinct": "9d124934ecb8c2ac90f48c4adc50f8d1687436a24be230a31c67948068a7c690",
    "b4_n2_duplicates_allowed": "46b4cfd15f677c5075042239b9675275246d65178477adcf2da5d76621b86c7e",
    "b4_n4_distinct": "a5b822cfa23039a8f9a5cf7ea86ae2d82a984e2f2c754509b227ebbed5b1cbf7",
    "b4_n4_duplicates_allowed": "b6d9c994587bf6c956cd5c257060eb4b4cd01dab40eb86b8154cf697bd2a24a9",
    "b4_n8_distinct": "a49a86ad42ffb96b0c3e5f30d4aa649f21eed6a9878f608a3640dccaef2b09ad",
    "b4_n8_duplicates_allowed": "77ba6aadc447e8aa867271951f2c3d5fed31b0e8cd5c5c0cb3cba01043727803",
    "b4_n16_distinct": "0f5209aa939da6ae6a082960b6d9a01a05c5f20c8669e48f682e635716659ef5",
    "b4_n16_duplicates_allowed": "1bd59b8ae4bd6e37dd5d021b08b5c2abccd409721ad99272a291731e1dcd3806",
    "b8_n2_distinct": "6887b230c8f5b882177818d5277a061aec79c3d3d060cb7a4b5834cedad6d285",
    "b8_n2_duplicates_allowed": "4366440412f639ce5777c2a954bc54c89b5620ddf63f27ce495827eb0b9f8bdf",
    "b8_n4_distinct": "25247cb898d7e9e0c75a893804f654fe071dd8c909007142859d461fd721dc20",
    "b8_n4_duplicates_allowed": "c09bdc5407d97f853f9c367e1f37284b4b6628570a9703918810028708241641",
    "b8_n8_distinct": "906e92e2f0cc99b07954fc0486b404768302eec07ade54a000847c569b11c23b",
    "b8_n8_duplicates_allowed": "fc3b33024cd97e5eec84b6cb9f057668221ca29c311bc69f1c2ca799987fca7d",
    "b8_n16_distinct": "a2f89d5f47862e3124456dfec2ef41606e127114e375800b2f50df3971ac9152",
    "b8_n16_duplicates_allowed": "b974457253242a55e4227547fb50c798045ad06aa07e94262b86ddd35f5c6939",
    "b8_n32_distinct": "132dc04aaefe973d42b13759dd0c734a995a3e1330cf4c0e4c1428c76549acfb",
    "b8_n32_duplicates_allowed": "492f6c7980649ad1b8d8a2d052f5acbdd4898d01a7d3cbc273a295d5b47d38c5",
    "b8_n64_distinct": "90c5d739ae5e78ed2cf0c887c827e6ead5826bded9f08ca9626ceea928e8ec55",
    "b8_n64_duplicates_allowed": "c5d141dc59a2da3598e55ef66b1073d41b4bf7eee18182f2acbb673fceb86816",
    "b8_n128_distinct": "dda190398b034bc90f33ac9a5508ea690e606a401fa7abe007a6f0e4ef8a45b8",
    "b8_n128_duplicates_allowed": "2666494aa94456437ba445ccc672565bb1365cf772af971d5342261ec38af867",
    "b8_n256_distinct": "e5496abcbb81b7476cb9fdf37c0b5d1f352387fbbc5e32084c1e0f7f78dc5c33",
    "b8_n256_duplicates_allowed": "2b54fefe2ff5995e02730203bc78f46cdfbfb035dbad7e265d2de4a4c682898b",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_records(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    indices = np.argsort(data, axis=-1, kind="stable")
    values = np.take_along_axis(data, indices, axis=-1)
    return values, indices


def validate_records(data: np.ndarray, values: np.ndarray, indices: np.ndarray) -> None:
    if values.shape != data.shape or indices.shape != data.shape:
        raise AssertionError("wrong output shape")
    if indices.dtype.kind not in "iu":
        raise AssertionError("indices must be integer")
    n = data.shape[-1]
    if not np.all(np.sort(indices, axis=-1) == np.arange(n)):
        raise AssertionError("output indices are not a permutation")
    if not np.array_equal(values, np.take_along_axis(data, indices, axis=-1)):
        raise AssertionError("sorted values and record indices disagree")
    if np.any(values[..., 1:] < values[..., :-1]):
        raise AssertionError("keys are not sorted")
    tied = values[..., 1:] == values[..., :-1]
    if np.any(tied & (indices[..., 1:] <= indices[..., :-1])):
        raise AssertionError("stable order of equal keys was not preserved")


def measure_passes(batches: tuple[np.ndarray, ...], passes: int) -> float:
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        start = time.perf_counter_ns()
        for _ in range(passes):
            for batch in batches:
                stable_records(batch)
        return (time.perf_counter_ns() - start) * 1e-9
    finally:
        if was_enabled:
            gc.enable()


def environment() -> dict:
    cpu = platform.processor()
    info = Path("/proc/cpuinfo")
    if info.exists():
        cpu = next(
            (line.split(":", 1)[1].strip() for line in info.read_text().splitlines()
             if line.startswith("model name")),
            cpu,
        )
    quota = Path("/sys/fs/cgroup/cpu.max")
    return {
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "cpu_model": cpu,
        "logical_cpus_visible": os.cpu_count(),
        "affinity_cpus": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "cgroup_cpu_max": quota.read_text().strip() if quota.exists() else None,
        "thread_environment": {
            key: os.environ.get(key)
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "timer": "time.perf_counter_ns",
        "timer_resolution_s": time.get_clock_info("perf_counter").resolution,
        "gpu_executed": False,
        "photonic_hardware_executed": False,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> None:
    if args.repeats < 5 or args.target_ms <= 0 or not math.isfinite(args.target_ms):
        raise ValueError("repeats >= 5 and finite positive target_ms required")
    if args.warmup_passes < 1:
        raise ValueError("warmup_passes must be positive")
    if any(size < 1 for size in args.batch_sizes):
        raise ValueError("batch sizes must be positive")
    if len(set(args.batch_sizes)) != len(args.batch_sizes):
        raise ValueError("duplicate batch size")
    if len(set(args.dtypes)) != len(args.dtypes):
        raise ValueError("duplicate dtype")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output directory must be empty")

    input_archive_sha256 = sha256_bytes(args.input.read_bytes())
    if input_archive_sha256 != EXPECTED_INPUT_ARCHIVE_SHA256:
        raise ValueError("input archive differs from the declared thesis corpus")
    dataset_hashes = {}
    validation = []
    cases = []

    with np.load(args.input, allow_pickle=False) as corpus:
        if set(corpus.files) != set(EXPECTED_DATASET_HASHES):
            raise ValueError("input dataset names differ from the declared thesis corpus")
        for name in sorted(corpus.files):
            original = np.asarray(corpus[name])
            bit_tag, n_tag, family = name.split("_", 2)
            bits, n = int(bit_tag[1:]), int(n_tag[1:])
            if original.shape != (1000, n) or original.dtype.kind not in "iu":
                raise ValueError(f"unexpected schema for {name}")
            if np.any(original < 0) or np.any(original >= 2**bits):
                raise ValueError(f"key outside declared range in {name}")
            normalized = np.ascontiguousarray(original, dtype="<i8")
            digest = sha256_bytes(normalized.tobytes())
            dataset_hashes[name] = digest
            if digest != EXPECTED_DATASET_HASHES[name]:
                raise ValueError(f"dataset content hash mismatch for {name}")

            for dtype in args.dtypes:
                data = np.ascontiguousarray(original, dtype=dtype)
                if not np.array_equal(data, original):
                    raise ValueError(f"storage conversion changed values for {name}/{dtype}")
                before = data.tobytes()
                values, indices = stable_records(data)
                validate_records(data, values, indices)
                if data.tobytes() != before:
                    raise AssertionError("baseline modified input")
                validation.append({
                    "dataset": name,
                    "storage_dtype": dtype,
                    "arrays": len(data),
                    "valid": True,
                    "sorted": True,
                    "stable": True,
                    "input_unchanged": True,
                })
                data.flags.writeable = False
                for batch_size in args.batch_sizes:
                    if len(data) % batch_size:
                        raise ValueError("batch size must divide 1000; no padding/drop allowed")
                    batches = tuple(
                        data[start:start + batch_size]
                        for start in range(0, len(data), batch_size)
                    )
                    cases.append({
                        "dataset": name,
                        "key_bits": bits,
                        "n": n,
                        "family": family,
                        "storage_dtype": dtype,
                        "batch_size": batch_size,
                        "batches": batches,
                    })

    rng = random.Random(args.seed)
    rng.shuffle(cases)
    raw = []
    summaries = []
    started = time.perf_counter()

    for order, case in enumerate(cases):
        batches = case["batches"]
        for _ in range(args.warmup_passes):
            measure_passes(batches, 1)
        calibration_s = measure_passes(batches, 1)
        passes = max(1, math.ceil(args.target_ms / 1000 / max(calibration_s, 1e-9)))
        fields = {key: value for key, value in case.items() if key != "batches"}
        samples = []
        for repeat in range(args.repeats):
            elapsed = measure_passes(batches, passes)
            calls = passes * len(batches)
            per_batch = elapsed / calls
            samples.append(per_batch)
            raw.append({
                **fields,
                "case_order": order,
                "repeat": repeat,
                "passes": passes,
                "batch_calls": calls,
                "elapsed_s": elapsed,
                "mean_batch_s": per_batch,
            })
        q25, median, q75 = np.quantile(samples, [0.25, 0.5, 0.75])
        summaries.append({
            **fields,
            "repeats": args.repeats,
            "dataset_arrays": sum(map(len, batches)),
            "median_mean_batch_s": float(median),
            "p25_mean_batch_s": float(q25),
            "p75_mean_batch_s": float(q75),
            "relative_iqr": float((q75 - q25) / median),
            "amortized_s_per_array": float(median / case["batch_size"]),
            "arrays_per_s": float(case["batch_size"] / median),
            "keys_per_s": float(case["batch_size"] * case["n"] / median),
        })
        if (order + 1) % 24 == 0:
            print(f"CPU cases complete: {order + 1}/{len(cases)}", flush=True)

    summaries.sort(key=lambda row: (
        row["key_bits"], row["n"], row["family"], row["storage_dtype"], row["batch_size"]
    ))

    summary_dir = output / "summary"
    samples_dir = output / "samples"
    summary_dir.mkdir()
    samples_dir.mkdir()
    groups = sorted({(row["key_bits"], row["n"]) for row in summaries})
    result_files = []
    for bits, n in groups:
        summary_path = summary_dir / f"b{bits}_n{n}.csv"
        sample_path = samples_dir / f"b{bits}_n{n}.csv"
        write_csv(summary_path, [row for row in summaries if row["key_bits"] == bits and row["n"] == n])
        write_csv(sample_path, [row for row in raw if row["key_bits"] == bits and row["n"] == n])
        result_files.extend([str(summary_path.relative_to(output)), str(sample_path.relative_to(output))])

    validation_doc = {
        "all_passed": True,
        "checks": validation,
        "unique_input_arrays": 24000,
        "dataset_content_hashes": dataset_hashes,
        "dataset_hashes_match_declared_corpus": dataset_hashes == EXPECTED_DATASET_HASHES,
        "note": "The same numerical arrays are checked once per storage dtype; these are not independent new inputs.",
    }
    (output / "validation.json").write_text(json.dumps(validation_doc, indent=2) + "\n", encoding="utf-8")

    source_sha256 = sha256_bytes(Path(__file__).read_bytes())
    metadata = {
        "run_id": output.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment(),
        "input_archive": str(args.input),
        "input_archive_sha256": input_archive_sha256,
        "dataset_hashes_match_declared_corpus": True,
        "benchmark_source_sha256": source_sha256,
        "baseline": "NumPy stable argsort + take_along_axis",
        "input_storage_dtypes": args.dtypes,
        "index_dtype": str(np.dtype(np.intp)),
        "batch_sizes": args.batch_sizes,
        "repeats": args.repeats,
        "target_ms": args.target_ms,
        "warmup_passes": args.warmup_passes,
        "case_order_seed": args.seed,
        "measured_cases": len(cases),
        "raw_samples": len(raw),
        "result_files": result_files,
        "benchmark_elapsed_s": time.perf_counter() - started,
        "scope": "CPU application calls returning sorted keys and original indices; allocation and gather included",
        "excluded": "File loading, dtype conversion, input preparation, validation and result-file writing",
        "protocol": "Warm-cache repeated full-corpus passes; immutable inputs; GC disabled only during timing",
        "statistic": "Median across repeated mean batch times; IQR is repeat variation, not tail latency or a confidence interval",
        "limits": [
            "Platform-specific benchmark; not a universal CPU lower bound",
            "No GPU, NPU, photonic latency, device energy or photonic speedup measured",
            "NumPy library baseline, not a hand-optimized sorting kernel",
            "Amortized batch time per array is not isolated single-request latency",
        ],
        "units": "Physical seconds and throughput; separate from algorithmic complexity T/W/S/H/D",
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(cases)} cases and {len(raw)} timing samples to {output}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/inputs.npz")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/cpu_baseline_reproduced")
    parser.add_argument("--batch-sizes", nargs="+", type=int, default=[1, 10, 100, 1000])
    parser.add_argument("--dtypes", nargs="+", choices=["uint8", "int64"], default=["uint8", "int64"])
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--target-ms", type=float, default=15.0)
    parser.add_argument("--warmup-passes", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261107)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
