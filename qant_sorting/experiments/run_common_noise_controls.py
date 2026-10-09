# Reading guide: controlled experiments for common_noise_model.py.
# SETTINGS describes changes within one signal model, all with explicit assumed
# noise/rounding/offset values. Pair controls run first, selected full sorts second.
# Direct and ideal-sine variants share standard-normal samples to isolate the
# transfer's effect; these paired outputs are not independent observations.
# The saved subset is the FIRST requested rows of six existing datasets, not a
# new random corpus or the old full 1,000-trial result relabelled as a new run.
# No SDK, NPU, hardware timing, or incomplete-archive recovery is involved here.
# Result hashes describe the code that produced them; adding comments changes
# future source hashes without changing old numerical evidence.

"""Small reproducible controls for the common model; no SDK/hardware required."""
from qant_sorting.io import file_hash, write_csv

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.special import ndtr

from qant_sorting.common_noise_model import NoiseConfig, CommonNoiseComparison, evaluate_difference, transfer_value, ALPHA
from qant_sorting.ranking_quality import prepare_keys, score_saved_order
from qant_sorting.sorting_schedules import bitonic_sort, rank_sort

from qant_sorting.paths import ROOT, INPUT_SHA256 as INPUT_SHA
SEED = 20261007
# Controlled changes within ONE model. Every numeric noise/drift setting is assumed.
SETTINGS = {
    "no_noise": {},
    "prequantized_control": dict(upstream_sigma_lsb=.25, pre_step_lsb=1, post_step_lsb=0),
    "upstream_only": dict(upstream_sigma_lsb=.25),
    "readout_only": dict(readout_sigma_lsb=.25),
    "combined": dict(upstream_sigma_lsb=.25, readout_sigma_lsb=.25),
    "fine_output": dict(upstream_sigma_lsb=.25, readout_sigma_lsb=.25, post_step_lsb=.5),
    "coarse_output": dict(upstream_sigma_lsb=.25, readout_sigma_lsb=.25, post_step_lsb=2),
    "no_output_quantizer": dict(readout_sigma_lsb=.25, post_step_lsb=0),
    "positive_offset": dict(upstream_sigma_lsb=.25, readout_sigma_lsb=.25, output_drift_lsb=.25),
    "negative_offset": dict(upstream_sigma_lsb=.25, readout_sigma_lsb=.25, output_drift_lsb=-.25),
}
SORT_SETTINGS = ("no_noise", "prequantized_control", "upstream_only", "combined", "coarse_output", "positive_offset")


# Return (probabilities [negative,zero,positive], clipping_error_bound) when
# the configured case has the implemented closed form; otherwise return None.
# Treat rounding as a zero-code interval, not as an added independent variance.
# For direct mixed Gaussian noise use summed variances; where omitted input
# clipping can matter, bound the error by the clipped-tail probability.
# For monotone sine with upstream-only noise invert the decision threshold.
# For sine with both stochastic stages do not pretend the output remains Gaussian.
# Deterministic sigma=0 cases are evaluated exactly, including halfway rounding.
def analytic_probabilities(d, config):
    """Exact negative/zero/positive probabilities for tractable controls.

    With post-noise and input clipping, the direct Gaussian sum omits the
    input-tail event. Return that probability as an explicit error bound.
    Mixed nonlinear noise is left blank rather than treated as Gaussian.
    """
    c = config
    delta = c.delta
    if c.gain_error != 0 or c.input_drift_lsb != 0 or c.output_drift_lsb != 0:
        return None
    bound = 0.0
    if c.pre_step_lsb and not c.readout_sigma_lsb and not c.post_step_lsb:
        mean, sigma, threshold = d, c.upstream_sigma_lsb*delta, c.pre_step_lsb*delta/2
    elif not c.pre_step_lsb and c.transfer == "direct":
        mean = d
        sigma = np.hypot(c.upstream_sigma_lsb, c.readout_sigma_lsb)*delta
        threshold = c.post_step_lsb*delta/2
        su = c.upstream_sigma_lsb*delta
        if su and c.readout_sigma_lsb:
            bound = float(ndtr((-1-d)/su) + ndtr((d-1)/su))
    elif not c.pre_step_lsb and not c.upstream_sigma_lsb:
        mean = float(transfer_value(d, c.transfer))
        sigma, threshold = c.readout_sigma_lsb*delta, c.post_step_lsb*delta/2
    elif not c.pre_step_lsb and not c.readout_sigma_lsb:
        threshold = c.post_step_lsb*delta/2
        if ALPHA*threshold >= 1:
            return None
        mean, sigma = d, c.upstream_sigma_lsb*delta
        threshold = np.arcsin(ALPHA*threshold)/ALPHA
    else:
        return None
    if sigma == 0:
        measured, _ = evaluate_difference([d], c)
        return np.array([measured[0] < 0, measured[0] == 0, measured[0] > 0], dtype=float), 0.0
    negative = float(ndtr((-threshold-mean)/sigma))
    positive = float(ndtr((mean-threshold)/sigma))
    zero = max(0.0, 1-negative-positive)
    return np.array([negative, zero, positive]), bound


# Input sample counts and a fresh output path. Verify fixed corpus identity
# and save hashes of source code plus the archived CPU calibration reference.
# Pair controls compare shared samples with analytical probabilities where known;
# failure tolerance includes sampling error and any explicit clipping bound.
# Then run selected original datasets through both schedules and score saved
# orders with the independent ranking-quality module. Persist indices and flags.
# No-noise correctness and prequantized direct/sine identity are required checks.
# Output counts include paired controls, not that many independent device trials.
def run(args):
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Use an empty output directory to preserve prior evidence")
    if args.pair_samples < 10000 or not 1 <= args.sort_trials <= 1000:
        raise ValueError("Need >=10000 pair samples and 1..1000 sort trials")
    source_names = ("qant_sorting/common_noise_model.py", "qant_sorting/experiments/run_common_noise_controls.py", "qant_sorting/ranking_quality.py",
                    "qant_sorting/sorting_schedules.py", "qant_sorting/io.py", "qant_sorting/paths.py",
                    "data/inputs.npz", "results/periodic/pair_checks.json")
    before = {name: file_hash(ROOT/name) for name in source_names}
    if before["data/inputs.npz"] != INPUT_SHA:
        raise ValueError("Unexpected saved corpus")
    # Stage 1: small pair controls establish signal margins and probability checks
    # before any complete array is sorted. Absolute key gaps include equality,
    # neighbours and both full-range extremes.
    pair_rows, scale_rows, quality_rows, saved = [], [], [], {}
    checked = control_pairs = 0
    for bits in (4, 8):
        delta = 2.0**(-bits)
        raw_margin = np.sin(ALPHA*delta)
        scale_rows.append(dict(bits=bits, delta=delta, legacy_sigma=.25*delta,
            legacy_direct_zero_margin_sigma=4.0, legacy_rounding_boundary_margin_sigma=2.0,
            legacy_ideal_sine_zero_margin_sigma=raw_margin/(.25*delta),
            normalized_sine_nearest_margin=raw_margin/ALPHA,
            normalized_sine_zero_margin_sigma=raw_margin/ALPHA/(.25*delta),
            upstream_false_tie_probability=float(ndtr(-2)-ndtr(-6)),
            upstream_sign_reversal_probability=float(ndtr(-6)),
            true_tie_broken_probability=float(2*ndtr(-2))))
        gaps = [-(2**bits-1), -2, -1, 0, 1, 2, 2**bits-1]
        for setting_index, (name, parameters) in enumerate(SETTINGS.items()):
            for gap in gaps:
                rng = np.random.default_rng(np.random.SeedSequence([SEED, 3, bits, setting_index, gap+256]))
                # Draw each stochastic stage once for this case, then reuse those samples for
                # both transfer functions. This isolates the transfer difference without adding
                # unrelated Monte Carlo variation between the paired variants.
                zu, zr = rng.standard_normal((2, args.pair_samples))
                decisions = []
                for kind in ("direct", "ideal_sine"):
                    c = NoiseConfig(bits, transfer=kind, **parameters)
                    value, diag = evaluate_difference(gap*delta, c, zu, zr)
                    counts = np.array([np.count_nonzero(value < 0), np.count_nonzero(value == 0),
                                       np.count_nonzero(value > 0)])
                    decisions.append(np.sign(value))
                    row = dict(bits=bits, setting=name, transfer=kind, signed_gap=gap,
                        trials=args.pair_samples, negative=int(counts[0]), zero=int(counts[1]), positive=int(counts[2]),
                        **diag, analytic_negative=None, analytic_zero=None, analytic_positive=None,
                        analytic_clipping_error_bound=None, analytic_check=None)
                    analytical = analytic_probabilities(gap*delta, c)
                    if analytical is not None:
                        probabilities, bound = analytical
                        observed = counts / args.pair_samples
                        tolerance = 6*np.sqrt(probabilities*(1-probabilities)/args.pair_samples) + 5/args.pair_samples + bound
                        passed = bool(np.all(np.abs(observed-probabilities) <= tolerance))
                        row.update(zip(("analytic_negative", "analytic_zero", "analytic_positive"), probabilities))
                        row.update(analytic_clipping_error_bound=bound, analytic_check=passed)
                        if not passed:
                            raise AssertionError(f"Analytic probability check failed: {row}")
                        checked += 1
                    pair_rows.append(row)
                if name == "prequantized_control":
                    np.testing.assert_array_equal(*decisions)
                    control_pairs += args.pair_samples
    # Stage 2: use a predeclared small subset of existing arrays. The six settings
    # exercise noiseless behavior, intermediate/output rounding, combined noise and
    # a fixed offset; this is model validation rather than a calibrated hardware sweep.
    with np.load(ROOT/"data/inputs.npz", allow_pickle=False) as corpus:
        datasets = [name for name in corpus.files if "_n16_" in name or "_n256_" in name]
        matched_sorts = 0
        for dataset_index, dataset in enumerate(datasets):
            bits = int(dataset.split("_")[0][1:])
            keys = corpus[dataset][:args.sort_trials]
            prepared = prepare_keys(keys, bits)
            n = keys.shape[1]
            for name in SORT_SETTINGS:
                for mapping_index, (mapping, sorter) in enumerate((("bitonic", bitonic_sort), ("rank", rank_sort))):
                    orders = []
                    for kind in ("direct", "ideal_sine"):
                        c = NoiseConfig(bits, kind, **SETTINGS[name])
                        comparator = CommonNoiseComparison(c, range(len(keys)), (SEED, 3, dataset_index, mapping_index))
                        _, order, validity = sorter(keys, comparator)
                        metrics = score_saved_order(prepared, order, [1, min(10, n), n])
                        np.testing.assert_array_equal(validity, metrics["flags"][:, 0])
                        orders.append(order)
                        valid, correct, stable = metrics["flags"].sum(axis=0).tolist()
                        tau = metrics["tau_b"]
                        tau_normalized = metrics["tau_key_normalized"]
                        # Quality reporting conditions tau and one recall mean on valid permutations.
                        # Also save a separately named all-trial recall with invalid outputs valued zero,
                        # so a high conditional score cannot conceal rank-placement failures.
                        recall = metrics["recall"][min(10,n)]["tie_neutral"]
                        inv = metrics["distance_inversions"]
                        pair_den = metrics["distance_pairs"]
                        row = dict(dataset=dataset, bits=bits, n=n, setting=name, transfer=kind, mapping=mapping,
                            trials=len(keys), valid=valid, correct=correct, stable=stable,
                            tau_b_defined=int(np.isfinite(tau).sum()),
                            tau_b_mean_valid=float(np.nanmean(tau)) if np.isfinite(tau).any() else None,
                            tau_key_mean_valid=float(np.nanmean(tau_normalized)) if np.isfinite(tau_normalized).any() else None,
                            recall_k=min(10,n), recall_tie_neutral_mean_valid=float(np.nanmean(recall)) if valid else None,
                            recall_tie_neutral_mean_all_invalid_zero=float(np.nansum(recall)/len(keys)),
                            inversions_gap1=int(inv[1]), pairs_gap1_valid=int(pair_den[1]),
                            inversions_gap2=int(inv[2]), pairs_gap2_valid=int(pair_den[2]),
                            inversions_gap3plus=int(inv[3:].sum()), pairs_gap3plus_valid=int(pair_den[3:].sum()),
                            **comparator.counts)
                        quality_rows.append(row)
                        case = f"{dataset}_{name}_{mapping}_{kind}"
                        saved[case+"_indices"] = order.astype(np.int16)
                        saved[case+"_flags"] = metrics["flags"]
                        if name == "no_noise" and (valid, correct, stable) != (len(keys),)*3:
                            raise AssertionError("Noiseless sort failed")
                    if name == "prequantized_control":
                        np.testing.assert_array_equal(*orders)
                        matched_sorts += len(keys)
    after = {name: file_hash(ROOT/name) for name in source_names}
    if after != before:
        raise AssertionError("Sources changed during evaluation")
    write_csv(out/"signal_scales.csv", scale_rows)
    write_csv(out/"pair_controls.csv", pair_rows)
    write_csv(out/"sort_quality.csv", quality_rows)
    np.savez_compressed(out/"sort_outputs.npz", **saved)
    validation = dict(analytic_probability_cases_passed=checked, pair_cases=len(pair_rows),
        pair_decisions=sum(row["trials"] for row in pair_rows),
        prequantized_identical_paired_decisions=control_pairs,
        sort_cases=len(quality_rows), sort_runs=sum(row["trials"] for row in quality_rows),
        prequantized_identical_paired_sort_outputs=matched_sorts,
        noiseless_sort_cases_passed=sum(row["setting"] == "no_noise" for row in quality_rows),
        source_hashes_unchanged=True,
        note="Synthetic Float64 controls, not SDK executions or Q.ANT measurements.")
    (out/"validation.json").write_text(json.dumps(validation, indent=2)+"\n")
    metadata = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__, seed=SEED,
        pair_samples_per_case=args.pair_samples, first_saved_trials_per_dataset=args.sort_trials,
        sort_datasets=datasets, settings={name: asdict(NoiseConfig(8, **p)) for name,p in SETTINGS.items()},
        setting_note="bits=8 is an example; run covers 4 and 8, both transfers. All noise/drift settings are assumptions.",
        source_sha256=before,
        output_sha256={p.name:file_hash(p) for p in out.iterdir()},
        random_pairing="Transfer variants share standard-normal samples. Stages/trials independent; drift fixed.",
        exclusions=["physical tcos/BF16", "measured receiver parameters", "time/channel covariance calibration", "hardware timing/energy"])
    (out/"metadata.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"results/common_noise_reproduced")
    parser.add_argument("--pair-samples", type=int, default=100000)
    parser.add_argument("--sort-trials", type=int, default=100)
    run(parser.parse_args())
