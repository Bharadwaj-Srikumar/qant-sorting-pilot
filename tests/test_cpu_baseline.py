# Test guide: correctness of the digital benchmark's output contract.
# These checks run outside timing: sorted values and original record indices
# must both be correct, with stable ties and unchanged input arrays.
# They do not assert absolute CPU speed or compare physical accelerator timing.

"""Checks for the output contract used in the digital timing experiment."""

import unittest
import numpy as np
from run_cpu_baseline import stable_records, validate_records


# Unit-test group: independent contracts and edge cases for this module family.
# Each method creates its own fixtures/streams, so tests do not depend on order
# or change the stored research corpus and reference result archives.
class CpuBaselineTests(unittest.TestCase):
    # Check uint8/int64 extremes, repeated keys, all-equal rows and stable indices.
    # Also ensure the timed helper leaves its input records unchanged.
    def test_ties_extremes_and_multiple_rows(self):
        for dtype in (np.uint8, np.int64):
            data = np.array([[255, 0, 255, 1, 0], [7, 7, 7, 7, 7]], dtype=dtype)
            values, indices = stable_records(data)
            np.testing.assert_array_equal(indices, [[1, 4, 3, 0, 2], [0, 1, 2, 3, 4]])
            validate_records(data, values, indices)
            np.testing.assert_array_equal(data, [[255, 0, 255, 1, 0], [7, 7, 7, 7, 7]])

    # Feed swapped equal-key identities, duplicate indices and inconsistent values
    # to the validator. Each violates a different required benchmark output property.
    def test_invalid_and_unstable_outputs_are_rejected(self):
        data = np.array([[2, 1, 1]])
        for values, indices in (([[1, 1, 2]], [[2, 1, 0]]),
                                ([[1, 1, 2]], [[1, 1, 0]]),
                                ([[1, 2, 2]], [[1, 2, 0]])):
            with self.assertRaises(AssertionError):
                validate_records(data, np.array(values), np.array(indices))

    # Compare concatenated results from different batch partitions with the full
    # batch. Batch size may affect timing, but must not alter the sorted records.
    def test_batching_keeps_records_and_order(self):
        data = np.random.default_rng(42).integers(0, 16, (12, 16), dtype=np.uint8)
        expected = stable_records(data)
        for batch_size in (1, 3, 12):
            results = [stable_records(data[i:i+batch_size]) for i in range(0, 12, batch_size)]
            for field in (0, 1):
                np.testing.assert_array_equal(np.concatenate([r[field] for r in results]), expected[field])


# Direct execution starts this file's command-line/test entry point.
# Importing helpers does not run THIS block; the module reading guide
# identifies any other top-level file loading or writing separately.
if __name__ == "__main__":
    unittest.main()
