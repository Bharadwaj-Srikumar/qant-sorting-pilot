"""Optional CPU integration tests for a deliberately fallible affine candidate.

These tests check a real precision counterexample and input contracts; they do
not redefine the candidate as a correct 8-bit comparator. No evidence is saved.
"""
import unittest

import numpy as np

try:
    from qant_sorting.experiments.check_affine_periodic import AffinePeriodicComparison, comparator
except ImportError:
    AffinePeriodicComparison = None


@unittest.skipIf(AffinePeriodicComparison is None, "optional Q.ANT CPU SDK not installed")
class AffinePeriodicTests(unittest.TestCase):
    """Keep true equality, precision loss and controls independently observable."""

    def test_equal_keys_use_one_reference(self):
        """Every equality must match the reference measured only at (0,0)."""
        for bits in (4, 8):
            keys = np.arange(2 ** bits)
            np.testing.assert_array_equal(AffinePeriodicComparison(bits)(keys, keys), 0)

    def test_adjacent_8bit_counterexample_is_not_repaired(self):
        """BF16 affine products erase this difference; the other paths retain it."""
        a, b = np.array([165, 166, 165]), np.array([166, 165, 165])
        model = AffinePeriodicComparison(8)
        phase, _ = model.raw(a, b)
        np.testing.assert_array_equal(phase.astype(float), [1.5703125] * 3)
        np.testing.assert_array_equal(model(a, b), [0, 0, 0])
        for path in ("direct_difference", "host_phase"):
            np.testing.assert_array_equal(np.sign(comparator(path, 8)(a, b)), [-1, 1, 0])

    def test_shape_domain_and_input_preservation(self):
        """Reject malformed inputs instead of silently clipping or broadcasting."""
        model = AffinePeriodicComparison(4)
        keys = np.array([[0, 15], [7, 8]])
        original = keys.copy()
        self.assertEqual(model(keys, keys).shape, keys.shape)
        np.testing.assert_array_equal(keys, original)
        for a, b in (([0], [0, 1]), ([], []), ([-1], [0]), ([16], [0]),
                     ([0.0], [0.0]), ([True], [False])):
            with self.assertRaises(ValueError):
                model(a, b)
        with self.assertRaises(ValueError):
            AffinePeriodicComparison(7)


if __name__ == "__main__":
    unittest.main()
