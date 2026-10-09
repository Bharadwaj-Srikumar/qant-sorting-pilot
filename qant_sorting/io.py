"""Small, dependency-free file helpers shared by experiment runners.

These helpers handle serialization and provenance only. They do not choose
noise parameters, seeds, output schemas or algorithms for an experiment.
"""
import csv
import hashlib
from pathlib import Path

from qant_sorting.paths import ROOT


def file_hash(path):
    """Return SHA-256 without loading an entire result archive into memory."""
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_csv(path, rows):
    """Write nonempty record rows in their original field order, using UTF-8."""
    if not rows:
        raise ValueError("Cannot infer CSV columns from an empty record list")
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_hashes():
    """Identify every current package source, including shared helpers.

    Repository-relative keys remain unique across subpackages. Old experiment
    metadata retain their original hashes and are never rewritten by this call.
    """
    return {str(path.relative_to(ROOT)): file_hash(path)
            for path in sorted((ROOT / "qant_sorting").rglob("*.py"))}
