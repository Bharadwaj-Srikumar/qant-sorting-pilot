"""Regression checks for the new entry point and file-handling boundaries."""
import csv
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qant_sorting.__main__ import main
from qant_sorting.io import file_hash, write_csv
from qant_sorting.paths import ROOT


class StructureTests(unittest.TestCase):
    """Exercise user-facing routing and the former import-time writer."""

    def test_help_without_optional_or_numerical_dependencies(self):
        """-S excludes site-packages; help must still explain available commands."""
        result = subprocess.run([sys.executable, "-S", "-m", "qant_sorting", "--help"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("common-noise", result.stdout)
        self.assertIn("affine", result.stdout)

    def test_forwarding_preserves_arguments_and_restores_argv(self):
        """A user's path/flags survive dispatch; the caller's argv is restored."""
        previous = sys.argv
        observed = []
        def capture(module, run_name):
            observed.append((module, run_name, sys.argv.copy()))
        with patch("qant_sorting.__main__.runpy.run_module", side_effect=capture):
            main(["noise", "--output-dir", "folder with spaces", "--batch-size", "32"])
        self.assertIs(sys.argv, previous)
        self.assertEqual(observed[0][:2], ("qant_sorting.experiments.run_noise_sweep", "__main__"))
        self.assertEqual(observed[0][2][1:], ["--output-dir", "folder with spaces", "--batch-size", "32"])

    def test_summary_import_does_not_create_or_write_evidence(self):
        """The historical summary used to create its output directory on import."""
        code = """
from pathlib import Path
from unittest.mock import patch
with patch.object(Path, 'mkdir', side_effect=AssertionError('import created directory')), \\
     patch.object(Path, 'open', side_effect=AssertionError('import opened evidence')):
    import qant_sorting.experiments.summarize_periodic_results
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shared_csv_and_hash_preserve_field_order_and_content(self):
        """Preserve serialized evidence semantics, including Unicode and empties."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.csv"
            write_csv(path, [{"scenario": "Gleichstände", "count": 4},
                             {"scenario": "", "count": 0}])
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, ["scenario", "count"])
                self.assertEqual(list(reader)[0], {"scenario": "Gleichstände", "count": "4"})
            self.assertEqual(file_hash(path), hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                write_csv(Path(directory) / "empty.csv", [])


if __name__ == "__main__":
    unittest.main()
