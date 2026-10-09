# Q.ANT sorting pilot

Reproducible research on stable bitonic and rank sorting, finite precision,
noise and hybrid photonic mappings. CPU simulation does not establish a
photonic speed or energy advantage.

## Start here

- **Research:** [current complete thesis report, in German](reports/Masterarbeit_Hybride_Photonische_Sortierung.pdf).
- **Code:** [reading guide and command map](docs/CODE_GUIDE.md).
- **Method:** [how a key comparison becomes a sort](docs/METHOD.md).

Only the current PDF is kept in `reports/`. Source text, bibliography and
provenance are in `report_assets/`; earlier reports remain in Git history.

## Run from the repository root

Use Python **3.12** and a virtual environment:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements/analysis.txt
python -m qant_sorting --help
python -m unittest discover -s tests -v
python -m qant_sorting noise
```

The reference sweep checks all **288 configurations and 576 saved arrays**
against `results/reference/`. It writes to `results/reproduced/`.
`requirements/reference.txt` preserves the original NumPy pin; `analysis.txt`
is the separate NumPy/SciPy environment used for the newer analyses. Select the
recorded environment when reproducing a dated experiment.

Optional SDK checks need the bundled official CPU backend:

```bash
python -m pip install -r requirements/sdk.txt
python -m qant_sorting install-sdk --no-deps
python -m qant_sorting affine
```

`--no-deps` preserves the explicitly installed SDK environment. Without it, the
installer uses the historical SDK dependency pins. SDK tests skip explicitly
when the optional backend is absent. No command silently substitutes CPU for hardware.

To rebuild the report from saved evidence:

```bash
python -m pip install -r requirements/report.txt
python -m qant_sorting report
```

## Where things belong

| Location | Purpose |
|---|---|
| `qant_sorting/` | Reusable algorithms, comparison models and quality metrics |
| `qant_sorting/experiments/` | Explicit experiment and verification commands |
| `qant_sorting/report.py` | Current report generation |
| `legacy/` | Superseded prototype and historical report builder |
| `data/`, `results/`, `validation/` | Saved inputs, evidence and checks |
| `docs/`, `report_assets/` | Methods, focused guides and editable report sources |
| `requirements/`, `vendor/`, `tests/` | Environments, official SDK and tests |

The old root-level `python script.py` commands now use
`python -m qant_sorting COMMAND`; see the [command map](docs/CODE_GUIDE.md).
Historical metadata retain their original paths and hashes. The
[path inventory](docs/source_layout.json) maps old locations to current files.

## Current findings and limits

The [affine CPU feasibility check](docs/PERIODIC_FEASIBILITY.md) finds 40 false
8-bit ties; the direct-difference and host-phase controls remain correct.
[Common-noise controls](docs/COMMON_NOISE_MODEL.md),
[ranking quality](docs/RANKING_QUALITY.md) and the
[CPU baseline](docs/CPU_BASELINE.md) are separate evaluations with stated assumptions.

Historical periodic raw archives are missing from this Git tree; derived
quality tables remain available, with five documented output gaps. Full
historical quality reanalysis requires those original archives. GPU timing,
physical Q.ANT noise, NPU performance and energy remain open.
See the [work plan](docs/FEEDBACK_SPRINTS.md) and [changes](CHANGELOG.md).
