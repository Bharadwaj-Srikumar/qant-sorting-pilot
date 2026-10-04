"""Validate raw keys once, before normalization or sorting begins."""

import numbers

import numpy as np


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
