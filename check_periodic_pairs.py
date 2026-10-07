# Reading guide: exhaustive CPU calibration evidence for the periodic scorer.
# For every ordered pair compute SDK difference -> periodic output -> reference
# subtraction, then compare the resulting three-way sign with the integer truth.
# The raw output can be nonzero at equality because pi/2 is rounded in BF16.
# Subtracting the same-path d=0 reference corrects this deterministic offset.
# The minimum unequal score is an empirical CPU margin, not an analog noise limit.
# The output-file option writes JSON and may replace an existing calibration file.

"""Exhaustively check the proposed periodic CPU comparison, without noise.

Run after install_sdk.py: python check_periodic_pairs.py
Checks every ordered key pair, including duplicates and domain extremes.
Reports raw zero-threshold errors as well as the corrected reference result.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from ml_dtypes import bfloat16

from periodic_comparison import (
    ALPHA, U0, calibration_reference, periodic_values, require_cpu_backend,
)
from sdk_mapping import SdkDifference

ROOT = Path(__file__).resolve().parent


# Input destination JSON Path. Guard CPU execution, measure a fixed zero
# reference, and exhaustively test all ordered pairs for each registered width.
# Raise on any corrected three-way sign error. Record uncorrected errors and
# minimum unequal score so the reference's role and BF16 margins are auditable.
# Selected positive/negative/tie/extreme examples expose phase rounding explicitly.
# Create the destination parent if needed and write/print the calibration record.
def run(output):
    identity = require_cpu_backend()
    reference = calibration_reference()
    rows = []
    examples = []
    for bits in (4, 8):
        levels = 2 ** bits
        a, b = np.meshgrid(np.arange(levels), np.arange(levels), indexing="ij")
        d = SdkDifference(bits)(a, b)
        raw = periodic_values(d)
        score = raw - reference
        expected = np.sign(a - b)
        errors = int(np.count_nonzero(np.sign(score) != expected))
        if errors:
            raise AssertionError(f"{errors} periodic comparisons failed")
        unequal = a != b
        # This is a CPU finite-precision result, not a physical noise margin.
        rows.append(dict(
            bits=bits, ordered_pairs=a.size, equal_pairs=levels,
            raw_zero_threshold_errors=int(np.count_nonzero(
                np.sign(raw) != expected)), referenced_errors=errors,
            false_ties=int(np.count_nonzero(unequal & (score == 0))),
            minimum_cpu_score_margin=float(np.min(abs(score[unequal]))),
        ))
        for ai, bi in ((10, 9), (9, 10), (9, 9), (levels - 1, 0)):
            examples.append(dict(
                bits=bits, a=ai, b=bi, difference=float(d[ai, bi]),
                phase_ideal=float(U0 - ALPHA * d[ai, bi]),
                phase_bf16=float(bfloat16(U0 - ALPHA * d[ai, bi])),
                periodic_output_bf16=float(raw[ai, bi]),
                reference=reference, score=float(score[ai, bi]),
            ))
    result = dict(
        sdk=identity, hardware_executed=False, phase_offset=U0, alpha=ALPHA,
        reference=reference, noise_added=False, fixed_point_score_quantizer=False,
        reference_policy="One noiseless CPU d=0 measurement per run",
        rows=rows, examples=examples,
        scope="Full pair comparison check, not full sorting or measured tcos",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


# Direct execution starts this file's command-line/test entry point.
# Importing helpers does not run THIS block; the module reading guide
# identifies any other top-level file loading or writing separately.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-file", type=Path,
                        default=ROOT / "results/periodic/pair_checks.json")
    run(parser.parse_args().output_file)
