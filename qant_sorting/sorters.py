"""Bitonic and rank sorting driven by an injected difference function."""

import numpy as np


def compact_bitonic_layers(n):
    """Return (left, right, ascending) arrays for each Bitonic network layer."""
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
    """Route (trials, N) keys through Bitonic layers using difference(a, b).

    Return (values, original_indices, valid_flags). Zero scores use original
    indices to break ties; noise can leave keys out of ascending order.
    """
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
    """Rank (trials, N) keys by thresholding all N**2 directed differences.

    Matrix axes are (trial, competitor, record); sums over competitors,
    minus one, give each record's rank. A lower-triangular bias breaks ties.
    Return (values, original_indices, valid_flags).
    """
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
    """Place (trials, N) keys at their proposed zero-based ranks.

    Return (values, original_indices, valid_flags). Duplicate or out-of-range
    ranks make a trial invalid and leave its values and indices at -1.
    """
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
