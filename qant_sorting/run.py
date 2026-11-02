"""Run the main Bitonic-versus-rank noise experiment.

Start with evaluate_case() to follow one batch, then run() for the full sweep.
Run from the repository root: python -m qant_sorting.run
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from qant_sorting.comparison import NoisyDifference, Precision, validate_keys
from qant_sorting.evaluation import reference_flags, wilson_interval
from qant_sorting.sorters import bitonic_sort, rank_sort


# These settings define the saved reference experiment.
ROOT = Path(__file__).resolve().parents[1]
INPUT_SHA256 = "79efbd1ee270242cc122d8f9e1848fe07a85077bcf310324b27dd60f8faf11da"
REFERENCE = ROOT / "results/reference"
ETA_VALUES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25)
MASTER_SEED = 20260930
MAPPINGS = {
    "Pipelined bitonic adaptation": (bitonic_sort, 1),
    # Keep the label used by the saved experiment.
    "Louri full-matrix rank": (rank_sort, 2),
}


def file_hash(path):
    """Return SHA-256 without loading an entire result archive into memory."""
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_csv(path, rows):
    """Write nonempty record rows in their original field order, using UTF-8."""
    if not rows:
        raise ValueError("Cannot infer CSV columns from an empty record list")
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_hashes():
    """Record the code used by a new run; leave old metadata unchanged."""
    hashes = {}
    for directory in ("qant_sorting", "studies", "tools"):
        for path in sorted((ROOT / directory).rglob("*.py")):
            hashes[str(path.relative_to(ROOT))] = file_hash(path)
    return hashes


def evaluate_case(data, precision, eta, sort, seed_context, batch_size):
    """Evaluate one width/N/family/noise/mapping condition in small batches."""
    if sort is rank_sort:
        batch_size = min(batch_size, max(1, 1_000_000 // data.shape[1]**2))
    totals = dict.fromkeys(NoisyDifference.counter_names, 0)
    flags, indices = [], []
    first_failure = None
    for start in range(0, len(data), batch_size):
        stop = min(start + batch_size, len(data))
        batch = data[start:stop]
        difference = NoisyDifference(precision, eta, seed_context, range(start, stop))
        if sort is rank_sort:
            result = rank_sort(batch, difference, bias_step=precision.delta_in)
        else:
            result = sort(batch, difference)
        batch_flags = reference_flags(batch, result)
        flags.append(batch_flags)
        indices.append(result[1])
        for name in totals:
            totals[name] += getattr(difference, name)

        # Save a concrete counterexample without storing every output twice:
        # all record indices are retained in NPZ; the original keys are saved.
        if first_failure is None and np.any(~batch_flags[:, 1]):
            i = int(np.flatnonzero(~batch_flags[:, 1])[0])
            first_failure = {
                "trial_index": start + i,
                "input": batch[i].tolist(),
                "output": result[0][i].tolist(),
                "indices": result[1][i].tolist(),
                "valid": bool(batch_flags[i, 0]),
            }
    return np.concatenate(flags), np.concatenate(indices), totals, first_failure


def run(output_directory, batch_size):
    """Evaluate the saved inputs, check each run, and write the results."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    output_directory = output_directory.resolve()
    if output_directory == REFERENCE.resolve() and REFERENCE.exists():
        raise ValueError("Choose a separate output directory; the reference is immutable")
    output_directory.mkdir(parents=True, exist_ok=True)
    if any(output_directory.iterdir()):
        raise ValueError("Use an empty output directory")
    input_path = ROOT / "data/inputs.npz"
    if hashlib.sha256(input_path.read_bytes()).hexdigest() != INPUT_SHA256:
        raise ValueError("Saved input corpus checksum differs from the agreed experiment")

    started = time.perf_counter()
    rows, saved, failures = [], {}, []
    with np.load(input_path) as corpus:
        for dataset in corpus.files:
            bit_tag, n_tag, family = dataset.split("_", 2)
            bits, n = int(bit_tag[1:]), int(n_tag[1:])
            precision = Precision(key_bits=bits, input_bits=bits, output_bits=bits)
            data = validate_keys(corpus[dataset], bits)
            family_id = 0 if family == "distinct" else 1
            for eta in ETA_VALUES:
                for name, (sort, stream_id) in MAPPINGS.items():
                    # Keep the original streams. Positive eta values reuse
                    # the same draws, scaled in strength. Between mappings,
                    # stream_id provides independent random streams.
                    mode_id = 1 if eta == 0 else 2
                    context = [MASTER_SEED, bits, bits, bits, n, family_id, mode_id, stream_id]
                    flags, indices, totals, first = evaluate_case(
                        data, precision, eta, sort, context, batch_size
                    )
                    counts = flags.sum(axis=0).astype(int)
                    low, high = wilson_interval(int(counts[1]), len(data))
                    row = dict(
                        mapping=name, key_bits=precision.key_bits,
                        input_bits=precision.input_bits, output_bits=precision.output_bits,
                        n=n, family=family, eta=eta,
                        delta_in=precision.delta_in, delta_out=precision.delta_out,
                        sigma=eta * precision.delta_out, trials=len(data),
                        valid_outputs=int(counts[0]), correct_sorts=int(counts[1]),
                        stable_sorts=int(counts[2]), accuracy=float(counts[1] / len(data)),
                        ci95_low=low, ci95_high=high,
                        invalid_outputs=int(len(data) - counts[0]), **totals,
                        seed_context=json.dumps(context),
                        input_sha256=hashlib.sha256(data.tobytes()).hexdigest(),
                    )

                    # Counts independently check the active comparison schedule.
                    m = n.bit_length() - 1
                    expected_pairs = n * m * (m + 1) // 4 if stream_id == 1 else n * n
                    if totals["comparisons"] != len(data) * expected_pairs:
                        raise AssertionError("Comparison count differs from the algorithm")
                    if eta == 0 and not flags.all():
                        raise AssertionError("A noiseless sort failed")

                    noise_tag = "zero" if eta == 0 else f"noise{round(eta * 100):03d}"
                    mapping_tag = "bitonic" if stream_id == 1 else "rank"
                    case = f"{dataset}_{noise_tag}_{mapping_tag}"
                    saved[case + "_flags"] = flags
                    # -1 is the invalid marker; all valid indices fit in int16.
                    saved[case + "_indices"] = indices.astype(np.int16)
                    if first:
                        failures.append(dict(case=case, **first))
                    rows.append(row)
            print(f"{dataset}: complete", flush=True)

    write_csv(output_directory / "accuracy.csv", rows)
    np.savez_compressed(output_directory / "trial_outcomes.npz", **saved)
    (output_directory / "failures.json").write_text(json.dumps(failures, indent=2))

    # These checks were performed above using this run's inputs and outputs.
    validation = dict(
        configurations=len(rows),
        comparison_counts_checked=True,
        noiseless_outputs_valid_correct_stable=True,
        noiseless_sort_executions=sum(r["trials"] for r in rows if r["eta"] == 0),
    )
    (output_directory / "validation.json").write_text(json.dumps(validation, indent=2))
    metadata = dict(
        revision="thesis_full_matrix_20261024",
        rank_algorithm="Full N*N rank matrix including measured diagonal",
        rank_bias="Subtract delta_in below diagonal AFTER output quantization; exact >=0 threshold and column sum",
        rows=len(rows), executions=sum(row["trials"] for row in rows),
        input_master_seed=MASTER_SEED, eta_values=list(ETA_VALUES),
        batch_size=batch_size, inputs_sha256=INPUT_SHA256,
        python=platform.python_version(), numpy=np.__version__,
        elapsed_seconds=time.perf_counter() - started,
        hardware_executed=False, sdk_noise_model=False,
        noise=(
            "Independent Gaussian draws for every directed matrix cell INCLUDING the diagonal "
            "and between mappings; paired streams across positive eta levels. "
            "Assumed, not physical calibration."
        ),
        timing="Run duration only; not a hardware latency or sorting performance benchmark.",
        source_sha256=source_hashes(),
        **validation,
    )
    (output_directory / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Completed {len(rows)} configurations, {metadata['executions']:,} executions.")
    print(f"Results: {output_directory}")


def main(argv=None):
    """Parse the two run options and start the evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/reproduced")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args(argv)
    run(args.output_dir, args.batch_size)


if __name__ == "__main__":
    main()
