"""Audit and score saved outputs. Does not import or run the SDK or sorters."""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import time

import numpy as np
from ranking_quality import prepare_keys, score_saved_order
from saved_output_reader import SavedOutputs

ROOT = Path(__file__).resolve().parent
INPUT_SHA256 = "79efbd1ee270242cc122d8f9e1848fe07a85077bcf310324b27dd60f8faf11da"
SOURCES = ("reference", "periodic", "periodic_deadband")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def statistics(values, prefix):
    values = values[np.isfinite(values)]
    if not len(values):
        return {prefix+suffix: None for suffix in ("_mean", "_median", "_min", "_p05")}
    return {prefix+"_mean": float(np.mean(values)), prefix+"_median": float(np.median(values)),
            prefix+"_min": float(np.min(values)), prefix+"_p05": float(np.quantile(values, .05))}


def run(args):
    start = time.perf_counter()
    root, output = args.project_dir.resolve(), args.output_dir.resolve()
    source_paths = [root/"data/inputs.npz"]
    for source in SOURCES:
        source_paths += [root/"results"/source/name for name in ("trial_outcomes.npz", "accuracy.csv", "metadata.json")]
    hashes = {str(path.relative_to(root)): digest(path) for path in source_paths}
    if hashes["data/inputs.npz"] != INPUT_SHA256:
        raise ValueError("Unexpected input corpus")
    for source in SOURCES:
        meta = json.loads((root/"results"/source/"metadata.json").read_text())
        if meta.get("inputs_sha256") != INPUT_SHA256:
            raise ValueError("Source metadata refers to a different input corpus")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty output directory to preserve prior evidence")
    with np.load(root/"data/inputs.npz", allow_pickle=False) as corpus:
        prepared = {name: prepare_keys(corpus[name], int(name.split("_", 1)[0][1:])) for name in corpus.files}

    summaries, recalls, coverage, archive_audit = [], [], [], {}
    reference = SavedOutputs(root/"results/reference/trial_outcomes.npz")
    duplicate_checks = 0
    distance_rows = 0
    # Exact integer distances are streamed into a compressed CSV; no binning.
    with (output/"distance.csv.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                distance_writer = None
                for source in SOURCES:
                    directory = root/"results"/source
                    archive = reference if source == "reference" else SavedOutputs(
                        directory/"trial_outcomes.npz", args.allow_incomplete)
                    archive_audit[source] = archive.audit
                    rows = list(csv.DictReader((directory/"accuracy.csv").open()))
                    for number, row in enumerate(rows):
                        scenario = row.get("scenario", "direct")
                        bits, n = int(row["key_bits"]), int(row["n"])
                        dataset = f"b{bits}_n{n}_{row['family']}"
                        mapping = "bitonic" if "bitonic" in row["mapping"].lower() else "rank"
                        eta = float(row["eta"])
                        noise = "zero" if eta == 0 else f"noise{round(100*eta):03d}"
                        case = f"{dataset}_{noise}_{mapping}"
                        member = case if source == "reference" else scenario+"_"+case
                        flags_key, indices_key = member+"_flags", member+"_indices"
                        fields = dict(source=source, scenario=scenario, dataset=dataset,
                                      key_bits=bits, n=n, family=row["family"], eta=eta, mapping=mapping)
                        have_flags, have_indices = flags_key in archive, indices_key in archive
                        coverage.append(dict(**fields, expected_trials=int(row["trials"]),
                                             flags_available=have_flags, indices_available=have_indices,
                                             status="evaluated" if have_flags and have_indices else "missing_saved_outputs"))
                        if not have_flags or not have_indices:
                            if have_flags:
                                counts = archive[flags_key].sum(axis=0)
                                if tuple(counts) != tuple(int(row[k]) for k in ("valid_outputs", "correct_sorts", "stable_sorts")):
                                    raise AssertionError("Available partial flags disagree with accuracy.csv")
                            continue
                        saved_flags, indices = archive[flags_key], archive[indices_key]
                        keys = prepared[dataset]
                        result = score_saved_order(keys, indices)
                        flags = result["flags"]
                        if not np.array_equal(flags, saved_flags):
                            raise AssertionError("Reconstructed validity/correctness/stability disagrees: " + member)
                        counts = flags.sum(axis=0).astype(int)
                        if tuple(counts) != tuple(int(row[k]) for k in ("valid_outputs", "correct_sorts", "stable_sorts")):
                            raise AssertionError("Output counts disagree with accuracy.csv: " + member)
                        trials = len(flags)
                        if trials != int(row["trials"]):
                            raise AssertionError("Unexpected trial count")
                        if scenario == "upstream":
                            if not np.array_equal(indices, reference[case+"_indices"]) or not np.array_equal(flags, reference[case+"_flags"]):
                                raise AssertionError("Upstream and direct reference differ")
                            duplicate_checks += 1
                        valid, correct, stable = map(int, counts)
                        defined = int(np.isfinite(result["tau_b"]).sum())
                        summary = dict(**fields, trials=trials, valid_outputs=valid,
                                       invalid_outputs=trials-valid, correct_sorts=correct, stable_sorts=stable,
                                       whole_sort_accuracy=correct/trials, stable_accuracy=stable/trials,
                                       tau_defined_outputs=defined, constant_key_valid_outputs=valid-defined,
                                       comparable_pairs_valid=int(result["distance_pairs"].sum()),
                                       inverted_pairs_valid=int(result["distance_inversions"].sum()))
                        for metric in ("tau_b", "tau_b_ceiling", "tau_key_normalized"):
                            summary.update(statistics(result[metric], metric))
                        summary.update(statistics(result["inversions"][flags[:, 0]], "inversions_valid"))
                        summaries.append(summary)
                        for gap in range(1, keys.levels):
                            pairs = int(result["distance_pairs"][gap])
                            if not pairs:
                                continue
                            errors = int(result["distance_inversions"][gap])
                            record = dict(**fields, key_distance=gap, valid_outputs=valid,
                                          pairs_at_distance=pairs, inverted_pairs=errors, inversion_rate=errors/pairs)
                            if distance_writer is None:
                                distance_writer = csv.DictWriter(text, fieldnames=list(record))
                                distance_writer.writeheader()
                            distance_writer.writerow(record)
                            distance_rows += 1
                        for k, variants in result["recall"].items():
                            recall = dict(**fields, k=k, selection="largest", full_set_control=(k==n),
                                          trials=trials, valid_outputs=valid, invalid_outputs=trials-valid)
                            for variant, values in variants.items():
                                finite = values[np.isfinite(values)]
                                recall[variant+"_mean_valid"] = float(np.mean(finite)) if len(finite) else None
                                recall[variant+"_min_valid"] = float(np.min(finite)) if len(finite) else None
                                recall[variant+"_mean_all_invalid_zero"] = float(np.nansum(values)/trials)
                            recalls.append(recall)
                    if archive is not reference:
                        archive.close()
                    print(f"{source}: {sum(c['status']=='evaluated' for c in coverage if c['source']==source)}/{len(rows)} cases evaluated", flush=True)
    reference.close()
    if duplicate_checks != 288:
        raise AssertionError("Expected all 288 direct/upstream identity checks")
    for path in source_paths:
        if digest(path) != hashes[str(path.relative_to(root))]:
            raise AssertionError("Source evidence changed during evaluation")
    write_csv(output/"summary.csv", summaries)
    write_csv(output/"recall.csv", recalls)
    write_csv(output/"coverage.csv", coverage)
    missing = [row for row in coverage if row["status"] != "evaluated"]
    validation = dict(
        available_outputs_passed=True, expected_cases=len(coverage), evaluated_cases=len(summaries),
        evaluated_outputs=sum(row["trials"] for row in summaries), missing_cases=missing,
        missing_outputs=sum(row["expected_trials"] for row in missing),
        direct_upstream_identical_cases=duplicate_checks, distance_rows=distance_rows,
        existing_flags_and_csv_counts_reproduced=True, source_files_unchanged=True,
        complete_coverage=(not missing),
    )
    metadata = dict(
        created_at_utc=datetime.now(timezone.utc).isoformat(), python=platform.python_version(), numpy=np.__version__,
        elapsed_seconds=time.perf_counter()-start, source_sha256=hashes,
        evaluation_code_sha256={name: digest(ROOT/name) for name in
                               ("ranking_quality.py", "saved_output_reader.py", "evaluate_ranking_quality.py")},
        archive_audit=archive_audit, allow_incomplete=args.allow_incomplete,
        new_sorter_executions=0, sdk_loaded=False, hardware_executed=False,
        kendall="tau_b(true key of each record, output position of that record); no ties in output positions",
        tau_ceiling="sqrt(M/C); M=unequal-key pairs; C=N(N-1)/2",
        tau_key_normalized="tau_b/ceiling = 1-2*I/M; separate derived normalization, not standard tau-b",
        undefined_tau="Invalid outputs and valid arrays with no unequal-key pair; counts explicitly reported",
        distances="Final output inversions among unequal-key pairs, pooled by exact integer key distance; not internal comparator errors",
        recall_cutoffs="{1,5,10,32} intersect [1,N], plus k=N as full-set control",
        top_k="Largest k keys: suffix of ascending output. Strict reference is suffix of stable (key,original index) order.",
        strict_boundary_ties="Later original indices belong to the reference suffix at an equal-key boundary",
        tie_neutral_recall="Count selected keys strictly above threshold plus min(remaining tie slots, selected keys at threshold), divided by k",
        invalid_policy="Tau/distances and mean_valid recall condition on valid outputs. mean_all_invalid_zero explicitly assigns invalid outputs zero utility.",
        dependence="Same 24,000 inputs reused across conditions; direct and upstream outputs are identical controls, not independent evidence",
        limits=["Existing synthetic noise/quantization scenarios remain physically unmatched",
                "No hardware advantage or PRISM task performance follows from these quality metrics",
                "Keys are reconstructed from saved original-record indices; original routed key values are not remeasured"],
    )
    for name, value in (("validation.json", validation), ("metadata.json", metadata)):
        (output/name).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Scored {validation['evaluated_outputs']} existing outputs; {len(missing)} cases unavailable. No new sorts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"results/ranking_quality_reproduced")
    parser.add_argument("--allow-incomplete", action="store_true", help="Score CRC-verified complete members of incomplete NPZ archives and report missing cases")
    run(parser.parse_args())
