"""Source equations, directed comparisons and invalid rank placement."""

import unittest

import numpy as np

from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.sorters import place_ranks, rank_sort


class RankSorterTests(unittest.TestCase):
    def test_published_matrix_example(self):
        """Literal matrices from Applied Optics 34 (1995), p. 3089."""
        keys = np.array([[7, 8, 2, 8, 5]])
        difference = keys[:, None, :] - keys[:, :, None]
        biased = difference - np.tril(np.ones((5, 5), dtype=int), k=-1)
        votes = biased >= 0
        np.testing.assert_array_equal(difference[0], [
            [0, 1, -5, 1, -2], [-1, 0, -6, 0, -3], [5, 6, 0, 6, 3],
            [-1, 0, -6, 0, -3], [2, 3, -3, 3, 0],
        ])
        np.testing.assert_array_equal(biased[0], [
            [0, 1, -5, 1, -2], [-2, 0, -6, 0, -3], [4, 5, 0, 6, 3],
            [-2, -1, -7, 0, -3], [1, 2, -4, 2, 0],
        ])
        np.testing.assert_array_equal(votes[0], [
            [1, 1, 0, 1, 0], [0, 1, 0, 1, 0], [1, 1, 1, 1, 1],
            [0, 0, 0, 1, 0], [1, 1, 0, 1, 1],
        ])
        np.testing.assert_array_equal(votes.sum(axis=1), [[3, 4, 1, 5, 2]])
        result = rank_sort(keys, NoisyDifference(Precision(4, 4, 4)), bias_step=1/16)
        np.testing.assert_array_equal(result[1], [[2, 4, 0, 1, 3]])

    def test_equal_keys_and_singleton_keep_their_positions(self):
        for bits in (4, 8):
            for keys in (np.array([[3, 3, 3, 3]]), np.array([[15]])):
                result = rank_sort(
                    keys, NoisyDifference(Precision(bits, bits, bits)),
                    bias_step=2.0**(-bits),
                )
                np.testing.assert_array_equal(result[1], [np.arange(keys.shape[1])])
                self.assertTrue(result[2].all())

    def test_invalid_ranks_are_rejected(self):
        keys = np.array([[0, 1], [0, 1], [0, 1]])
        result = place_ranks(keys, np.array([[-1, 0], [0, 2], [1, 1]]))
        self.assertFalse(result[2].any())
        self.assertTrue(np.all(result[0] == -1))
        self.assertTrue(np.all(result[1] == -1))

    def test_every_directed_cell_is_evaluated(self):
        keys = np.array([[3, 1, 3, 0]])
        calls = []

        def difference(a, b):
            calls.append((a.copy(), b.copy()))
            return (a - b) / 16

        result = rank_sort(keys, difference, bias_step=1/16)
        self.assertEqual(len(calls), 1)
        np.testing.assert_array_equal(calls[0][0], [[3, 1, 3, 0] * 4])
        np.testing.assert_array_equal(calls[0][1], [[3]*4 + [1]*4 + [3]*4 + [0]*4])
        np.testing.assert_array_equal(result[1], [[3, 1, 0, 2]])

    def test_reverse_decisions_and_diagonal_are_not_repaired(self):
        result = rank_sort(
            np.array([[1, 0]]), lambda a, b: np.array([[0, 1, 1, 0]]) / 16,
            bias_step=1/16,
        )
        self.assertFalse(result[2][0])
        result = rank_sort(np.array([[1]]), lambda a, b: np.array([[-.01]]), bias_step=1/16)
        self.assertFalse(result[2][0])
        np.testing.assert_array_equal(result[1], [[-1]])

    def test_seeded_noise_agrees_with_explicit_matrix_equations(self):
        keys = np.random.default_rng(43).integers(0, 16, (20, 9))
        context, delta = (91, 4), 1/16
        errors = np.stack([
            np.random.default_rng(np.random.SeedSequence([*context, i]))
            .normal(0, .25 * delta, (9, 9)) for i in range(len(keys))
        ])
        difference = (keys[:, None, :] - keys[:, :, None]) * delta
        measured = np.clip(np.rint((difference + errors) / delta), -8, 7) * delta
        votes = measured - delta * np.tril(np.ones((9, 9)), k=-1) >= 0
        expected = place_ranks(keys, votes.sum(axis=1) - 1)
        actual = rank_sort(
            keys, NoisyDifference(Precision(4, 4, 4), .25, context, range(len(keys))),
            bias_step=delta,
        )
        for observed, reference in zip(actual, expected):
            np.testing.assert_array_equal(observed, reference)

    def test_resource_counts(self):
        from qant_sorting.resources import counts
        self.assertEqual(counts(4, 16), (3, 6, 16, 3, 1))
        self.assertEqual(counts(16, 256), (10, 80, 256, 10, 1))
        self.assertEqual(counts(256, 65536), (36, 4608, 65536, 36, 1))


if __name__ == "__main__":
    unittest.main()
