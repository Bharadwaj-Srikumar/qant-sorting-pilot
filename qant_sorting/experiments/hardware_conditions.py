# Reading guide: conditional resource accounting, not a hardware benchmark.
# counts describes one full sort at a chosen maximum pairs per software call.
# main derives logical BF16 buffer sizes and idealized bandwidth floors, then
# varies that submission cap to expose the trade-off between calls and pair work.
# Bitonic cannot combine dependent layers into one call simply because they fit.
# Rank has more independent pair work but may need fewer submissions.
# --verify-sdk adds an optional CPU API check; otherwise no SDK is imported.
# The latency formula uses conditional physical costs and does not redefine T.

"""Count logical operations/transfers under explicit execution conditions.

No measured Q.ANT pair rate, tile size, ENOB or optical cascade is assumed.
The pair cap is a software submission limit, not a physical matrix dimension.
These analytical counts need no SDK. --verify-sdk optionally tests chunking
against the official CPU backend, which still does not measure real hardware.
"""

from qant_sorting.io import write_csv

import argparse
import json

import numpy as np

from qant_sorting.sorting_schedules import bitonic_sort, rank_sort

from qant_sorting.paths import ROOT
# PCIe Gen4 x8: 16 GT/s per lane, eight lanes, 128/130 line coding, 8 bits/byte.
# This is a directional link ceiling before protocol/driver overhead.
B_PEAK = 16e9 * 8 * (128 / 130) / 8


# Input N (power of two >=2) and cap (positive integer pairs per submission).
# Return (layers, bitonic_pairs, rank_pairs, bitonic_calls, rank_calls).
# Calls use ceiling division: each bitonic layer is split separately because its
# next layer depends on current results; all independent rank pairs can be chunked.
# Counts apply to ONE input array, without cross-array batching or device tiling.
def counts(n, cap):
    """Return layers, bitonic/rank pairs, bitonic/rank calls for ONE sort."""
    if n < 2 or n & (n - 1):
        raise ValueError("n must be a power of two and at least 2")
    if type(cap) is not int or cap < 1:
        raise ValueError("pair cap must be a positive integer")
    m = n.bit_length() - 1
    layers = m * (m + 1) // 2
    bitonic_pairs = n * layers // 2
    rank_pairs = n * (n - 1) // 2
    # Each dependent bitonic layer must complete before the next starts.
    # Rank comparisons can be submitted together or split into chunks.
    bitonic_calls = layers * ((n // 2 + cap - 1) // cap)
    rank_calls = (rank_pairs + cap - 1) // cap
    return layers, bitonic_pairs, rank_pairs, bitonic_calls, rank_calls


# Optional official-CPU test of the logical accounting for selected N/cap cases.
# Lazy-import the SDK, require its pinned CPU identity, sort descending examples,
# and compare observed adapter counters with counts and BF16 byte formulas.
# Return validation records; this verifies API packing only, not physical capacity.
def verify_sdk_chunks():
    """Verify submitted shapes/counts, without inferring physical tiling."""
    # Lazy imports keep the analytical accounting and main sweep NumPy-only.
    from qant_sorting.sdk_mapping import SdkDifference, backend_identity

    identity = backend_identity()
    if identity["sdk_version"] != "2.3.1" or not identity["driver_info"].startswith("cpu-backend;"):
        raise RuntimeError("Chunk verification requires the official 2.3.1 CPU backend")
    checks = []
    for n in (16, 256):
        bits = 4 if n == 16 else 8
        data = np.arange(n)[::-1][None, :]
        maximum = n * (n - 1) // 2
        for cap in sorted({1, min(8, maximum), min(128, maximum), min(1024, maximum), maximum}):
            _, cb, cr, qb, qr = counts(n, cap)
            for name, sorter, pairs, calls in (
                ("Bitonic", bitonic_sort, cb, qb), ("Rank", rank_sort, cr, qr)
            ):
                base = SdkDifference(bits)

                # Closure capturing the current SdkDifference adapter and submission cap.
                # Flatten pairs, submit consecutive slices of at most cap, concatenate results,
                # and restore the caller's shape. Flattening does not change pair order or values.
                # The outer adapter retains counters across these smaller public API calls.
                def chunked_difference(a, b):
                    flat_a, flat_b = a.reshape(-1), b.reshape(-1)
                    pieces = [
                        base(flat_a[start:start + cap], flat_b[start:start + cap])
                        for start in range(0, a.size, cap)
                    ]
                    return np.concatenate(pieces).reshape(a.shape)

                values, _, valid = sorter(data, chunked_difference)
                c = base.counts
                if not valid.all() or not np.array_equal(values, np.sort(data, axis=1)):
                    raise AssertionError("Chunked SDK sorting control failed")
                actual = (c.pair_differences, c.api_calls, c.feature_bytes, c.output_bytes, c.weight_bytes)
                if actual != (pairs, calls, 4 * pairs, 2 * pairs, 4 * calls):
                    raise AssertionError("Logical SDK call or transfer counts changed")
                checks.append(dict(n=n, mapping=name, cap=cap, pairs=pairs, calls=calls, correct=True))
    return checks


# Generate per-sort logical resource rows and a complete integer cap sweep.
# Bandwidth floors exclude protocol/software overhead; full-duplex and serialized
# cases explicitly differ in whether upload/download can overlap.
# Only compute the call-overhead break-even ratio when rank saves calls; leave
# the field blank otherwise instead of dividing by zero or reversing its meaning.
# Write CSV/JSON under results/hardware, optionally adding CPU chunk checks.
def main(verify_sdk=False):
    output = ROOT / "results/hardware"
    output.mkdir(parents=True, exist_ok=True)
    resources, sensitivity = [], []
    for n in (2, 4, 8, 16, 32, 64, 128, 256):
        _, cb, cr, qb, qr = counts(n, n * (n - 1) // 2)
        for name, pairs, calls in (("Bitonic", cb, qb), ("Rank", cr, qr)):
            # BF16: two inputs (4 bytes) and one output (2 bytes) per pair.
            # W=[1,-1] is another 4 bytes if reloaded for every submission.
            up, down = 4 * pairs + 4 * calls, 2 * pairs
            resources.append(dict(
                n=n, mapping=name, pairs=pairs, calls=calls,
                bf16_feature_bytes=4 * pairs, weight_bytes_reload=4 * calls,
                weight_bytes_once=4, output_bytes=down, payload_bytes_reload=up + down,
                full_duplex_payload_floor_us=max(up, down) / B_PEAK * 1e6,
                serialized_payload_floor_us=(up + down) / B_PEAK * 1e6,
            ))
        for cap in range(1, cr + 1):
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
        cap_domain="Every integer 1 through N(N-1)/2; application submissions, not device tiles.",
        bandwidth_domain="0 < B_eff <= B_peak. No measured link utilization assumed.",
        model="t_A = q_A*ell + C_A*t_arithmetic + U_A/B_up + V_A/B_down + h_A",
        threshold="a=ell+4/B_up; tau=t_arithmetic+4/B_up+2/B_down. Rank wins if (q_B-q_R)*a > (C_R-C_B)*tau + h_R-h_B.",
        limitations="Logical payload only; no measured latency, throughput or energy verdict.",
        checks=verify_sdk_chunks() if verify_sdk else [],
    )
    (output / "validation.json").write_text(json.dumps(metadata, indent=2))
    print(f"Saved {len(resources)} resource rows and {len(sensitivity):,} conditional sensitivity rows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-sdk", action="store_true", help="Also check chunked submissions on the CPU SDK")
    args = parser.parse_args()
    main(args.verify_sdk)
