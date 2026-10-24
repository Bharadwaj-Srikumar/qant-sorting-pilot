# Reading guide: current sorting control and record routing.
# Each row is an independent list. A record is (integer key, original index).
# The supplied difference(a, b) callable is the only interchangeable arithmetic
# component; it must return the same shape, with positive/zero/negative scores.
# Bitonic evaluates dependent layers; rank sorting evaluates every directed matrix entry, including the diagonal.
# All swaps, rank sums, tie decisions and output placement are exact electronic
# operations in this simulation. Their Python execution is not optical timing.
# Both functions return (values, indices, valid_mask), with values/indices of
# shape (trials, N). Rank failures retain signed -1 markers instead of repair.
# Pass the signed integer arrays produced by input_validation.validate_keys.

"""Two algorithmic mappings; electronic records and control remain exact.

Stirk and Athale motivate a pipeline of compare/exchange modules. Here we
execute its active Batcher layers, not its bit-serial optical device physics.
Louri motivates broadcast-and-compare ranking. The full N-by-N difference/bias/threshold equations are used; sums and
record placement are electronic in this mapping.
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


def rank_sort(keys, difference, *, bias_step):
    """Execute Louri's full matrix; evaluate BOTH directions and every diagonal.

    keys has shape (trials,N). The supplied callable receives (trials,N*N)
    raw-key pairs in row-major matrix order: cell (i,j) evaluates x[j]-x[i].
    Each cell is a separate observation; no reverse decision is complemented,
    and no noisy diagonal is silently restored. This also lets the SDK submit
    all N*N pairs through its normal linear adapter.

    bias_step is the normalized distance between adjacent INTEGER keys (2**-b
    in the registered experiments), not a noise tolerance. Returned scores must
    be DIFFERENCES in those units. A cosine/sine score is not interchangeable.
    Subtract the lower-triangular bias, threshold >=0, then sum COLUMNS. Source
    ranks start at 1 because noiseless self-comparisons contribute one.
    Invalid/out-of-range ranks retain -1 records; no digital repair is performed.
    """
    from qant_sorting.louri_reference import place_ranks
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
    biased = measured.reshape(shape) - bias_step * np.tril(np.ones((n, n)), k=-1)
    ranks = np.sum(biased >= 0, axis=1, dtype=np.int64) - 1
    return place_ranks(keys, ranks)
