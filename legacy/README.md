# Historical prototype

These files belong to the initial three-architecture experiment. Their output
quantizer uses `2/2**output_bits`; current code uses another explicitly defined
protocol. Do not import these models into current experiments.

`model.py`, `sorting.py`, `evaluate.py`, `validate.py`, `config.json` and
`MANIFEST.json` were moved without changing their bytes. The manifest describes
its original snapshot, not the current directory layout. The historical report
builder was moved from `tools/` without changing its code.

From the repository root, use a separate environment with
`requirements/legacy.txt` if these historical commands are needed:

```bash
python legacy/validate.py
python legacy/evaluate.py --config legacy/config.json --output tmp/legacy_reproduced
python legacy/build_reports.py
```

The report builder reads the original top-level result files and writes only
to `tmp/legacy_reports/`. It has historical import-time side effects; execute it
as a script. It never generates the current thesis report.

The [dated instructions](../docs/LEGACY_README_20261002.md) document the original
root layout. For a checkout with those exact original paths, use the historical
Git revision; current paths are listed in [source_layout.json](../docs/source_layout.json).
