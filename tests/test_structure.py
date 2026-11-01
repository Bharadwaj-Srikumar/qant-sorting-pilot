"""Checks for the direct commands and protection of saved evidence."""
import csv
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from qant_sorting.run import REFERENCE, ROOT, file_hash, run, write_csv


class StructureTests(unittest.TestCase):
    def test_main_commands_explain_their_options(self):
        """The two main workflows can be invoked directly without an SDK command."""
        commands = (
            ("qant_sorting.run", "--batch-size"),
            ("qant_sorting.controls", "--pair-samples"),
        )
        for module, option in commands:
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-m", module, "--help"],
                    cwd=ROOT, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--output-dir", result.stdout)
                self.assertIn(option, result.stdout)

    def test_existing_results_are_not_overwritten(self):
        """Refuse both the committed reference and a nonempty output directory."""
        reference_hash = file_hash(REFERENCE / "trial_outcomes.npz")
        with self.assertRaises(ValueError):
            run(REFERENCE, batch_size=1)
        self.assertEqual(file_hash(REFERENCE / "trial_outcomes.npz"), reference_hash)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            marker = output / "existing.txt"
            marker.write_text("Keep the previous run.")
            with self.assertRaises(ValueError):
                run(output, batch_size=1)
            self.assertEqual(marker.read_text(), "Keep the previous run.")

    def test_shared_csv_and_hash_preserve_field_order_and_content(self):
        """Preserve serialized evidence semantics, including Unicode and empties."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.csv"
            write_csv(path, [{"scenario": "Ties (τ)", "count": 4},
                             {"scenario": "", "count": 0}])
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, ["scenario", "count"])
                self.assertEqual(list(reader)[0], {"scenario": "Ties (τ)", "count": "4"})
            self.assertEqual(file_hash(path), hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                write_csv(Path(directory) / "empty.csv", [])


if __name__ == "__main__":
    unittest.main()
