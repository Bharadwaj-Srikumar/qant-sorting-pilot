"""Reproduce source-equation checks and paired rank-noise sensitivity controls.

Read docs/LOURI_REFERENCE.md for the protocol and its physical limitations.
The default sweep uses the first 100 rows of six existing datasets. No input,
old result, or sorter is modified. A nonempty output directory is rejected.
"""
import argparse
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import platform

import numpy as np

from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.experiments.settings import ETA_VALUES
from qant_sorting.io import file_hash, source_hashes, write_csv
from qant_sorting.louri_reference import comparison_errors, louri_matrix_rank, quantize_difference
from qant_sorting.metrics import reference_flags, wilson_interval
from qant_sorting.paths import ROOT, INPUT_SHA256
from qant_sorting.ranking_quality import prepare_keys, score_saved_order
from qant_sorting.sorting_schedules import rank_sort

SEED = 20261024


def batches(keys, batch_size):
    """Bound full-matrix temporaries to approximately one million cells each."""
    step = min(batch_size, max(1, 1_000_000 // keys.shape[1]**2))
    for start in range(0, len(keys), step):
        yield start, keys[start:start+step]


def verify_noiseless(corpus, batch_size):
    """Compare source ranks and both outputs against independent stable argsort.

    Counts describe input arrays, each checked with raw source equations,
    matched quantization, and the existing unordered-pair implementation.
    Exhaustive four-record lists cover ties and nontrivial rank accumulation.
    The saved-corpus check uses ALL rows, regardless of --sort-trials.
    """
    cases = [
        ("all_4bit_ordered_pairs", 4, np.indices((16, 16)).reshape(2, -1).T),
        ("all_8bit_ordered_pairs", 8, np.indices((256, 256)).reshape(2, -1).T),
        ("all_4bit_four_record_lists", 4, np.indices((16,)*4).reshape(4, -1).T),
    ]
    cases.extend((name, int(name.split("_")[0][1:]), corpus[name]) for name in corpus.files)
    counts = {}
    for name, bits, raw in cases:
        for _, keys in batches(raw.astype(np.int64), batch_size):
            expected = np.argsort(keys, axis=1, kind="stable")
            expected_ranks = np.argsort(expected, axis=1) + 1
            adaptation = rank_sort(keys, NoisyDifference(Precision(bits, bits, bits)))
            np.testing.assert_array_equal(adaptation[1], expected)
            if not np.all(reference_flags(keys, adaptation)):
                raise AssertionError("Unordered noiseless flags failed")
            for quantization in ("none", "matched"):
                ref = louri_matrix_rank(keys, bits, quantization=quantization)
                np.testing.assert_array_equal(ref.ranks_one_based, expected_ranks)
                for a, b in zip(ref.result, adaptation):
                    np.testing.assert_array_equal(a, b)
        counts[name] = len(raw)
    return dict(arrays=sum(counts.values()), cases=counts, failures=0,
                checks_per_array=["raw source", "matched source", "existing unordered", "stable argsort"])


def finite_mean(values):
    """Undefined conditional quality stays empty in CSV, never silently zero."""
    values = np.asarray(values)
    finite = values[np.isfinite(values)]
    return float(finite.mean()) if len(finite) else None


def boundary_controls():
    """Check adjacent-key threshold probabilities against Gaussian integrals.

    For [1,0], the biased reverse cell has zero raw margin. With exact diagonal,
    raw antisymmetric correct probability is 1/2; independent is Phi(1/eta)/2.
    Matched rounding changes that margin to half a step. Correct probabilities
    become Phi(0.5/eta) and its square. The reverse valid order is also counted
    in validity, so validity is not silently equated with correctness.
    """
    eta, samples = .25, 100_000
    phi = lambda z: .5 * math.erfc(-z / math.sqrt(2))
    rows = []
    keys = np.tile([1, 0], (samples, 1))
    for bits in (4, 8):
        for coupling in ("antisymmetric", "independent"):
            _, errors = comparison_errors(2, bits, eta, range(samples), (SEED, 99, bits), coupling)
            for quantization in ("none", "matched"):
                if quantization == "none":
                    correct = .5 if coupling == "antisymmetric" else .5*phi(1/eta)
                    reversed_order = phi(-1/eta) * (1 if coupling == "antisymmetric" else .5)
                else:
                    power = 1 if coupling == "antisymmetric" else 2
                    correct, reversed_order = phi(.5/eta)**power, phi(-.5/eta)**power
                ref = louri_matrix_rank(keys, bits, errors=errors,
                                        quantization=quantization, diagonal="exact")
                valid_count, correct_count, _ = reference_flags(keys, ref.result).sum(axis=0).tolist()
                for observed, expected in ((correct_count/samples, correct),
                                           (valid_count/samples, correct+reversed_order)):
                    tolerance = 6*math.sqrt(expected*(1-expected)/samples) + 5/samples
                    if abs(observed-expected) > tolerance:
                        raise AssertionError("Adjacent-key Gaussian probability control failed")
                rows.append(dict(bits=bits, eta=eta, coupling=coupling, quantization=quantization,
                    diagonal="exact", input_keys="[1,0]", samples=samples,
                    valid=valid_count, correct=correct_count, analytic_correct=correct,
                    analytic_valid=correct+reversed_order, within_six_standard_errors=True))
    return rows


def summarize(keys, prepared, indices, info, saved, prefix, rows, distances, diagnostics=None):
    """Score original record identities; save enough output to rescore later."""
    quality = score_saved_order(prepared, indices, [1, min(10, keys.shape[1]), keys.shape[1]])
    flags = quality["flags"]
    counts = flags.sum(axis=0).tolist()
    row = dict(**info, trials=len(keys), valid=counts[0], correct=counts[1], stable=counts[2])
    for name, count in zip(("valid", "correct", "stable"), counts):
        lo, hi = wilson_interval(count, len(keys))
        row.update({name+"_wilson_low": lo, name+"_wilson_high": hi})
    recall = quality["recall"][min(10, keys.shape[1])]
    row.update(tau_defined=int(np.isfinite(quality["tau_b"]).sum()),
               tau_b_valid_mean=finite_mean(quality["tau_b"]),
               tau_key_valid_mean=finite_mean(quality["tau_key_normalized"]),
               recall10_stable_valid_mean=finite_mean(recall["stable"]),
               recall10_tie_neutral_valid_mean=finite_mean(recall["tie_neutral"]),
               recall10_tie_neutral_invalid_as_zero=float(np.nan_to_num(recall["tie_neutral"]).mean()))
    # One unordered decision always awards exactly one vote. Full-matrix cells
    # can award zero or two. These diagnostics precede any output validity filter.
    for name in ("pairs_both_zero", "pairs_both_one", "diagonal_failures", "vote_mismatches"):
        value = np.zeros(len(keys), dtype=np.int64) if diagnostics is None else diagnostics[name]
        row[name] = int(value.sum())
        saved[prefix+"__"+name] = value
    row["all_votes_match_unordered"] = (len(keys) if diagnostics is None else
        int(np.count_nonzero(diagnostics["vote_mismatches"] == 0)))
    rows.append(row)
    for field in ("flags", "inversions", "tau_b", "tau_key_normalized"):
        saved[prefix+"__"+field] = quality[field]
    saved[prefix+"__indices"] = indices
    saved[prefix+"__recall10_stable"] = recall["stable"]
    saved[prefix+"__recall10_tie_neutral"] = recall["tie_neutral"]
    for gap, denominator in enumerate(quality["distance_pairs"]):
        if denominator:
            distances.append(dict(**info, key_gap=gap, valid_output_pairs=int(denominator),
                                  inversions=int(quality["distance_inversions"][gap])))


def run(args):
    """Run paired models with declared covariance, diagonal and quantizer controls."""
    if not 1 <= args.sort_trials <= 1000 or args.batch_size < 1:
        raise ValueError("Use 1..1000 sort trials and a positive batch size")
    if file_hash(ROOT/"data/inputs.npz") != INPUT_SHA256:
        raise ValueError("The input corpus does not match its registered SHA-256")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Use an empty output directory to preserve prior evidence")
    before = source_hashes()
    rows, distances = [], []
    matched_trials = 0
    controls = boundary_controls()
    write_csv(out/"boundary_controls.csv", controls)
    with np.load(ROOT/"data/inputs.npz", allow_pickle=False) as corpus:
        verification = verify_noiseless(corpus, args.batch_size)
        print(f"Noiseless agreement: {verification['arrays']} arrays", flush=True)
        datasets = [name for name in corpus.files if "_n16_" in name or "_n256_" in name]
        for dataset_index, dataset in enumerate(datasets):
            bits = int(dataset.split("_")[0][1:])
            keys = corpus[dataset][:args.sort_trials].astype(np.int64)
            n = keys.shape[1]
            left, right = np.triu_indices(n, 1)
            prepared = prepare_keys(keys, bits)
            context = (SEED, dataset_index)
            saved = {"trial_ids": np.arange(len(keys))}
            for eta_index, eta in enumerate(ETA_VALUES):
                for quantization in ("none", "matched"):
                    outputs = []
                    matrix_outputs, matrix_ranks, matrix_diagnostics = {}, {}, {}
                    for coupling in ("antisymmetric", "independent"):
                        for diagonal in ("exact", "measured"):
                            key = (coupling, diagonal)
                            matrix_outputs[key], matrix_ranks[key] = [], []
                            matrix_diagnostics[key] = {name: [] for name in (
                                "pairs_both_zero", "pairs_both_one", "diagonal_failures", "vote_mismatches")}
                    for start, batch in batches(keys, args.batch_size):
                        ids = range(start, start+len(batch))
                        primary, _ = comparison_errors(n, bits, eta, ids, context, "antisymmetric")
                        measured = quantize_difference(
                            (batch[:, left]-batch[:, right])*2.**(-bits)+primary, bits, quantization)
                        triangular = rank_sort(batch, lambda a, b: measured)
                        outputs.append(triangular[1])
                        if quantization == "matched":
                            # Confirm this control really invokes the old numerical contract.
                            existing = rank_sort(batch, NoisyDifference(
                                Precision(bits, bits, bits), eta, context, ids))
                            for a, b in zip(existing, triangular):
                                np.testing.assert_array_equal(a, b)
                        wins = measured > 0
                        for coupling in ("antisymmetric", "independent"):
                            _, errors = comparison_errors(n, bits, eta, ids, context, coupling)
                            for diagonal in ("exact", "measured"):
                                key = (coupling, diagonal)
                                ref = louri_matrix_rank(batch, bits, errors=errors,
                                    quantization=quantization, diagonal=diagonal)
                                upper, lower = ref.threshold[:, left, right], ref.threshold[:, right, left]
                                self_failures = np.count_nonzero(~np.diagonal(ref.threshold, axis1=1, axis2=2), axis=1)
                                diagnostics = dict(
                                    pairs_both_zero=np.count_nonzero(~upper & ~lower, axis=1),
                                    pairs_both_one=np.count_nonzero(upper & lower, axis=1),
                                    diagonal_failures=self_failures,
                                    vote_mismatches=np.count_nonzero(upper != ~wins, axis=1)
                                      + np.count_nonzero(lower != wins, axis=1) + self_failures)
                                if quantization == "matched" and key == ("antisymmetric", "exact"):
                                    # Check ALL votes, including invalid/colliding output trials.
                                    if np.any(diagnostics["vote_mismatches"]):
                                        raise AssertionError("Matched antisymmetric vote identity failed")
                                    for a, b in zip(ref.result, triangular):
                                        np.testing.assert_array_equal(a, b)
                                    matched_trials += len(batch)
                                if eta == 0 and not np.all(reference_flags(batch, ref.result)):
                                    raise AssertionError("Noiseless sensitivity control failed")
                                matrix_outputs[key].append(ref.result[1])
                                matrix_ranks[key].append(ref.ranks_one_based)
                                for name, values in diagnostics.items():
                                    matrix_diagnostics[key][name].append(values)
                    common = dict(dataset=dataset, bits=bits, n=n, eta=eta, quantization=quantization)
                    prefix = f"e{eta_index}_{quantization}_unordered"
                    summarize(keys, prepared, np.concatenate(outputs),
                              dict(**common, algorithm="unordered", coupling="shared", diagonal="omitted"),
                              saved, prefix, rows, distances)
                    for (coupling, diagonal), parts in matrix_outputs.items():
                        prefix = f"e{eta_index}_{quantization}_{coupling}_{diagonal}"
                        diagnostics = {name: np.concatenate(values) for name, values in
                                       matrix_diagnostics[coupling, diagonal].items()}
                        saved[prefix+"__ranks_one_based"] = np.concatenate(matrix_ranks[coupling, diagonal])
                        summarize(keys, prepared, np.concatenate(parts),
                                  dict(**common, algorithm="louri_matrix", coupling=coupling, diagonal=diagonal),
                                  saved, prefix, rows, distances, diagnostics)
            np.savez_compressed(out/(dataset+".npz"), **saved)
            print(f"Sensitivity complete: {dataset}, {len(keys)} input arrays", flush=True)
    write_csv(out/"summary.csv", rows)
    write_csv(out/"distance.csv", distances)
    # Deterministic gzip keeps a large gap histogram small without losing rows.
    with (out/"distance.csv.gz").open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as compressed:
            compressed.write((out/"distance.csv").read_bytes())
    (out/"distance.csv").unlink()
    verification["matched_antisymmetric_noisy_and_noiseless_trials"] = matched_trials
    verification["sensitivity_configurations"] = len(rows)
    verification["sensitivity_sort_evaluations"] = sum(row["trials"] for row in rows)
    verification["analytic_boundary_controls"] = len(controls)
    verification["boundary_pair_evaluations"] = sum(row["samples"] for row in controls)
    (out/"validation.json").write_text(json.dumps(verification, indent=2)+"\n")
    if before != source_hashes():
        raise RuntimeError("Source changed during the experiment")
    metadata = dict(
        created_utc=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
        numpy=np.__version__, source_doi="10.1364/AO.34.003087", source_hashes=before,
        inputs_sha256=INPUT_SHA256, seed=SEED, datasets=datasets,
        selected_trial_ids=list(range(args.sort_trials)), batch_size=args.batch_size,
        eta_values=list(ETA_VALUES), sigma="eta * 2**(-bits)",
        assumptions={
            "scope": "Equation-level sensitivity; no measured device parameters or optical timing",
            "source_equations": "D[i,j]=delta*(x[j]-x[i]); U[i,j]=1 if i>j; R=(Q(D+E)-delta*U)>=0; ranks=column sums",
            "quantization_none": "Identity: no rounding and no clipping",
            "quantization_matched": "Before bias: delta*clip(rint(v/delta), -2**(bits-1), 2**(bits-1)-1); ties to even",
            "independent": "Independent off-diagonal directed Gaussian errors",
            "antisymmetric": "Reverse directed error is the exact negative of the primary one",
            "diagonal_measured": "Independent Gaussian self-difference errors",
            "diagonal_exact": "Known self-differences restored to zero before quantization",
            "remaining_operations": "Exact bias, zero threshold, integer rank sum and electronic placement; no repair",
            "pairing": "Same primary samples across algorithms/couplings; same standard samples across eta and quantizers",
            "streams": "Primary SeedSequence([seed,dataset_index,trial_id]); reverse adds 1; diagonal adds 2",
            "metrics": "Whole-array flags over all trials; tau/recall and inversion gaps conditional on valid outputs; explicit invalid-as-zero recall also saved",
            "intervals": "Per-configuration 95% Wilson intervals; paired configurations are not independent hardware measurements",
            "archives": "Keys are selected by trial_ids from pinned corpus; indices/flags/quality/diagnostics and full-matrix one-based ranks saved; no pickle",
        },
        artifact_sha256={p.name: file_hash(p) for p in sorted(out.iterdir())})
    (out/"metadata.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps({k: v for k, v in verification.items() if k != "cases"}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"results/louri_reference_reproduced")
    parser.add_argument("--sort-trials", type=int, default=100,
                        help="First 1..1000 saved rows per sensitivity dataset (default: 100)")
    parser.add_argument("--batch-size", type=int, default=256,
                        help="Maximum trials per batch; large matrices use a smaller memory cap")
    run(parser.parse_args(argv))


if __name__ == "__main__":
    main()
