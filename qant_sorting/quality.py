"""Rescore saved sorting outputs and export quality metrics without rerunning sorts."""

import argparse
import csv
import gzip
import io
import json
import platform
from pathlib import Path

import numpy as np

from qant_sorting.evaluation import prepare_keys, score_saved_order
from qant_sorting.run import (
    ETA_VALUES, INPUT_SHA256, ROOT, file_hash, prepare_output_directory, source_hashes, write_csv,
)


def statistics(values, prefix):
    """Summarize finite values, using None for each undefined statistic."""
    values = values[np.isfinite(values)]
    if not len(values):
        return {prefix + suffix: None for suffix in ("_mean", "_median", "_min", "_p05")}
    return {prefix + "_mean": float(np.mean(values)),
            prefix + "_median": float(np.median(values)),
            prefix + "_min": float(np.min(values)),
            prefix + "_p05": float(np.quantile(values, .05))}


def run(results_dir, output_dir):
    """Validate saved cases and write quality summaries, recall, and inversion distances."""
    results_dir, output_dir = results_dir.resolve(), output_dir.resolve()
    inputs = ROOT / "data/inputs.npz"
    sources = [inputs, results_dir / "simulation_accuracy.csv", results_dir / "simulation_trial_outcomes.npz"]
    hashes = {path.name: file_hash(path) for path in sources}
    if hashes["inputs.npz"] != INPUT_SHA256:
        raise ValueError("Unexpected input corpus")
    output_dir = prepare_output_directory(output_dir, (
        "quality_summary.csv", "quality_recall.csv", "quality_distance.csv.gz",
        "quality_metadata.json",
    ))
    with sources[1].open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("The accuracy CSV contains no cases")

    summaries, recalls, distances = [], [], []
    expected_members = set()
    with np.load(inputs, allow_pickle=False) as corpus, np.load(sources[2], allow_pickle=False) as outputs:
        prepared = {}
        for row in rows:
            bits, n, eta = int(row["key_bits"]), int(row["n"]), float(row["eta"])
            if eta not in ETA_VALUES:
                raise ValueError(f"Unknown noise level: {row['eta']}")
            dataset = f"b{bits}_n{n}_{row['family']}"
            if dataset not in prepared:
                prepared[dataset] = prepare_keys(corpus[dataset], bits)
            label = row["mapping"].strip().lower()
            if label in ("bitonic", "pipelined bitonic adaptation"):
                mapping = "bitonic"
            elif label in ("rank", "louri full-matrix rank"):
                mapping = "rank"
            else:
                raise ValueError(f"Unknown sorting mapping: {row['mapping']}")
            tag = "zero" if eta == 0 else f"noise{round(100 * eta):03d}"
            case = f"{dataset}_{tag}_{mapping}"
            members = {case + "_indices", case + "_flags"}
            if expected_members & members:
                raise ValueError(f"Duplicate case in accuracy CSV: {case}")
            expected_members.update(members)
            result = score_saved_order(prepared[dataset], outputs[case + "_indices"])
            flags = result["flags"]
            if not np.array_equal(flags, outputs[case + "_flags"]):
                raise ValueError(f"Saved flags disagree with rescoring: {case}")
            valid, correct, stable = flags.sum(axis=0).tolist()
            trials = len(flags)
            count_fields = ("trials", "valid_outputs", "correct_sorts", "stable_sorts")
            if [trials, valid, correct, stable] != [int(row[key]) for key in count_fields]:
                raise ValueError(f"Saved accuracy counts disagree with rescoring: {case}")

            fields = dict(dataset=dataset, key_bits=bits, n=n, family=row["family"], eta=eta, mapping=mapping)
            summary = dict(**fields, trials=trials, valid_outputs=valid, invalid_outputs=trials-valid,
                correct_sorts=correct, stable_sorts=stable, whole_sort_accuracy=correct/trials,
                tau_defined_outputs=int(np.isfinite(result["tau_b"]).sum()),
                comparable_pairs_valid=int(result["distance_pairs"].sum()),
                inverted_pairs_valid=int(result["distance_inversions"].sum()))
            for metric in ("tau_b", "tau_b_ceiling", "tau_key_normalized"):
                summary.update(statistics(result[metric], metric))
            summary.update(statistics(result["inversions"][flags[:, 0]], "inversions_valid"))
            summaries.append(summary)
            for gap, denominator in enumerate(result["distance_pairs"]):
                if denominator:
                    errors = int(result["distance_inversions"][gap])
                    distances.append(dict(**fields, key_distance=gap, valid_outputs=valid,
                        pairs_at_distance=int(denominator), inverted_pairs=errors,
                        inversion_rate=errors/int(denominator)))
            for k, variants in result["recall"].items():
                recall = dict(**fields, k=k, selection="largest", full_set_control=(k == n),
                              trials=trials, valid_outputs=valid, invalid_outputs=trials-valid)
                for variant, values in variants.items():
                    finite = values[np.isfinite(values)]
                    recall[variant + "_mean_valid"] = float(finite.mean()) if len(finite) else None
                    recall[variant + "_min_valid"] = float(finite.min()) if len(finite) else None
                    recall[variant + "_mean_all_invalid_zero"] = float(np.nansum(values)/trials)
                recalls.append(recall)
        if set(outputs.files) != expected_members or len(outputs.files) != len(expected_members):
            raise ValueError("Saved output cases do not match the accuracy CSV")

    if any(file_hash(path) != hashes[path.name] for path in sources):
        raise ValueError("Inputs or saved outputs changed during quality evaluation")

    write_csv(output_dir / "quality_summary.csv", summaries)
    write_csv(output_dir / "quality_recall.csv", recalls)
    distance_fields = ["dataset", "key_bits", "n", "family", "eta", "mapping", "key_distance",
                       "valid_outputs", "pairs_at_distance", "inverted_pairs", "inversion_rate"]
    with (output_dir / "quality_distance.csv.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=distance_fields)
                writer.writeheader()
                writer.writerows(distances)
    validation = dict(evaluated_cases=len(rows), evaluated_outputs=sum(row["trials"] for row in summaries),
        complete_coverage=True, saved_flags_and_counts_reproduced=True,
        distance_rows=len(distances), new_sorter_executions=0)
    metadata = dict(python=platform.python_version(), numpy=np.__version__, source_sha256=hashes,
        results_directory=str(results_dir), evaluation_code_sha256=source_hashes(),
        kendall="tau_b(true keys, output positions); ceiling sqrt(M/C); tau_key=1-2*I/M",
        distances="Unequal-key inversions of valid outputs, grouped by integer key gap",
        recall="Largest k; stable-ID and tie-neutral conventions; k=N checks record preservation",
        invalid_policy="Undefined conditional quality; mean_all_invalid_zero assigns zero utility",
        coverage="All cases in the chosen accuracy CSV and output archive are scored",
        scope="Synthetic sorting quality; saved inputs are reused across noise levels and algorithms",
        validation=validation)
    (output_dir / "quality_metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
    print(json.dumps(validation, indent=2))


def main(argv=None):
    """Parse command-line directories and run quality evaluation."""
    parser = argparse.ArgumentParser(description="Score saved sorting outputs.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/reproduced")
    args = parser.parse_args(argv)
    run(args.results_dir, args.output_dir)


if __name__ == "__main__":
    main()
