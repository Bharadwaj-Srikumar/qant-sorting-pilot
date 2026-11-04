"""Command entry points and protection of saved results."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from qant_sorting.run import REFERENCE, ROOT, file_hash, run


class StructureTests(unittest.TestCase):
    def test_main_commands_explain_their_options(self):
        """Every documented command explains its options without loading the SDK."""
        commands = (
            ("qant_sorting.run", "--batch-size"),
            ("qant_sorting.quality", "--results-dir"),
            ("qant_sorting.sdk", "--output-dir"),
            ("qant_sorting.resources", "--output-dir"),
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

if __name__ == "__main__":
    unittest.main()
