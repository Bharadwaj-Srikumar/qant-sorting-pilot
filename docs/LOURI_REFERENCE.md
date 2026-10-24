# Louri's full matrix and our unordered-pair adaptation

The two algorithms agree without noise. They need not agree under noise:
reusing one pair decision imposes a correlation that two independent directed
measurements do not have. The source's unit bias also puts some signals exactly
on a threshold. This study separates those effects instead of attributing all
differences to a physical architecture.

## 1. Follow the source equations

Source: A. Louri, J. A. Hatch, Jr. and J. Na, *Constant-time parallel sorting
algorithm and its optical implementation using smart pixels*, Applied Optics
34(17), 3087–3096 (1995), [DOI: 10.1364/AO.34.003087](https://doi.org/10.1364/AO.34.003087).
The reference implements equations (1)–(7), especially the matrices on p. 3089.

Row `i` is the competitor; column `j` is the record being ranked. The paper
broadcasts the keys into `A[i,j]=x[j]` and subtracts its transpose. In our
normalized units, **both keys and the unit bias** are scaled by Δ = 2⁻ᵇ:

```math
D_{ij}=\Delta(x_j-x_i),\qquad
U_{ij}=\mathbf{1}[i>j],\qquad D'_{ij}=D_{ij}-\Delta U_{ij}.
```

```math
R'_{ij}=\mathbf{1}[D'_{ij}\geq 0],\qquad
r_j^{(1)}=\sum_i R'_{ij},\qquad r_j^{(0)}=r_j^{(1)}-1.
```

The diagonal contributes one to each column, so the paper's ranks start at 1.
Subtracting one gives the Python output position. Do not transpose the rank
sum or subtract an unscaled bias of 1 from normalized differences.

Published example:

| Original record | 7 | first 8 | 2 | second 8 | 5 |
|---|---:|---:|---:|---:|---:|
| Paper rank | 3 | 4 | 1 | 5 | 2 |
| Python position | 2 | 3 | 0 | 4 | 1 |

Output indices are `[2,4,0,1,3]`, giving `[2,5,7,8,8]`. Equal keys retain
their original order. **Source discrepancy:** prose on p. 3089 calls the earlier
equal record larger and elsewhere describes an above-diagonal modification.
The displayed lower-triangular bias, threshold matrix and resolved ranks show
the opposite conventions. The implementation follows the displayed equations
and worked matrices; a literal reading of those prose statements would disagree.

For any two integer keys, the difference is an integer multiple of Δ. Subtracting
Δ below the diagonal removes a vote for equality but keeps every strictly positive
difference nonnegative. Thus the rank counts smaller keys plus earlier equal keys,
exactly as our stable unordered-pair adaptation does.

## 2. Code and reproducibility

Read these additions in order:

1. [`louri_reference.py`](../qant_sorting/louri_reference.py): matrices, bias,
   threshold, ranks, safe placement and explicitly paired error generation.
2. [`test_louri_reference.py`](../tests/test_louri_reference.py): the literal paper
   matrices, ties, threshold boundaries, clipping, negative ranks and rank cycles.
3. [`run_louri_reference.py`](../qant_sorting/experiments/run_louri_reference.py):
   exhaustive checks, Gaussian probability controls, sensitivity sweep and scoring.

Run from the repository root with the existing analysis environment:

```bash
python -m pip install -r requirements/analysis.txt
python -m unittest discover -s tests -v
python -m qant_sorting louri
```

The default destination is `results/louri_reference_reproduced/`; nonempty
destinations are rejected. `--sort-trials` selects the first 1–1000 saved rows
per sensitivity dataset (default 100). `--batch-size` changes grouping, not
random samples. It does not reduce the complete noiseless verification.

The [saved run](../results/louri_reference_20261024/) contains:

- `validation.json`: **155,328 noiseless arrays** agree: 256 ordered 4-bit pairs,
  65,536 ordered 8-bit pairs, 65,536 four-record 4-bit lists, and all 24,000 saved
  arrays. These overlapping control sets are not independent random samples.
- `summary.csv`: **360 configurations / 36,000 sort evaluations**, including
  28,800 full-matrix and 7,200 unordered evaluations. Six datasets use the first
  100 arrays: 4-bit N=16 and 8-bit N=16/256, each with distinct keys or duplicates
  allowed. Repeated controls are paired evaluations, not 36,000 different inputs.
- `boundary_controls.csv`: eight adjacent-key controls, each with 100,000 pairs,
  checked against analytic Gaussian probabilities within six standard errors
  plus five counts. These are additional pair evaluations, not full-array trials.
- Six `.npz` archives: original trial IDs, output indices, flags, ranking quality,
  per-trial diagnostics and the full-matrix one-based ranks. Invalid outputs retain
  `-1` markers. `distance.csv.gz` stores output inversions by integer key distance.
- `metadata.json`: pinned input hash, code hashes, Python/NumPy versions, seeds,
  assumptions and output hashes. Historical experiment files remain unchanged.

## 3. Noise and quantization assumptions

Every error is added to the normalized difference **before bias and threshold**:

```math
\widehat D_{ij}=Q(D_{ij}+E_{ij}),\qquad
R'_{ij}=\mathbf{1}[\widehat D_{ij}-\Delta U_{ij}\geq0],\qquad
E_{ij}\sim\mathcal N(0,(\eta\Delta)^2).
```

All positive noise levels are **assumed sensitivity parameters**, not measured
Louri or Q.ANT values: η ∈ {0, 0.05, 0.10, 0.15, 0.20, 0.25}. Signal spacing is
Δ=1/16 or 1/256. For example η=0.25 means σ=Δ/4, not variance Δ/4.

| Control | Exact meaning |
|---|---|
| Quantization `none` | No rounding **and no clipping**; raw equation-level threshold control |
| Quantization `matched` | Before bias: nearest-even rounding to Δ, clipped to signed b-bit codes −2ᵇ⁻¹ through 2ᵇ⁻¹−1; same quantizer as `NoisyDifference` |
| `antisymmetric` errors | E[j,i]=−E[i,j]; one noisy difference supplies both directions |
| `independent` errors | Separate Gaussian samples for both directed cells |
| Diagonal `exact` | Restore the known self-difference to zero before quantization |
| Diagonal `measured` | Independent Gaussian errors on self-differences |
| Other operations | Exact bias, threshold, rank sum and electronic placement; no collision repair |

The bias is applied **after** the quantizer and is not clipped again. Its physical
implementation and precision are not established by this control. The unordered
`none` path is also a new control; `matched` reproduces the existing comparator.

Each dataset/trial has deterministic independent RNG streams. The primary error
for `x[i]-x[j]`, i<j, is negated for matrix cell `(i,j)`, whose difference has the
opposite orientation. Reverse and diagonal streams are separate. Models reuse
the same primary samples, and eta values rescale the same standard samples.
Independent-directed and antisymmetric errors are assumed covariance endpoints;
real shared input/channel errors can have more complicated correlations.

## 4. Why equivalence can disappear

With matched quantization, a positive quantized difference is at least Δ.
Consequently the lower cell's `measured >= Δ` is equivalent to `measured > 0`.
With antisymmetric errors, the upper cell supplies the complementary vote.
The exact diagonal adds one. This proves equality of all votes and ranks with
the adaptation, including when noisy comparisons create an invalid rank cycle.
All **3,600 paired trials** of that control agree, including η=0.

Without quantization, a positive difference can lie strictly between 0 and Δ.
The two matrix cells then both vote zero. Example: keys `[1,0]` give a lower
cell Δ before bias and **zero after bias**. An error of just −0.01Δ makes this
cell negative. A symmetric continuous error changes this zero-margin vote with
probability 1/2 even as its nonzero standard deviation becomes small.
Floating-point resolution eventually limits that idealized statement.

For `[1,0]`, exact diagonal and η=0.25, the predicted full-matrix correct-sort
probabilities are:

| Noise coupling | No quantization | Matched pre-bias quantization |
|---|---:|---:|
| Antisymmetric | 1/2 | Φ(2) ≈ 97.725% |
| Independent | Φ(4)/2 ≈ 49.998% | Φ(2)² ≈ 95.502% |

Φ is the standard normal cumulative distribution. The half-step boundary comes
from rounding: the biased positive vote survives when its error is at least
−Δ/2. The recorded pair controls check these probabilities. Independent cells
can also both vote one; noisy diagonal cells can lose a self-vote. None of these
effects is represented by simply halving the number of independent comparisons.

## 5. Observed sensitivity and its limits

Example: **4-bit, N=16, duplicates allowed, η=0.25**, first 100 saved arrays.
Matrix rows below use an **exact diagonal** to isolate directed pair behavior.

| Quantizer | Algorithm / coupling | Valid / 100 | Correct / 100 | Stable / 100 |
|---|---|---:|---:|---:|
| None | Unordered | 74 | 74 | 1 |
| None | Matrix, antisymmetric | 0 | 0 | 0 |
| None | Matrix, independent | 0 | 0 | 0 |
| Matched | Unordered | 93 | 88 | 76 |
| Matched | Matrix, antisymmetric | 93 | 88 | 76 |
| Matched | Matrix, independent | 53 | 53 | 53 |

For the matched matrix with **measured** diagonal, validity falls to 71/100
(antisymmetric) and 42/100 (independent) in this example. At 8-bit N=256 with
distinct keys, matched unordered/antisymmetric-exact yield 98 valid but only
4 correct arrays out of 100; independent-exact yields no valid arrays. A complete
array is a strict metric, and these assumed errors accumulate over many comparisons.

Each configuration includes 95% Wilson intervals. Kendall-τ-b, key-normalized τ,
Recall@10 and key-distance inversions are conditional on valid outputs; invalid
outputs have undefined quality, not perfect or zero quality. A separate explicitly
named recall column values invalid outputs at zero. Stable-ID and tie-neutral
recall are both retained. Validity must accompany every conditional quality claim.

**Conclusion supported by this experiment:** the adaptation is a correct
noiseless algorithmic reduction and a precisely equivalent noisy model under
the matched/antisymmetric/exact-diagonal assumptions. Other assumptions change
its sensitivity. Neither model reproduces the complete physical noise of Louri's
smart-pixel system or Q.ANT hardware. The source's photodetection, electronic
subtraction/threshold, optical rank summation and routing need device-specific
models and data before a physical reliability comparison is justified.

Next: constrain covariance, bias/threshold offsets, quantizer location and rank
readout uncertainty using supported device information. Retain these equation-level
controls as checks; do not choose a noise model merely because its results look better.
