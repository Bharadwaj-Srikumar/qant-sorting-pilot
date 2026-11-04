"""Small integration checks of the official CPU mapping, without added noise."""

from importlib.util import find_spec
import unittest

import numpy as np

from qant_sorting.sdk import SdkDifference, backend_identity
from qant_sorting.sorters import bitonic_sort, rank_sort


SDK_AVAILABLE = all(find_spec(name) is not None for name in (
    "qant_native_computing_toolkit", "ml_dtypes",
))


@unittest.skipUnless(SDK_AVAILABLE, "official Q.ANT CPU SDK and ml_dtypes are not installed")
class SdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        identity = backend_identity()
        if identity["sdk_version"] != "2.3.1" or not identity["driver_info"].startswith("cpu-backend;"):
            raise RuntimeError("SDK tests require the pinned official 2.3.1 CPU backend")

    def test_all_pairs_match_the_declared_normalization(self):
        """Test ties, adjacent keys and both extremes in both complete domains."""
        for bits in (4, 8):
            a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing="ij")
            a.flags.writeable = b.flags.writeable = False
            model = SdkDifference(bits)
            result = model(a, b)
            np.testing.assert_array_equal(result, (a-b)/2**bits)
            self.assertEqual(result.dtype, np.dtype(np.float32))
            self.assertEqual(model.counts.api_calls, 1)
            self.assertEqual(model.counts.pair_differences, a.size)
            self.assertEqual(model.counts.feature_bytes, 4*a.size)
            self.assertEqual(model.counts.output_bytes, 2*a.size)
            self.assertEqual(model.counts.weight_bytes, 4)

    def test_both_sorters_keep_original_records_and_stable_ties(self):
        for bits in (4, 8):
            keys = np.array([[3, 1, 3, 0], [2**bits-1, 0, 2**bits-1, 1]])
            original = keys.copy()
            expected = np.argsort(keys, axis=1, kind="stable")
            for sorter, pairs, calls in ((bitonic_sort, 12, 3), (rank_sort, 32, 1)):
                model = SdkDifference(bits)
                if sorter is rank_sort:
                    values, indices, valid = sorter(keys, model, bias_step=2.**(-bits))
                else:
                    values, indices, valid = sorter(keys, model)
                np.testing.assert_array_equal(indices, expected)
                np.testing.assert_array_equal(values, np.take_along_axis(keys, expected, axis=1))
                self.assertTrue(valid.all())
                self.assertEqual(model.counts.pair_differences, pairs)
                self.assertEqual(model.counts.api_calls, calls)
                np.testing.assert_array_equal(keys, original)

    def test_full_rank_matrix_submits_both_directions_and_diagonal(self):
        keys = np.array([[3, 1, 3, 0]])
        model = SdkDifference(4)
        submitted = []

        def observed(a, b):
            submitted.append((a.copy(), b.copy()))
            return model(a, b)

        result = rank_sort(keys, observed, bias_step=1/16)
        self.assertEqual(len(submitted), 1)
        np.testing.assert_array_equal(submitted[0][0], [[3, 1, 3, 0]*4])
        np.testing.assert_array_equal(submitted[0][1], [[3]*4 + [1]*4 + [3]*4 + [0]*4])
        self.assertEqual(model.counts.pair_differences, 16)
        self.assertEqual(model.counts.api_calls, 1)
        np.testing.assert_array_equal(result[1], [[3, 1, 0, 2]])


if __name__ == "__main__":
    unittest.main()
