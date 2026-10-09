"""Summarize historical periodic CSVs without executing any sorters.

Reading or importing the module has no file-writing side effects. Missing raw
NPZ members are a separate coverage issue; this command summarizes CSVs only.
Resource tables count logical buffers and exclude reference calibration.
"""
import argparse
import csv
import json
import math
from pathlib import Path

from qant_sorting.io import write_csv
from qant_sorting.paths import ROOT


def run(output, project_dir=ROOT):
    """Write derived tables to a fresh directory, preserving historical evidence."""
    sources = [project_dir / "results" / folder / "accuracy.csv"
               for folder in ("periodic", "periodic_deadband")]
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError("Historical CSVs are not bundled: " + ", ".join(missing)
                                + "; use --project-dir with the original evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Choose an empty output directory")
    # Read existing CSV summaries only. This aggregation does not validate that
    # every saved NPZ member remains available; see the later coverage audit for
    # the incomplete deadband archive.
    rows = []
    for path in sources:
        with path.open() as stream:
            rows.extend(csv.DictReader(stream))
    assert len(rows) == 864
    # Every noiseless run must also preserve the stable original-record order.
    assert all(float(r["accuracy"]) == float(r["stable_accuracy"]) == 1
               for r in rows if float(r["eta"]) == 0)
    fields = ["scenario", "mapping", "key_bits", "n", "family", "eta",
              "accuracy", "stable_accuracy", "ci95_low", "ci95_high"]
    with (output / "accuracy.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in rows)

    # Derive public API traffic for one sort. The periodic variant performs one
    # linear and one periodic call per submitted group, doubling call count and
    # adding BF16 phase/amplitude/return buffers. These are not PCIe measurements.
    resources = []
    for bits in (4, 8):
        for exponent in range(1, bits + 1):
            n = 2 ** exponent
            stages = exponent * (exponent + 1) // 2
            for mapping, pairs in (("bitonic", n * stages // 2),
                                   ("rank", n * (n - 1) // 2)):
                # Capacity cases are sensitivity assumptions, not Q.ANT specifications.
                for capacity in (128, "all_fit"):
                    if mapping == "bitonic":
                        linear_calls = stages * (math.ceil((n // 2) / capacity)
                                                   if capacity != "all_fit" else 1)
                    else:
                        linear_calls = (math.ceil(pairs / capacity)
                                        if capacity != "all_fit" else 1)
                    resources.append(dict(bits=bits, n=n, mapping=mapping,
                        capacity_case=capacity, pairs=pairs,
                        baseline_calls=linear_calls, periodic_calls=2 * linear_calls,
                        baseline_buffer_bytes=6 * pairs + 4 * linear_calls,
                        periodic_buffer_bytes=12 * pairs + 4 * linear_calls))
    write_csv(output / "resources.csv", resources)
    metadata = dict(configurations=864, executions=sum(int(r["trials"]) for r in rows),
        hardware_executed=False, reference_call_excluded_from_resources=True,
        calibration_buffer_bytes=6,
        transfer_boundary="Public API logical BF16 buffers, not measured PCIe traffic",
        noise_protocols="Upstream difference noise and new score noise are different experiments")
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/periodic_summary_reproduced")
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.output_dir, args.project_dir)
