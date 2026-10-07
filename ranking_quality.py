# Reading guide: evaluate existing output orders without rerunning a sorter.
# prepare_keys caches reference orders and original-key distance denominators.
# score_saved_order reconstructs the output from original record identities.
# Three different questions stay separate: are records valid, are keys ordered,
# and are equal-key records stable? Ranking metrics only use valid permutations.
# NaN means undefined, not zero quality; callers must report the valid denominator.
# Top-k means the LARGEST keys, hence the suffix of an ascending output.
# The returned key-normalized tau is explicitly distinct from standard tau-b.
# No metric in this module can establish measured photonic speed or PRISM recall.

"""Quality of saved ascending output permutations; no sorter is executed.

Kendall tau-b compares true keys with output positions of the same records.
Equal keys are ties in the truth, while output positions are distinct. Thus
even a perfect order has ceiling sqrt(M / C), where M counts unequal pairs
and C counts all pairs. The additional normalized value 1-2I/M removes that
ceiling; it is explicitly not relabelled as standard tau-b.
"""

from dataclasses import dataclass
import numpy as np


# Reference/cache container shared across scores for one input dataset.
# data holds signed keys; expected_order and sorted_keys define the stable truth.
# distances has shape (trials,2**bits), counting ORIGINAL unordered pairs at
# each absolute integer key distance, including zero for true equalities.
# left/right enumerate all unordered record pairs; levels is the key-domain size.
# This cached truth is only used for evaluation, never to repair sorter output.
@dataclass
class PreparedKeys:
    data: np.ndarray
    expected_order: np.ndarray
    sorted_keys: np.ndarray
    distances: np.ndarray
    left: np.ndarray
    right: np.ndarray
    levels: int


# Validate a nonempty 2-D 4/8-bit integer corpus and build PreparedKeys.
# Cast to signed int16 before subtraction to prevent uint8 distance wraparound.
# Count pair distances in blocks of 32 trial rows to bound temporary memory;
# row-offset encoding lets one bincount accumulate all histograms in a block.
# Return the reference order, sorted keys, pair indices and per-row denominators.
# These denominators later include only trials whose output permutation is valid.
def prepare_keys(data, bits):
    data = np.asarray(data)
    if bits not in (4, 8) or data.ndim != 2 or data.shape[1] < 1 or len(data) < 1:
        raise ValueError("Expected a nonempty 2-D 4/8-bit key corpus")
    if data.dtype.kind not in "iu" or np.any(data < 0) or np.any(data >= 2**bits):
        raise ValueError("Keys must be integers within the declared range")
    data = data.astype(np.int16)  # signed subtraction must not wrap at uint8
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


# Return sorted, unique predeclared cutoffs {1,5,10,32} that fit N, plus N.
# k=N is a full-set preservation control: every valid permutation has recall 1
# there, even when its order is completely wrong. It is not a useful top-k claim.
def selected_k(n):
    """Predeclared cutoffs; k=N is a labelled full-set control."""
    return sorted({k for k in (1, 5, 10, 32, n) if k <= n})


# Input PreparedKeys, saved original-index rows of the same shape, and optional
# k cutoffs. Return per-trial flags/inversion counts/tau values/recall plus pooled
# inversion and denominator histograms by exact integer key distance.
# Invalid permutations receive NaN ranking metrics and inversion sentinel -1;
# all-equal valid arrays also have undefined tau because no strict pair exists.
# For C=N(N-1)/2, M unequal pairs, I inversions: tau_b=(M-2I)/sqrt(C*M).
# Its perfect-order ceiling is sqrt(M/C); tau_key=1-2I/M is reported separately.
# Stable-ID recall compares exact record identities. Tie-neutral recall accepts
# equivalent boundary-key choices, but full credit still requires recovering all
# true keys strictly above that boundary. Report invalid-output coverage too.
def score_saved_order(prepared, indices, ks=None):
    data = prepared.data
    indices = np.asarray(indices)
    trials, n = data.shape
    if indices.shape != data.shape or indices.dtype.kind not in "iu":
        raise ValueError("Saved indices must be an integer array matching the input shape")
    ks = selected_k(n) if ks is None else list(ks)
    if not ks or any(not isinstance(k, (int, np.integer)) or k < 1 or k > n for k in ks):
        raise ValueError("Recall cutoffs must lie between 1 and N")
    # Stage 1: validate record identity before any output lookup. Duplicate, negative
    # or out-of-domain indices cannot be interpreted as a ranked version of the
    # input. Subsequent arrays named order/values contain VALID rows only.
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
    # Correctly sorted key sequences have no inversions, irrespective of tie order.
    # Stage 2: count inversions only for key-incorrect valid rows; correct rows
    # contribute zero errors but still contribute all their pair denominators.
    # An inversion is a final-output ordering error, not an internal comparator event.
    bad = np.flatnonzero(~correct[valid])
    for start in range(0, len(bad), 32):
        local = bad[start:start+32]
        batch = values[local]
        difference = batch[:, prepared.left] - batch[:, prepared.right]
        inverted = difference > 0
        inversions[valid_rows[local]] = np.count_nonzero(inverted, axis=1)
        inverted_by_gap += np.bincount(difference[inverted], minlength=prepared.levels)
    available_by_gap = prepared.distances[valid].sum(axis=0)
    available_by_gap[0] = 0  # equal-key pairs do not have a correct strict order
    if np.any(inverted_by_gap > available_by_gap):
        raise AssertionError("Inversion count exceeds the number of comparable pairs")
    if int(inverted_by_gap.sum()) != int(inversions[valid].sum()):
        raise AssertionError("Gap histogram and per-array inversion counts disagree")
    if not np.array_equal(inversions[valid] == 0, correct[valid]):
        raise AssertionError("Zero inversions and key-sort correctness disagree")

    # Stage 3: equal-key pairs do not have a required strict order. Remove them
    # from M but retain them in total-pair count C for standard tau-b normalization.
    # This is why a correct order with duplicates can have tau-b below one.
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

    # Stage 4: invert the stable reference permutation so each original record ID
    # can be tested for membership in the true top-k suffix without sorting output.
    truth_position = np.argsort(prepared.expected_order[valid], axis=1)
    recall = {}
    for k in ks:
        # Top-k means the k largest keys: the suffix of an ascending output.
        chosen = order[:, -k:]
        truth_ranks = np.take_along_axis(truth_position, chosen, axis=1)
        strict = np.sum(truth_ranks >= n-k, axis=1) / k
        threshold = prepared.sorted_keys[valid, n-k]
        # All keys strictly above the kth-key threshold are required; the remaining
        # slots can be filled by any records equal to that threshold. Limit their credit
        # to tie_slots so repeated boundary values cannot hide missed larger keys.
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
