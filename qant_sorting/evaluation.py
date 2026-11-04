"""Whole-sort correctness and partial ranking quality.

All reference calculations happen after sorting. Top-k means the largest
keys, at the end of an ascending output. Invalid outputs have undefined
conditional quality; runners report any zero-failure recall utility separately.
"""

from dataclasses import dataclass
import math

import numpy as np


def reference_flags(data, result):
    """Return per-trial [valid, correct, stable] flags.

    Validity checks a complete ID permutation and unchanged key-ID pairs.
    Correct additionally requires sorted keys; stable requires the exact
    stable-reference IDs. The reference never guides noisy decisions.
    """
    values, indices, reported_valid = result
    expected_indices = np.argsort(data, axis=1, kind="stable")
    expected_values = np.take_along_axis(data, expected_indices, axis=1)
    permutation = np.all(np.sort(indices, axis=1) == np.arange(data.shape[1]), axis=1)

    # Safe lookup only: the separate permutation check still rejects -1 IDs.
    safe_indices = np.clip(indices, 0, data.shape[1] - 1)
    records_preserved = np.all(
        values == np.take_along_axis(data, safe_indices, axis=1), axis=1
    )
    valid = reported_valid & permutation & records_preserved
    correct = valid & np.all(values == expected_values, axis=1)
    stable = correct & np.all(indices == expected_indices, axis=1)
    return np.stack((valid, correct, stable), axis=1)


def wilson_interval(successes, trials):
    """Return a two-sided 95% Wilson interval for successes/trials.

    Callers supply a positive trial count. The interval describes sampling
    uncertainty, not hardware uncertainty or universal correctness.
    Observed 100% success still has a lower confidence bound below one.
    """
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    midpoint = (p + z * z / (2 * trials)) / denominator
    half_width = z * math.sqrt(
        p * (1 - p) / trials + z * z / (4 * trials * trials)
    ) / denominator
    return max(0.0, midpoint - half_width), min(1.0, midpoint + half_width)


@dataclass
class PreparedKeys:
    """Cached truth and unordered-pair gap counts for one input dataset.

    Data/order/value arrays have shape (trials,N); distances has shape
    (trials,2**bits). left/right list each unordered record pair once.
    """
    data: np.ndarray
    expected_order: np.ndarray
    sorted_keys: np.ndarray
    distances: np.ndarray
    left: np.ndarray
    right: np.ndarray
    levels: int


def prepare_keys(data, bits):
    """Validate a 4/8-bit corpus and prepare reusable scoring information.

    Use signed keys before subtraction, then count original pair distances
    in blocks of 32 trials. Row offsets let one bincount build separate
    histograms. The stable reference is used only to evaluate outputs.
    """
    data = np.asarray(data)
    if bits not in (4, 8) or data.ndim != 2 or data.shape[1] < 1 or len(data) < 1:
        raise ValueError("Expected a nonempty 2-D 4/8-bit key corpus")
    if data.dtype.kind not in "iu" or np.any(data < 0) or np.any(data >= 2**bits):
        raise ValueError("Keys must be integers within the declared range")
    # Subtract signed values: uint8 would wrap negative key differences.
    data = data.astype(np.int16)
    n = data.shape[1]
    left, right = np.triu_indices(n, 1)
    levels = 2**bits
    distances = np.zeros((len(data), levels), dtype=np.int64)
    for start in range(0, len(data), 32):
        batch = data[start:start+32]
        gaps = np.abs(batch[:, left] - batch[:, right]).astype(np.int32)
        encoded = gaps + np.arange(len(batch), dtype=np.int32)[:, None] * levels
        distances[start:start+len(batch)] = np.bincount(
            encoded.ravel(), minlength=len(batch)*levels).reshape(len(batch), levels)
    order = np.argsort(data, axis=1, kind="stable")
    return PreparedKeys(data, order, np.take_along_axis(data, order, 1),
                        distances, left, right, levels)


def selected_k(n):
    """Return applicable cutoffs {1,5,10,32,N}; N checks preservation only."""
    return sorted({k for k in (1, 5, 10, 32, n) if k <= n})


def score_saved_order(prepared, indices, ks=None):
    """Score saved original IDs without executing a sorter.

    Return validity/order flags, inversions, tau metrics, gap histograms and
    largest-key Recall@k. Invalid permutations have NaN conditional metrics
    and inversion marker -1. All-equal arrays also have undefined tau.
    Stable-ID recall requires exact reference records; tie-neutral recall
    allows equivalent boundary ties while still requiring larger keys.
    """
    data = prepared.data
    indices = np.asarray(indices)
    trials, n = data.shape
    if indices.shape != data.shape or indices.dtype.kind not in "iu":
        raise ValueError("Saved indices must be an integer array matching the input shape")
    ks = selected_k(n) if ks is None else list(ks)
    if not ks or any(not isinstance(k, (int, np.integer)) or k < 1 or k > n for k in ks):
        raise ValueError("Recall cutoffs must lie between 1 and N")

    # Validate IDs before gathering keys; later order/values contain valid rows only.
    valid = np.all(np.sort(indices, axis=1) == np.arange(n), axis=1)
    valid_rows = np.flatnonzero(valid)
    order = indices[valid]
    values = np.take_along_axis(data[valid], order, 1)
    correct = np.zeros(trials, dtype=bool)
    stable = np.zeros(trials, dtype=bool)
    correct[valid] = np.all(values == prepared.sorted_keys[valid], axis=1)
    stable[valid] = np.all(order == prepared.expected_order[valid], axis=1)
    flags = np.column_stack((valid, correct, stable))

    inversions = np.full(trials, -1, dtype=np.int64)
    inversions[valid] = 0
    inverted_by_gap = np.zeros(prepared.levels, dtype=np.int64)

    # Only misordered valid rows need inversion counting; all valid rows add denominators.
    bad = np.flatnonzero(~correct[valid])
    for start in range(0, len(bad), 32):
        local = bad[start:start+32]
        batch = values[local]
        difference = batch[:, prepared.left] - batch[:, prepared.right]
        inverted = difference > 0
        inversions[valid_rows[local]] = np.count_nonzero(inverted, axis=1)
        inverted_by_gap += np.bincount(difference[inverted], minlength=prepared.levels)
    available_by_gap = prepared.distances[valid].sum(axis=0)
    # Equal-key pairs have no required strict order.
    available_by_gap[0] = 0
    if np.any(inverted_by_gap > available_by_gap):
        raise AssertionError("Inversion count exceeds the number of comparable pairs")
    if int(inverted_by_gap.sum()) != int(inversions[valid].sum()):
        raise AssertionError("Gap histogram and per-array inversion counts disagree")
    if not np.array_equal(inversions[valid] == 0, correct[valid]):
        raise AssertionError("Zero inversions and key-sort correctness disagree")

    # For C total pairs, M unequal pairs and I inversions: tau_b=(M-2I)/sqrt(C*M).
    comparable = prepared.distances[:, 1:].sum(axis=1)
    all_pairs = n * (n - 1) // 2
    defined = valid & (comparable > 0)
    tau_b = np.full(trials, np.nan)
    ceiling = np.full(trials, np.nan)
    normalized = np.full(trials, np.nan)
    if all_pairs:
        m = comparable[defined].astype(np.float64)
        tau_b[defined] = (m - 2*inversions[defined]) / np.sqrt(m * all_pairs)
        # Ties lower standard tau-b's ceiling; tau_key uses a separate normalization.
        ceiling[defined] = np.sqrt(m / all_pairs)
        normalized[defined] = 1 - 2*inversions[defined] / m

    # Invert the stable permutation to map each record ID to its true rank.
    truth_position = np.argsort(prepared.expected_order[valid], axis=1)
    recall = {}
    for k in ks:

        # The suffix selects the largest k keys.
        chosen = order[:, -k:]
        truth_ranks = np.take_along_axis(truth_position, chosen, axis=1)
        strict = np.sum(truth_ranks >= n-k, axis=1) / k
        threshold = prepared.sorted_keys[valid, n-k]

        # Cap boundary-tie credit so ties cannot hide a missing strictly larger key.
        mandatory = np.sum(data[valid] > threshold[:, None], axis=1)
        tie_slots = k - mandatory
        chosen_values = values[:, -k:]
        greater = np.sum(chosen_values > threshold[:, None], axis=1)
        tied = np.sum(chosen_values == threshold[:, None], axis=1)
        tie_neutral = (greater + np.minimum(tied, tie_slots)) / k
        strict_all = np.full(trials, np.nan)
        neutral_all = np.full(trials, np.nan)
        strict_all[valid] = strict
        neutral_all[valid] = tie_neutral
        if np.any(strict > tie_neutral) or np.any(tie_neutral > 1):
            raise AssertionError("Recall bounds are inconsistent")
        if k == n and (np.any(strict != 1) or np.any(tie_neutral != 1)):
            raise AssertionError("Full-set recall must be one for a valid permutation")
        recall[k] = dict(stable=strict_all, tie_neutral=neutral_all)
    return dict(flags=flags, inversions=inversions, comparable_pairs=comparable,
                tau_b=tau_b, tau_b_ceiling=ceiling, tau_key_normalized=normalized,
                distance_pairs=available_by_gap, distance_inversions=inverted_by_gap,
                recall=recall)


# Self-tests

import itertools
import unittest


class RankingQualityTests(unittest.TestCase):
    # Use hand-countable strict orders to verify inversion count, tau-b, exact gap
    # histogram and top-k recall. A full reversal provides the tau=-1 endpoint.
    def test_adjacent_swap_and_reversal(self):
        p = prepare_keys(np.array([[0, 1, 2, 3]]), 4)
        result = score_saved_order(p, np.array([[0, 2, 1, 3]]), [1, 2, 4])
        self.assertEqual(result["inversions"][0], 1)
        self.assertAlmostEqual(result["tau_b"][0], 2/3)
        self.assertEqual(result["distance_inversions"][1], 1)
        self.assertEqual(result["distance_pairs"][1], 3)
        self.assertEqual(result["recall"][2]["stable"][0], .5)
        reversed_result = score_saved_order(p, np.array([[3, 2, 1, 0]]))
        self.assertEqual(reversed_result["inversions"][0], 6)
        self.assertEqual(reversed_result["tau_b"][0], -1)

    # Swap equal-key identities at a top-k boundary: key order remains correct,
    # stability and strict recall can fail, but tie-neutral recall remains one.
    # The standard tau-b ceiling is below one because truth contains a tie.
    def test_boundary_ties_do_not_count_as_key_errors(self):
        p = prepare_keys(np.array([[2, 2, 1, 3]]), 4)
        result = score_saved_order(p, np.array([[2, 1, 0, 3]]), [2])
        np.testing.assert_array_equal(result["flags"], [[True, True, False]])
        self.assertAlmostEqual(result["tau_b"][0], np.sqrt(5/6))
        self.assertEqual(result["tau_key_normalized"][0], 1)
        self.assertEqual(result["recall"][2]["stable"][0], .5)
        self.assertEqual(result["recall"][2]["tie_neutral"][0], 1)

    # Arrays with no unequal pair have no meaningful ordering correlation. Require
    # NaN tau while preserving valid key correctness and tie-neutral set recall.
    def test_all_equal_and_singleton_tau_are_undefined(self):
        for data, indices in (([[5, 5, 5]], [[2, 1, 0]]), ([[7]], [[0]])):
            p = prepare_keys(np.array(data), 4)
            result = score_saved_order(p, np.array(indices), [1])
            self.assertTrue(np.isnan(result["tau_b"][0]))
            self.assertTrue(np.isnan(result["tau_key_normalized"][0]))
            self.assertEqual(result["recall"][1]["tie_neutral"][0], 1)
            self.assertTrue(result["flags"][0, 1])

    # Use duplicate, negative and too-large indices to ensure invalid permutations
    # receive neither tau nor recall nor comparable-pair denominators.
    def test_invalid_outputs_never_get_rank_quality(self):
        p = prepare_keys(np.tile([0, 1, 2, 3], (3, 1)), 4)
        result = score_saved_order(p, np.array([[0, 0, 2, 3], [-1, 0, 1, 2], [0, 1, 2, 8]]))
        self.assertFalse(result["flags"].any())
        self.assertTrue(np.isnan(result["tau_b"]).all())
        self.assertEqual(result["distance_pairs"].sum(), 0)
        self.assertTrue(np.isnan(result["recall"][1]["stable"]).all())

    # The reversed pair [0,255] has distance 255, not 1 after unsigned wraparound.
    # Check both its denominator and inversion histogram use signed differences.
    def test_uint8_key_distances_do_not_wrap(self):
        p = prepare_keys(np.array([[0, 255]], dtype=np.uint8), 8)
        result = score_saved_order(p, np.array([[1, 0]]))
        self.assertEqual(result["distance_pairs"][255], 1)
        self.assertEqual(result["distance_inversions"][255], 1)

    # For all permutations of a strict and a tied five-record dataset, independently
    # enumerate inversions and optimal top-k subsets. This checks metric semantics
    # without copying the vectorized implementation formula as the expected answer.
    def test_exhaustive_small_orders_against_pair_enumeration(self):
        # 240 permutations: strict order plus a weak order with ties.
        for keys in ([0, 1, 2, 3, 4], [0, 0, 1, 2, 2]):
            permutations = np.array(list(itertools.permutations(range(5))))
            p = prepare_keys(np.tile(keys, (len(permutations), 1)), 4)
            result = score_saved_order(p, permutations, [1, 2, 3, 5])
            expected_hist = np.zeros(16, dtype=int)
            for row, order in enumerate(permutations):
                values = [keys[i] for i in order]
                inversion_count = 0
                for a in range(5):
                    for b in range(a+1, 5):
                        if values[a] > values[b]:
                            inversion_count += 1
                            expected_hist[values[a]-values[b]] += 1
                self.assertEqual(result["inversions"][row], inversion_count)
                truth = sorted(range(5), key=lambda i: (keys[i], i))
                for k in (1, 2, 3, 5):
                    expected = len(set(order[-k:]) & set(truth[-k:])) / k
                    self.assertEqual(result["recall"][k]["stable"][row], expected)
                    # Brute-force all optimal key-only subsets, independent of the threshold formula.
                    choices = list(itertools.combinations(range(5), k))
                    best = max(sum(keys[i] for i in choice) for choice in choices)
                    neutral = max(len(set(order[-k:]) & set(choice)) / k for choice in choices
                                  if sum(keys[i] for i in choice) == best)
                    self.assertEqual(result["recall"][k]["tie_neutral"][row], neutral)
            np.testing.assert_array_equal(result["distance_inversions"], expected_hist)

    # Present duplicated/lost record identities despite a claimed valid flag.
    # The independent scorer must reject them rather than trusting the sorter.
    def test_record_checks_detect_lost_or_changed_keys(self):
        data = np.array([[1, 2]])
        bad = (np.array([[1, 1]]), np.array([[0, 0]]), np.array([True]))
        self.assertFalse(reference_flags(data, bad).any())
