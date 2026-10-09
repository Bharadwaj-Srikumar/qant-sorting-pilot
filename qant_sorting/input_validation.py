# Reading guide: public validation boundary for integer sorting inputs.
# Validation happens before conversion/normalization so bad keys are not silently
# rounded, clipped, or accepted after string/bool coercion. Returned int64 keys
# support signed differences and the -1 failure markers used by rank sorting.
# This checks the key domain, not network size, precision matching, or a device's
# physical input range; those belong to the caller/model that uses the keys.

"""Validate raw keys once, before normalization or sorting begins."""

import numbers

import numpy as np


# Input: a nonempty one-dimensional list or rectangular two-dimensional batch,
# plus an integer key width from 1 to 30. Return a separate int64 array.
# Object conversion preserves original element types until each is checked;
# otherwise a string or boolean could silently become an accepted integer.
# Whole finite real values such as 3.0 are allowed, but fractions/NaN/infinity,
# booleans, strings, negatives and values above 2**key_bits-1 raise ValueError.
# Error locations are zero-based. Shape/network and physical-range checks remain
# the responsibility of the caller that selects a sorting architecture.
def validate_keys(keys, key_bits):
    """Accept a nonempty 1-D array or batch of whole, finite numbers.

    Indexes in errors are zero-based. Integral floats (e.g. 3.0) are accepted;
    strings and booleans are not numeric keys. Return an independent int64 array.
    The initial experiment only uses 4/8 bits; supported key widths are 1..30.
    """
    if (
        not isinstance(key_bits, int)
        or isinstance(key_bits, bool)
        or not 1 <= key_bits <= 30
    ):
        raise ValueError('key_bits must be an integer from 1 to 30')
    # Object dtype preserves the original type, so strings and booleans are
    # rejected instead of being silently converted to integer keys.
    a = np.asarray(keys, dtype=object)
    if a.ndim not in (1, 2) or 0 in a.shape:
        raise ValueError('keys must be a nonempty array or a rectangular batch of arrays')
    maximum = 2**key_bits - 1
    for index, value in np.ndenumerate(a):
        location = (
            'input index %d' % index[0] if a.ndim == 1
            else 'array index %d, key index %d' % index
        )
        ok = not isinstance(value, (bool, np.bool_)) and (
            isinstance(value, numbers.Integral) or
            (isinstance(value, numbers.Real) and np.isfinite(float(value))
             and float(value).is_integer()))
        if not ok or not 0 <= value <= maximum:
            raise ValueError(f'{location}: key {value!r} must be a finite whole number in range [0, {maximum}]')
    return a.astype(np.int64)
