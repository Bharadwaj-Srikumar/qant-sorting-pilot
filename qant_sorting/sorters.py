"""Bitonic and full-matrix rank sorting with replaceable arithmetic.

Original integer keys and IDs stay exact. The supplied difference(a,b)
callback models arithmetic; swaps, bias, thresholds and sums run on the host.
Both sorters return (values, indices, valid), with array shapes (trials,N),
(trials,N) and (trials,). Logical layers are not measured optical stages.
"""

import numpy as np


def compact_bitonic_layers(n):
    """Build the fixed layers for N=2**m, N>=2.

    Each of m(m+1)/2 layers has N/2 disjoint pairs. XOR selects partner
    wires; visiting only the lower address avoids duplicate pairs.
    Increasing merge sizes and decreasing distances build the network.
    """
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
    """Sort a validated (trials, N) batch using measured pair scores.

    Positive means the left record is larger; measured zero compares
    original IDs, including false ties. Ascending/descending layers swap
    keys and IDs together. Return values, IDs and a (trials,) validity mask;
    swaps always preserve records but noisy outputs may be misordered.
    """
    values = keys.copy()
    indices = np.broadcast_to(np.arange(keys.shape[1]), keys.shape).copy()
    for left, right, ascending in compact_bitonic_layers(keys.shape[1]):

        # Advanced indexing copies both sides before either is overwritten.
        a, b = values[:, left], values[:, right]
        ai, bi = indices[:, left], indices[:, right]
        measured = difference(a, b)
        greater = (measured > 0) | ((measured == 0) & (ai > bi))
        exchange = np.where(ascending, greater, ~greater)
        values[:, left] = np.where(exchange, b, a)
        values[:, right] = np.where(exchange, a, b)
        indices[:, left] = np.where(exchange, bi, ai)
        indices[:, right] = np.where(exchange, ai, bi)

    return values, indices, np.ones(len(keys), dtype=bool)


def rank_sort(keys, difference, *, bias_step):
    """Evaluate the full N*N rank difference matrix, including the diagonal.

    Cell (i,j) measures x[j]-x[i]; both directions are separate observations.
    The callback receives (trials,N*N) pairs and must return finite differences
    in the units of bias_step. Subtract that step below the diagonal,
    threshold >=0 and sum columns. Source ranks start at one, so placement
    uses ranks minus one. Sine scores cannot replace these difference units.
    """
    if not np.isfinite(bias_step) or bias_step <= 0:
        raise ValueError("bias_step must be finite and positive")
    keys = np.asarray(keys)
    if keys.ndim != 2 or 0 in keys.shape:
        raise ValueError("keys must be a nonempty (trials,N) array")
    trials, n = keys.shape
    shape = (trials, n, n)
    # Row i is the competitor; column j is the record whose rank is counted.
    a = np.broadcast_to(keys[:, None, :], shape).reshape(trials, n*n)
    b = np.broadcast_to(keys[:, :, None], shape).reshape(trials, n*n)
    measured = np.asarray(difference(a, b), dtype=np.float64)
    if measured.shape != a.shape or not np.isfinite(measured).all():
        raise ValueError("difference must return finite scores with the pair-array shape")
    biased = measured.reshape(shape) - bias_step * np.tril(np.ones((n, n)), k=-1)
    # Sum competitor rows to get column ranks; remove the noiseless self-vote.
    ranks = np.sum(biased >= 0, axis=1, dtype=np.int64) - 1
    return place_ranks(keys, ranks)


def place_ranks(keys, zero_based_ranks):
    """Route records only when ranks uniquely fill positions 0..N-1.

    Reject out-of-range destinations before indexing. A collision or missing
    position invalidates the whole trial, leaving -1 values and IDs.
    No digital re-sorting, diagonal restoration or rank repair is performed.
    """
    keys = np.asarray(keys)
    ranks = np.asarray(zero_based_ranks)
    if ranks.shape != keys.shape or ranks.dtype.kind not in "iu" or keys.ndim != 2:
        raise ValueError("ranks must be a 2-D integer array matching keys")
    trials, n = keys.shape
    in_range = np.all((ranks >= 0) & (ranks < n), axis=1)
    rows = np.flatnonzero(in_range)
    occupied = np.zeros((trials, n), dtype=np.int64)
    # add.at counts repeated destinations correctly, exposing collisions.
    np.add.at(occupied, (rows[:, None], ranks[rows]), 1)
    valid = in_range & np.all(occupied == 1, axis=1)
    values = np.full(keys.shape, -1, dtype=np.int64)
    indices = np.full(keys.shape, -1, dtype=np.int64)
    rows = np.flatnonzero(valid)
    values[rows[:, None], ranks[rows]] = keys[rows]
    indices[rows[:, None], ranks[rows]] = np.arange(n)
    return values, indices, valid


# Self-tests
# Exhaustive stable-routing controls, seeded noise and literal rank equations.
# Run with: python -m unittest qant_sorting.sorters -v

import itertools
import unittest

from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.evaluation import reference_flags


class SorterTests(unittest.TestCase):
    """Network structure, stable records and batch-invariant noise."""

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
                self.assertTrue(reference_flags(data, sorter(data, model, **({"bias_step": 1/16} if sorter is rank_sort else {}))).all())

    # Inject a cyclic three-way relation with no consistent total order. Require
    # invalid output and -1 markers, proving collisions are not hidden by digital repair.
    def test_rank_cycles_fail_without_repair(self):
        # 0 beats 1, 1 beats 2, 2 beats 0: each gets rank 1, so placement fails.
        data = np.array([[3, 1, 2]])
        result = rank_sort(data, lambda a, b: np.array([[0, -1, 1, 1, 0, -1, -1, 1, 0]]), bias_step=1)
        self.assertFalse(result[2][0])
        np.testing.assert_array_equal(result[0], [[-1, -1, -1]])

    # Run identical trial IDs as one batch and several chunks for both schedules.
    # Exact tuple equality verifies memory batching does not redefine the noise process.
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
    """Source equations, directed comparisons and invalid rank placement."""

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
