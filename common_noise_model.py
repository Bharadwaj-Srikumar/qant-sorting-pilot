"""Explicit, dimensionless sensitivity model; not a Q.ANT device simulator.

All *_lsb settings use the original normalized key step 2**(-bits).
The ideal sine is divided by its zero-point slope, so output units match
input units locally. BF16 and physical tcos are deliberately not emulated.
"""

from dataclasses import dataclass
import numpy as np

ALPHA = np.pi / 2
ELEMENTARY_CHARGE_C = 1.602176634e-19


@dataclass(frozen=True)
class NoiseConfig:
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
        return 2.0 ** (-self.bits)


def quantize(value, step):
    """Nearest-even, zero-centred uniform quantizer. step=0 disables it.

    Clipping belongs to explicit pipeline stages, not this function. No
    independent uniform quantization noise is added on top of rounding.
    """
    value = np.asarray(value, dtype=np.float64)
    if not np.isfinite(step) or step < 0:
        raise ValueError("Quantizer step must be finite and nonnegative")
    return np.rint(value / step) * step if step else value.copy()


def transfer_value(value, kind):
    if kind == "direct":
        return np.asarray(value, dtype=np.float64)
    if kind == "ideal_sine":
        return np.sin(ALPHA * np.asarray(value, dtype=np.float64)) / ALPHA
    raise ValueError("Unknown transfer")


def evaluate_difference(difference, config, upstream_standard=0.0, readout_standard=0.0):
    """Evaluate one signal path, with externally supplied N(0,1) samples.

    Clipping to [-1,1] keeps the sine on its monotone branch. This is an
    assumed model range, not a manufacturer-approved phase/input range.
    Fixed offsets represent a residual held constant during an experiment.
    """
    c = config
    d, zu, zr = np.broadcast_arrays(np.asarray(difference, dtype=np.float64),
                                    upstream_standard, readout_standard)
    if not (np.isfinite(d).all() and np.isfinite(zu).all() and np.isfinite(zr).all()):
        raise ValueError("Signals and supplied noise samples must be finite")
    analog = d + c.delta * (c.input_drift_lsb + c.upstream_sigma_lsb * zu)
    pre = np.clip(quantize(analog, c.pre_step_lsb * c.delta), -1, 1)
    score = (1 + c.gain_error) * transfer_value(pre, c.transfer)
    analog_output = score + c.delta * (c.output_drift_lsb + c.readout_sigma_lsb * zr)
    output = np.clip(quantize(analog_output, c.post_step_lsb * c.delta), -1, 1)
    return output, {
        "input_range_exceeded": int(np.count_nonzero(np.abs(analog) > 1)),
        "output_range_exceeded": int(np.count_nonzero(np.abs(analog_output) > 1)),
    }


class CommonNoiseComparison:
    """Drop-in comparator for the existing schedules, with per-trial streams.

    Noise stages have separate streams. Changing a stage's sigma does not
    shift the other stage's samples. Common seeds pair transfer variants;
    they do not assert physically correlated devices or reuse noise by key.
    """
    def __init__(self, config, trial_ids, seed_context=(20261007, 3)):
        self.config = config
        ids = list(trial_ids)
        self.streams = [[np.random.default_rng(np.random.SeedSequence(
            [*seed_context, int(i), stage])) for i in ids] for stage in (0, 1)]
        self.counts = dict(comparisons=0, input_range_exceeded=0, output_range_exceeded=0)

    def __call__(self, a, b):
        a, b = np.asarray(a), np.asarray(b)
        if a.shape != b.shape or a.ndim != 2 or len(a) != len(self.streams[0]):
            raise ValueError("Expected equal 2-D pair arrays and one stream per trial")
        for values in (a, b):
            if values.dtype.kind not in "iu" or np.any(values < 0) or np.any(values >= 2**self.config.bits):
                raise ValueError("Keys must be integers in the declared domain")
        # Cast BEFORE subtraction: uint8 subtraction would wrap.
        d = (a.astype(np.float64) - b.astype(np.float64)) * self.config.delta
        samples = [np.stack([rng.standard_normal(a.shape[1:]) for rng in streams])
                   for streams in self.streams]
        result, diagnostic = evaluate_difference(d, self.config, *samples)
        self.counts["comparisons"] += a.size
        for name, value in diagnostic.items():
            self.counts[name] += value
        return result


def receiver_current_variance(current_a, bandwidth_hz, rin_db_per_hz, thermal_psd_a2_per_hz):
    """Single photodiode: white, one-sided PSDs over equivalent noise bandwidth.

    Returns A², with RIN I², shot 2qI, and thermal current PSD contributions.
    This helper needs explicit measured/assumed inputs; it is NOT a fitted
    Q.ANT receiver. For balanced receivers use branch currents/covariances,
    never substitute the signed difference current into the shot-noise term.
    """
    current = np.asarray(current_a, dtype=np.float64)
    if (not np.isfinite(current).all() or np.any(current < 0)
            or not np.isfinite(bandwidth_hz) or bandwidth_hz < 0
            or not np.isfinite(rin_db_per_hz)
            or not np.isfinite(thermal_psd_a2_per_hz) or thermal_psd_a2_per_hz < 0):
        raise ValueError("Invalid physical receiver inputs")
    return bandwidth_hz * (thermal_psd_a2_per_hz + 2 * ELEMENTARY_CHARGE_C * current
                           + 10.0 ** (rin_db_per_hz / 10) * current**2)


def projected_variance(jacobian, covariance):
    """First-order scalar propagation J Sigma J^T, retaining correlations."""
    j, cov = np.asarray(jacobian, dtype=float), np.asarray(covariance, dtype=float)
    if (j.ndim != 1 or cov.shape != (len(j), len(j)) or not np.isfinite(j).all()
            or not np.isfinite(cov).all() or not np.allclose(cov, cov.T, rtol=1e-12, atol=0)):
        raise ValueError("Expected finite vector and symmetric covariance")
    scale = max(float(np.max(np.abs(cov))), np.finfo(float).tiny)
    if np.linalg.eigvalsh(cov).min() < -1e-12 * scale:
        raise ValueError("Covariance must be positive semidefinite")
    return max(0.0, float(j @ cov @ j))
