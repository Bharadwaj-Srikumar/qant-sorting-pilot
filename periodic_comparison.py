"""A proposed comparison using the official SDK's periodic CPU operation.

This is a hybrid software experiment, not a measured Q.ANT comparator.
The physical tcos curve is only documented as cosine-like. The CPU backend
uses cosine and BF16 I/O. Host code prepares the phase and interprets the
referenced score; original records remain in electronic memory.
"""

import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant

from comparison import Precision
from sdk_mapping import SdkDifference, backend_identity

U0 = np.pi / 2
ALPHA = np.pi / 2


def require_cpu_backend():
    """Prevent an illustrative noise experiment from silently using a device."""
    identity = backend_identity()
    if "cpu-backend" not in identity["driver_info"]:
        raise RuntimeError("This experiment requires the official CPU backend")
    return identity


def periodic_values(difference):
    """Host phase calculation, then one official periodic API call.

    The ideal identity is cos(pi/2 - pi*d/2) = sin(pi*d/2).
    BF16 phase rounding makes the actual CPU result slightly different.
    No b-bit fixed-point output quantizer is added at this new boundary.
    """
    phase = np.ascontiguousarray(
        U0 - ALPHA * difference.reshape(-1), dtype=bfloat16
    )
    amplitudes = np.ones(phase.shape, dtype=bfloat16)
    output = qant.native.calc_scaled_periodic_nl_fprop(phase, amplitudes)
    return output.astype(np.float32).reshape(difference.shape)


def calibration_reference():
    """Use the same BF16/API path at d=0; subtracting it preserves true ties.

    This deterministic, noiseless CPU reference is measured once per run.
    Its noise, drift and recalibration cost on hardware remain unknown.
    """
    return float(periodic_values(np.zeros(1, dtype=np.float32))[0])


class PeriodicComparison:
    """Return a referenced periodic score for the existing sorting schedules.

    upstream: keep the previous Gaussian difference noise, nearest-even
      quantization and clipping, then apply the periodic operation.
    output: use the full noiseless SDK difference; add independent Gaussian
      noise to the referenced periodic score, after BF16 API output.

    For output, sigma=eta/2**bits is a NEW illustrative output-score scale.
    It is not a BF16 ULP, an ENOB claim, or a measured Q.ANT error. No second
    fixed-point output quantizer is used. These scenarios must not be merged.
    """

    def __init__(self, bits, eta, scenario, context, trial_ids, reference, tie_band=0.0):
        if scenario not in ("upstream", "output"):
            raise ValueError("scenario must be upstream or output")
        if not np.isfinite(eta) or eta < 0:
            raise ValueError("eta must be finite and nonnegative")
        self.precision = Precision(bits, bits, bits)
        self.difference = SdkDifference(bits)
        self.eta, self.scenario, self.reference = eta, scenario, reference
        if not np.isfinite(tie_band) or tie_band < 0:
            raise ValueError("tie_band must be finite and nonnegative")
        self.tie_band = tie_band
        self.sigma = eta * self.precision.delta_out
        self.rngs = [np.random.default_rng(np.random.SeedSequence(
            [*context, int(i)])) for i in trial_ids] if eta else []
        self.periodic_calls = 0
        self.comparisons = self.false_ties = self.sign_reversals = 0
        self.broken_true_ties = self.saturations = 0

    def noise(self, shape):
        """One stream per input trial, independent of batching."""
        return np.stack([rng.normal(0, self.sigma, shape[1:])
                         for rng in self.rngs])

    def __call__(self, a, b):
        d = self.difference(a, b)
        if self.scenario == "upstream":
            # Match the established channel, including its signed saturation.
            if self.eta:
                d = d + self.noise(a.shape)
            step = self.precision.delta_out
            codes = np.rint(d / step)
            half = 2 ** (self.precision.output_bits - 1)
            self.saturations += int(np.count_nonzero(
                (codes < -half) | (codes > half - 1)))
            d = np.clip(codes, -half, half - 1) * step

        score = periodic_values(d) - self.reference
        self.periodic_calls += 1
        if self.scenario == "output" and self.eta:
            score = score + self.noise(a.shape)
        # OPTIONAL new sensitivity rule: a calibrated, fixed deadband.
        # Its value is inferred from exhaustive CPU key-pair margins, never
        # from the true keys of the current trial. It is a host threshold.
        if self.tie_band:
            score = np.where(abs(score) <= self.tie_band, 0.0, score)

        # Diagnostics never alter a decision or repair a failed sort.
        self.comparisons += a.size
        self.false_ties += int(np.count_nonzero((a != b) & (score == 0)))
        self.sign_reversals += int(np.count_nonzero(
            ((a > b) & (score < 0)) | ((a < b) & (score > 0))))
        self.broken_true_ties += int(np.count_nonzero(
            (a == b) & (score != 0)))
        return score
