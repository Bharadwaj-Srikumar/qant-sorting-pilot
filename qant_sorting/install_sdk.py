import argparse
import hashlib
import platform
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Install the bundled Q.ANT CPU SDK.")
    parser.add_argument("--no-deps", action="store_true",
                        help="Keep the environment already installed from requirements.txt")
    args = parser.parse_args()
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
    archive = ROOT / "vendor/qant-native-computing-toolkit-wheels-cpu-backend-v2.3.1.zip"
    expected = "99b4669d3256d92cc35efc1a2d6d59deef7a033d78397d71150333011eb93898"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise SystemExit("Official SDK archive checksum mismatch")

    with tempfile.TemporaryDirectory() as directory:
        with zipfile.ZipFile(archive) as bundle:
            name = next(name for name in bundle.namelist() if name.endswith(tag + ".whl"))
            wheel = Path(directory) / Path(name).name
            wheel.write_bytes(bundle.read(name))
        dependencies = (["--no-deps"] if args.no_deps else
                        ["-r", str(ROOT / "requirements.txt")])
        subprocess.run([sys.executable, "-m", "pip", "install", str(wheel),
                        *dependencies], check=True)
    print("Installed the official CPU backend. Run python -m qant_sorting.sdk")


if __name__ == "__main__":
    main()
