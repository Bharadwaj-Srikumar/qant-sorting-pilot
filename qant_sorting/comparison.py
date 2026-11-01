"""Input validation and the main matched-step comparison model.

For registered width b, keys become x/2**b and sigma = eta/2**b.
Output rounding uses the same step but a signed range [-1/2, 1/2-step].
This is an assumed sensitivity model, not measured Q.ANT device noise.
"""

from dataclasses import dataclass
import numbers

import numpy as np


def validate_keys(keys, key_bits):
    """Return an independent int64 array of valid whole-number keys.

    Accept a nonempty 1-D list or 2-D batch in [0, 2**key_bits - 1].
    Integral floats are allowed; booleans, strings, fractions and nonfinite
    values are rejected with their zero-based position. Widths 1..30 are
    valid here; the registered experiment separately restricts precision.
    """
    if (
        not isinstance(key_bits, int)
        or isinstance(key_bits, bool)
        or not 1 <= key_bits <= 30
    ):
        raise ValueError('key_bits must be an integer from 1 to 30')

    # Preserve bool/string types until validation; convert only afterward.
    a = np.asarray(keys, dtype=object)
    if a.ndim not in (1, 2) or 0 in a.shape:
        raise ValueError('keys must be a nonempty array or a rectangular batch of arrays')
    maximum = 2**key_bits - 1
    for index, value in np.ndenumerate(a):
        location = (
            'input index %d' % index[0] if a.ndim == 1
            else 'array index %d, key index %d' % index
        )
        ok = not isinstance(value, (bool, np.bool_)) and (
            isinstance(value, numbers.Integral) or
            (isinstance(value, numbers.Real) and np.isfinite(float(value))
             and float(value).is_integer()))
        if not ok or not 0 <= value <= maximum:
            raise ValueError(f'{location}: key {value!r} must be a finite whole number in range [0, {maximum}]')
    return a.astype(np.int64)


@dataclass(frozen=True)
class Precision:
    """Record the registered key, input and output widths.

    Only (4,4,4) and (8,8,8) are supported. Keeping separate fields makes
    the matched-width assumption explicit.
    """

    key_bits: int
    input_bits: int
    output_bits: int

    def __post_init__(self):
        """Reject mixed widths and non-integer width declarations."""
        widths = (self.key_bits, self.input_bits, self.output_bits)
        if any(type(width) is not int for width in widths):
            raise ValueError("Bit widths must be integers")
        if widths not in ((4, 4, 4), (8, 8, 8)):
            raise ValueError("This evaluation supports (4,4,4) and (8,8,8) only")

    @property
    def delta_in(self):
        """Normalized spacing between input keys: 2**(-input_bits)."""
        return 1 / 2**self.input_bits

    @property
    def delta_out(self):
        """Output spacing; signed codes cover [-1/2, 1/2 - delta_out]."""
        return 1 / 2**self.output_bits


class NoisyDifference:
    """Normalize key pairs, add Gaussian noise, then round and saturate.

    The callable returns measured differences shaped like its inputs.
    Generators and diagnostic counts persist across calls, including the
    successive layers of a Bitonic sort. Raw keys must be validated first.
    """

    counter_names = (
        "comparisons", "saturations", "false_ties", "sign_reversals",
        "broken_true_ties",
    )

    def __init__(self, precision, eta=0.0, seed_context=(), trial_ids=()):
        """Set sigma = eta * delta_out and create one stream per trial.

        Keep absolute trial IDs when splitting batches. eta=0 creates no
        generators; positive eta consumes fresh samples on every call.
        """
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
        """Measure equally shaped key pairs, normally (trials, pairs).

        With noise enabled, each row uses its configured trial generator.
        The signed quantizer preserves noiseless sign but can lose magnitude.
        Diagnostics observe errors without correcting the returned scores.
        """
        if a.shape != b.shape:
            raise ValueError("Both pair arrays must have the same shape")
        delta_in = self.precision.delta_in
        delta_out = self.precision.delta_out

        # Registered integer keys already lie exactly on the input grid.
        qa = np.rint((a * delta_in) / delta_in) * delta_in
        qb = np.rint((b * delta_in) / delta_in) * delta_in
        noisy = qa - qb

        if self.eta:
            if a.ndim != 2 or len(self.rngs) != a.shape[0]:
                raise ValueError("Noisy batches need one trial seed per input row")
            noisy = noisy + np.stack([
                rng.normal(0, self.sigma, a.shape[1:]) for rng in self.rngs
            ])

        # Nearest-even rounding, then saturation of signed integer codes.
        codes = np.rint(noisy / delta_out)
        half_levels = 2 ** (self.precision.output_bits - 1)
        low, high = -half_levels, half_levels - 1
        measured = np.clip(codes, low, high) * delta_out

        # True-key checks only count errors; they never repair measured.
        self.comparisons += a.size
        self.saturations += int(np.count_nonzero((codes < low) | (codes > high)))
        self.false_ties += int(np.count_nonzero((a != b) & (measured == 0)))
        self.sign_reversals += int(np.count_nonzero(
            ((a > b) & (measured < 0)) | ((a < b) & (measured > 0))
        ))
        self.broken_true_ties += int(np.count_nonzero((a == b) & (measured != 0)))
        return measured
