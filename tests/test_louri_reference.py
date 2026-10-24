"""Source fixtures and controls for the equation-level Louri reference."""
import unittest

import numpy as np

from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.louri_reference import (
    comparison_errors, louri_matrix_rank, place_ranks, quantize_difference,
)
from qant_sorting.sorting_schedules import rank_sort


class LouriReferenceTests(unittest.TestCase):
    def test_published_matrices_and_one_based_ranks(self):
        """Literal fixture transcribed from p. 3089, not another rank algorithm."""
        ref = louri_matrix_rank([[7, 8, 2, 8, 5]], 4)
        np.testing.assert_array_equal(ref.difference[0] * 16, [
            [0, 1, -5, 1, -2], [-1, 0, -6, 0, -3], [5, 6, 0, 6, 3],
            [-1, 0, -6, 0, -3], [2, 3, -3, 3, 0]])
        np.testing.assert_array_equal(ref.biased_difference[0] * 16, [
            [0, 1, -5, 1, -2], [-2, 0, -6, 0, -3], [4, 5, 0, 6, 3],
            [-2, -1, -7, 0, -3], [1, 2, -4, 2, 0]])
        np.testing.assert_array_equal(ref.threshold[0], [
            [1, 1, 0, 1, 0], [0, 1, 0, 1, 0], [1, 1, 1, 1, 1],
            [0, 0, 0, 1, 0], [1, 1, 0, 1, 1]])
        np.testing.assert_array_equal(ref.ranks_one_based, [[3, 4, 1, 5, 2]])
        np.testing.assert_array_equal(ref.result[1], [[2, 4, 0, 1, 3]])

    def test_all_equal_keys_keep_original_order(self):
        for bits in (4, 8):
            for quantization in ("none", "matched"):
                ref = louri_matrix_rank([[3, 3, 3, 3]], bits, quantization=quantization)
                np.testing.assert_array_equal(ref.ranks_one_based, [[1, 2, 3, 4]])

    def test_singleton_includes_its_self_vote(self):
        ref = louri_matrix_rank([[15]], 4)
        np.testing.assert_array_equal(ref.ranks_one_based, [[1]])
        self.assertTrue(ref.result[2][0])

    def test_all_ordered_four_bit_pairs_with_saturation(self):
        keys = np.indices((16, 16)).reshape(2, -1).T
        expected = np.argsort(keys, axis=1, kind="stable")
        for quantization in ("none", "matched"):
            ref = louri_matrix_rank(keys, 4, quantization=quantization)
            np.testing.assert_array_equal(ref.result[1], expected)

    def test_zero_margin_of_literal_unit_bias(self):
        """An arbitrarily small negative error flips a biased adjacent-key cell."""
        errors = np.zeros((1, 2, 2))
        errors[0, 1, 0] = -1e-10
        raw = louri_matrix_rank([[1, 0]], 4, errors=errors, diagonal="exact")
        rounded = louri_matrix_rank([[1, 0]], 4, errors=errors,
                                    diagonal="exact", quantization="matched")
        self.assertFalse(raw.result[2][0])
        self.assertTrue(rounded.result[2][0])
        np.testing.assert_array_equal(raw.ranks_one_based, [[1, 1]])

    def test_measured_diagonal_can_create_zero_rank(self):
        errors = np.array([[[-1e-10]]])
        measured = louri_matrix_rank([[3]], 4, errors=errors)
        exact = louri_matrix_rank([[3]], 4, errors=errors, diagonal="exact")
        self.assertEqual(measured.ranks_one_based[0, 0], 0)
        self.assertFalse(measured.result[2][0])
        self.assertEqual(measured.result[1][0, 0], -1)
        self.assertTrue(exact.result[2][0])

    def test_invalid_ranks_are_rejected_without_negative_indexing(self):
        keys = np.array([[0, 1], [0, 1], [0, 1]])
        result = place_ranks(keys, np.array([[-1, 0], [0, 2], [1, 1]]))
        self.assertFalse(result[2].any())
        self.assertTrue(np.all(result[0] == -1))
        self.assertTrue(np.all(result[1] == -1))

    def test_quantizer_boundary_even_rounding_and_clipping(self):
        values = np.array([-.5, .5, 1.5, 2.5, -15, 15]) / 16
        np.testing.assert_array_equal(quantize_difference(values, 4, "matched") * 16,
                                      [0, 0, 2, 2, -8, 7])
        np.testing.assert_array_equal(quantize_difference(values, 4, "none"), values)

    def test_primary_noise_reproduces_existing_comparator(self):
        keys = np.array([[10, 9, 3, 3], [0, 15, 8, 9]])
        errors, matrix = comparison_errors(4, 4, .25, [7, 12], (31, 4), "antisymmetric")
        left, right = np.triu_indices(4, 1)
        measured = NoisyDifference(Precision(4, 4, 4), .25, (31, 4), [7, 12])(
            keys[:, left], keys[:, right])
        expected = quantize_difference((keys[:, left]-keys[:, right])/16 + errors, 4, "matched")
        np.testing.assert_array_equal(measured, expected)
        np.testing.assert_array_equal(matrix[:, left, right], -errors)
        np.testing.assert_array_equal(matrix[:, right, left], errors)

    def test_streams_are_batch_invariant_and_coupling_is_explicit(self):
        whole = comparison_errors(4, 4, .25, [2, 3, 4], (19,), "independent")
        parts = [comparison_errors(4, 4, .25, [i], (19,), "independent") for i in (2, 3, 4)]
        for slot in (0, 1):
            np.testing.assert_array_equal(whole[slot], np.concatenate([p[slot] for p in parts]))
        anti = comparison_errors(4, 4, .25, [2, 3, 4], (19,), "antisymmetric")
        np.testing.assert_array_equal(whole[0], anti[0])
        left, right = np.triu_indices(4, 1)
        self.assertFalse(np.array_equal(whole[1][:, left, right], -whole[1][:, right, left]))

    def test_matched_antisymmetric_control_even_with_large_noise(self):
        """Compare every directed vote, including trials with rank collisions."""
        rng = np.random.default_rng(13)
        for bits in (4, 8):
            keys = rng.integers(0, 2**bits, (50, 16))
            primary, errors = comparison_errors(16, bits, 3, range(50), (73,), "antisymmetric")
            left, right = np.triu_indices(16, 1)
            measured = quantize_difference((keys[:, left]-keys[:, right])*2.**(-bits)+primary,
                                           bits, "matched")
            ref = louri_matrix_rank(keys, bits, errors=errors, quantization="matched", diagonal="exact")
            np.testing.assert_array_equal(ref.threshold[:, right, left], measured > 0)
            np.testing.assert_array_equal(ref.threshold[:, left, right], measured <= 0)
            actual = rank_sort(keys, lambda a, b: measured)
            for expected, observed in zip(actual, ref.result):
                np.testing.assert_array_equal(expected, observed)

    def test_shared_decisions_can_still_have_a_rank_cycle(self):
        """Complementary pair votes do not guarantee transitivity or valid ranks."""
        keys = np.array([[0, 1, 2]])
        # i>j votes for pairs (0,1),(0,2),(1,2): 0<1, 0>2, 1<2.
        desired = np.array([[-1, 1, -1]]) / 16
        left, right = np.triu_indices(3, 1)
        e = desired - (keys[:, left]-keys[:, right])/16
        errors = np.zeros((1, 3, 3))
        errors[:, left, right], errors[:, right, left] = -e, e
        ref = louri_matrix_rank(keys, 4, errors=errors, quantization="matched", diagonal="exact")
        np.testing.assert_array_equal(ref.ranks_one_based, [[2, 2, 2]])
        self.assertFalse(ref.result[2][0])

    def test_invalid_inputs_fail_clearly(self):
        for kwargs in ({"errors": np.zeros((2, 2))}, {"errors": np.full((1, 2, 2), np.nan)},
                       {"diagonal": "unknown"}, {"quantization": "unknown"}):
            with self.assertRaises(ValueError):
                louri_matrix_rank([[1, 0]], 4, **kwargs)
        with self.assertRaises(ValueError):
            louri_matrix_rank([[16, 0]], 4)


if __name__ == "__main__":
    unittest.main()
