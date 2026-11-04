# Method: from integer records to evaluated outputs

The experiment compares Bitonic sorting with a full N×N rank sorter. Both move
original integer keys and record IDs; only the comparison scores are disturbed.
The code follows **inputs → comparison model → sorting → evaluation → saved results**.

## 1. Fixed inputs and precision

[`data/inputs.npz`](../data/inputs.npz) contains 24 datasets of 1,000 arrays each:
4-bit keys at N = 2, 4, 8, 16 and 8-bit keys at N = 2, 4, …, 256, each with
`distinct` and `duplicates_allowed` inputs. The latter are sampled with
replacement; an individual array need not contain a duplicate. The same arrays
are reused across algorithms and noise levels.

[`comparison.py`](../qant_sorting/comparison.py) rejects invalid keys before
arithmetic. The registered key, input and output widths are matched: (4,4,4)
or (8,8,8). For their common width b, define

```math
L=2^b,\qquad \Delta=1/L,\qquad x\in\{0,\ldots,L-1\},\qquad \widehat{x}=x/L.
```

Every permitted key lies exactly on the input grid. Normalization uses the
declared domain, not each array's minimum and maximum. Each record also keeps
its original ID, 0 through N−1, so equal keys remain distinguishable.

## 2. One noisy, quantized difference

For a pair of keys a and b, the arithmetic is a normalized subtraction:

```math
d=\widehat a-\widehat b
=\begin{bmatrix}1&-1\end{bmatrix}
 \begin{bmatrix}\widehat a\\\widehat b\end{bmatrix},\qquad
\epsilon\sim\mathcal N(0,(\eta\Delta)^2).
```

Noise is added **before** nearest-even rounding and signed saturation:

```math
c=\operatorname{round}_{even}((d+\epsilon)/\Delta),\qquad
\widetilde d=Q(d+\epsilon)
=\Delta\min(L/2-1,\max(-L/2,c)).
```

The output range is [−1/2, 1/2−Δ]. Saturation can remove magnitude while preserving
the noiseless sign. At 8 bits, keys 10 and 9 differ by Δ. A noise sample −0.6Δ
makes the rounded code zero: a false tie. The sorter then follows its tie rule;
it does not use the true keys to repair the decision.

The sweep uses η = 0, .05, .10, .15, .20, .25. Thus η=.25 means a standard
deviation of one quarter of an output step. Independent Gaussian errors are
assumed between comparison events, trials and algorithms. In the rank sorter
this includes both directions and every self-comparison. Physical bias, drift,
correlation and signal-dependent noise are not calibrated by this model.

The master seed is 20260930. Each trial has its own stream, so changing the batch
size does not change that trial's draws. Positive η values reuse the same draws
scaled by η, pairing noise by event position. In Bitonic, an earlier changed
swap can make a later event compare different records. The diagnostics count
comparisons, saturation, false ties, sign reversals and broken true ties without
correcting the measured scores. See [`run.py`](../qant_sorting/run.py) for seeds
and [`comparison.py`](../qant_sorting/comparison.py) for the exact counters.

## 3. Use the scores in two different algorithms

### Bitonic: exchange records through dependent layers

For N=2^m, the fixed network has K=m(m+1)/2 layers, with N/2 disjoint pairs in
each. A positive measured difference means the left key is larger; measured
zero compares original IDs. Each ascending or descending layer swaps keys and
IDs together. Later layers depend on earlier decisions. There are NK/2 pair
comparisons per sort, and every output remains a permutation even when its
order is wrong. Implementation: [`sorters.py`](../qant_sorting/sorters.py).

### Rank: evaluate every directed matrix cell

The rank mapping follows equations (1)–(7) and the worked matrices in
[Louri, Hatch and Na (1995), Applied Optics 34, 3087–3096](https://doi.org/10.1364/AO.34.003087).
Row i is a competitor; column j is the record being ranked. Define

```math
D_{ij}=\Delta(x_j-x_i),\qquad U_{ij}=\mathbf 1[i>j],\qquad
\widehat D_{ij}=Q(D_{ij}+E_{ij}),
```

```math
R_{ij}=\mathbf 1[\widehat D_{ij}-\Delta U_{ij}\geq0],\qquad
r_j=\sum_i R_{ij}-1.
```

All N² cells are evaluated independently, including the diagonal. Quantization
comes before the exact electronic bias ΔU. The inclusive threshold is applied
to each biased cell; **columns of the threshold matrix** are then summed. The
noiseless diagonal contributes one, so subtracting one converts source ranks
to Python positions. No noisy diagonal is restored, and no reverse vote is
inferred from another cell.

For noiseless keys `[3,1,3,0]`, all 16 threshold entries are:

| Competitor row | ID 0: first 3 | ID 1: 1 | ID 2: second 3 | ID 3: 0 |
|---|---:|---:|---:|---:|
| ID 0: first 3 | 1 | 0 | 1 | 0 |
| ID 1: 1 | 1 | 1 | 1 | 0 |
| ID 2: second 3 | 0 | 0 | 1 | 0 |
| ID 3: 0 | 1 | 1 | 1 | 1 |
| Column sum | **3** | **2** | **4** | **1** |

Positions `[2,1,3,0]` produce keys `[0,1,3,3]` and IDs `[3,1,0,2]`. The bias
removes the later competitor's equality vote, preserving the original order
of equal keys. A positive one-step difference below the diagonal becomes zero
and still passes the inclusive threshold.

Noise can create colliding ranks or ranks outside 0…N−1. Placement accepts only
unique ranks covering every position. A failed array retains `-1` values and
IDs; it is not digitally repaired. The difference callback must return scores
in the same units as the explicit `bias_step=Δ`.

## 4. Score complete outputs against a digital reference

[`evaluation.py`](../qant_sorting/evaluation.py) uses stable NumPy argsort after
the algorithm finishes. The reference never guides a noisy decision.

| Metric | Required condition |
|---|---|
| Valid | Every original ID appears once, paired with its unchanged key |
| Correct | Valid, with keys in nondecreasing order |
| Stable | Correct, with equal-key IDs in their original order |

The reported accuracy is the fraction of **entire arrays** correctly sorted.
For s successful arrays out of n trials, p=s/n. The two-sided 95% Wilson interval
saved in `accuracy.csv` is

```math
\frac{p+z^2/(2n)\ \pm\ z\sqrt{p(1-p)/n+z^2/(4n^2)}}{1+z^2/n},
\qquad z=1.959963984540054.
```

This describes trial sampling uncertainty under the declared experiment.
Observed 100% success is not universal correctness or a measured hardware
reliability. The 288,000 sort executions reuse 24,000 input arrays; they are
not 288,000 independently drawn inputs.

## 5. Measure partial ordering quality

[`quality.py`](../qant_sorting/quality.py) reads saved record IDs, reconstructs
keys from the input corpus and independently checks every saved flag and count.
It does not execute a sorter. Invalid permutations have undefined conditional
quality. The following metrics concern final outputs, not internal comparisons.

### Kendall-τ, its ceiling and key-normalized τ

For a valid output, let C=N(N−1)/2 be all unordered record pairs, M the pairs
with unequal keys, and I the inversions: unequal pairs in the wrong order.
This evaluation pair count C is separate from the rank algorithm's N² cells.
The implementation reports

```math
\tau_b=\frac{M-2I}{\sqrt{CM}},\qquad
\tau_{\mathrm{ceiling}}=\sqrt{M/C},\qquad
\tau_{\mathrm{key}}=1-\frac{2I}{M}.
```

Keys may tie but output positions do not. Consequently, perfect key ordering
can have standard τ-b below one; `tau_b_ceiling` records that limit.
`tau_key_normalized` removes the ceiling and is separately named. All three
are undefined when M=0, including all-equal arrays. Summaries use only defined
outputs and report their count, mean, median, minimum and fifth percentile.

For each integer gap g=|a−b|>0, `distance.csv.gz` pools inversions and available
pairs across valid outputs. Their ratio shows which key separations are
misordered. Equal-key pairs are excluded. Inversion counts are also summarized
per valid array.

### Recall@k / Top-k

Top-k means the k **largest** keys, selected from the suffix of an ascending
output. Cutoffs are {1,5,10,32,N} where applicable. Let S be the k returned IDs
and G the last k IDs of the stable reference. Stable-ID recall is

```math
R_{\mathrm{stable}}(k)=|S\cap G|/k.
```

Tie-neutral recall allows interchangeable keys at the selection boundary.
Let t be the kth-largest true key and h the number of input keys strictly
larger than t. Then

```math
R_{\mathrm{tie}}(k)=
\frac{|\{j\in S:x_j>t\}|+
\min(|\{j\in S:x_j=t\}|,\ k-h)}{k}.
```

Capping tie credit at k−h prevents boundary ties from hiding a missing larger
key. Recall tests selection, not the order within the selected set. Recall@N
is one for every valid permutation and is only a record-preservation control.

For each variant, `mean_valid` averages over valid outputs. The separate
`mean_all_invalid_zero` divides the sum of valid recalls by **all** trials,
assigning invalid outputs zero utility. If no output is valid, conditional
recall and τ stay blank while this all-trial recall is zero. Always read these
metrics together with the validity rate.

## 6. Run, save and rescore

From the repository root, after the setup in the [README](../README.md):

```bash
python -m qant_sorting.run --output-dir results/reproduced
python -m qant_sorting.quality --results-dir results/reproduced --output-dir results/ranking_quality_reproduced
```

The sweep runs 24 datasets × 6 noise levels × 2 algorithms: 288 configurations
and 288,000 sorts. It checks comparison counts and every noiseless output.
`accuracy.csv` holds aggregate results and diagnostics; `trial_outcomes.npz`
holds all IDs and flags; `failures.json` holds example failures. Metadata and
validation record inputs, code hashes, settings and checks. Quality adds
`summary.csv`, `recall.csv` and `distance.csv.gz` with its own metadata and
validation. Use a fresh output directory for each reproduction.

The recorded findings are in [RESULTS.md](RESULTS.md). The independent official
CPU SDK check and conditional hardware accounting are explained in
[HARDWARE.md](HARDWARE.md).
