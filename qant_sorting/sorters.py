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
    """Evaluate Louri's full N*N difference matrix, including the diagonal.

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
