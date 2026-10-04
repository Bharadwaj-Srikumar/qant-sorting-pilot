"""Score completed outputs; the digital reference never guides a sorter."""

import math

import numpy as np


def reference_flags(data, result):
    """Return per-trial flags in order: valid records, sorted keys, stable sort."""
    values, indices, reported_valid = result
    expected_indices = np.argsort(data, axis=1, kind="stable")
    expected_values = np.take_along_axis(data, expected_indices, axis=1)
    permutation = np.all(np.sort(indices, axis=1) == np.arange(data.shape[1]), axis=1)

    # Safe lookup avoids indexing with invalid -1 output markers. Clipping is
    # ONLY for this scoring lookup, never for rank placement or output repair.
    safe_indices = np.clip(indices, 0, data.shape[1] - 1)
    records_preserved = np.all(
        values == np.take_along_axis(data, safe_indices, axis=1), axis=1
    )
    valid = reported_valid & permutation & records_preserved
    correct = valid & np.all(values == expected_values, axis=1)
    stable = correct & np.all(indices == expected_indices, axis=1)
    return np.stack((valid, correct, stable), axis=1)


def wilson_interval(successes, trials):
    """Two-sided 95% Wilson interval for a success probability.

    1,000 observed successes do not prove universal 100% correctness under
    noise. The interval describes sampling uncertainty for this input model.
    """
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    midpoint = (p + z * z / (2 * trials)) / denominator
    half_width = z * math.sqrt(
        p * (1 - p) / trials + z * z / (4 * trials * trials)
    ) / denominator
    return max(0.0, midpoint - half_width), min(1.0, midpoint + half_width)
