"""Check a new run against every saved result from the original noise sweep."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "results/reference"


def verify_results(actual_directory, reference_directory=REFERENCE):
    """Require identical CSV results and per-trial flags/record permutations.

    Metadata may change because code, runtime and batching change. Numerical
    results, seeds and input hashes must not. Compare NPZ contents rather than
    ZIP bytes, whose container metadata is irrelevant to the experiment.
    """
    with (reference_directory / "accuracy.csv").open(newline="") as handle:
        expected_rows = list(csv.DictReader(handle))
    with (actual_directory / "accuracy.csv").open(newline="") as handle:
        actual_rows = list(csv.DictReader(handle))
    if actual_rows != expected_rows:
        raise AssertionError("CSV results differ from the saved reference")

    with np.load(reference_directory / "trial_outcomes.npz") as expected:
        with np.load(actual_directory / "trial_outcomes.npz") as actual:
            if set(actual.files) != set(expected.files):
                raise AssertionError("Saved trial arrays differ in their case names")
            for name in expected.files:
                if not np.array_equal(actual[name], expected[name]):
                    raise AssertionError(f"Changed trial result: {name}")
            array_count = len(expected.files)

    # Failure examples also identify exactly the same first failing trial.
    expected_failures = json.loads((reference_directory / "failures.json").read_text())
    actual_failures = json.loads((actual_directory / "failures.json").read_text())
    if actual_failures != expected_failures:
        raise AssertionError("First-failure examples changed")
    return {"matched_configurations": len(actual_rows), "matched_arrays": array_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=ROOT / "results/reproduced")
    args = parser.parse_args()
    print(json.dumps(verify_results(args.directory), indent=2))
