# Reading guide: separate arithmetic proof/check of the ReLU min/max identity.
# For d=a-b and r=max(d,0), min=a-r and max=b+r. Exact difference magnitudes
# are needed; sign-preserving clipping alone is not enough for reconstruction.
# The implementation exercises the official CPU SDK and records a counterexample
# for the clipped magnitude. It does not sort records or prove stable routing.
# The SDK's host ReLU and native periodic CPU stand-in are distinct operations.

"""Check the min/max identity using the pinned Q.ANT CPU SDK.

This is a separate arithmetic check, NOT a new sorting or optical experiment.
The SDK implements relu_fprop on the host CPU. Its native periodic operation
has a hardware-driver entry point, but this script exercises only its cosine
CPU stand-in. No Gaussian noise or sign-only output clipping is added here.
"""

from qant_sorting.io import source_hashes

import argparse
import json
from pathlib import Path

import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant

from qant_sorting.sdk_mapping import SdkDifference, backend_identity

from qant_sorting.paths import ROOT
SDK_COMMIT = "72a2d99f10240b6df3c6d0f636dfa0e2b5d38902"


# Input bits=4 or 8. Compute every pair through the official linear API, apply
# the SDK host ReLU, and compare reconstructed normalized min/max with exact keys.
# Return counts and an extreme-pair counterexample showing why clipped scores
# cannot substitute for full differences in this identity.
# This checks arithmetic values only, not stable record identities or optical ReLU.
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


# Parse output path, require official CPU SDK 2.3.1, run both exhaustive checks,
# and record a small native-periodic CPU example with source hashes.
# Create/write the JSON result and print concise counts. SDK/backend identity
# and explicit hardware_executed=False delimit what the successful checks mean.
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
        "source_sha256": source_hashes(),
    }
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(checks, indent=2) + "\n")
    for row in pair_checks:
        print(f"{row['key_bits']}-bit: {row['ordered_pairs']} pairs, zero min/max errors (CPU)")
    print(f"Saved {args.output_file}")


if __name__ == "__main__":
    main()
