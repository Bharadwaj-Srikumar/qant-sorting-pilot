"""Shared upstream/transfer/readout sensitivity model.

Flow: difference -> upstream noise/offset -> optional rounding -> clipping
-> normalized transfer/gain -> readout noise/offset -> rounding/clipping.
The Float64 sine, [-1,1] limits and noise independence are assumptions,
not a calibrated Q.ANT circuit or the official BF16 periodic CPU backend.
"""

from dataclasses import dataclass

import numpy as np

ALPHA = np.pi / 2
ELEMENTARY_CHARGE_C = 1.602176634e-19


@dataclass(frozen=True)
class NoiseConfig:
    """Settings for the shared Float64 signal channel.

    All *_lsb values use the original key step delta=2**(-bits).
    Zero quantizer steps disable rounding. Offsets are fixed during a run;
    noise strengths are standard deviations, not constant additions.
    """
    bits: int
    transfer: str = "direct"
    upstream_sigma_lsb: float = 0.0
    readout_sigma_lsb: float = 0.0
    pre_step_lsb: float = 0.0
    post_step_lsb: float = 1.0
    input_drift_lsb: float = 0.0
    output_drift_lsb: float = 0.0
    gain_error: float = 0.0

    def __post_init__(self):
        """Check finite parameters, nonnegative scales and positive gain."""
        if self.bits not in (4, 8) or self.transfer not in ("direct", "ideal_sine"):
            raise ValueError("Expected 4/8-bit keys and direct/ideal_sine transfer")
        for name in ("upstream_sigma_lsb", "readout_sigma_lsb", "pre_step_lsb", "post_step_lsb",
                     "input_drift_lsb", "output_drift_lsb", "gain_error"):
            value = getattr(self, name)
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if name.endswith(("sigma_lsb", "step_lsb")) and value < 0:
                raise ValueError(f"{name} must be nonnegative")
        if self.gain_error <= -1:
            raise ValueError("Gain must remain positive")

    @property
    def delta(self):
        """Original normalized key step, not BF16 spacing or measured ENOB."""
        return 2.0 ** (-self.bits)


def quantize(value, step):
    """Round to nearest-even multiples of step; zero disables rounding.

    Clipping is handled by evaluate_difference. No additional independent
    quantization-noise variance is added to this deterministic operation.
    """
    value = np.asarray(value, dtype=np.float64)
    if not np.isfinite(step) or step < 0:
        raise ValueError("Quantizer step must be finite and nonnegative")
    return np.rint(value / step) * step if step else value.copy()


def transfer_value(value, kind):
    """Apply identity or sin(alpha*x)/alpha, with unit slope at zero.

    The main pipeline clips inputs to [-1,1], where the sine is monotone.
    This helper itself does not clip or emulate BF16 arithmetic.
    """
    if kind == "direct":
        return np.asarray(value, dtype=np.float64)
    if kind == "ideal_sine":
        return np.sin(ALPHA * np.asarray(value, dtype=np.float64)) / ALPHA
    raise ValueError("Unknown transfer")


def evaluate_difference(difference, config, upstream_standard=0.0, readout_standard=0.0):
    """Transform normalized differences using externally supplied samples.

    Broadcast d, upstream_standard and readout_standard to one shape.
    Each noise sample is scaled by its sigma in key-step units. No random
    numbers are drawn here: omitted samples are zero even at nonzero sigma.
    Return the measured scores and counts of analog range exceedances.
    """
    c = config
    d, zu, zr = np.broadcast_arrays(np.asarray(difference, dtype=np.float64),
                                    upstream_standard, readout_standard)
    if not (np.isfinite(d).all() and np.isfinite(zu).all() and np.isfinite(zr).all()):
        raise ValueError("Signals and supplied noise samples must be finite")

    # Upstream disturbance passes through rounding, clipping and transfer.
    analog = d + c.delta * (c.input_drift_lsb + c.upstream_sigma_lsb * zu)
    pre = np.clip(quantize(analog, c.pre_step_lsb * c.delta), -1, 1)
    score = (1 + c.gain_error) * transfer_value(pre, c.transfer)

    # Readout noise is new noise added after the transfer.
    analog_output = score + c.delta * (c.output_drift_lsb + c.readout_sigma_lsb * zr)
    output = np.clip(quantize(analog_output, c.post_step_lsb * c.delta), -1, 1)
    return output, {
        "input_range_exceeded": int(np.count_nonzero(np.abs(analog) > 1)),
        "output_range_exceeded": int(np.count_nonzero(np.abs(analog_output) > 1)),
    }


class CommonNoiseComparison:
    """Connect raw-key sorters to the shared two-stage channel.

    Each trial has separate upstream and readout generators. Shared seeds
    pair control variants by event position, not by key pair or physical
    correlation between devices.
    """

    def __init__(self, config, trial_ids, seed_context=(20261007, 3)):
        """Create stage/trial streams and counters for one batch.

        Reuse absolute trial IDs when changing batch size. Both stages have
        streams even when a sigma is zero, preserving the draw schedule.
        """
        self.config = config
        ids = list(trial_ids)
        self.streams = [[np.random.default_rng(np.random.SeedSequence(
            [*seed_context, int(i), stage])) for i in ids] for stage in (0, 1)]
        self.counts = dict(comparisons=0, input_range_exceeded=0, output_range_exceeded=0)

    def __call__(self, a, b):
        """Return measured scores for (trials, pairs) integer arrays.

        Validate shape and key range, draw both stages, evaluate the channel,
        and accumulate diagnostics. The sorter alone interprets the scores.
        """
        a, b = np.asarray(a), np.asarray(b)
        if a.shape != b.shape or a.ndim != 2 or len(a) != len(self.streams[0]):
            raise ValueError("Expected equal 2-D pair arrays and one stream per trial")
        for values in (a, b):
            if values.dtype.kind not in "iu" or np.any(values < 0) or np.any(values >= 2**self.config.bits):
                raise ValueError("Keys must be integers in the declared domain")

        # Cast before subtraction so unsigned integers cannot wrap.
        d = (a.astype(np.float64) - b.astype(np.float64)) * self.config.delta
        # Draw both stages even at zero sigma to keep paired streams aligned.
        samples = [np.stack([rng.standard_normal(a.shape[1:]) for rng in streams])
                   for streams in self.streams]
        result, diagnostic = evaluate_difference(d, self.config, *samples)
        self.counts["comparisons"] += a.size
        for name, value in diagnostic.items():
            self.counts[name] += value
        return result


def receiver_current_variance(current_a, bandwidth_hz, rin_db_per_hz, thermal_psd_a2_per_hz):
    """Return one photodiode current variance in A^2.

    Inputs: nonnegative current [A], equivalent bandwidth [Hz], RIN [dB/Hz]
    and thermal current PSD [A^2/Hz]. The formula assumes white, one-sided
    PSDs. Balanced receivers need branch currents and covariance, not a
    signed difference current. No device parameters are supplied by default.
    """
    current = np.asarray(current_a, dtype=np.float64)
    if (not np.isfinite(current).all() or np.any(current < 0)
            or not np.isfinite(bandwidth_hz) or bandwidth_hz < 0
            or not np.isfinite(rin_db_per_hz)
            or not np.isfinite(thermal_psd_a2_per_hz) or thermal_psd_a2_per_hz < 0):
        raise ValueError("Invalid physical receiver inputs")
    # Thermal + shot + RIN power spectral densities, integrated over bandwidth.
    return bandwidth_hz * (thermal_psd_a2_per_hz + 2 * ELEMENTARY_CHARGE_C * current
                           + 10.0 ** (rin_db_per_hz / 10) * current**2)


def projected_variance(jacobian, covariance):
    """Return first-order output variance J @ covariance @ J.

    J is a 1-D Jacobian; covariance must be finite, symmetric and positive
    semidefinite. This retains correlations but does not model large errors
    through nonlinear transfer, clipping or hard quantization exactly.
    """
    j, cov = np.asarray(jacobian, dtype=float), np.asarray(covariance, dtype=float)
    if (j.ndim != 1 or cov.shape != (len(j), len(j)) or not np.isfinite(j).all()
            or not np.isfinite(cov).all() or not np.allclose(cov, cov.T, rtol=1e-12, atol=0)):
        raise ValueError("Expected finite vector and symmetric covariance")
    scale = max(float(np.max(np.abs(cov))), np.finfo(float).tiny)
    if np.linalg.eigvalsh(cov).min() < -1e-12 * scale:
        raise ValueError("Covariance must be positive semidefinite")
    return max(0.0, float(j @ cov @ j))
