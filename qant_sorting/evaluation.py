"""Validate saved record orders and measure ranking quality per trial."""

import math
from dataclasses import dataclass

import numpy as np


def reference_flags(data, result):
    """Return (trials, 3) flags for validity, ascending order, and stable ties.

    Data has shape (trials, N); result is (values, original_indices,
    reported_valid). Validity requires each original record exactly once.
    """
    values, indices, reported_valid = result
    permutation = np.all(np.sort(indices, axis=1) == np.arange(data.shape[1]), axis=1)

    safe_indices = np.clip(indices, 0, data.shape[1] - 1)
    records_preserved = np.all(
        values == np.take_along_axis(data, safe_indices, axis=1), axis=1
    )
    valid = reported_valid & permutation & records_preserved
    correct = valid & np.all(values[:, :-1] <= values[:, 1:], axis=1)
    stable_ties = np.all(
        (values[:, :-1] != values[:, 1:]) | (indices[:, :-1] < indices[:, 1:]), axis=1
    )
    stable = correct & stable_ties
    return np.stack((valid, correct, stable), axis=1)


def wilson_interval(successes, trials):
    """Return the lower and upper 95% Wilson bounds for successes / trials."""
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
    """Cached (trials, N) keys and reference orders with pair counts by gap."""

    data: np.ndarray
    expected_order: np.ndarray
    sorted_keys: np.ndarray
    distances: np.ndarray
    left: np.ndarray
    right: np.ndarray
    levels: int


def prepare_keys(data, bits):
    """Validate a (trials, N) 4/8-bit corpus and cache references in PreparedKeys.

    Signed storage prevents subtraction overflow; pair counts group each
    unordered pair by absolute key difference, including ties at gap zero.
    """
    data = np.asarray(data)
    if bits not in (4, 8) or data.ndim != 2 or data.shape[1] < 1 or len(data) < 1:
        raise ValueError("Expected a nonempty 2-D 4/8-bit key corpus")
    if data.dtype.kind not in "iu" or np.any(data < 0) or np.any(data >= 2**bits):
        raise ValueError("Keys must be integers within the declared range")
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
    """Return sorted unique cutoffs from {1, 5, 10, 32, n} that fit n."""
    return sorted({k for k in (1, 5, 10, 32, n) if k <= n})


def score_saved_order(prepared, indices, ks=None):
    """Score saved record indices with order flags, inversions, tau, and recall.

    indices has shape (trials, N); recall scores the last k output positions
    against the true largest-k reference.
    Invalid orders get -1 inversions and NaN tau/recall. Tau also needs
    unequal-key pairs. The result includes pair and inversion counts by gap.
    """
    data = prepared.data
    indices = np.asarray(indices)
    trials, n = data.shape
    if indices.shape != data.shape or indices.dtype.kind not in "iu":
        raise ValueError("Saved indices must be an integer array matching the input shape")
    ks = selected_k(n) if ks is None else list(ks)
    if not ks or any(not isinstance(k, (int, np.integer)) or k < 1 or k > n for k in ks):
        raise ValueError("Recall cutoffs must lie between 1 and N")

    valid = np.all(np.sort(indices, axis=1) == np.arange(n), axis=1)
    valid_rows = np.flatnonzero(valid)
    order = indices[valid]
    valid_data = data[valid]
    values = np.take_along_axis(valid_data, order, 1)
    correct = np.zeros(trials, dtype=bool)
    stable = np.zeros(trials, dtype=bool)
    correct[valid] = np.all(values == prepared.sorted_keys[valid], axis=1)
    stable[valid] = np.all(order == prepared.expected_order[valid], axis=1)
    flags = np.column_stack((valid, correct, stable))

    inversions = np.full(trials, -1, dtype=np.int64)
    inversions[valid] = 0
    inverted_by_gap = np.zeros(prepared.levels, dtype=np.int64)

    bad = np.flatnonzero(~correct[valid])
    for start in range(0, len(bad), 32):
        local = bad[start:start+32]
        batch = values[local]
        difference = batch[:, prepared.left] - batch[:, prepared.right]
        inverted = difference > 0
        inversions[valid_rows[local]] = np.count_nonzero(inverted, axis=1)
        inverted_by_gap += np.bincount(difference[inverted], minlength=prepared.levels)
    available_by_gap = prepared.distances[valid].sum(axis=0)
    available_by_gap[0] = 0
    if np.any(inverted_by_gap > available_by_gap):
        raise AssertionError("Inversion count exceeds the number of comparable pairs")
    if int(inverted_by_gap.sum()) != int(inversions[valid].sum()):
        raise AssertionError("Gap histogram and per-array inversion counts disagree")
    if not np.array_equal(inversions[valid] == 0, correct[valid]):
        raise AssertionError("Zero inversions and key-sort correctness disagree")

    comparable = prepared.distances[:, 1:].sum(axis=1)
    all_pairs = n * (n - 1) // 2
    defined = valid & (comparable > 0)
    tau_b = np.full(trials, np.nan)
    ceiling = np.full(trials, np.nan)
    normalized = np.full(trials, np.nan)
    if all_pairs:
        m = comparable[defined].astype(np.float64)
        tau_b[defined] = (m - 2*inversions[defined]) / np.sqrt(m * all_pairs)
        ceiling[defined] = np.sqrt(m / all_pairs)
        normalized[defined] = 1 - 2*inversions[defined] / m

    truth_position = np.argsort(prepared.expected_order[valid], axis=1)
    recall = {}
    for k in ks:

        chosen = order[:, -k:]
        truth_ranks = np.take_along_axis(truth_position, chosen, axis=1)
        strict = np.sum(truth_ranks >= n-k, axis=1) / k
        threshold = prepared.sorted_keys[valid, n-k]

        mandatory = np.sum(valid_data > threshold[:, None], axis=1)
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
    return dict(flags=flags, inversions=inversions,
                tau_b=tau_b, tau_b_ceiling=ceiling, tau_key_normalized=normalized,
                distance_pairs=available_by_gap, distance_inversions=inverted_by_gap,
                recall=recall)
