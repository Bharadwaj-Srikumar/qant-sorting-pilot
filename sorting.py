# Reading guide: LEGACY schedules used by model.py and the initial report.
# The compact network and the fixed-shuffle layout express different routing
# counts. shuffle_schedule includes bypass steps; only active steps compare keys.
# Labels in the schedule describe logical wires, while indices travelling with
# values identify original input records. Confusing these breaks stable ties.
# The legacy rank routine scans pair masks per record and checks ranks by sorting;
# the later sorting_schedules.py has different rank-accumulation/validation code.
# Consequently do not transfer implementation work counts between these modules.
# Inputs are validated signed 2-D keys; outputs preserve the standard tuple.

"""Sorting schedules adapted from the preceding validated pilot.

All functions receive RAW integer keys. Difference handles normalization.
Beyette and Desmulliez share the fixed-shuffle numerical schedule; their
historical physical implementations and timings are distinct.
"""
import math
import numpy as np


# Input N: integer power of two, at least 2. Return a list of triples
# (left_indices, right_indices, ascending_mask), each describing N/2 disjoint pairs.
# For m=log2(N), there are m(m+1)/2 dependent layers and N*m(m+1)/4 pair operations.
# XOR chooses partner wires; the direction mask alternates ordered runs so a
# larger merge can combine them. These are algorithmic layers, not optical stages.
def compact_bitonic_layers(n):
    """Return the compare/exchange pairs of the COMPACT bitonic network.

    n must be a power of two. In each merge, the pair distance is halved.
    XOR selects a partner whose corresponding binary address bit differs.
    i < partner ensures that each pair is visited only once.

    This gives K=log2(n)*(log2(n)+1)/2 layers, each with n/2 comparisons.
    It is NOT Beyette 1994's fixed perfect-shuffle layout, whose Eq. (1)
    counts extra routing/straight-pass stages. We check that separately.
    """
    if n < 2 or n & (n - 1):
        raise ValueError('n must be a power of two and at least 2')
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
    """Compare noisy differences, then exchange ORIGINAL electronic records.

    Input shape: (trials, n). Keys themselves are never numerically rebuilt.
    Original indices travel with keys, making the tie rule explicit: when a
    measured difference is zero, smaller original index is treated as smaller.
    This is a hybrid comparison/routing implementation, not an optical ReLU
    cascade. It preserves records even when a comparison is wrong.
    """
    values = keys.copy()
    indices = np.broadcast_to(np.arange(keys.shape[1]), keys.shape).copy()
    for left, right, ascending in compact_bitonic_layers(keys.shape[1]):
        a, b = values[:, left].copy(), values[:, right].copy()
        ai, bi = indices[:, left].copy(), indices[:, right].copy()
        d = difference(a, b)
        greater = (d > 0) | ((d == 0) & (ai > bi))
        exchange = np.where(ascending, greater, ~greater)
        values[:, left], values[:, right] = np.where(exchange, b, a), np.where(exchange, a, b)
        indices[:, left], indices[:, right] = np.where(exchange, bi, ai), np.where(exchange, ai, bi)
    return values, indices, np.ones(len(keys), dtype=bool)

# Input keys: signed integer rows; each unordered pair (i,j), i<j, is compared
# once. A measured positive difference votes that i is larger; otherwise j is
# larger, which includes the stable tie rule favoring earlier index i.
# The number of smaller records is a proposed zero-based output position.
# Return valid outputs only when these positions form a permutation of 0..N-1.
# Inconsistent/noisy comparisons can create collisions; an invalid row contains
# -1 values AND indices. No digital re-sort or silent collision repair is allowed.
def rank_sort(keys, difference):
    """Compare all unordered pairs, count ranks electronically, then place keys.

    Louri 1995 uses a full difference matrix, a bias matrix and thresholding
    (Eqs. 3-7). Here one comparison per unordered pair supplies complementary
    outcomes. This is an explicit implementation change, reducing N^2 matrix
    entries to N(N-1)/2 useful pair differences; the noisy circuits are not
    claimed equivalent. Electronic integer sums and scatter replace the
    paper's optical column sum and smart-pixel reordering.

    Zero measured difference goes to the earlier original index. A noisy set
    of comparisons can create duplicate ranks. Such trials fail: there is no
    digital re-sort or other hidden repair.
    """
    n = keys.shape[1]
    left, right = np.triu_indices(n, 1)
    d = difference(keys[:, left], keys[:, right])
    left_is_larger = d > 0
    ranks = np.zeros_like(keys, dtype=int)
    for index in range(n):
        # Rank = number of other records deemed smaller than this record.
        ranks[:, index] = (left_is_larger[:, left == index].sum(axis=1)
                          + (~left_is_larger[:, right == index]).sum(axis=1))
    valid = np.all(np.sort(ranks, axis=1) == np.arange(n), axis=1)
    output = np.full_like(keys, -1)
    indices = np.full_like(keys, -1)
    rows = np.flatnonzero(valid)
    output[rows[:, None], ranks[rows]] = keys[rows]
    indices[rows[:, None], ranks[rows]] = np.arange(n)
    return output, indices, valid

# Return (destination, schedule) for the historical fixed perfect-shuffle layout.
# destination maps OLD wire index to NEW wire index; labels track logical wires.
# Each instruction records whether to compare or bypass and which pairs ascend.
# For N=2**m there are 1+m(m-1) processing steps, but only m(m+1)/2 compare rounds.
# Assertions check partner alignment, total/active counts and final natural order.
# These checks reproduce routing structure, not propagation delays or regeneration.
def shuffle_schedule(n):
    """Reconstruct the fixed-shuffle schedule of Desmulliez Fig.3, section3.B.

    N=2^m. First merge needs one comparison step. Every subsequent merge
    takes m processing steps: bypass until the correct pairs align, then
    perform its comparisons. Total P=1+m(m-1), with m(m+1)/2 active rounds.

    An out-shuffle rotates the binary wire address left by one bit:
    destination(i)=2*i mod (N-1), with wire N-1 fixed. Labels track logical
    wire positions, NOT data-record identities. This lets us derive the
    ascending/descending controls transparently rather than hardcode masks.
    We reproduce the sorting schedule, not the optical mask generator.
    """
    if n < 2 or n & (n-1):
        raise ValueError('N must be a power of two')
    m = int(math.log2(n))
    destination = (np.arange(n)*2) % (n-1)
    destination[-1] = n-1
    labels = np.arange(n)
    schedule = []
    for merge_bits in range(1,m+1):
        # For the first merge compare adjacent wires immediately. Thereafter
        # one full m-step shuffle rotation aligns all needed partner distances.
        distances = [0] if merge_bits == 1 else list(range(m-1,-1,-1))
        for partner_bit in distances:
            if schedule:
                permuted = np.empty_like(labels)
                permuted[destination] = labels
                labels = permuted
            assert np.all((labels[0::2] ^ labels[1::2]) == 2**partner_bit)
            active = partner_bit < merge_bits
            ascending = (labels[0::2] & (2**merge_bits)) == 0
            schedule.append(dict(active=active, ascending=ascending.copy(),
                                 labels=labels.copy(), merge_bits=merge_bits))
    assert len(schedule) == m*m-m+1
    assert sum(s['active'] for s in schedule) == m*(m+1)//2
    assert np.array_equal(labels, np.arange(n))  # Natural output wire order.
    return destination, schedule

# Execute the fixed routing permutation between processing steps, preserving
# each key's original index. Active steps compare adjacent physical wires;
# bypass steps route only and deliberately consume no comparison-noise samples.
# Optional trace is a caller-owned list: append one-based step information and
# the first example's current values for comparison with the paper's figure.
# Return the same (values, indices, valid_mask) contract as compact bitonic.
def shuffle_sort(keys, difference, trace=None):
    """Execute optical-routing permutations and electronic record decisions.

    A bypass step only moves records. It does not call the difference model.
    We assume error-free routing, storage and regeneration; only comparisons
    receive the shared numerical impairment. Consequently this model cannot
    distinguish the two bitonic devices' physical precision.
    """
    values = keys.copy()
    indices = np.broadcast_to(np.arange(keys.shape[1]), keys.shape).copy()
    destination, schedule = shuffle_schedule(keys.shape[1])
    for step, instruction in enumerate(schedule):
        if step:
            old_values, old_indices = values.copy(), indices.copy()
            values[:, destination] = old_values
            indices[:, destination] = old_indices
        if instruction['active']:
            a, b = values[:,0::2].copy(), values[:,1::2].copy()
            ai, bi = indices[:,0::2].copy(), indices[:,1::2].copy()
            d = difference(a, b)
            greater = (d > 0) | ((d == 0) & (ai > bi))
            exchange = np.where(instruction['ascending'], greater, ~greater)
            values[:,0::2], values[:,1::2] = np.where(exchange,b,a), np.where(exchange,a,b)
            indices[:,0::2], indices[:,1::2] = np.where(exchange,bi,ai), np.where(exchange,ai,bi)
        if trace is not None:
            trace.append(dict(step=step+1,operation='compare' if instruction['active'] else 'bypass',
                              output_first_example=values[0].tolist()))
    return values, indices, np.ones(len(keys),dtype=bool)
