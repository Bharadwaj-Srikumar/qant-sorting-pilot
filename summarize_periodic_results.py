# Reading guide: historical table assembly from already saved CPU evidence.
# This module is a SCRIPT WITH TOP-LEVEL SIDE EFFECTS: importing it reads both
# accuracy CSVs, checks the expected 864 rows, and writes periodic_summary files.
# It does not execute sorters, fit noise, or resolve the later missing-NPZ issue.
# Resource tables describe one sort under two assumed capacity settings.
# The one-time reference-calibration call is excluded and disclosed separately.
# An all_fit case means all pairs of an independent submission fit, not that
# dependent bitonic layers become simultaneous. Scenarios retain different units.

"""Produce compact tables from saved evidence; no new sorting or fitting."""
from pathlib import Path
import csv
import json
import math

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/periodic_summary"
OUT.mkdir(parents=True, exist_ok=True)
# Read existing CSV summaries only. This aggregation does not validate that
# every saved NPZ member remains available; see the later coverage audit for
# the incomplete deadband archive.
rows = []
for folder in ("periodic", "periodic_deadband"):
    with (ROOT / "results" / folder / "accuracy.csv").open() as stream:
        rows.extend(csv.DictReader(stream))
assert len(rows) == 864
# Every noiseless run must also preserve the stable original-record order.
assert all(float(r["accuracy"]) == float(r["stable_accuracy"]) == 1
           for r in rows if float(r["eta"]) == 0)
fields = ["scenario", "mapping", "key_bits", "n", "family", "eta",
          "accuracy", "stable_accuracy", "ci95_low", "ci95_high"]
with (OUT / "accuracy.csv").open("w", newline="") as stream:
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
with (OUT / "resources.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(resources[0]))
    writer.writeheader(); writer.writerows(resources)
metadata = dict(configurations=864, executions=sum(int(r["trials"]) for r in rows),
    hardware_executed=False, reference_call_excluded_from_resources=True,
    calibration_buffer_bytes=6,
    transfer_boundary="Public API logical BF16 buffers, not measured PCIe traffic",
    noise_protocols="Upstream difference noise and new score noise are different experiments")
(OUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
print(json.dumps(metadata, indent=2))
