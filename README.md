# Photonic sorting: explicit 4-bit and 8-bit evaluation

Research code for Bharadwaj Srikumar's master's thesis. Revision: 2 October 2026.

Compares functional mappings based on **Beyette**, **Desmulliez** and **Louri**.
This is a numerical sensitivity experiment, not a Q.ANT device emulator.

## Open in VS Code

1. Extract the ZIP, then open the `qant_sorting_pilot` folder in VS Code.
2. Install Python 3.12 and the VS Code Python extension if needed.
3. Open a terminal in this folder. On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe validate.py
.\.venv\Scripts\python.exe evaluate.py
.\.venv\Scripts\python.exe build_reports.py
```

On Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python validate.py
.venv/bin/python evaluate.py
.venv/bin/python build_reports.py
```

Select this `.venv` via **Python: Select Interpreter**. Open the HTML report in
a web browser; it works offline. Saved results are included, so no rerun is
needed to read them. `evaluate.py` overwrites the selected result folder;
use `--output results_trial` to preserve the included run.

## Agreed experiment

| Setting | Value |
|---|---|
| Raw keys | Whole numbers, 0..15 or 0..255, inclusive |
| Input precision | 4 or 8 bits, recorded independently |
| Signed difference output precision | 4 or 8 bits, recorded independently |
| Tested pairs | (input, output) = (4,4) and (8,8) |
| N | Powers of two from 2 through 2^key_bits |
| Inputs | Uniform without replacement; uniform with replacement |
| Trials | 1,000 per configuration |
| Conditions | Ideal; quantization only; quantization plus Gaussian noise |
| Noise | Independent, zero-mean, sigma = 0.25 output steps |
| Normalization | Fixed by declared key range and input converter grid |
| Tie rule | Original index when the measured difference is zero |
| Rank collisions | Fail; no digital re-sort or rank repair |

The entire run contains 216 rows / 216,000 architecture executions. Beyette
and Desmulliez share the same numerical schedule and error samples; their
equal results are paired evidence and must not be pooled as independent trials.

## Files to read

| File | Purpose |
|---|---|
| `config.json` | Complete sweep settings |
| `model.py` | Raw-key validation, normalization, quantization, noise |
| `sorting.py` | Compact reference, fixed shuffle, pairwise rank mapping |
| `validate.py` | Source examples and independent mathematical checks |
| `evaluate.py` | Matched inputs, reproducible streams, metrics and CSV output |
| `build_reports.py` | Rebuild HTML/PDF and scientific figures from saved results |
| `results/precision.csv` | Every case, counts, intervals and diagnostics |
| `results/inputs.npz` | Exact input arrays (NumPy compressed archive) |
| `results/trial_outcomes.npz` | Per-trial columns: correct, stable, valid |
| `results/failures.json` | First incorrect output for each failing configuration |
| `results/resources.csv` | Algorithmic pair counts, rounds and bypass steps |
| `results/validation.json` | Passed checks and unresolved source discrepancy |
| `results/run_metadata.json` | Runtime versions and code hashes |
| `report_assets/historical_foundation.pdf` | Preserved theoretical chapters from the preceding report |

## Try your own keys

```python
from model import run_sort

(values, original_indices, valid), model = run_sort(
    [10, 9, 0, 15], architecture="Beyette",
    key_bits=4, input_bits=4, output_bits=4,
    mode="quantized_noise", noise_lsb=0.25,
    seed_context=(20260930,),
)
print(values, original_indices, valid)
```

For an input `[0, 16]` with `key_bits=4`, the error identifies index 1 and
requires a whole number in `[0, 15]`. Integral floats such as `3.0` are accepted;
fractional values, booleans, strings and nonfinite numbers are rejected. Array
and element indexes in errors are zero-based. A rank failure produces a false
validity flag and a row of `-1` sentinels; never treat that row as a valid sort.

## Numerical interpretation

Let M=2^key_bits-1 and Lin=2^input_bits. Encode
`u = key * (1 - 1/Lin) / M`; quantize by `rint(Lin*u)/Lin`.
With matched widths this simplifies to `u=key/2^key_bits`, representing every
allowed integer exactly at the input. Output step is `2/2^output_bits` on a
signed grid `[-1, 1-step]`. NumPy `rint` uses nearest-even rounding.

For 8 bits, an adjacent-key difference is 1/256 but the output step is 1/128.
Its output code is `rint(0.5)=0`: a false tie can occur without noise. The same
ratio holds for the 4-bit case. Added noise can move a half-step across a
rounding boundary, so higher observed success with this noise setting is
possible. It is not evidence that physical noise generally helps sorting.

Fixed normalization is an explicit experimental choice, not a universal
optimum. The output grid, exact electronic operations, independent Gaussian
noise and its amplitude are modeling assumptions, not Q.ANT specifications.
Changing key range together with converter precision compares operating
scenarios; it does not isolate converter precision alone.
In raw-key units, both matched-width scenarios have an output step of 2 and
noise sigma of 0.5. Their adjacent-integer resolution is therefore the same;
the larger 8-bit domain allows sparser random inputs at a fixed N.

The original record values remain electronic and unchanged. Only their
comparison differences are impaired. Rank sums, routing, storage and output
placement are exact. The pilot therefore does not model analog-value cascades.

## Evidence and limitations

The source-validation table in the reports distinguishes equations/examples,
hybrid adaptations and unverified hardware assumptions. The original Louri
matrix is checked separately; noisy evaluation uses one unordered pair and
complementary outcomes, not two independent directed measurements.

Historical timing expressions remain source reproductions. Python runtime is
not photonic latency. Q.ANT throughput, energy, ENOB and cascade depth are not
inferred from these results. PRISM is related photonic scoring with electronic
selection, not a full-sort performance baseline.

Literature PDFs are not included in this code repository. Bibliographic links
and source hashes identify the supplied research corpus. No open-source
license has been assigned on the author's behalf.
