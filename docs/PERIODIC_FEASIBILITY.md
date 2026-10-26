# Periodic comparison: data path and finite precision

As of 24 October 2026. A limited CPU feasibility study, not a hardware measurement.

## Findings and significance

The existing path already returns the difference to the host. An electronic
sign decision is sufficient; the subsequent periodic call has no demonstrated
benefit in this path. A mathematically equivalent affine phase calculation can
be moved into `linear_fprop`. However, the public interface still returns the
intermediate result as a NumPy array. This does not establish a data path without
a host round trip.

Furthermore, this particular affine implementation is numerically unsuitable
for 8-bit comparison: **40 of 65,536 ordered pairs become false ties without
added noise**. All 256 pairs are correct at 4 bits. Direct SDK difference
comparison and the existing host-phase path remain correct at both widths.
This negative result applies to the selected coefficients and official CPU
arithmetic, not to every affine encoding or to the physical NPU.

## Which work moves where?

Integer keys a,b of width w, ranging from 0 to 2^w−1, are first encoded as
x=a/2^w and y=b/2^w. With u0=α=π/2, the exact model gives:

`u = u0 − α(x−y) = [x, y, 1] · [−α, α, u0]`.

The additional constant input implements the bias. Ideally, the CPU cosine
produces `cos(u)=sin(α(x−y))`, yielding the required sign. A single equal input
(0,0) establishes the CPU zero reference. Final thresholding, the tie rule,
and all record movements remain electronic.

| Data path | Visible steps | Interpretation |
|---|---|---|
| Electronic comparison | Host compares original keys | Digital baseline; no nonlinearity required |
| Direct SDK difference | MVM → host sign(d) | Control with one SDK call |
| Existing periodic variant | MVM → host difference and phase → tcos → host threshold | Two calls; correct in the noiseless CPU test |
| Affine CPU variant | Affine MVM → host phase → tcos → host threshold | Two calls; 8-bit information loss |
| Intended internal connection | Affine MVM → resident intermediate value → nonlinearity | Requires manufacturer confirmation; not executed |

For P pairs per software call group, logical BF16 buffer volumes, excluding
calibration and without assumed caching, are: direct difference `6P+4` bytes,
existing periodic path `12P+4` bytes, and affine variant `14P+6` bytes.
These count inputs, weights, and outputs at each public API boundary; they are
neither measured PCIe bytes nor internal conversions. The affine variant removes
host phase arithmetic but saves neither a call nor the return of an intermediate
value in the demonstrated API path. It also needs a third input column.
This accounting supplements the evaluation; C=(T,S,H,D) remains unchanged.

## What the SDK establishes

Version 2.3.1 was checked at source commit
`72a2d99f10240b6df3c6d0f636dfa0e2b5d38902`. Eight locally inspected source files
match the blob hashes in the official Git tree. Individual files and permanent
source links are listed in [`sdk_source_audit.json`](sdk_source_audit.json).

- `_wrapper.py` documents NumPy BF16 inputs and outputs for `linear_fprop`
  and the separate periodic call; `_utils.py` validates NumPy arrays.
- `qant_driver_import/mod.rs` allocates separate output buffers and invokes
  separate driver functions for MVM and periodic processing.
- `backend_cpu.rs` rounds **each product to BF16**, accumulates in FP32, and
  rounds the MVM result back to BF16. The nonlinearity uses cosine.
- The KAN composition in `non_linear.rs` explicitly adds the phase offset on
  the CPU between driver calls. A higher-level function call therefore does
  not demonstrate a cascade without host involvement.
- The linked hardware driver does not expose its internal processing or
  caching. The public contract does not establish that every hardware version
  fundamentally excludes such an internal connection.

Internal execution without a host round trip would not automatically be purely
optical or free of regeneration. Any reduction in physical conversions or
change in optical depth D would require separate evidence.

## Reproducible pair check

`check_affine_periodic.py` checks every ordered 4-/8-bit pair and saves scores
and affine phases. There is no added noise, additional fixed-point rounding,
tolerance band, or repair based on the correct answer.

| Width | Pairs per path | Direct difference: errors | Host phase: errors | Affine phase: errors |
|---|---:|---:|---:|---:|
| 4 bits | 256 | 0 | 0 | 0 |
| 8 bits | 65,536 | 0 | 0 | 40 |

All 40 errors are false ties; no sign is reversed, and all true ties are
preserved. For the pair (165,166), the three rounded products are
`[-1.015625, +1.015625, 1.5703125]`. The first two cancel. This produces the same
phase, 1.5703125, as (0,0), and therefore a zero score after reference
subtraction. The reverse pair is also indistinguishable. Exactly representable
input keys do not prevent this product-rounding error.

The minimum affine score magnitude over **all unequal 8-bit pairs is zero**.
The smallest *nonzero* magnitude, 0.007808685302734375, therefore does not provide
a usable minimum margin. Reference subtraction or a wider tolerance band cannot
recover information that has already been lost.

## Role in the thesis

The periodic variants are evaluated as pair-level feasibility studies. They do
not replace the difference matrix of the canonical Louri implementation: its
position-dependent bias is defined in linear difference units. The complete
Louri sorter uses the direct channel and has been checked separately through
the official CPU SDK. Earlier reduced-rank runs are not presented as results
for the full matrix.

## Reproduction and saved evidence

Linux x86_64, Python 3.12.14, official CPU SDK 2.3.1;
NumPy 2.3.5, ml-dtypes 0.6.0, cffi 2.1.1, pycparser 3.0.
The versions used are pinned in requirements/sdk.txt.
A separate Python 3.12 environment can be set up as follows:

```bash
python3.12 -m venv .venv-affine
. .venv-affine/bin/activate
python -m pip install -r requirements/sdk.txt
sha256sum vendor/qant-native-computing-toolkit-wheels-cpu-backend-v2.3.1.zip
wheel_dir=$(mktemp -d)
python -m zipfile -e vendor/qant-native-computing-toolkit-wheels-cpu-backend-v2.3.1.zip "$wheel_dir"
python -m pip install --no-deps "$wheel_dir/qant_native_computing_toolkit-2.3.1-cp312-cp312-linux_x86_64.whl"
python -m qant_sorting affine --output-dir results/affine_periodic_reproduced
```

The ZIP hash must be
`99b4669d3256d92cc35efc1a2d6d59deef7a033d78397d71150333011eb93898`.
The runner also checks this hash, the existing input-corpus hash, and the
reported CPU driver identity. An existing destination is not overwritten.
There is no automatic hardware mode.

`results/affine/` contains `summary.json` with counts and environment information
and `outputs.npz` with every pair score and phase. The SDK source audit is in
`docs/sdk_source_audit.json`. This pair study contains no complete periodic rank
sorting runs. The known failing 8-bit pairs remain saved.

## Consequence and next decision

The affine variant is **not** adopted as a correct 8-bit comparator. The periodic
function remains a limited feasibility study with a concrete negative precision
result. The internal data path, bias representation, and actual arithmetic and
signal precision must first be clarified. Only a confirmed data path justifies
targeted encoding changes and a comparison of accuracy, conversions, and total
cost against the direct decision. Blind parameter search is no substitute.

The [Q.ANT inquiry draft](QANT_FEEDBACK_INQUIRY_EN.txt) contains these questions.
It has not been sent; a manufacturer response and hardware validation remain pending.
