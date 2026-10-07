# Reading guide: the software boundary of the linear Q.ANT mapping.
# Pack each pair into one row [a/2**bits, b/2**bits], use weights [1, -1],
# and reshape the returned single-column tensor back to the caller's pair grid.
# The returned number is still interpreted and routed by the host sorter.
# Counters describe buffers visible at the public API, not observed bus traffic.
# Importing this module requires the optional SDK and ml_dtypes; the pure NumPy
# reference experiment does not import it. CPU integration checks are in
# run_sdk_control.py, and backend identity must accompany any reported result.

"""Execute the common pair-difference operation through Q.ANT's official API.

This module never substitutes NumPy subtraction for the SDK call. The official
CPU backend uses BF16 multiplication, FP32 accumulation and BF16 output. Its
answers validate software integration, not photonic accuracy or NPU speed.

The original integer records stay in electronic memory. Only normalized pairs
enter the SDK. Their returned signs control electronic record swaps or rank increments.
Only native.linear_fprop is called here. The public SDK implements ReLU on
the host CPU; this module does not execute a native nonlinear C&E kernel.
See docs/QANT_NONLINEARITY.md for the source-verified execution boundary.
"""
from dataclasses import dataclass
import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant



# Mutable accounting record for one SdkDifference instance.
# api_calls counts public linear submissions; pair_differences counts scalar pairs.
# feature/weight/output bytes use actual allocated BF16 buffers. largest_pair_batch
# records the biggest software submission, not a hardware tile or proven capacity.
@dataclass
class CallCounts:
    """Logical API traffic. These are not observed PCIe transaction bytes."""
    api_calls: int = 0
    pair_differences: int = 0
    feature_bytes: int = 0
    weight_bytes: int = 0
    output_bytes: int = 0
    largest_pair_batch: int = 0


# Adapter from the sorters' arbitrary pair-array shape to the SDK matrix API.
# For P pairs, features has shape (P,2), weights (1,2), output (P,1).
# One call handles all supplied pairs regardless of how many trial rows they came
# from. The supported CPU batch shape is not evidence that physical hardware fits it.
class SdkDifference:
    """Use X.shape=(number_of_pairs, 2), W.shape=(1, 2), Y=X@W.T.

    A trial batch may combine independent sorts into one SDK call per active
    bitonic layer, or one rank-pair call. Accepted batch shapes in the CPU
    backend are NOT evidence of a physical tile or maximum hardware batch size.
    """
    # Accept only the registered 4/8-bit key domains; retain the selected device ID.
    # Normalize by the declared key range scale 2**bits, never by observed maxima.
    # Prepare BF16 [1,-1] weights once and initialize logical accounting counters.
    # The constructor alone does not verify CPU/hardware identity; callers do that.
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

    # Flatten equal-shaped raw key arrays into P two-feature rows and submit them
    # through native.linear_fprop. Require the documented BF16 single-column output.
    # Return a float32 view of the returned numbers reshaped to the original pair grid.
    # Widening the dtype does not recover precision lost inside the SDK.
    # Every invocation increases call/pair/payload counters; inputs are not modified.
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


# Return installed SDK version and actual driver description as a small dict.
# Use this evidence in output metadata and CPU guards. A chosen device_id alone
# does not prove that an NPU was reached or that an optical computation ran.
def backend_identity():
    """Report actual runtime identity; never mistake synthetic NPU IDs for hardware."""
    return {'sdk_version': qant.__version__, 'driver_info': qant.info.get_driver_info()}
