"""Check the min/max identity using the pinned Q.ANT CPU SDK.

This is a separate arithmetic check, NOT a new sorting or optical experiment.
The SDK implements relu_fprop on the host CPU. Its native periodic operation
has a hardware-driver entry point, but this script exercises only its cosine
CPU stand-in. No Gaussian noise or sign-only output clipping is added here.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant

from sdk_mapping import SdkDifference, backend_identity

ROOT = Path(__file__).resolve().parent
SDK_COMMIT = "72a2d99f10240b6df3c6d0f636dfa0e2b5d38902"


def check_pairs(bits):
    """Cover every ordered key pair, including equality and both extremes."""
    levels = 2**bits
    a, b = np.meshgrid(np.arange(levels), np.arange(levels), indexing="ij")

    # This call uses the official linear API, not a NumPy replacement.
    d = SdkDifference(bits)(a, b)
    if not np.array_equal(d, (a - b) / levels):
        raise AssertionError("The SDK CPU difference check failed")

    # Source audit: this SDK function executes a Rust max(x, 0) loop on CPU.
    # Its presence in the AI API does not make it a photonic ReLU primitive.
    r = qant.ai.relu_fprop(np.ascontiguousarray(d, dtype=bfloat16))
    r = r.astype(np.float32)
    if not np.array_equal(r, np.maximum(d, 0)):
        raise AssertionError("The SDK host ReLU check failed")

    # These two host operations reconstruct normalized min and max values.
    # They check arithmetic values only, not record identity or stable routing.
    lo = a / levels - r
    hi = b / levels + r
    errors = int(np.count_nonzero(
        (lo != np.minimum(a, b) / levels) |
        (hi != np.maximum(a, b) / levels)
    ))
    if errors:
        raise AssertionError(f"{errors} min/max pairs failed at {bits} bits")

    # Explain why the existing sign-only quantizer cannot be reused here.
    # At (L-1, 0), it clips the positive difference to (L/2-1)/L.
    clipped_d = (levels // 2 - 1) / levels
    clipped_lo = (levels - 1) / levels - clipped_d
    clipped_hi = clipped_d
    return {
        "key_bits": bits, "ordered_pairs": levels**2,
        "min_max_errors": errors, "equal_pairs": levels,
        "clipping_counterexample": {
            "keys": [levels - 1, 0],
            "exact_difference": (levels - 1) / levels,
            "clipped_difference": clipped_d,
            "reconstructed_key_values": [clipped_lo * levels, clipped_hi * levels],
            "expected_key_values": [0, levels - 1],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-file", type=Path,
                        default=ROOT / "results/nonlinearity_reproduced/checks.json")
    args = parser.parse_args()
    identity = backend_identity()
    if identity["sdk_version"] != "2.3.1" or not identity["driver_info"].startswith("cpu-backend;"):
        raise RuntimeError("This check requires the official 2.3.1 CPU backend")

    pair_checks = [check_pairs(bits) for bits in (4, 8)]
    # The CPU stand-in uses cos(u)*v. This is not the measured hardware tcos.
    u = np.array([-1, 0, 1], dtype=bfloat16)
    periodic = qant.native.calc_scaled_periodic_nl_fprop(u, np.ones_like(u))
    checks = {
        **identity, "sdk_source_commit": SDK_COMMIT,
        "hardware_executed": False, "full_sort_experiment": False,
        "added_noise": False, "sign_only_quantizer_applied": False,
        "relu_execution": "host CPU, as verified in SDK src/non_linear.rs",
        "pair_checks": pair_checks,
        "periodic_cpu_example": {
            "inputs": [-1, 0, 1], "weights": [1, 1, 1],
            "outputs": periodic.astype(np.float32).tolist(),
            "interpretation": "Cosine CPU stand-in, not a hardware transfer curve",
        },
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("check_sdk_nonlinearity.py", "sdk_mapping.py")
        },
    }
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(checks, indent=2) + "\n")
    for row in pair_checks:
        print(f"{row['key_bits']}-bit: {row['ordered_pairs']} pairs, zero min/max errors (CPU)")
    print(f"Saved {args.output_file}")


if __name__ == "__main__":
    main()
