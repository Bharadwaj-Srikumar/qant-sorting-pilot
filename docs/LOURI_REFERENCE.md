# Louri's full matrix: the thesis rank implementation

Source: A. Louri, J. A. Hatch, Jr. and J. Na, *Constant-time parallel sorting
algorithm and its optical implementation using smart pixels*, Applied Optics
34(17), 3087–3096 (1995), [DOI](https://doi.org/10.1364/AO.34.003087).
The implementation follows equations (1)–(7) and the worked matrices on p. 3089.

## 1. All entries are evaluated

For N=4 the algorithm has **16 matrix entries**: twelve directed comparisons of
different records plus four self-comparisons. Row i is the competitor; column j
is the record being ranked. No reverse vote is inferred by complementing a vote.

For integer keys normalized by Δ=2⁻ᵇ:

```math
D_{ij}=\Delta(x_j-x_i),\qquad U_{ij}=\mathbf{1}[i>j],\qquad D'_{ij}=D_{ij}-\Delta U_{ij}.
```

Equivalently, before normalization the paper constructs A[i,j]=x[j] and computes
A−(Aᵀ+U). The normalized bias is ΔU, not U. Threshold each cell separately:

```math
R'_{ij}=\mathbf{1}[D'_{ij}\geq0],\qquad r_j^{(1)}=\sum_i R'_{ij},\qquad r_j^{(0)}=r_j^{(1)}-1.
```

Sum **columns of the threshold matrix**, not raw differences. The diagonal adds
one to each noiseless source rank, so only output placement subtracts one.

## 2. A four-record example

For keys `[3,1,3,0]`, the threshold matrix is:

| Competitor row | Column 0: first 3 | Column 1: 1 | Column 2: second 3 | Column 3: 0 |
|---|---:|---:|---:|---:|
| 0: first 3 | 1 | 0 | 1 | 0 |
| 1: 1 | 1 | 1 | 1 | 0 |
| 2: second 3 | 0 | 0 | 1 | 0 |
| 3: 0 | 1 | 1 | 1 | 1 |
| Column sum | **3** | **2** | **4** | **1** |

Python positions `[2,1,3,0]` yield `[0,1,first 3,second 3]`. The unit bias removes
only the later competitor's equality vote; it preserves a positive integer-key
difference as nonnegative. Equal keys therefore retain original order.

The paper's `[7,8,2,8,5]` example gives ranks `[3,4,1,5,2]`. Two prose statements
on p. 3089 contradict the displayed tie direction / triangular modification.
We follow the equations and worked matrices, and test those matrices literally.

## 3. Code and SDK path

[`rank_sort`](../qant_sorting/sorting_schedules.py) packs all pairs in row-major
matrix order into `(trials,N*N)` arrays. The difference callable processes each
cell separately. Then the host subtracts the lower-triangular bias, thresholds,
sums columns and validates placement. Invalid ranks produce `-1` records.

[`louri_reference.py`](../qant_sorting/louri_reference.py) exposes intermediate
matrices for explanation and source checking. It implements the same algorithm.

With [`SdkDifference`](../qant_sorting/sdk_mapping.py), all N² pair rows are sent
to the official `linear_fprop` CPU backend with weights `[1,-1]`. This is tested
on every saved list. Bias, threshold, ranks and routing remain electronic.
One logical batch need not equal one physical parallel hardware operation.

## 4. Main noise assumptions

The main sweep measures every cell, including self-comparisons:

```math
\widehat D_{ij}=Q(D_{ij}+E_{ij}),\qquad
R'_{ij}=\mathbf{1}[\widehat D_{ij}-\Delta U_{ij}\geq0],\qquad
E_{ij}\sim\mathcal N(0,(\eta\Delta)^2).
```

Errors are assumed independent across directed cells and trials. A shared
physical input can introduce correlations; independence is not a device claim.
No reverse error is forced to equal the negative of another. No noisy diagonal
is overwritten with zero.

Q rounds to nearest even multiples of Δ, with signed b-bit saturation from
−2ᵇ⁻¹ through 2ᵇ⁻¹−1. It acts **before bias**. Bias, threshold, column summation
and placement are exact host operations. Eta is 0, .05, .10, .15, .20 or .25.

The raw equations have zero threshold margin in some cells. For `[1,0]`, the
lower difference Δ becomes zero after subtracting Δ. A tiny negative error
changes its vote. Pre-bias rounding instead gives a half-step decision boundary.
The separate pair controls hold the diagonal exact solely to isolate this effect.
With independent directed errors and η=.25, their correct-sort probabilities are
Φ(4)/2 ≈49.998% without quantization and Φ(2)² ≈95.502% with matched rounding.
These are checked analytically and by sampling; they are not physical reliability.

## 5. Verification and findings

- **155,328 noiseless arrays:** source raw/matched matrices and the canonical
  sorter agree with stable argsort. Includes all 4-/8-bit pairs, every four-record
  4-bit list and all 24,000 saved lists.
- **48,000 complete SDK CPU sorts:** both architectures are correct and stable.
  The rank adapter's N² cell counts are independently checked.
- **288,000 current sensitivity sorts:** the same corpus, six noise levels, two
  architectures. All outputs are stored and independently rescored.
- At 4-bit N=16, η=.25 and duplicates allowed, full rank produces **354 valid,
  352 correct, 350 stable outputs per 1,000**. At 8-bit N=256, η=.25, neither
  input family has a valid rank output. See [results](RESULTS.md) for context.

```bash
python -m qant_sorting louri
python -m qant_sorting noise
python -m qant_sorting sdk
```

The corresponding current evidence lives in `results/louri`, `results/reference`
and `results/sdk`. The source check uses overlapping control sets, not independent
random samples. The simulation does not reproduce the complete smart-pixel
physics, optical rank summation, measured Q.ANT noise or hardware performance.
