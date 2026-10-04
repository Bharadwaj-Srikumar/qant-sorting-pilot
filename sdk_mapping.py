"""Execute the common pair-difference operation through Q.ANT's official API.

This module never substitutes NumPy subtraction for the SDK call. The official
CPU backend uses BF16 multiplication, FP32 accumulation and BF16 output. Its
answers validate software integration, not photonic accuracy or NPU speed.

The original integer records stay in electronic memory. Only normalized pairs
enter the SDK. Their measured signs control record swaps or rank increments.
"""
from dataclasses import dataclass
import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant



@dataclass
class CallCounts:
    """Logical API traffic. These are not observed PCIe transaction bytes."""
    api_calls: int = 0
    pair_differences: int = 0
    feature_bytes: int = 0
    weight_bytes: int = 0
    output_bytes: int = 0
    largest_pair_batch: int = 0


class SdkDifference:
    """Use X.shape=(number_of_pairs, 2), W.shape=(1, 2), Y=X@W.T.

    A trial batch may combine independent sorts into one SDK call per active
    bitonic layer, or one rank-pair call. Accepted batch shapes in the CPU
    backend are NOT evidence of a physical tile or maximum hardware batch size.
    """
    def __init__(self, key_bits, device_id=0):
        if key_bits not in (4, 8):
            raise ValueError('This registered pilot accepts 4-bit or 8-bit key domains')
        self.key_bits = key_bits
        self.device_id = device_id
        # Retain the declared-range scale from the prior matched-input cases.
        # These multiples of 1/16 or 1/256 are exactly representable in BF16.
        self.denominator = 2 ** key_bits
        self.weights = np.array([[1, -1]], dtype=bfloat16)
        self.counts = CallCounts()

    def __call__(self, a, b):
        """Normalize and pack raw integer pairs, execute SDK, restore shape."""
        if a.shape != b.shape:
            raise ValueError('The two pair arrays must have the same shape')
        features = np.stack((a, b), axis=-1).reshape(-1, 2)
        features = np.ascontiguousarray(features / self.denominator, dtype=bfloat16)
        result = qant.native.linear_fprop(features, self.weights, self.device_id)
        if result.shape != (a.size, 1) or result.dtype != np.dtype(bfloat16):
            raise AssertionError('Unexpected SDK output contract')
        c = self.counts
        c.api_calls += 1
        c.pair_differences += a.size
        c.feature_bytes += features.nbytes
        c.weight_bytes += self.weights.nbytes
        c.output_bytes += result.nbytes
        c.largest_pair_batch = max(c.largest_pair_batch, a.size)
        # Widen the returned values for electronic sign decisions; this does not
        # recover lost precision or perform a second arithmetic comparison.
        return result.astype(np.float32).reshape(a.shape)


def backend_identity():
    """Report actual runtime identity; never mistake synthetic NPU IDs for hardware."""
    return {'sdk_version': qant.__version__, 'driver_info': qant.info.get_driver_info()}
