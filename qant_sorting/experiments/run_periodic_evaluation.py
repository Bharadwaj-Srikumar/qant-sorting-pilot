# Reading guide: reproduce historical periodic CPU-SDK sorting scenarios.
# The raw corpus and reference outcomes are prerequisites; pair_checks.json
# supplies the optional fixed equality band. No true keys tune that band at run time.
# Each batch calls the SDK linear difference and then the periodic operation.
# Electronic routing follows each bitonic layer or the single rank-pair stage.
# Only upstream is required to match the original direct outcomes exactly.
# Output noise is in a different score scale; see common_noise_model.py for the
# later controlled model. Buffer counts are logical API data, not device timing.
# This script writes to its chosen directory and can replace existing files;
# use --output-dir with a fresh path when preserving an earlier run.

"""Run both sorters with the actual periodic SDK CPU operation.

Uses the unchanged 24,000 saved inputs and six eta values. The upstream
scenario is checked trial-by-trial against the previous reference outcomes.
The output scenario is an explicitly separate noise-location experiment.
Full-sort correctness and stable record order remain separate measurements.
"""
from qant_sorting.io import source_hashes, write_csv

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from qant_sorting.input_validation import validate_keys
from qant_sorting.metrics import reference_flags, wilson_interval
from qant_sorting.periodic_comparison import (
    PeriodicComparison, calibration_reference, require_cpu_backend,
)
from qant_sorting.experiments.settings import ETA_VALUES, MASTER_SEED, MAPPINGS

from qant_sorting.paths import ROOT, INPUT_SHA256


# Inputs: output Path, positive batch size, and requested historical scenarios.
# Require a CPU backend, immutable input hash, reference outcomes and CPU pair
# calibration file. Calibrate d=0 once, then derive optional fixed tie bands.
# Replay each case in chunks with persistent per-trial stream identities.
# Count both linear and periodic submissions and their public BF16 buffers;
# the separate one-time reference call is disclosed in metadata.
# Save complete flag/index outputs, row summaries and failure examples. This
# routine can overwrite matching names in output; use a fresh path for new runs.
def run(output, batch_size, scenarios=("upstream", "output")):
    identity = require_cpu_backend()
    if batch_size < 1:
        raise ValueError("batch-size must be positive")
    input_path = ROOT / "data/inputs.npz"
    if hashlib.sha256(input_path.read_bytes()).hexdigest() != INPUT_SHA256:
        raise ValueError("Saved inputs changed")
    output.mkdir(parents=True, exist_ok=True)
    reference = calibration_reference()
    pairs = json.loads((ROOT / "results/periodic/pair_checks.json").read_text())
    # The threshold is frozen from an exhaustive noiseless CPU calibration. It is
    # not fitted to these noisy sort outcomes and is not a measured hardware band.
    # Using half the minimum unequal margin balances two bounded-error distances.
    tie_bands = {r["bits"]: r["minimum_cpu_score_margin"] / 2
                 for r in pairs["rows"]}
    rows, saved, failures = [], {}, []
    baseline_matches = 0
    started = time.perf_counter()
    with np.load(input_path) as corpus, np.load(
        ROOT / "results/reference/trial_outcomes.npz"
    ) as baseline:
        for dataset in corpus.files:
            bit_tag, n_tag, family = dataset.split("_", 2)
            bits, n = int(bit_tag[1:]), int(n_tag[1:])
            data = validate_keys(corpus[dataset], bits)
            family_id = 0 if family == "distinct" else 1
            for scenario in scenarios:
                for eta in ETA_VALUES:
                    for name, (sort, stream_id) in MAPPINGS.items():
                        context = [MASTER_SEED, bits, bits, bits, n, family_id,
                                   1 if eta == 0 else 2, stream_id]
                        flags, indices = [], []
                        calls = pairs = feature_bytes = weight_bytes = return_bytes = 0
                        totals = dict(false_ties=0, sign_reversals=0,
                                      broken_true_ties=0, saturations=0)
                        first = None
                        for start in range(0, len(data), batch_size):
                            stop = min(start + batch_size, len(data))
                            batch = data[start:stop]
                            compare = PeriodicComparison(
                                bits, eta, "output" if scenario=="output_deadband" else scenario,
                                context, range(start, stop), reference,
                                tie_band=tie_bands[bits] if scenario=="output_deadband" else 0.0,
                            )
                            result = sort(batch, compare)
                            f = reference_flags(batch, result)
                            flags.append(f)
                            indices.append(result[1].astype(np.int16))
                            c = compare.difference.counts
                            calls += c.api_calls + compare.periodic_calls
                            pairs += c.pair_differences
                            # Actual public SDK buffers: linear + periodic.
                            feature_bytes += c.feature_bytes + 2 * c.pair_differences
                            weight_bytes += c.weight_bytes + 2 * c.pair_differences
                            return_bytes += c.output_bytes + 2 * c.pair_differences
                            for key in totals:
                                totals[key] += getattr(compare, key)
                            if first is None and np.any(~f[:, 1]):
                                i = int(np.flatnonzero(~f[:, 1])[0])
                                first = dict(trial=start+i, input=batch[i].tolist(),
                                             output=result[0][i].tolist(),
                                             flags=f[i].tolist())
                        f = np.concatenate(flags)
                        ind = np.concatenate(indices)
                        noise_tag = "zero" if eta == 0 else f"noise{round(eta*100):03d}"
                        mapping_tag = "bitonic" if stream_id == 1 else "rank"
                        case = f"{dataset}_{noise_tag}_{mapping_tag}"
                        # Identity check applies to the upstream protocol only. The output protocol
                        # changes both the disturbance location and fixed-rounding boundary; equal eta
                        # therefore does not make these two protocols physically matched.
                        if scenario == "upstream":
                            if not np.array_equal(f, baseline[case+"_flags"]) or not np.array_equal(ind, baseline[case+"_indices"]):
                                raise AssertionError(f"Upstream baseline mismatch: {case}")
                            baseline_matches += 1
                        if eta == 0 and not f.all():
                            raise AssertionError(f"Noiseless sort failed: {case}")
                        counts = f.sum(axis=0).astype(int)
                        low, high = wilson_interval(int(counts[1]), len(data))
                        rows.append(dict(
                            scenario=scenario, mapping=name, key_bits=bits,
                            tie_band=tie_bands[bits] if scenario=="output_deadband" else 0.0,
                            n=n, family=family, eta=eta, sigma=eta/2**bits,
                            noise_location="quantized difference" if scenario=="upstream" else "referenced periodic score",
                            score_precision="SDK BF16; host FP32 reference subtraction",
                            trials=len(data), correct_sorts=int(counts[1]),
                            stable_sorts=int(counts[2]), valid_outputs=int(counts[0]),
                            accuracy=float(counts[1]/len(data)),
                            stable_accuracy=float(counts[2]/len(data)),
                            ci95_low=low, ci95_high=high,
                            comparisons=pairs, sdk_calls=calls,
                            feature_bytes=feature_bytes, weight_bytes=weight_bytes,
                            output_bytes=return_bytes, **totals,
                            seed_context=json.dumps(context),
                        ))
                        saved[scenario+"_"+case+"_flags"] = f
                        # Save the exact output order for evidence and future checks.
                        saved[scenario+"_"+case+"_indices"] = ind
                        if first:
                            failures.append(dict(scenario=scenario, case=case, **first))
            print(f"{dataset}: both scenarios complete", flush=True)
    write_csv(output / "accuracy.csv", rows)
    np.savez_compressed(output / "trial_outcomes.npz", **saved)
    (output / "failures.json").write_text(json.dumps(failures, indent=2)+"\n")
    metadata = dict(
        sdk=identity, inputs_sha256=INPUT_SHA256, reference=reference,
        reference_calibration_calls=1, reference_buffer_bytes=6,
        rows=len(rows), executions=sum(r["trials"] for r in rows),
        upstream_cases_identical_to_baseline=baseline_matches,
        batch_size=batch_size, elapsed_seconds=time.perf_counter()-started,
        hardware_executed=False, noise_values=list(ETA_VALUES),
        sigma="eta/2**key_bits; location and units differ between scenarios",
        output_noise="NEW illustrative Gaussian score noise after SDK BF16 output, no extra quantizer",
        tie_band_policy="Optional output_deadband: half the minimum exhaustive CPU unequal-pair score margin",
        tie_bands=tie_bands, scenarios=list(scenarios),
        calibration_noise="Not modeled; fixed noiseless CPU reference",
        host_operations="Phase scaling/offset, reference subtraction, sign/ties, exchanges, rank sums, placement",
        transfers="Logical public API buffer bytes, not measured PCIe traffic",
        timing="Runtime only, not a hardware latency benchmark",
        source_sha256=source_hashes(),
    )
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/periodic_reproduced")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--scenario", choices=("both", "upstream", "output", "output_deadband"), default="both")
    args = parser.parse_args()
    scenarios = ("upstream", "output") if args.scenario=="both" else (args.scenario,)
    run(args.output_dir.resolve(), args.batch_size, scenarios)
