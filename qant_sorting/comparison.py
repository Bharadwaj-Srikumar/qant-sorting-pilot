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


# Self-tests
# Matched-step mathematical controls, input validation and seeded noise checks.
# Run with: python -m unittest qant_sorting.comparison -v

import math
import unittest


class ComparisonTests(unittest.TestCase):
    """Independent controls for the assumed comparison sensitivity model."""

    # Exhaustively prove the current matched-step model preserves all 4/8-bit signs,
    # including equal pairs, even though some large magnitudes saturate.
    def test_every_noiseless_pair_has_the_correct_sign(self):
        for bits in (4, 8):
            a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing="ij")
            model = NoisyDifference(Precision(bits, bits, bits))
            actual = model(a, b)
            np.testing.assert_array_equal(np.sign(actual), np.sign(a - b))
            self.assertEqual(model.false_ties, 0)
            self.assertGreater(model.saturations, 0)

    # Check explicit 8-bit adjacent, positive/negative extreme and equality outputs.
    # These numerical fixtures catch wrong step size or asymmetric signed endpoints.
    def test_adjacent_example_and_saturation(self):
        model = NoisyDifference(Precision(8, 8, 8))
        a = np.array([[10, 255, 0, 9]])
        b = np.array([[9, 0, 255, 9]])
        np.testing.assert_array_equal(model(a, b), [[1 / 256, 127 / 256, -0.5, 0]])

    # Reject malformed keys before normalization, and retain a useful array/key
    # location in the error message so an invalid dataset can be corrected.
    def test_invalid_keys_report_the_location_and_range(self):
        with self.assertRaisesRegex(ValueError, r"array index 1, key index 0.*\[0, 15\]"):
            validate_keys([[1, 2], [16, 0]], 4)
        for invalid in (-1, 1.5, np.inf, True, "2"):
            with self.assertRaises(ValueError):
                validate_keys([invalid], 4)

    # Require unsupported mixed precision to fail instead of quietly changing
    # the agreed matched-width quantization/noise experiment.
    def test_unequal_widths_are_not_silently_assumed(self):
        with self.assertRaises(ValueError):
            Precision(4, 4, 8)

    # Check negative, NaN and infinite eta values are rejected before RNG use.
    # Otherwise a malformed parameter could yield uninterpretable comparison scores.
    def test_invalid_noise_is_rejected(self):
        for eta in (-0.1, np.nan, np.inf):
            with self.assertRaises(ValueError):
                NoisyDifference(Precision(4, 4, 4), eta)

    # Compare seeded Monte Carlo with an independently written Gaussian-tail formula.
    # The false-tie interval is [-1.5,-0.5] output steps for a +1-step difference.
    def test_adjacent_false_tie_probability_uses_half_step_boundary(self):
        # An independent units check: 1 + noise rounds to zero for noise
        # between -1.5 and -0.5 output steps. This is NOT a hardware fit.
        noise = np.random.default_rng(20261004).normal(0, 0.25, 200000)
        observed = np.mean(np.rint(1 + noise) == 0)
        expected = 0.5 * (math.erfc(2 / math.sqrt(2)) - math.erfc(6 / math.sqrt(2)))
        self.assertLess(abs(observed - expected), 0.002)
