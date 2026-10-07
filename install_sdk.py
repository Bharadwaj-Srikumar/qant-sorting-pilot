# Reading guide: explicit installer, not a module required by all experiments.
# The entry point checks Python, virtual environment, platform and archive hash
# before extracting one official wheel and invoking pip with historical pins.
# Those pins reproduce the SDK setup; the separate CPU-baseline/common-model
# requirements files document their own environments. Do not conflate the pins.
# Running this script modifies the ACTIVE virtual environment and may require
# package-index access for dependencies. Importing the module does not install.

"""Install the bundled official CPU SDK into a Python 3.12 virtual environment.

The vendor archive is unmodified and checksum-checked. The Gaussian sweep does
not need it; install only to run the separate SDK integration control.
"""

import hashlib
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile


# Require Python 3.12 and an active virtual environment, then choose a wheel
# for a supported OS/architecture and verify the entire bundled archive hash.
# Extract only the selected wheel basename into a temporary directory, invoke
# pip using the same Python interpreter, and propagate installation failures.
# This is an environment-changing command; no installation occurs on import.
def main():
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use Python 3.12 for the supplied official wheels")
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Create and activate a virtual environment first")

    tags = {
        ("Linux", "x86_64"): "linux_x86_64",
        ("Windows", "AMD64"): "win_amd64",
        ("Darwin", "arm64"): "macosx_11_0_arm64",
    }
    tag = tags.get((platform.system(), platform.machine()))
    if tag is None:
        raise SystemExit("No bundled official wheel for this operating system/architecture")
    archive = Path(__file__).resolve().parent / "vendor/qant-native-computing-toolkit-wheels-cpu-backend-v2.3.1.zip"
    expected = "99b4669d3256d92cc35efc1a2d6d59deef7a033d78397d71150333011eb93898"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise SystemExit("Official SDK archive checksum mismatch")

    # Extract only the matching wheel by its basename. Other archive paths
    # are never written; the license files are provided alongside the archive.
    with tempfile.TemporaryDirectory() as directory:
        with zipfile.ZipFile(archive) as bundle:
            name = next(name for name in bundle.namelist() if name.endswith(tag + ".whl"))
            wheel = Path(directory) / Path(name).name
            wheel.write_bytes(bundle.read(name))
        subprocess.run([
            sys.executable, "-m", "pip", "install", str(wheel),
            "numpy==2.5.3", "ml-dtypes==0.6.0", "cffi==1.17.1", "pycparser==3.0",
        ], check=True)
    print("Installed the official CPU backend. Run python run_sdk_control.py")


# Direct execution starts this file's command-line/test entry point.
# Importing helpers does not run THIS block; the module reading guide
# identifies any other top-level file loading or writing separately.
if __name__ == "__main__":
    main()
