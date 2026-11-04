"""Check ranking metrics and scoring saved runs with small independent examples."""

from contextlib import redirect_stdout
import csv
import gzip
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from qant_sorting import quality
from qant_sorting.evaluation import prepare_keys, score_saved_order


class RankingQualityTests(unittest.TestCase):
    # Use hand-countable strict orders to verify inversion count, tau-b, exact gap
    # histogram and top-k recall. A full reversal provides the tau=-1 endpoint.
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

    # Swap equal-key identities at a top-k boundary: key order remains correct,
    # stability and strict recall can fail, but tie-neutral recall remains one.
    # The standard tau-b ceiling is below one because truth contains a tie.
    def test_boundary_ties_do_not_count_as_key_errors(self):
        p = prepare_keys(np.array([[2, 2, 1, 3]]), 4)
        result = score_saved_order(p, np.array([[2, 1, 0, 3]]), [2])
        np.testing.assert_array_equal(result["flags"], [[True, True, False]])
        self.assertAlmostEqual(result["tau_b"][0], np.sqrt(5/6))
        self.assertEqual(result["tau_key_normalized"][0], 1)
        self.assertEqual(result["recall"][2]["stable"][0], .5)
        self.assertEqual(result["recall"][2]["tie_neutral"][0], 1)

    # Arrays with no unequal pair have no meaningful ordering correlation. Require
    # NaN tau while preserving valid key correctness and tie-neutral set recall.
    def test_all_equal_and_singleton_tau_are_undefined(self):
        for data, indices in (([[5, 5, 5]], [[2, 1, 0]]), ([[7]], [[0]])):
            p = prepare_keys(np.array(data), 4)
            result = score_saved_order(p, np.array(indices), [1])
            self.assertTrue(np.isnan(result["tau_b"][0]))
            self.assertTrue(np.isnan(result["tau_key_normalized"][0]))
            self.assertEqual(result["recall"][1]["tie_neutral"][0], 1)
            self.assertTrue(result["flags"][0, 1])

    # Use duplicate, negative and too-large indices to ensure invalid permutations
    # receive neither tau nor recall nor comparable-pair denominators.
    def test_invalid_outputs_never_get_rank_quality(self):
        p = prepare_keys(np.tile([0, 1, 2, 3], (3, 1)), 4)
        result = score_saved_order(p, np.array([[0, 0, 2, 3], [-1, 0, 1, 2], [0, 1, 2, 8]]))
        self.assertFalse(result["flags"].any())
        self.assertTrue(np.isnan(result["tau_b"]).all())
        self.assertEqual(result["distance_pairs"].sum(), 0)
        self.assertTrue(np.isnan(result["recall"][1]["stable"]).all())

    # The reversed pair [0,255] has distance 255, not 1 after unsigned wraparound.
    # Check both its denominator and inversion histogram use signed differences.
    def test_uint8_key_distances_do_not_wrap(self):
        p = prepare_keys(np.array([[0, 255]], dtype=np.uint8), 8)
        result = score_saved_order(p, np.array([[1, 0]]))
        self.assertEqual(result["distance_pairs"][255], 1)
        self.assertEqual(result["distance_inversions"][255], 1)

    # For all permutations of a strict and a tied five-record dataset, independently
    # enumerate inversions and optimal top-k subsets. This checks metric semantics
    # without copying the vectorized implementation formula as the expected answer.
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


class QualityRunnerTests(unittest.TestCase):
    def write_fixture(self, directory, extra_member=False):
        """Create a tiny saved run outside its project, with one invalid output."""
        project, results = directory / "project", directory / "new_run"
        (project / "data").mkdir(parents=True)
        results.mkdir()
        dataset = "b4_n4_duplicates"
        inputs = project / "data/inputs.npz"
        np.savez(inputs, **{dataset: np.array([[3, 1, 3, 0], [3, 1, 3, 0]])})
        case = dataset + "_noise025_rank"
        members = {
            case + "_indices": np.array([[3, 1, 0, 2], [-1, -1, -1, -1]]),
            case + "_flags": np.array([[True, True, True], [False, False, False]]),
        }
        if extra_member:
            members["unlisted_case_flags"] = np.array([[True, True, True]])
        np.savez(results / "trial_outcomes.npz", **members)
        row = dict(key_bits=4, n=4, family="duplicates", eta=.25, mapping="rank",
                   trials=2, valid_outputs=1, correct_sorts=1, stable_sorts=1)
        quality.write_csv(results / "accuracy.csv", [row])
        return project, results, quality.file_hash(inputs)

    def test_results_directory_and_invalid_zero_recall(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project, results, checksum = self.write_fixture(directory)
            output = directory / "quality"
            with patch.object(quality, "ROOT", project), \
                 patch.object(quality, "INPUT_SHA256", checksum), \
                 patch.object(quality, "source_hashes", return_value={}), \
                 redirect_stdout(io.StringIO()):
                quality.main(["--results-dir", str(results), "--output-dir", str(output)])
            with (output / "summary.csv").open(newline="") as handle:
                summary = list(csv.DictReader(handle))[0]
            self.assertEqual((summary["valid_outputs"], summary["invalid_outputs"]), ("1", "1"))
            self.assertEqual(float(summary["whole_sort_accuracy"]), .5)
            with (output / "recall.csv").open(newline="") as handle:
                recall = next(row for row in csv.DictReader(handle) if row["k"] == "1")
            for variant in ("stable", "tie_neutral"):
                self.assertEqual(float(recall[variant + "_mean_valid"]), 1)
                self.assertEqual(float(recall[variant + "_mean_all_invalid_zero"]), .5)
            with gzip.open(output / "distance.csv.gz", "rt", newline="") as handle:
                distances = list(csv.DictReader(handle))
            self.assertEqual(sum(int(row["pairs_at_distance"]) for row in distances), 5)
            validation = json.loads((output / "validation.json").read_text())
            self.assertEqual(validation["evaluated_outputs"], 2)
            self.assertTrue(validation["complete_coverage"])

    def test_unlisted_output_case_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project, results, checksum = self.write_fixture(directory, extra_member=True)
            with patch.object(quality, "ROOT", project), \
                 patch.object(quality, "INPUT_SHA256", checksum):
                with self.assertRaisesRegex(ValueError, "cases do not match"):
                    quality.run(results, directory / "quality")


if __name__ == "__main__":
    unittest.main()
