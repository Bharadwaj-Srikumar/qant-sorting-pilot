"""Optional CPU periodic pair checks; no historical unmatched noise scenarios."""
import unittest
import numpy as np
try:
    from qant_sorting.periodic_comparison import periodic_values, calibration_reference, require_cpu_backend
    from qant_sorting.sdk_mapping import SdkDifference
except ImportError:
    periodic_values = None

@unittest.skipIf(periodic_values is None, "optional Q.ANT CPU SDK not installed")
class PeriodicTests(unittest.TestCase):
    def test_all_pairs_after_one_zero_reference(self):
        require_cpu_backend()
        reference = calibration_reference()
        for bits in (4,8):
            a,b = np.meshgrid(np.arange(2**bits),np.arange(2**bits),indexing="ij")
            score=periodic_values(SdkDifference(bits)(a,b))-reference
            np.testing.assert_array_equal(np.sign(score),np.sign(a-b))

    def test_full_matrix_sdk_submits_diagonal_and_both_directions(self):
        from qant_sorting.sorting_schedules import rank_sort
        require_cpu_backend()
        model=SdkDifference(4)
        result=rank_sort(np.array([[3,1,3,0]]),model,bias_step=1/16)
        self.assertEqual(model.counts.pair_differences,16)
        self.assertEqual(model.counts.api_calls,1)
        np.testing.assert_array_equal(result[1],[[3,1,0,2]])

if __name__=="__main__":
    unittest.main()
