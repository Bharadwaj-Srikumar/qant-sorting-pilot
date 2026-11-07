"""Quantized pairwise subtraction with optional Gaussian noise."""

import numbers
from dataclasses import dataclass

import numpy as np


def validate_keys(keys, key_bits):
    """Validate a key array or (trials, N) batch and return int64 values."""
    if (
        not isinstance(key_bits, int)
        or isinstance(key_bits, bool)
        or not 1 <= key_bits <= 30
    ):
        raise ValueError('key_bits must be an integer from 1 to 30')

    a = np.asarray(keys, dtype=object)
    if a.ndim not in (1, 2) or 0 in a.shape:
        raise ValueError('keys must be a nonempty array or a rectangular batch of arrays')
    maximum = 2**key_bits - 1
    for index, value in np.ndenumerate(a):
        ok = not isinstance(value, (bool, np.bool_)) and (
            isinstance(value, numbers.Integral) or
            (isinstance(value, numbers.Real) and np.isfinite(float(value))
             and float(value).is_integer()))
        if not ok or not 0 <= value <= maximum:
            location = (
                'input index %d' % index[0] if a.ndim == 1
                else 'array index %d, key index %d' % index
            )
            raise ValueError(f'{location}: key {value!r} must be a finite whole number in range [0, {maximum}]')
    return a.astype(np.int64)


@dataclass(frozen=True)
class Precision:
    """Matched 4- or 8-bit widths for stored keys, inputs, and differences."""

    key_bits: int
    input_bits: int
    output_bits: int

    def __post_init__(self):
        """Reject unsupported or noninteger precision settings."""
        widths = (self.key_bits, self.input_bits, self.output_bits)
        if any(type(width) is not int for width in widths):
            raise ValueError("Bit widths must be integers")
        if widths not in ((4, 4, 4), (8, 8, 8)):
            raise ValueError("This evaluation supports (4,4,4) and (8,8,8) only")

    @property
    def delta_in(self):
        """Spacing between consecutive encoded input keys."""
        return 1 / 2**self.input_bits

    @property
    def delta_out(self):
        """Spacing between consecutive quantized difference levels."""
        return 1 / 2**self.output_bits


class NoisyDifference:
    """Callable subtraction model with per-trial noise and diagnostic counters."""

    counter_names = (
        "comparisons", "saturations", "false_ties", "sign_reversals",
        "broken_true_ties",
    )

    def __init__(self, precision, eta=0.0, seed_context=(), trial_ids=()):
        """Set noise standard deviation to eta output steps and seed each trial."""
        if not np.isfinite(eta) or eta < 0:
            raise ValueError("eta must be finite and nonnegative")
        self.precision = precision
        self.eta = eta
        self.sigma = eta * precision.delta_out

        self.rngs = [
            np.random.default_rng(np.random.SeedSequence([*seed_context, int(i)]))
            for i in trial_ids
        ] if eta else []
        for name in self.counter_names:
            setattr(self, name, 0)

    def __call__(self, a, b):
        """Return normalized (a - b) after noise, rounding, and clipping.

        Arrays have equal shapes; noisy inputs use (trials, pairs). Preserve
        that shape in the output and update diagnostic counters.
        """
        if a.shape != b.shape:
            raise ValueError("Both pair arrays must have the same shape")
        delta_in = self.precision.delta_in
        delta_out = self.precision.delta_out

        qa = a * delta_in
        qb = b * delta_in
        noisy = qa - qb

        if self.eta:
            if a.ndim != 2 or len(self.rngs) != a.shape[0]:
                raise ValueError("Noisy batches need one trial seed per input row")
            noisy = noisy + np.stack([
                rng.normal(0, self.sigma, a.shape[1:]) for rng in self.rngs
            ])

        codes = np.rint(noisy / delta_out)
        half_levels = 2 ** (self.precision.output_bits - 1)
        low, high = -half_levels, half_levels - 1
        measured = np.clip(codes, low, high) * delta_out

        self.comparisons += a.size
        self.saturations += int(np.count_nonzero((codes < low) | (codes > high)))
        self.false_ties += int(np.count_nonzero((a != b) & (measured == 0)))
        self.sign_reversals += int(np.count_nonzero(
            ((a > b) & (measured < 0)) | ((a < b) & (measured > 0))
        ))
        self.broken_true_ties += int(np.count_nonzero((a == b) & (measured != 0)))
        return measured
