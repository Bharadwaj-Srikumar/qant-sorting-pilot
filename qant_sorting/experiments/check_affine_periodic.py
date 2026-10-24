"""CPU feasibility control: form the periodic phase inside the linear SDK call.

Reading guide: the candidate packs [a/2**bits, b/2**bits, 1] and uses one
BF16 weight row [-pi/2, pi/2, pi/2]. It does not compute a-b on the host.
The returned phase is still a host NumPy array passed to a SECOND SDK call.
This tests arithmetic placement and precision, not a host-free hardware cascade.

Run in the separately documented SDK environment; existing evidence is never
overwritten. Candidate errors are research results, not repaired comparisons.
The direct-difference and existing host-phase controls must remain correct.
"""

from qant_sorting.io import file_hash, source_hashes

import argparse
import importlib.metadata
import json
import platform
from pathlib import Path

import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant

from qant_sorting.periodic_comparison import ALPHA, U0, calibration_reference, periodic_values, require_cpu_backend
from qant_sorting.sdk_mapping import SdkDifference

from qant_sorting.paths import ROOT, INPUT_SHA256
SDK_ARCHIVE_SHA256 = "99b4669d3256d92cc35efc1a2d6d59deef7a033d78397d71150333011eb93898"


class AffinePeriodicComparison:
    """CPU-only affine candidate, with one fixed same-path equality reference.

    Inputs are equally shaped nonempty integer arrays in the declared domain.
    The result is a float32 score of the same shape, interpreted electronically
    in this pair feasibility study. Widening BF16 does not restore lost information.
    Calibration uses only the pair (0,0); integer truth never guides a decision.
    """

    def __init__(self, bits):
        """Guard CPU execution, encode the constant feature, and measure zero."""
        if bits not in (4, 8):
            raise ValueError("Only the registered 4/8-bit domains are supported")
        self.identity = require_cpu_backend()
        self.bits = bits
        self.scale = 2 ** bits
        self.weights = np.array([[-ALPHA, ALPHA, U0]], dtype=bfloat16)
        _, raw = self.raw(np.array([0]), np.array([0]))
        self.reference = float(raw[0])

    def raw(self, a, b):
        """Return (BF16 phase, float32 periodic output) with no truth correction.

        Each row of X is [normalized a, normalized b, constant 1]. The SDK
        computes X @ W.T, materializes its result, then evaluates tcos(phase).
        There is no additional fixed-point quantizer, noise or deadband.
        Both arrays preserve the caller's shape; input arrays are never changed.
        """
        a, b = np.asarray(a), np.asarray(b)
        if a.shape != b.shape or a.size == 0:
            raise ValueError("Nonempty equally shaped pair arrays are required")
        for keys in (a, b):
            if not np.issubdtype(keys.dtype, np.integer):
                raise ValueError("Keys must have an integer dtype")
            if np.any(keys < 0) or np.any(keys >= self.scale):
                raise ValueError("Key outside the declared unsigned domain")
        features = np.ones((a.size, 3), dtype=bfloat16)
        features[:, 0] = a.reshape(-1) / self.scale
        features[:, 1] = b.reshape(-1) / self.scale
        phase = qant.native.linear_fprop(features, self.weights)
        if phase.shape != (a.size, 1) or phase.dtype != np.dtype(bfloat16):
            raise AssertionError("Unexpected linear SDK output contract")
        phase = np.ascontiguousarray(phase.reshape(-1))
        raw = qant.native.calc_scaled_periodic_nl_fprop(
            phase, np.ones(phase.shape, dtype=bfloat16))
        if raw.shape != phase.shape or raw.dtype != np.dtype(bfloat16):
            raise AssertionError("Unexpected periodic SDK output contract")
        return phase.reshape(a.shape), raw.astype(np.float32).reshape(a.shape)

    def __call__(self, a, b):
        """Subtract the single calibrated zero and return the unmodified score."""
        return self.raw(a, b)[1] - self.reference


def comparator(path, bits):
    """Construct one candidate/control with a fixed reference for one run.

    The host-phase control is the existing noiseless mapping. The direct
    control stops at the SDK difference; neither control repairs the candidate.
    """
    if path == "affine_phase":
        return AffinePeriodicComparison(bits)
    difference = SdkDifference(bits)
    if path == "direct_difference":
        return difference
    if path == "host_phase":
        reference = calibration_reference()
        return lambda a, b: periodic_values(difference(a, b)) - reference
    raise ValueError(f"Unknown comparison path: {path}")


def pair_checks(arrays):
    """Enumerate every ordered pair; save scores including all failed pairs.

    Minimum unequal magnitude INCLUDES zeros. The nonzero-only minimum is
    separately labelled and cannot be interpreted as an available noise margin.
    A representative product trace shows where BF16 information can be lost.
    """
    rows = []
    for bits in (4, 8):
        levels = 2 ** bits
        a, b = np.meshgrid(np.arange(levels), np.arange(levels), indexing="ij")
        expected = np.sign(a - b)
        for path in ("direct_difference", "host_phase", "affine_phase"):
            model = comparator(path, bits)
            if path == "affine_phase":
                phase, raw = model.raw(a, b)
                score = raw - model.reference
                arrays[f"pairs_b{bits}_phase"] = phase.astype(np.float32)
            else:
                score = model(a, b)
            arrays[f"pairs_b{bits}_{path}_score"] = score
            sign = np.sign(score)
            failures = sign != expected
            unequal = a != b
            nonzero = unequal & (score != 0)
            row = dict(bits=bits, path=path, ordered_pairs=a.size,
                       errors=int(failures.sum()),
                       false_ties=int(np.count_nonzero(unequal & (score == 0))),
                       sign_reversals=int(np.count_nonzero(sign * expected < 0)),
                       broken_true_ties=int(np.count_nonzero(~unequal & (score != 0))),
                       minimum_unequal_magnitude=float(np.min(abs(score[unequal]))),
                       minimum_nonzero_unequal_magnitude=(float(np.min(abs(score[nonzero])))
                                                          if nonzero.any() else None))
            if path == "affine_phase":
                row["reference"] = model.reference
                row["encoded_weights"] = model.weights.astype(np.float32).tolist()
                row["first_failures"] = []
                for ai, bi in np.argwhere(failures)[:8]:
                    # Diagnostic only, after inference: CPU SDK source specifies
                    # BF16 products, FP32 accumulation and BF16 final output.
                    products = np.array([ai / levels, bi / levels, 1], dtype=bfloat16) * model.weights[0]
                    row["first_failures"].append(dict(a=int(ai), b=int(bi),
                        phase=float(phase[ai, bi]), score=float(score[ai, bi]),
                        products_bf16=products.astype(np.float32).tolist()))
            elif row["errors"]:
                raise AssertionError(f"Noiseless control failed: {row}")
            rows.append(row)
    return rows


def run(output_dir):
    """Check pinned identities, run finite controls, and write a fresh evidence set.

    Refuse an existing destination so historical outputs cannot be overwritten.
    Record installed dependencies rather than relabelling the older environment.
    A candidate failure is retained and reported; a failed control aborts.
    """
    identity = require_cpu_backend()
    if identity["sdk_version"] != "2.3.1":
        raise RuntimeError("This registered control requires SDK 2.3.1")
    if output_dir.exists():
        raise FileExistsError(f"Choose a fresh output directory: {output_dir}")
    archive = ROOT / "vendor/qant-native-computing-toolkit-wheels-cpu-backend-v2.3.1.zip"
    if file_hash(ROOT / "data/inputs.npz") != INPUT_SHA256 or file_hash(archive) != SDK_ARCHIVE_SHA256:
        raise RuntimeError("Pinned input or SDK archive hash mismatch")
    arrays = {}
    pairs = pair_checks(arrays)
    output_dir.mkdir(parents=True)
    np.savez_compressed(output_dir / "outputs.npz", **arrays)
    report = dict(sdk=identity, python=platform.python_version(), platform=platform.platform(),
        packages={p: importlib.metadata.version(p) for p in ("numpy", "ml-dtypes", "cffi", "pycparser")},
        hardware_executed=False, added_noise=False, extra_quantizer=False, deadband=0,
        phase_constants=dict(u0=U0, alpha=ALPHA),
        calibration="One same-path (0,0) evaluation per affine instance; no per-pair correction",
        scope="Comparator feasibility only; periodic scores do not implement the canonical full-matrix rank bias",
        input_sha256=INPUT_SHA256, sdk_archive_sha256=SDK_ARCHIVE_SHA256,
        source_sha256=source_hashes(),
        outputs_sha256=file_hash(output_dir / "outputs.npz"), pairs=pairs)
    (output_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(pairs=pairs), indent=2))


if __name__ == "__main__":
    # Importing this file does not execute the experiment or write any files.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/affine_periodic_reproduced")
    run(parser.parse_args().output_dir)
