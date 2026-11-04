import itertools
import unittest

import numpy as np

from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.evaluation import reference_flags


def compact_bitonic_layers(n):
    if n < 2 or n & (n - 1):
        raise ValueError("n must be a power of two and at least 2")
    layers = []
    merge_size = 2
    while merge_size <= n:
        distance = merge_size // 2
        while distance:
            left = np.array([i for i in range(n) if i < (i ^ distance)])
            right = left ^ distance
            ascending = (left & merge_size) == 0
            layers.append((left, right, ascending))
            distance //= 2
        merge_size *= 2
    return layers


def bitonic_sort(keys, difference):
    values = keys.copy()
    indices = np.broadcast_to(np.arange(keys.shape[1]), keys.shape).copy()
    for left, right, ascending in compact_bitonic_layers(keys.shape[1]):

        a, b = values[:, left], values[:, right]
        ai, bi = indices[:, left], indices[:, right]
        measured = np.asarray(difference(a, b), dtype=np.float64)
        if measured.shape != a.shape or not np.isfinite(measured).all():
            raise ValueError("difference must return finite scores with the pair-array shape")
        greater = (measured > 0) | ((measured == 0) & (ai > bi))
        exchange = np.where(ascending, greater, ~greater)
        values[:, left] = np.where(exchange, b, a)
        values[:, right] = np.where(exchange, a, b)
        indices[:, left] = np.where(exchange, bi, ai)
        indices[:, right] = np.where(exchange, ai, bi)

    return values, indices, np.ones(len(keys), dtype=bool)


def rank_sort(keys, difference, *, bias_step):
    if not np.isfinite(bias_step) or bias_step <= 0:
        raise ValueError("bias_step must be finite and positive")
    keys = np.asarray(keys)
    if keys.ndim != 2 or 0 in keys.shape:
        raise ValueError("keys must be a nonempty (trials,N) array")
    trials, n = keys.shape
    shape = (trials, n, n)
    a = np.broadcast_to(keys[:, None, :], shape).reshape(trials, n*n)
    b = np.broadcast_to(keys[:, :, None], shape).reshape(trials, n*n)
    measured = np.asarray(difference(a, b), dtype=np.float64)
    if measured.shape != a.shape or not np.isfinite(measured).all():
        raise ValueError("difference must return finite scores with the pair-array shape")
    threshold = bias_step * np.tri(n, k=-1)
    ranks = np.sum(measured.reshape(shape) >= threshold, axis=1, dtype=np.int64) - 1
    return place_ranks(keys, ranks)


def place_ranks(keys, zero_based_ranks):
    keys = np.asarray(keys)
    ranks = np.asarray(zero_based_ranks)
    if ranks.shape != keys.shape or ranks.dtype.kind not in "iu" or keys.ndim != 2:
        raise ValueError("ranks must be a 2-D integer array matching keys")
    trials, n = keys.shape
    in_range = np.all((ranks >= 0) & (ranks < n), axis=1)
    rows = np.flatnonzero(in_range)
    occupied = np.zeros((trials, n), dtype=np.int64)
    np.add.at(occupied, (rows[:, None], ranks[rows]), 1)
    valid = in_range & np.all(occupied == 1, axis=1)
    values = np.full(keys.shape, -1, dtype=np.int64)
    indices = np.full(keys.shape, -1, dtype=np.int64)
    rows = np.flatnonzero(valid)
    values[rows[:, None], ranks[rows]] = keys[rows]
    indices[rows[:, None], ranks[rows]] = np.arange(n)
    return values, indices, valid


class SorterTests(unittest.TestCase):
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
        for n in (2, 4, 8):
            data = np.array(list(itertools.product((0, 1), repeat=n)))
            for sorter in (bitonic_sort, rank_sort):
                model = NoisyDifference(Precision(4, 4, 4))
                self.assertTrue(reference_flags(data, sorter(data, model, **({"bias_step": 1/16} if sorter is rank_sort else {}))).all())

    def test_bitonic_rejects_malformed_comparison_scores(self):
        keys = np.array([[0, 1]])
        for scores in (np.array(0.0), np.zeros((1, 2)),
                       np.array([[np.nan]]), np.array([[np.inf]])):
            with self.assertRaisesRegex(ValueError, "finite scores with the pair-array shape"):
                bitonic_sort(keys, lambda a, b: scores)

    def test_rank_cycles_fail_without_repair(self):
        data = np.array([[3, 1, 2]])
        result = rank_sort(data, lambda a, b: np.array([[0, -1, 1, 1, 0, -1, -1, 1, 0]]), bias_step=1)
        self.assertFalse(result[2][0])
        np.testing.assert_array_equal(result[0], [[-1, -1, -1]])

    def test_noise_is_invariant_to_batch_partition(self):
        data = np.random.default_rng(47).integers(0, 256, (23, 16))
        precision = Precision(8, 8, 8)
        for stream, sorter in enumerate((bitonic_sort, rank_sort), 1):
            context = [20260930, 8, 8, 8, 16, 1, 2, stream]
            options = {"bias_step": precision.delta_in} if sorter is rank_sort else {}
            whole = sorter(data, NoisyDifference(precision, 0.25, context, range(23)), **options)
            chunks = []
            for start in range(0, 23, 5):
                stop = min(start + 5, 23)
                model = NoisyDifference(precision, 0.25, context, range(start, stop))
                chunks.append(sorter(data[start:stop], model, **options))
            for i in range(3):
                np.testing.assert_array_equal(whole[i], np.concatenate([part[i] for part in chunks]))


class RankSorterTests(unittest.TestCase):
    def test_published_matrix_example(self):
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
