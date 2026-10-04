"""Two algorithmic mappings; electronic records and control remain exact.

Stirk and Athale motivate a pipeline of compare/exchange modules. Here we
execute its active Batcher layers, not its bit-serial optical device physics.
Louri motivates broadcast-and-compare ranking. Our adaptation compares each
unordered pair once and sums/places records electronically.
"""

import numpy as np


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
    offset = 0
    for i in range(n - 1):
        count = n - i - 1
        wins = left_is_larger[:, offset:offset + count]
        ranks[:, i] += wins.sum(axis=1)
        ranks[:, i + 1:] += ~wins
        offset += count

    # Inconsistent comparisons can produce repeated ranks. Count occupied
    # positions in O(N), rather than sorting the ranks or repairing them.
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
