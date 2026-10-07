"""Independent permutation examples, tie semantics and evidence recovery."""

import io
import itertools
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np
from ranking_quality import prepare_keys, score_saved_order
from saved_output_reader import SavedOutputs, recover_members


class RankingQualityTests(unittest.TestCase):
    def test_adjacent_swap_and_reversal(self):
        p = prepare_keys(np.array([[0, 1, 2, 3]]), 4)
        result = score_saved_order(p, np.array([[0, 2, 1, 3]]), [1, 2, 4])
        self.assertEqual(result["inversions"][0], 1)
        self.assertAlmostEqual(result["tau_b"][0], 2/3)
        self.assertEqual(result["distance_inversions"][1], 1)
        self.assertEqual(result["distance_pairs"][1], 3)
        self.assertEqual(result["recall"][2]["stable"][0], .5)
        reversed_result = score_saved_order(p, np.array([[3, 2, 1, 0]]))
        self.assertEqual(reversed_result["inversions"][0], 6)
        self.assertEqual(reversed_result["tau_b"][0], -1)

    def test_boundary_ties_do_not_count_as_key_errors(self):
        p = prepare_keys(np.array([[2, 2, 1, 3]]), 4)
        result = score_saved_order(p, np.array([[2, 1, 0, 3]]), [2])
        np.testing.assert_array_equal(result["flags"], [[True, True, False]])
        self.assertAlmostEqual(result["tau_b"][0], np.sqrt(5/6))
        self.assertEqual(result["tau_key_normalized"][0], 1)
        self.assertEqual(result["recall"][2]["stable"][0], .5)
        self.assertEqual(result["recall"][2]["tie_neutral"][0], 1)

    def test_all_equal_and_singleton_tau_are_undefined(self):
        for data, indices in (([[5, 5, 5]], [[2, 1, 0]]), ([[7]], [[0]])):
            p = prepare_keys(np.array(data), 4)
            result = score_saved_order(p, np.array(indices), [1])
            self.assertTrue(np.isnan(result["tau_b"][0]))
            self.assertTrue(np.isnan(result["tau_key_normalized"][0]))
            self.assertEqual(result["recall"][1]["tie_neutral"][0], 1)
            self.assertTrue(result["flags"][0, 1])

    def test_invalid_outputs_never_get_rank_quality(self):
        p = prepare_keys(np.tile([0, 1, 2, 3], (3, 1)), 4)
        result = score_saved_order(p, np.array([[0, 0, 2, 3], [-1, 0, 1, 2], [0, 1, 2, 8]]))
        self.assertFalse(result["flags"].any())
        self.assertTrue(np.isnan(result["tau_b"]).all())
        self.assertEqual(result["distance_pairs"].sum(), 0)
        self.assertTrue(np.isnan(result["recall"][1]["stable"]).all())

    def test_uint8_key_distances_do_not_wrap(self):
        p = prepare_keys(np.array([[0, 255]], dtype=np.uint8), 8)
        result = score_saved_order(p, np.array([[1, 0]]))
        self.assertEqual(result["distance_pairs"][255], 1)
        self.assertEqual(result["distance_inversions"][255], 1)

    def test_exhaustive_small_orders_against_pair_enumeration(self):
        # 240 permutations: strict order plus a weak order with ties.
        for keys in ([0, 1, 2, 3, 4], [0, 0, 1, 2, 2]):
            permutations = np.array(list(itertools.permutations(range(5))))
            p = prepare_keys(np.tile(keys, (len(permutations), 1)), 4)
            result = score_saved_order(p, permutations, [1, 2, 3, 5])
            expected_hist = np.zeros(16, dtype=int)
            for row, order in enumerate(permutations):
                values = [keys[i] for i in order]
                inversion_count = 0
                for a in range(5):
                    for b in range(a+1, 5):
                        if values[a] > values[b]:
                            inversion_count += 1
                            expected_hist[values[a]-values[b]] += 1
                self.assertEqual(result["inversions"][row], inversion_count)
                truth = sorted(range(5), key=lambda i: (keys[i], i))
                for k in (1, 2, 3, 5):
                    expected = len(set(order[-k:]) & set(truth[-k:])) / k
                    self.assertEqual(result["recall"][k]["stable"][row], expected)
                    # Brute-force all optimal key-only subsets, independent of the threshold formula.
                    choices = list(itertools.combinations(range(5), k))
                    best = max(sum(keys[i] for i in choice) for choice in choices)
                    neutral = max(len(set(order[-k:]) & set(choice)) / k for choice in choices
                                  if sum(keys[i] for i in choice) == best)
                    self.assertEqual(result["recall"][k]["tie_neutral"][row], neutral)
            np.testing.assert_array_equal(result["distance_inversions"], expected_hist)

    def test_tau_b_against_scipy(self):
        try:
            from scipy.stats import kendalltau
        except ImportError:
            self.skipTest("SciPy is an optional independent check, not an evaluation dependency")
        rng = np.random.default_rng(20261007)
        data = rng.integers(0, 8, (40, 17))
        orders = np.array([rng.permutation(17) for _ in range(40)])
        result = score_saved_order(prepare_keys(data, 4), orders)
        for i in range(40):
            positions = np.argsort(orders[i])
            expected = kendalltau(data[i], positions, variant="b").statistic
            self.assertAlmostEqual(result["tau_b"][i], expected, places=14)


class EvidenceReaderTests(unittest.TestCase):
    def test_missing_directory_preserves_complete_crc_checked_members(self):
        memory = io.BytesIO()
        np.savez_compressed(memory, flags=np.array([[True, False, False]]), indices=np.array([[1, 0]]))
        payload = memory.getvalue()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            directory = archive.start_dir
            second = archive.infolist()[1].header_offset
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"incomplete.npz"
            path.write_bytes(payload[:directory])
            with self.assertRaises(ValueError):
                SavedOutputs(path)
            reader = SavedOutputs(path, allow_incomplete=True)
            self.assertIn("flags", reader)
            np.testing.assert_array_equal(reader["indices"], [[1, 0]])
            self.assertFalse(reader.audit["complete_archive"])
            self.assertEqual(path.read_bytes(), payload[:directory])
            # An incomplete second header cannot produce an invented indices array.
            path.write_bytes(payload[:second+10])
            arrays, audit = recover_members(path)
            self.assertEqual(set(arrays), {"flags"})
            self.assertEqual(audit["complete_members"], 1)

    def test_corrupted_member_is_rejected(self):
        memory = io.BytesIO()
        np.savez(memory, x=np.arange(10))  # uncompressed member for controlled corruption
        payload = bytearray(memory.getvalue())
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            directory = archive.start_dir
        payload[directory-1] ^= 1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"corrupt.npz"
            path.write_bytes(payload[:directory])
            with self.assertRaisesRegex(ValueError, "CRC"):
                recover_members(path)


if __name__ == "__main__":
    unittest.main()
