"""Count pair operations, API calls and logical BF16 bytes for both sorters.

Run python -m qant_sorting.resources to write the resource tables.
The pair cap limits software submissions; it is not a physical tile size.
Bandwidth floors and timing thresholds are conditional, not hardware results.
"""

import argparse
import json
from pathlib import Path

from qant_sorting.run import ROOT, write_csv


# PCIe Gen4 x8 directional ceiling, after line coding but before other overhead.
B_PEAK = 16e9 * 8 * (128 / 130) / 8


def counts(n, cap):
    """Return layers, Bitonic/rank pairs and Bitonic/rank calls for one sort.

    Each Bitonic layer must finish before the next begins, so split its N/2
    pairs separately. All N*N rank pairs are independent submissions.
    Counts exclude batching across multiple input arrays.
    """
    if n < 2 or n & (n - 1):
        raise ValueError("n must be a power of two and at least 2")
    if type(cap) is not int or cap < 1:
        raise ValueError("pair cap must be a positive integer")
    m = n.bit_length() - 1
    layers = m * (m + 1) // 2
    bitonic_pairs = n * layers // 2
    rank_pairs = n * n
    bitonic_calls = layers * ((n // 2 + cap - 1) // cap)
    rank_calls = (rank_pairs + cap - 1) // cap
    return layers, bitonic_pairs, rank_pairs, bitonic_calls, rank_calls


def run(output=None):
    """Write resource rows and call-cap sensitivity without requiring the SDK."""
    output = (output or ROOT / "results/resources_reproduced").resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty resource output directory")
    resources, sensitivity = [], []
    for n in (2, 4, 8, 16, 32, 64, 128, 256):
        _, cb, cr, qb, qr = counts(n, n * n)
        for name, pairs, calls in (("Bitonic", cb, qb), ("Rank", cr, qr)):
            # Two BF16 inputs and one output cost 4+2 bytes per pair. Reloading
            # [1,-1] adds 4 bytes per call; resident weights are a separate case.
            up, down = 4 * pairs + 4 * calls, 2 * pairs
            resources.append(dict(
                n=n, mapping=name, pairs=pairs, calls=calls,
                bf16_feature_bytes=4 * pairs, weight_bytes_reload=4 * calls,
                weight_bytes_once=4, output_bytes=down, payload_bytes_reload=up + down,
                full_duplex_payload_floor_us=max(up, down) / B_PEAK * 1e6,
                serialized_payload_floor_us=(up + down) / B_PEAK * 1e6,
            ))
        for cap in sorted({1, min(8, cr), n//2, min(128, cr), min(1024, cr), cr}):
            _, _, _, qb, qr = counts(n, cap)
            saved_calls = qb - qr
            sensitivity.append(dict(
                n=n, pair_cap=cap, bitonic_calls=qb, rank_calls=qr,
                call_saving_for_rank=saved_calls, additional_rank_pairs=cr - cb,
                overhead_to_pair_time_threshold=(cr - cb) / saved_calls if saved_calls > 0 else "",
                scope="Same effective time per pair; equal/omitted host time only for this threshold.",
            ))
    write_csv(output / "resources.csv", resources)
    write_csv(output / "batch_sensitivity.csv", sensitivity)
    metadata = dict(
        hardware_executed=False, peak_link_bytes_per_second=B_PEAK,
        cap_domain="Predeclared caps {1, min(8,N*N), N/2, min(128,N*N), min(1024,N*N), N*N}; application submissions, not device tiles.",
        bandwidth_domain="0 < B_eff <= B_peak. No measured link utilization assumed.",
        model="t_A = q_A*ell + C_A*t_arithmetic + U_A/B_up + V_A/B_down + h_A",
        threshold="a=ell+4/B_up; tau=t_arithmetic+4/B_up+2/B_down. Rank wins if (q_B-q_R)*a > (C_R-C_B)*tau + h_R-h_B.",
        limitations="Logical payload only; no measured latency, throughput or energy verdict.",
        checks=[],
    )
    (output / "validation.json").write_text(json.dumps(metadata, indent=2))
    print(f"Saved {len(resources)} resource rows and {len(sensitivity):,} conditional sensitivity rows.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/resources_reproduced")
    args = parser.parse_args(argv)
    run(args.output_dir)


# Self-tests

import unittest


class ResourceTests(unittest.TestCase):
    def test_resource_counts(self):
        self.assertEqual(counts(4, 16), (3, 6, 16, 3, 1))
        self.assertEqual(counts(16, 256), (10, 80, 256, 10, 1))
        self.assertEqual(counts(256, 65536), (36, 4608, 65536, 36, 1))


if __name__ == "__main__":
    main()
