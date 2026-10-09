"""One discoverable entry point: python -m qant_sorting COMMAND [OPTIONS].

Only the selected command is loaded. Help and the numerical reference do not
import the optional SDK, plotting libraries or historical code. Each runner
keeps its own argument parser and scientific protocol.
"""
import argparse
import runpy
import sys

# A plain registry is sufficient: no plugin framework or execution abstraction.
COMMANDS = {
    "noise": ("run_noise_sweep", "Reproduce the matched-step reference"),
    "verify": ("verify_results", "Compare a run with the saved reference"),
    "common-noise": ("run_common_noise_controls", "Run shared signal/noise controls"),
    "quality": ("evaluate_ranking_quality", "Score saved outputs; requires original archives"),
    "cpu": ("run_cpu_baseline", "Measure the digital CPU baseline"),
    "resources": ("hardware_conditions", "Count logical calls and buffers"),
    "sdk": ("run_sdk_control", "Check the official CPU linear mapping"),
    "periodic-pairs": ("check_periodic_pairs", "Check every host-phase key pair"),
    "affine": ("check_affine_periodic", "Check affine phase feasibility"),
    "nonlinearity": ("check_sdk_nonlinearity", "Check CPU min/max and nonlinear boundaries"),
    "periodic": ("run_periodic_evaluation", "Reproduce historical periodic scenarios"),
    "periodic-summary": ("summarize_periodic_results", "Summarize saved periodic CSVs"),
    "curve": ("measure_periodic_curve", "Acquire API samples with explicit backend choice"),
    "install-sdk": ("install_sdk", "Install the bundled CPU SDK in a virtual environment"),
    "report": ("qant_sorting.report", "Build the current thesis PDF from saved evidence"),
}


def main(argv=None):
    """Forward command arguments unchanged and preserve argparse exit codes."""
    parser = argparse.ArgumentParser(
        description="Reproducible sorting research; run from the repository root.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Commands:\n" + "\n".join(f"  {name:19} {entry[1]}" for name, entry in COMMANDS.items())
               + "\n\nUse COMMAND --help for experiment-specific options.")
    parser.add_argument("command", nargs="?", choices=COMMANDS, metavar="COMMAND")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, metavar="OPTIONS")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return
    module = COMMANDS[args.command][0]
    if not module.startswith("qant_sorting."):
        module = "qant_sorting.experiments." + module
    previous = sys.argv
    try:
        sys.argv = [f"python -m qant_sorting {args.command}", *args.arguments]
        runpy.run_module(module, run_name="__main__")
    finally:
        sys.argv = previous


if __name__ == "__main__":
    main()
