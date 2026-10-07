# Reading guide: current sorting control and record routing.
# Each row is an independent list. A record is (integer key, original index).
# The supplied difference(a, b) callable is the only interchangeable arithmetic
# component; it must return the same shape, with positive/zero/negative scores.
# Bitonic evaluates dependent layers; rank sorting evaluates unordered pairs.
# All swaps, rank sums, tie decisions and output placement are exact electronic
# operations in this simulation. Their Python execution is not optical timing.
# Both functions return (values, indices, valid_mask), with values/indices of
# shape (trials, N). Rank failures retain signed -1 markers instead of repair.
# Pass the signed integer arrays produced by input_validation.validate_keys.

"""Two algorithmic mappings; electronic records and control remain exact.

Stirk and Athale motivate a pipeline of compare/exchange modules. Here we
execute its active Batcher layers, not its bit-serial optical device physics.
Louri motivates broadcast-and-compare ranking. Our adaptation compares each
unordered pair once and sums/places records electronically.
"""

import numpy as np


# Input N: integer power of two, at least 2. Return a list of triples
# (left_indices, right_indices, ascending_mask), each describing N/2 disjoint pairs.
# For m=log2(N), there are m(m+1)/2 dependent layers and N*m(m+1)/4 pair operations.
# XOR chooses partner wires; the direction mask alternates ordered runs so a
# larger merge can combine them. These are algorithmic layers, not optical stages.
def compact_bitonic_layers(n):
    """Return K=m(m+1)/2 layers, each with N/2 pairs, for N=2**m.

    XOR changes one address bit to select the comparison partner. Visiting
    only the smaller wire address avoids comparing the same pair twice.
    Increasing merge sizes build sorted runs; decreasing distances merge them.
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


# Input keys: signed integer array (trials,N); difference: callable on pairs.
# Return (values, original_indices, valid_mask) with the same key-array shape.
# The routine only exchanges existing records. Each layer must finish before
# the next layer selects its current pairs; within a layer pairs are disjoint.
# Measured equality uses original indices to define a stable total order.
# Validity is always true because swaps preserve the record multiset; sortedness
# and stability can still fail after noisy comparisons and are scored separately.
def bitonic_sort(keys, difference):
    """Sort a validated (trials, N) batch; return values, indices, validity.

    The difference callable models only arithmetic. Sign interpretation, tie
    handling and record exchanges happen electronically. Original indices
    travel with records; a measured zero uses the smaller original index as
    the smaller record, even when noise caused a false tie.
    """
    values = keys.copy()
    indices = np.broadcast_to(np.arange(keys.shape[1]), keys.shape).copy()
    for left, right, ascending in compact_bitonic_layers(keys.shape[1]):
        # Advanced indexing makes copies, so both sides survive the exchange.
        a, b = values[:, left], values[:, right]
        ai, bi = indices[:, left], indices[:, right]
        measured = difference(a, b)
        greater = (measured > 0) | ((measured == 0) & (ai > bi))
        exchange = np.where(ascending, greater, ~greater)
        values[:, left] = np.where(exchange, b, a)
        values[:, right] = np.where(exchange, a, b)
        indices[:, left] = np.where(exchange, bi, ai)
        indices[:, right] = np.where(exchange, ai, bi)

    # Swapping preserves every record even when a noisy decision is wrong.
    return values, indices, np.ones(len(keys), dtype=bool)


# Input keys: signed integer rows; each unordered pair (i,j), i<j, is compared
# once. A measured positive difference votes that i is larger; otherwise j is
# larger, which includes the stable tie rule favoring earlier index i.
# The number of smaller records is a proposed zero-based output position.
# Return valid outputs only when these positions form a permutation of 0..N-1.
# Inconsistent/noisy comparisons can create collisions; an invalid row contains
# -1 values AND indices. No digital re-sort or silent collision repair is allowed.
def rank_sort(keys, difference):
    """Compare every unordered pair, count smaller records, then place them.

    One difference supplies complementary decisions for a pair (i,j), i<j.
    A positive difference increments rank[i]; otherwise rank[j] increases.
    Thus a measured zero favors the earlier original index. This differs
    explicitly from Louri's full optical difference/bias matrix and optical
    summation; no equivalence of the physical noisy circuits is claimed.
    """
    n = keys.shape[1]
    left, right = np.triu_indices(n, 1)
    left_is_larger = difference(keys[:, left], keys[:, right]) > 0
    ranks = np.zeros_like(keys, dtype=np.int64)

    # np.triu_indices lists (0,1),(0,2),...,(1,2),... in contiguous groups.
    # Visit each group's outcomes once. This removes the old N full scans
    # of all pairs: rank accumulation now uses O(N²) work per input array.
    # Pairs from triu_indices are grouped by their left endpoint. Consume each
    # comparison once: wins update that left record, complementary outcomes update
    # the corresponding right records. A repeated full pair-mask scan is avoided.
    offset = 0
    for i in range(n - 1):
        count = n - i - 1
        wins = left_is_larger[:, offset:offset + count]
        ranks[:, i] += wins.sum(axis=1)
        ranks[:, i + 1:] += ~wins
        offset += count

    # Inconsistent comparisons can produce repeated ranks. Count occupied
    # positions in O(N), rather than sorting the ranks or repairing them.
    # A valid ranking occupies every output position exactly once. Counting these
    # occupancies checks the condition in linear placement work; it does not sort
    # or repair inconsistent ranks.
    occupied = np.zeros_like(ranks)
    rows = np.arange(len(keys))[:, None]
    np.add.at(occupied, (rows, ranks), 1)
    valid = np.all(occupied == 1, axis=1)

    # Only a unique rank permutation is placed. Invalid trials get -1 markers
    # and remain failed sorts; no rank clipping or digital re-sort occurs.
    output = np.full_like(keys, -1)
    indices = np.full_like(keys, -1)
    valid_rows = np.flatnonzero(valid)
    output[valid_rows[:, None], ranks[valid_rows]] = keys[valid_rows]
    indices[valid_rows[:, None], ranks[valid_rows]] = np.arange(n)
    return output, indices, valid
