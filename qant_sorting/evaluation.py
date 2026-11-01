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
