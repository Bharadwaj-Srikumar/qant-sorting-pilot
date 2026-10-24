"""Inspectable equation-level reference for the canonical full-matrix sorter.

Source: Louri, Hatch and Na, Applied Optics 34 (1995), pp. 3088-3090,
equations (1)-(7), DOI 10.1364/AO.34.003087. Row i is the competing record;
column j is the record whose rank is accumulated. Thus D[i,j] = x[j]-x[i].
The lower-triangular bias U[i,j] = 1 if i>j resolves equal integer keys.
The published matrices imply stable ties (earlier index first), despite
contradictory prose on p. 3089. The reference follows those matrices.

Scaling every value AND the unit bias by delta=2**(-bits) preserves the
paper's noiseless equations. The optional noise and quantizer are declared
sensitivity assumptions. They are not a reconstruction of smart-pixel
physics or a Q.ANT hardware model. Rank summation and routing remain exact.
"""

from dataclasses import dataclass

import numpy as np

from qant_sorting.comparison import Precision
from qant_sorting.input_validation import validate_keys
from qant_sorting.sorting_schedules import place_ranks


def quantize_difference(values, bits, quantization):
    """Apply no quantizer, or the existing matched-step signed quantizer.

    Quantization is BEFORE Louri's bias. This location is deliberate: it
    lets both algorithms consume the same quantized difference information.
    The bias, threshold, integer summation and output routing are then exact.
    No-quantizer mode also has no clipping; it is the equation-level control.
    """
    precision = Precision(bits, bits, bits)
    values = np.asarray(values, dtype=np.float64)
    if quantization == "none":
        return values.copy()
    if quantization != "matched":
        raise ValueError("quantization must be 'none' or 'matched'")
    half = 2 ** (bits - 1)
    codes = np.rint(values / precision.delta_out)
    return np.clip(codes, -half, half - 1) * precision.delta_out


@dataclass
class MatrixRanking:
    """Inspectable intermediate matrices, ranks and routed output for a batch."""

    difference: np.ndarray
    measured_difference: np.ndarray
    biased_difference: np.ndarray
    threshold: np.ndarray
    ranks_one_based: np.ndarray
    result: tuple


def louri_matrix_rank(keys, bits, *, errors=None, quantization="none", diagonal="measured"):
    """Evaluate the full matrix, lower-triangular bias, >=0 threshold and ranks.

    keys: validated here as a nonempty (trials,N) batch of 4/8-bit integers.
    errors: optional finite (trials,N,N) deviations in NORMALIZED signal units,
        added to D before any quantization or bias. Never generated implicitly.
    diagonal: 'measured' retains diagonal noise; 'exact' explicitly restores the
        known self-difference to zero. The latter is an algorithmic control.
    quantization: 'none' reproduces the noiseless source equations by default;
        'matched' adds the documented pre-bias quantizer from comparison.py.

    The paper counts each diagonal one, hence ranks are 1..N. Only placement
    subtracts one. Equal keys acquire increasing ranks in original-index order.
    """
    precision = Precision(bits, bits, bits)
    keys = validate_keys(keys, bits)
    if keys.ndim != 2:
        raise ValueError("keys must have shape (trials,N)")
    if diagonal not in ("exact", "measured"):
        raise ValueError("diagonal must be 'exact' or 'measured'")
    delta = precision.delta_in
    encoded = keys * delta
    difference = encoded[:, None, :] - encoded[:, :, None]
    noisy = difference.copy()
    if errors is not None:
        errors = np.asarray(errors, dtype=np.float64)
        if errors.shape != difference.shape or not np.all(np.isfinite(errors)):
            raise ValueError("errors must be finite and have shape (trials,N,N)")
        noisy += errors
    n = keys.shape[1]
    if diagonal == "exact":
        noisy[:, np.arange(n), np.arange(n)] = 0
    measured = quantize_difference(noisy, bits, quantization)
    # U is one below the diagonal. The normalized unit bias is delta, not 1.
    bias = delta * np.tril(np.ones((n, n)), k=-1)
    biased = measured - bias
    threshold = biased >= 0
    # Axis 1 is the row/competitor axis; sum columns as in the paper.
    ranks = threshold.sum(axis=1, dtype=np.int64)
    return MatrixRanking(difference, measured, biased, threshold, ranks,
                         place_ranks(keys, ranks - 1))
