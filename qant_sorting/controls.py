"""Check how noise location, transfer shape and quantization affect comparisons.

Run: python -m qant_sorting.controls
The pair checks come first, then selected complete sorts. These are assumed
Float64 noise controls; this command does not execute the SDK or hardware.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.special import ndtr

from qant_sorting.common_noise import (
    ALPHA, CommonNoiseComparison, NoiseConfig, evaluate_difference, transfer_value,
)
from qant_sorting.evaluation import prepare_keys, score_saved_order
from qant_sorting.run import ROOT, INPUT_SHA256, file_hash, write_csv
from qant_sorting.sorters import bitonic_sort, rank_sort


SEED = 20261007
# Change one or more modeled effects at a time. Values are not hardware measurements.
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
SORT_SETTINGS = (
    "no_noise", "prequantized_control", "upstream_only",
    "combined", "coarse_output", "positive_offset",
)


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
        mean = d
        sigma = c.upstream_sigma_lsb * delta
        threshold = c.pre_step_lsb * delta / 2
    elif not c.pre_step_lsb and c.transfer == "direct":
        mean = d
        sigma = np.hypot(c.upstream_sigma_lsb, c.readout_sigma_lsb) * delta
        threshold = c.post_step_lsb * delta / 2
        su = c.upstream_sigma_lsb * delta
        if su and c.readout_sigma_lsb:
            bound = float(ndtr((-1 - d) / su) + ndtr((d - 1) / su))
    elif not c.pre_step_lsb and not c.upstream_sigma_lsb:
        mean = float(transfer_value(d, c.transfer))
        sigma = c.readout_sigma_lsb * delta
        threshold = c.post_step_lsb * delta / 2
    elif not c.pre_step_lsb and not c.readout_sigma_lsb:
        threshold = c.post_step_lsb * delta / 2
        if ALPHA * threshold >= 1:
            return None
        mean, sigma = d, c.upstream_sigma_lsb * delta
        threshold = np.arcsin(ALPHA * threshold) / ALPHA
    else:
        return None
    if sigma == 0:
        measured, _ = evaluate_difference([d], c)
        probabilities = np.array(
            [measured[0] < 0, measured[0] == 0, measured[0] > 0], dtype=float,
        )
        return probabilities, 0.0
    negative = float(ndtr((-threshold - mean) / sigma))
    positive = float(ndtr((mean - threshold) / sigma))
    zero = max(0.0, 1 - negative - positive)
    return np.array([negative, zero, positive]), bound


def run_pair_controls(pair_samples):
    """Compare sampled signs with analytical probabilities for each setting.

    Both transfer variants receive the same two standard-normal sample arrays.
    This isolates the transfer change instead of adding unrelated sampling error.
    """
    pair_rows, scale_rows = [], []
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
                rng = np.random.default_rng(np.random.SeedSequence(
                    [SEED, 3, bits, setting_index, gap + 256]
                ))
                # Draw each stochastic stage once for this case, then reuse those samples for
                # both transfer functions. This isolates the transfer difference without adding
                # unrelated Monte Carlo variation between the paired variants.
                zu, zr = rng.standard_normal((2, pair_samples))
                decisions = []
                for kind in ("direct", "ideal_sine"):
                    c = NoiseConfig(bits, transfer=kind, **parameters)
                    value, diag = evaluate_difference(gap*delta, c, zu, zr)
                    counts = np.array([
                        np.count_nonzero(value < 0),
                        np.count_nonzero(value == 0),
                        np.count_nonzero(value > 0),
                    ])
                    decisions.append(np.sign(value))
                    row = dict(bits=bits, setting=name, transfer=kind, signed_gap=gap,
                        trials=pair_samples, negative=int(counts[0]), zero=int(counts[1]), positive=int(counts[2]),
                        **diag, analytic_negative=None, analytic_zero=None, analytic_positive=None,
                        analytic_clipping_error_bound=None, analytic_check=None)
                    analytical = analytic_probabilities(gap*delta, c)
                    if analytical is not None:
                        probabilities, bound = analytical
                        observed = counts / pair_samples
                        tolerance = (
                            6*np.sqrt(probabilities*(1-probabilities)/pair_samples)
                            + 5/pair_samples + bound
                        )
                        passed = bool(np.all(np.abs(observed-probabilities) <= tolerance))
                        row.update(zip(
                            ("analytic_negative", "analytic_zero", "analytic_positive"),
                            probabilities,
                        ))
                        row.update(analytic_clipping_error_bound=bound, analytic_check=passed)
                        if not passed:
                            raise AssertionError(f"Analytic probability check failed: {row}")
                        checked += 1
                    pair_rows.append(row)
                if name == "prequantized_control":
                    np.testing.assert_array_equal(*decisions)
                    control_pairs += pair_samples
    return pair_rows, scale_rows, checked, control_pairs


def run_sort_controls(sort_trials):
    """Run selected settings on the first rows of the fixed input datasets.

    Rank uses direct differences because its bias is expressed in difference
    units. Bitonic also tests the ideal-sine transfer through the same interface.
    """
    quality_rows, saved = [], {}
    with np.load(ROOT/"data/inputs.npz", allow_pickle=False) as corpus:
        datasets = [name for name in corpus.files if "_n16_" in name or "_n256_" in name]
        matched_sorts = 0
        for dataset_index, dataset in enumerate(datasets):
            bits = int(dataset.split("_")[0][1:])
            keys = corpus[dataset][:sort_trials]
            prepared = prepare_keys(keys, bits)
            n = keys.shape[1]
            for name in SORT_SETTINGS:
                for mapping_index, (mapping, sorter) in enumerate(
                    (("bitonic", bitonic_sort), ("rank", rank_sort))
                ):
                    orders = []
                    for kind in (("direct",) if mapping == "rank" else ("direct", "ideal_sine")):
                        c = NoiseConfig(bits, kind, **SETTINGS[name])
                        comparator = CommonNoiseComparison(
                            c, range(len(keys)), (SEED, 3, dataset_index, mapping_index)
                        )
                        if mapping == "rank":
                            _, order, validity = rank_sort(keys, comparator, bias_step=c.delta)
                        else:
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
                    if name == "prequantized_control" and mapping == "bitonic":
                        np.testing.assert_array_equal(*orders)
                        matched_sorts += len(keys)
    return quality_rows, saved, datasets, matched_sorts


def run(args):
    """Prepare a fresh output folder, run both stages and save their evidence."""
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Use an empty output directory to preserve prior evidence")
    if args.pair_samples < 10000 or not 1 <= args.sort_trials <= 1000:
        raise ValueError("Need >=10000 pair samples and 1..1000 sort trials")

    source_names = (
        "qant_sorting/common_noise.py", "qant_sorting/controls.py",
        "qant_sorting/evaluation.py", "qant_sorting/sorters.py",
        "qant_sorting/comparison.py", "qant_sorting/run.py", "data/inputs.npz",
    )
    before = {name: file_hash(ROOT / name) for name in source_names}
    if before["data/inputs.npz"] != INPUT_SHA256:
        raise ValueError("Unexpected saved corpus")

    # Stage 1 checks the comparison channel; stage 2 measures complete sorts.
    pair_rows, scale_rows, checked, control_pairs = run_pair_controls(args.pair_samples)
    quality_rows, saved, datasets, matched_sorts = run_sort_controls(args.sort_trials)

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
        random_pairing="Bitonic and pair transfer variants share samples. Full-matrix rank uses direct differences only, independent cell/stage/trial errors including diagonal; drift fixed.",
        exclusions=["physical tcos/BF16", "measured receiver parameters", "time/channel covariance calibration", "hardware timing/energy"])
    (out/"metadata.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(validation, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/common_noise_reproduced")
    parser.add_argument("--pair-samples", type=int, default=100000)
    parser.add_argument("--sort-trials", type=int, default=100)
    run(parser.parse_args(argv))


if __name__ == "__main__":
    main()
