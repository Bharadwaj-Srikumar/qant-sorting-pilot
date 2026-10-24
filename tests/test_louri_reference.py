"""Source fixtures and controls for the equation-level Louri reference."""
import unittest

import numpy as np

from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.louri_reference import (
    louri_matrix_rank, quantize_difference,
)
from qant_sorting.sorting_schedules import place_ranks, rank_sort


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

    def test_all_sixteen_directed_cells_are_evaluated(self):
        keys = np.array([[3, 1, 3, 0]])
        calls = []
        def observed(a, b):
            calls.append((a.copy(), b.copy()))
            return (a-b)/16
        result = rank_sort(keys, observed, bias_step=1/16)
        self.assertEqual(len(calls), 1)
        np.testing.assert_array_equal(calls[0][0], [[3,1,3,0]*4])
        np.testing.assert_array_equal(calls[0][1], [[3]*4+[1]*4+[3]*4+[0]*4])
        np.testing.assert_array_equal(result[1], [[3,1,0,2]])

    def test_reverse_decisions_and_diagonal_are_never_repaired(self):
        # Both directed cells contribute one: no complementary decision is forced.
        result = rank_sort(np.array([[1,0]]), lambda a,b: np.array([[0,1,1,0]])/16,
                           bias_step=1/16)
        self.assertFalse(result[2][0])
        result = rank_sort(np.array([[1]]), lambda a,b: np.array([[-.01]]), bias_step=1/16)
        self.assertFalse(result[2][0])
        np.testing.assert_array_equal(result[1], [[-1]])

    def test_adapter_agrees_with_explicit_independent_matrix_errors(self):
        keys = np.random.default_rng(43).integers(0, 16, (20, 9))
        ids, context, sigma = range(20), (91, 4), .25/16
        errors = np.stack([np.random.default_rng(np.random.SeedSequence([*context,i]))
                           .normal(0, sigma, (9,9)) for i in ids])
        ref = louri_matrix_rank(keys, 4, errors=errors, quantization="matched", diagonal="measured")
        actual = rank_sort(keys, NoisyDifference(Precision(4,4,4), .25, context, ids), bias_step=1/16)
        for a,b in zip(actual, ref.result):
            np.testing.assert_array_equal(a,b)

    def test_full_matrix_resource_counts(self):
        from qant_sorting.experiments.hardware_conditions import counts
        self.assertEqual(counts(4,16), (3,6,16,3,1))
        self.assertEqual(counts(16,256), (10,80,256,10,1))
        self.assertEqual(counts(256,65536), (36,4608,65536,36,1))

    def test_invalid_inputs_fail_clearly(self):
        for kwargs in ({"errors": np.zeros((2, 2))}, {"errors": np.full((1, 2, 2), np.nan)},
                       {"diagonal": "unknown"}, {"quantization": "unknown"}):
            with self.assertRaises(ValueError):
                louri_matrix_rank([[1, 0]], 4, **kwargs)
        with self.assertRaises(ValueError):
            louri_matrix_rank([[16, 0]], 4)


if __name__ == "__main__":
    unittest.main()
