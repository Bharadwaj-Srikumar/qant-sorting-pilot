"""Repository paths and identities shared by the source-checkout workflows.

Data stay outside the package so moving an experiment cannot change its inputs.
Run commands from the repository root; no wheel installation is required.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_SHA256 = "79efbd1ee270242cc122d8f9e1848fe07a85077bcf310324b27dd60f8faf11da"
