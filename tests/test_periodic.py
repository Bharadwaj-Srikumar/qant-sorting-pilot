# Test guide: optional official CPU periodic operation and per-trial seeds.
# Import failure skips this class, so a skipped result must not be reported as
# an SDK pass. When the SDK is present, the CPU guard is still required.
# Exhaustive pair correctness does not prove full-sort robustness under noise.

"""Optional official CPU-SDK checks; skipped when the SDK is absent."""
import unittest
import numpy as np
try:
    from qant_sorting.periodic_comparison import PeriodicComparison, calibration_reference, require_cpu_backend
except ImportError:
    PeriodicComparison = None

@unittest.skipIf(PeriodicComparison is None, "optional Q.ANT CPU SDK not installed")
class PeriodicTests(unittest.TestCase):
    # On the guarded CPU SDK, enumerate both complete key domains and calibrate
    # a half-margin tie band. Check noiseless signs with and without that fixed band.
    def test_all_pairs_and_fixed_deadband(self):
        require_cpu_backend()
        reference = calibration_reference()
        for bits in (4, 8):
            a, b = np.meshgrid(np.arange(2 ** bits), np.arange(2 ** bits), indexing="ij")
            model = PeriodicComparison(bits, 0, "output", [1], range(len(a)), reference)
            score = model(a, b)
            margin = np.min(abs(score[a != b]))
            np.testing.assert_array_equal(np.sign(score), np.sign(a-b))
            calibrated = PeriodicComparison(bits, 0, "output", [1], range(len(a)),
                                            reference, margin / 2)
            np.testing.assert_array_equal(np.sign(calibrated(a, b)), np.sign(a-b))

    # Compare one output-noise batch with two batches using the same absolute IDs.
    # Bit-for-bit equality ensures CPU noise realization is independent of batching.
    def test_noise_stream_does_not_depend_on_batch_partition(self):
        reference = calibration_reference()
        a = np.array([[10, 9], [9, 9], [255, 0], [2, 3]])
        b = np.array([[9, 10], [9, 8], [0, 255], [3, 2]])
        whole = PeriodicComparison(8, .25, "output", [123], range(4), reference)(a, b)
        split = np.concatenate([PeriodicComparison(8, .25, "output", [123], range(i,i+2),
                            reference)(a[i:i+2], b[i:i+2]) for i in (0,2)])
        np.testing.assert_array_equal(whole, split)
