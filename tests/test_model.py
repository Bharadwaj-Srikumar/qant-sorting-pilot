# Test guide: current matched-step comparator and routing invariants.
# The filename is historical; these tests import comparison.py, NOT model.py.
# They test signs, equality, saturation, stable record routing and seeded noise.
# Small exhaustive examples and deliberately inconsistent rank decisions test
# properties independently of the large saved experiment. No SDK is required.

"""Independent mathematical controls plus record/seed regression checks.

Run from the project directory: python -m unittest discover -s tests -v
These tests require NumPy only; the SDK control is a separate optional run.
"""

import itertools
import math
import unittest

import numpy as np

from comparison import NoisyDifference, Precision
from input_validation import validate_keys
from metrics import reference_flags
from sorting_schedules import bitonic_sort, compact_bitonic_layers, rank_sort


# Unit-test group: independent contracts and edge cases for this module family.
# Each method creates its own fixtures/streams, so tests do not depend on order
# or change the stored research corpus and reference result archives.
class ModelTests(unittest.TestCase):
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

    # Check layer-count formulas and that every wire belongs to exactly one pair
    # per layer. Also reject non-power-of-two N rather than generating invalid wiring.
    def test_network_layers_and_work(self):
        for n in (2, 4, 8, 16, 32, 64, 128, 256):
            layers = compact_bitonic_layers(n)
            m = n.bit_length() - 1
            self.assertEqual(len(layers), m * (m + 1) // 2)
            for left, right, ascending in layers:
                np.testing.assert_array_equal(np.sort(np.r_[left, right]), np.arange(n))
                self.assertEqual(len(ascending), n // 2)
        with self.assertRaises(ValueError):
            compact_bitonic_layers(3)

    # Enumerate all binary arrays at N=2,4,8 and compare against a separate stable
    # reference. Binary inputs stress duplicate routing and both bitonic directions.
    def test_all_small_binary_inputs_sort_stably(self):
        # Exhaustive binary inputs exercise repeated keys and both directions
        # in the bitonic network, using an independent stable digital oracle.
        for n in (2, 4, 8):
            data = np.array(list(itertools.product((0, 1), repeat=n)))
            for sorter in (bitonic_sort, rank_sort):
                model = NoisyDifference(Precision(4, 4, 4))
                self.assertTrue(reference_flags(data, sorter(data, model)).all())

    # Inject a cyclic three-way relation with no consistent total order. Require
    # invalid output and -1 markers, proving collisions are not hidden by digital repair.
    def test_rank_cycles_fail_without_repair(self):
        # 0 beats 1, 1 beats 2, 2 beats 0: each gets rank 1, so placement fails.
        data = np.array([[3, 1, 2]])
        result = rank_sort(data, lambda a, b: np.array([[1, -1, 1]]))
        self.assertFalse(result[2][0])
        np.testing.assert_array_equal(result[0], [[-1, -1, -1]])

    # Present duplicated/lost record identities despite a claimed valid flag.
    # The independent scorer must reject them rather than trusting the sorter.
    def test_record_checks_detect_lost_or_changed_keys(self):
        data = np.array([[1, 2]])
        bad = (np.array([[1, 1]]), np.array([[0, 0]]), np.array([True]))
        self.assertFalse(reference_flags(data, bad).any())

    # Run identical trial IDs as one batch and several chunks for both schedules.
    # Exact tuple equality verifies memory batching does not redefine the noise process.
    def test_noise_is_invariant_to_batch_partition(self):
        data = np.random.default_rng(47).integers(0, 256, (23, 16))
        precision = Precision(8, 8, 8)
        for stream, sorter in enumerate((bitonic_sort, rank_sort), 1):
            context = [20260930, 8, 8, 8, 16, 1, 2, stream]
            whole = sorter(data, NoisyDifference(precision, 0.25, context, range(23)))
            chunks = []
            for start in range(0, 23, 5):
                stop = min(start + 5, 23)
                model = NoisyDifference(precision, 0.25, context, range(start, stop))
                chunks.append(sorter(data[start:stop], model))
            for i in range(3):
                np.testing.assert_array_equal(whole[i], np.concatenate([part[i] for part in chunks]))

    # Compare seeded Monte Carlo with an independently written Gaussian-tail formula.
    # The false-tie interval is [-1.5,-0.5] output steps for a +1-step difference.
    def test_adjacent_false_tie_probability_uses_half_step_boundary(self):
        # An independent units check: 1 + noise rounds to zero for noise
        # between -1.5 and -0.5 output steps. This is NOT a hardware fit.
        noise = np.random.default_rng(20261004).normal(0, 0.25, 200000)
        observed = np.mean(np.rint(1 + noise) == 0)
        expected = 0.5 * (math.erfc(2 / math.sqrt(2)) - math.erfc(6 / math.sqrt(2)))
        self.assertLess(abs(observed - expected), 0.002)


# Direct execution starts this file's command-line/test entry point.
# Importing helpers does not run THIS block; the module reading guide
# identifies any other top-level file loading or writing separately.
if __name__ == "__main__":
    unittest.main()
