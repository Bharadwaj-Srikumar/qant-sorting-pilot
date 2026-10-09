# Test guide: units, decision thresholds and integration of the common model.
# Exhaustive pairs cover unsigned-key subtraction as well as all equality cases.
# Other checks isolate rounding, seeded stages, coherent offsets and covariance.
# Physical receiver numbers used in an arithmetic test are fixtures only; they
# are not calibration data or settings of the saved sorting sensitivity sweep.

"""Decision boundaries, covariance, and integration of the common noise model."""
from dataclasses import replace
import unittest
import numpy as np
from qant_sorting.common_noise_model import (NoiseConfig, CommonNoiseComparison, evaluate_difference,
                                quantize, projected_variance, receiver_current_variance,
                                ELEMENTARY_CHARGE_C)
from qant_sorting.sorting_schedules import bitonic_sort, rank_sort


class CommonNoiseTests(unittest.TestCase):
    # Enumerate every ordered 4/8-bit pair for direct and ideal-sine transfers.
    # Use unsigned inputs to expose accidental subtraction wraparound before casting.
    def test_exhaustive_noiseless_pairs_both_widths_and_transfers(self):
        for bits in (4, 8):
            a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing="ij")
            for kind in ("direct", "ideal_sine"):
                result = CommonNoiseComparison(NoiseConfig(bits, kind), range(len(a)))(a.astype(np.uint8), b.astype(np.uint8))
                np.testing.assert_array_equal(np.sign(result), np.sign(a - b))

    # Check exact half-code rounding plus values just inside/outside both zero-code
    # boundaries. Correct signs alone would miss an incorrect equality interval.
    def test_nearest_even_boundaries_and_false_ties(self):
        np.testing.assert_array_equal(quantize(np.array([-.5, .5, 1.5, 2.5]), 1), [0, 0, 2, 2])
        c = NoiseConfig(8)
        for direction in (-1, 1):
            values = c.delta * direction * np.array([.49999, .5, .50001])
            got, _ = evaluate_difference(values, c)
            np.testing.assert_array_equal(np.sign(got), [0, 0, direction])

    # Give both monotone transfers identical noisy values AFTER the same rounding.
    # Their signs must match, including clipped tails and the quantized zero code.
    def test_shared_prequantized_noise_preserves_decisions(self):
        rng = np.random.default_rng(71)
        d = rng.uniform(-1.1, 1.1, 10000)
        noise = rng.standard_normal(10000)
        for bits in (4, 8):
            c = NoiseConfig(bits, upstream_sigma_lsb=.25, pre_step_lsb=1, post_step_lsb=0)
            direct, _ = evaluate_difference(d, c, noise)
            sine, _ = evaluate_difference(d, replace(c, transfer="ideal_sine"), noise)
            np.testing.assert_array_equal(np.sign(direct), np.sign(sine))

    # Verify a local gain scales both upstream signal separation and its standard
    # deviation, and check the same result through Jacobian variance propagation.
    def test_gain_normalization_does_not_create_free_noise_reduction(self):
        # First-order variance: raw sin gain alpha scales both signal and upstream noise.
        from qant_sorting.common_noise_model import ALPHA
        sigma = .25 / 256
        self.assertAlmostEqual((ALPHA / 256)/(ALPHA * sigma), (1/256)/sigma)
        self.assertAlmostEqual(projected_variance([ALPHA], [[sigma**2]]), (ALPHA*sigma)**2)

    # Check absolute trial IDs reproduce split batches, and changing upstream sigma
    # does not shift the readout-stage random stream. Stages must remain separable.
    def test_batch_independence_and_stage_streams(self):
        a = np.arange(16).reshape(4, 4)
        b = np.flip(a, axis=1)
        c = NoiseConfig(4, upstream_sigma_lsb=.25, readout_sigma_lsb=.25)
        together = CommonNoiseComparison(c, range(4))(a, b)
        apart = np.concatenate([CommonNoiseComparison(c, [i])(a[i:i+1], b[i:i+1]) for i in range(4)])
        np.testing.assert_array_equal(together, apart)
        no_upstream = CommonNoiseComparison(replace(c, upstream_sigma_lsb=0), range(4))
        with_upstream = CommonNoiseComparison(c, range(4))
        no_upstream(a, b)
        with_upstream(a, b)
        for r, s in zip(no_upstream.streams[1], with_upstream.streams[1]):
            np.testing.assert_array_equal(r.standard_normal(8), s.standard_normal(8))

    # Check repeated zero inputs share the fixed offset and extreme values saturate
    # without folding to a wrong sine sign. Count the two over-range inputs explicitly.
    def test_drift_is_fixed_and_clipping_stays_on_monotone_branch(self):
        c = NoiseConfig(4, "ideal_sine", post_step_lsb=0, output_drift_lsb=.25)
        out, diagnostic = evaluate_difference([0, 0, -100, 100], c)
        self.assertEqual(out[0], out[1])
        self.assertAlmostEqual(out[0], c.delta/4)
        self.assertEqual(diagnostic["input_range_exceeded"], 2)
        self.assertLess(out[2], 0)
        self.assertGreater(out[3], 0)

    # Exercise both schedules/transfers on domain endpoints and all-equal records.
    # Use signed arrays because the existing rank output reserves -1 for invalidity.
    def test_both_sorters_stable_noiseless_with_extremes(self):
        # The existing rank schedule uses signed -1 markers for invalid outputs.
        keys = np.array([[255, 0, 255, 1], [3, 3, 3, 3]], dtype=np.int64)
        for sorter in (bitonic_sort, rank_sort):
            for kind in ("direct", "ideal_sine"):
                _, indices, valid = sorter(keys, CommonNoiseComparison(NoiseConfig(8, kind), range(2)))
                self.assertTrue(valid.all())
                np.testing.assert_array_equal(indices, np.argsort(keys, axis=1, kind="stable"))

    # Check SI-unit receiver arithmetic using explicit fixture values, then show
    # perfect common-mode covariance cancels while independent branch variance adds.
    # Reject a covariance matrix that is not positive semidefinite.
    def test_receiver_units_and_covariance_cancellation(self):
        current, bandwidth, rin, thermal = 1e-3, 1e6, -145, 1e-24
        expected = bandwidth * (thermal + 2*ELEMENTARY_CHARGE_C*current + 10**(-14.5)*current**2)
        self.assertAlmostEqual(receiver_current_variance(current, bandwidth, rin, thermal)/expected, 1)
        # Perfect common-mode correlation cancels in a balanced difference.
        self.assertEqual(projected_variance([1, -1], [[4, 4], [4, 4]]), 0)
        self.assertEqual(projected_variance([1, -1], [[4, 0], [0, 4]]), 8)
        with self.assertRaises(ValueError):
            projected_variance([1, 1], [[1, 2], [2, 1]])

    # Reject negative/nonfinite scales, nonpositive gain and an out-of-domain key.
    # The simulation must fail at its input boundary, not produce plausible-looking scores.
    def test_reject_invalid_settings_and_keys(self):
        for settings in ({"readout_sigma_lsb": -1}, {"post_step_lsb": float("nan")}, {"gain_error": -1}):
            with self.assertRaises(ValueError):
                NoiseConfig(8, **settings)
        with self.assertRaises(ValueError):
            CommonNoiseComparison(NoiseConfig(4), [0])(np.array([[16]]), np.array([[0]]))


if __name__ == "__main__":
    unittest.main()
