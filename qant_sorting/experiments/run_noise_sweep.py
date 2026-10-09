# Reading guide: exact reproduction of the CURRENT matched-step reference.
# The immutable input archive supplies keys; this runner does not regenerate them.
# Each dataset is evaluated at six noise levels with both sorting schedules.
# Noise streams are identified by experimental settings and absolute trial IDs,
# so batch_size changes memory use/API grouping without changing the experiment.
# Positive eta values scale paired random draws; architecture streams differ.
# Outputs include per-trial record indices, three flags, summary rows, and one
# counterexample per failed case. verify_results checks numerical identity.
# The protected reference path is rejected, but other existing output files can
# be overwritten; choose a fresh result directory for a separate research run.

"""Reproduce the agreed six-level experiment using only NumPy.

Run: python -m qant_sorting noise
The saved reference is never overwritten. Every result is checked against it.
No SDK, NPU, digital repair, repeated comparison or new noise rule is used.
"""

from qant_sorting.io import source_hashes, write_csv

import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.input_validation import validate_keys
from qant_sorting.metrics import reference_flags, wilson_interval
from qant_sorting.experiments.verify_results import REFERENCE, verify_results

from qant_sorting.paths import ROOT, INPUT_SHA256
from qant_sorting.experiments.settings import ETA_VALUES, MASTER_SEED, MAPPINGS


# Inputs specify one dataset/precision/eta/sorter/seed context and batch size.
# For each chunk use absolute row IDs, run the sorter, independently score flags,
# and accumulate the comparator's event counters over every active layer.
# Return (flags, original_indices, totals, first_failure) concatenated in input order.
# The counterexample stores actual routed keys and indices; the complete index
# archive plus original inputs suffices to reconstruct every output ordering.
def evaluate_case(data, precision, eta, sort, seed_context, batch_size):
    """Evaluate one width/N/family/noise/mapping condition in small batches."""
    totals = dict.fromkeys(NoisyDifference.counter_names, 0)
    flags, indices = [], []
    first_failure = None
    for start in range(0, len(data), batch_size):
        stop = min(start + batch_size, len(data))
        batch = data[start:stop]
        difference = NoisyDifference(precision, eta, seed_context, range(start, stop))
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


# Input output Path and positive batch size. Refuse the immutable reference
# directory and require the registered input archive hash before any experiment.
# Loop over saved datasets, six eta values and two schedules; verify pair counts
# from their analytical formulas and require all noiseless flags to pass.
# Write accuracy, per-trial outcomes, first failures, validation and provenance.
# verify_results must confirm exact reference outcomes; differing source hashes
# after comments are expected, but numerical evidence may not silently change.
def run(output_directory, batch_size):
    """Use saved inputs and seeds, write evidence, and verify exact reproduction."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    output_directory = output_directory.resolve()
    if output_directory == REFERENCE.resolve():
        raise ValueError("Choose a separate output directory; the reference is immutable")
    output_directory.mkdir(parents=True, exist_ok=True)
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
                    expected_pairs = n * m * (m + 1) // 4 if stream_id == 1 else n * (n - 1) // 2
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

    # Refactoring is accepted only if all previously reported outcomes match.
    validation = verify_results(output_directory)
    (output_directory / "validation.json").write_text(json.dumps(validation, indent=2))
    metadata = dict(
        revision="documented_noise_sweep_20261004",
        rows=len(rows), executions=sum(row["trials"] for row in rows),
        input_master_seed=MASTER_SEED, eta_values=list(ETA_VALUES),
        batch_size=batch_size, inputs_sha256=INPUT_SHA256,
        python=platform.python_version(), numpy=np.__version__,
        elapsed_seconds=time.perf_counter() - started,
        hardware_executed=False, sdk_noise_model=False,
        noise="Independent Gaussian draws per comparison and between mappings; paired streams across positive eta levels.",
        timing="Run duration only; not a hardware latency or sorting performance benchmark.",
        source_sha256=source_hashes(),
        **validation,
    )
    (output_directory / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Verified {len(rows)} configurations, {metadata['executions']:,} executions.")
    print(f"Results: {output_directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/reproduced")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    run(args.output_dir, args.batch_size)
