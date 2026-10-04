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


class ModelTests(unittest.TestCase):
    def test_every_noiseless_pair_has_the_correct_sign(self):
        for bits in (4, 8):
            a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing="ij")
            model = NoisyDifference(Precision(bits, bits, bits))
            actual = model(a, b)
            np.testing.assert_array_equal(np.sign(actual), np.sign(a - b))
            self.assertEqual(model.false_ties, 0)
            self.assertGreater(model.saturations, 0)

    def test_adjacent_example_and_saturation(self):
        model = NoisyDifference(Precision(8, 8, 8))
        a = np.array([[10, 255, 0, 9]])
        b = np.array([[9, 0, 255, 9]])
        np.testing.assert_array_equal(model(a, b), [[1 / 256, 127 / 256, -0.5, 0]])

    def test_invalid_keys_report_the_location_and_range(self):
        with self.assertRaisesRegex(ValueError, r"array index 1, key index 0.*\[0, 15\]"):
            validate_keys([[1, 2], [16, 0]], 4)
        for invalid in (-1, 1.5, np.inf, True, "2"):
            with self.assertRaises(ValueError):
                validate_keys([invalid], 4)

    def test_unequal_widths_are_not_silently_assumed(self):
        with self.assertRaises(ValueError):
            Precision(4, 4, 8)

    def test_invalid_noise_is_rejected(self):
        for eta in (-0.1, np.nan, np.inf):
            with self.assertRaises(ValueError):
                NoisyDifference(Precision(4, 4, 4), eta)

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

    def test_all_small_binary_inputs_sort_stably(self):
        # Exhaustive binary inputs exercise repeated keys and both directions
        # in the bitonic network, using an independent stable digital oracle.
        for n in (2, 4, 8):
            data = np.array(list(itertools.product((0, 1), repeat=n)))
            for sorter in (bitonic_sort, rank_sort):
                model = NoisyDifference(Precision(4, 4, 4))
                self.assertTrue(reference_flags(data, sorter(data, model)).all())

    def test_rank_cycles_fail_without_repair(self):
        # 0 beats 1, 1 beats 2, 2 beats 0: each gets rank 1, so placement fails.
        data = np.array([[3, 1, 2]])
        result = rank_sort(data, lambda a, b: np.array([[1, -1, 1]]))
        self.assertFalse(result[2][0])
        np.testing.assert_array_equal(result[0], [[-1, -1, -1]])

    def test_record_checks_detect_lost_or_changed_keys(self):
        data = np.array([[1, 2]])
        bad = (np.array([[1, 1]]), np.array([[0, 0]]), np.array([True]))
        self.assertFalse(reference_flags(data, bad).any())

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

    def test_adjacent_false_tie_probability_uses_half_step_boundary(self):
        # An independent units check: 1 + noise rounds to zero for noise
        # between -1.5 and -0.5 output steps. This is NOT a hardware fit.
        noise = np.random.default_rng(20261004).normal(0, 0.25, 200000)
        observed = np.mean(np.rint(1 + noise) == 0)
        expected = 0.5 * (math.erfc(2 / math.sqrt(2)) - math.erfc(6 / math.sqrt(2)))
        self.assertLess(abs(observed - expected), 0.002)


if __name__ == "__main__":
    unittest.main()
