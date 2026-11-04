# Documentation

Read this document for the code walkthrough, mathematical model, Q.ANT mapping
and recorded results. Installation and main commands are in [README.md](README.md).

## Contents

1. [Code guide](#1-code-guide)
2. [Method and noise model](#2-method-and-noise-model)
3. [Hardware mapping and resource costs](#3-hardware-mapping-and-resource-costs)
4. [Results](#4-results)

## 1. Code guide

### Start with one four-key example

```python
from qant_sorting.comparison import Precision, NoisyDifference, validate_keys
from qant_sorting.sorters import bitonic_sort, rank_sort
from qant_sorting.evaluation import reference_flags

keys = validate_keys([[3, 1, 3, 0]], key_bits=4)
precision = Precision(4, 4, 4)
for sorter in (bitonic_sort, rank_sort):
    difference = NoisyDifference(precision, eta=0)
    options = {"bias_step": precision.delta_in} if sorter is rank_sort else {}
    result = sorter(keys, difference, **options)
    print(result[0])                 # [[0, 1, 3, 3]]
    print(result[1])                 # [[3, 1, 0, 2]]: original record IDs
    print(reference_flags(keys, result))  # [[True, True, True]]
```

One row is one sorting trial. The sorters move the original keys and IDs using
measured comparison scores. The digital reference is used afterwards to score
the output; it never supplies sorting decisions.

### Read in this order

| File | Functions to follow | Question answered |
|---|---|---|
| `qant_sorting/comparison.py` | `validate_keys`, `Precision`, `NoisyDifference.__call__` | How does a pair of keys become a noisy comparison? |
| `qant_sorting/sorters.py` | `compact_bitonic_layers`, `bitonic_sort`, `rank_sort`, `place_ranks` | How do comparison results determine the output order? |
| `qant_sorting/evaluation.py` | `reference_flags`, `wilson_interval`, `prepare_keys`, `score_saved_order` | How are validity, accuracy, stability, tau and Recall@k calculated? |
| `qant_sorting/run.py` | Settings, `evaluate_case`, `run`, `main` | How are the datasets, noise levels and sorters evaluated? |
| `qant_sorting/quality.py` | `statistics`, `run`, `main` | How are detailed metrics generated from saved orders? |
| `qant_sorting/sdk.py` | `SdkDifference`, `backend_identity`, `main` | How is subtraction submitted through the Q.ANT CPU SDK? |
| `qant_sorting/resources.py` | `counts`, `main` | What work and logical data movement does each mapping require? |

The first four files explain the main experiment. The final three produce its
detailed quality analysis, software mapping evidence and resource comparison.

`qant_sorting/install_sdk.py` is a setup helper in the same folder. Run it as
`python -m qant_sorting.install_sdk --no-deps` after installing `requirements.txt`
when you want to use the official CPU SDK. It is not part of the sorting flow.

### Checks in the same files

Each core module ends with a **Self-tests** section containing its mathematical
examples and implementation checks. Read the main functions first, then use the
test names and comments to see which behaviours are checked. Normal experiment
commands do not execute these tests.

Run all checks with `python -m qant_sorting.run --self-test`. To check only one
module, use e.g. `python -m unittest qant_sorting.comparison -v`. The SDK checks
skip when the official toolkit is not installed.

### Keep these conventions in mind

- Keys use 4 or 8 bits. The matched input/output step is delta = 2**(-bits).
- Main noise has standard deviation eta * delta. Output rounding is nearest-even;
  signed clipping limits are [-1/2, 1/2-delta].
- Bitonic uses dependent compare/exchange layers. Rank evaluates N² directed
  cells, including the diagonal, before bias, threshold and column sums.
- Invalid rank placements remain failures with `-1` markers.
- Kendall metrics and conditional recall require valid output. Always report
  validity alongside them. Top-k selects the largest k keys.
- The simulation assumes independent errors. The CPU SDK is a separate software
  integration check. Neither establishes a physical noise distribution.

Use [method and noise model](#2-method-and-noise-model) for equations and the rank example,
[recorded results](#4-results) for findings, and [hardware mapping and resource costs](#3-hardware-mapping-and-resource-costs) for the
mapping boundary and conditional costs. The [README](README.md) lists commands.

## 2. Method and noise model

The experiment compares Bitonic sorting with a full N×N rank sorter. Both move
original integer keys and record IDs; only the comparison scores are disturbed.
The code follows **inputs → comparison model → sorting → evaluation → saved results**.

### 2.1 Fixed inputs and precision

[`data/inputs.npz`](data/inputs.npz) contains 24 datasets of 1,000 arrays each:
4-bit keys at N = 2, 4, 8, 16 and 8-bit keys at N = 2, 4, …, 256, each with
`distinct` and `duplicates_allowed` inputs. The latter are sampled with
replacement; an individual array need not contain a duplicate. The same arrays
are reused across algorithms and noise levels.

[`comparison.py`](qant_sorting/comparison.py) rejects invalid keys before
arithmetic. The registered key, input and output widths are matched: (4,4,4)
or (8,8,8). For their common width b, define

```math
L=2^b,\qquad \Delta=1/L,\qquad x\in\{0,\ldots,L-1\},\qquad \widehat{x}=x/L.
```

Every permitted key lies exactly on the input grid. Normalization uses the
declared domain, not each array's minimum and maximum. Each record also keeps
its original ID, 0 through N−1, so equal keys remain distinguishable.

### 2.2 One noisy, quantized difference

For a pair of keys a and b, the arithmetic is a normalized subtraction:

```math
d=\widehat{a}-\widehat{b}
=\begin{bmatrix}1&-1\end{bmatrix}
 \begin{bmatrix}\widehat{a}\\\widehat{b}\end{bmatrix},\qquad
\epsilon\sim\mathcal{N}(0,(\eta\Delta)^2).
```

Noise is added **before** nearest-even rounding and signed saturation:

```math
c=\mathrm{round}_{\mathrm{even}}((d+\epsilon)/\Delta),\qquad
\widetilde{d}=Q(d+\epsilon)
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
correcting the measured scores. See [`run.py`](qant_sorting/run.py) for seeds
and [`comparison.py`](qant_sorting/comparison.py) for the exact counters.

### 2.3 Use the scores in two different algorithms

#### Bitonic: exchange records through dependent layers

For N=2^m, the fixed network has K=m(m+1)/2 layers, with N/2 disjoint pairs in
each. A positive measured difference means the left key is larger; measured
zero compares original IDs. Each ascending or descending layer swaps keys and
IDs together. Later layers depend on earlier decisions. There are NK/2 pair
comparisons per sort, and every output remains a permutation even when its
order is wrong. Implementation: [`sorters.py`](qant_sorting/sorters.py).

#### Rank: evaluate every directed matrix cell

The rank mapping follows equations (1)–(7) and the worked matrices in
[Louri, Hatch and Na (1995), Applied Optics 34, 3087–3096](https://doi.org/10.1364/AO.34.003087).
Row i is a competitor; column j is the record being ranked. Define

```math
D_{ij}=\Delta(x_j-x_i),\qquad U_{ij}=\mathbf{1}[i>j],\qquad
\widehat{D}_{ij}=Q(D_{ij}+E_{ij}),
```

```math
R_{ij}=\mathbf{1}[\widehat{D}_{ij}-\Delta U_{ij}\geq0],\qquad
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

### 2.4 Score complete outputs against a digital reference

[`evaluation.py`](qant_sorting/evaluation.py) uses stable NumPy argsort after
the algorithm finishes. The reference never guides a noisy decision.

| Metric | Required condition |
|---|---|
| Valid | Every original ID appears once, paired with its unchanged key |
| Correct | Valid, with keys in nondecreasing order |
| Stable | Correct, with equal-key IDs in their original order |

The reported accuracy is the fraction of **entire arrays** correctly sorted.
For s successful arrays out of n trials, p=s/n. The two-sided 95% Wilson interval
saved in `simulation_accuracy.csv` is

```math
\frac{p+z^2/(2n)\ \pm\ z\sqrt{p(1-p)/n+z^2/(4n^2)}}{1+z^2/n},
\qquad z=1.959963984540054.
```

This describes trial sampling uncertainty under the declared experiment.
Observed 100% success is not universal correctness or a measured hardware
reliability. The 288,000 sort executions reuse 24,000 input arrays; they are
not 288,000 independently drawn inputs.

### 2.5 Measure partial ordering quality

[`quality.py`](qant_sorting/quality.py) reads saved record IDs, reconstructs
keys from the input corpus and independently checks every saved flag and count.
It does not execute a sorter. Invalid permutations have undefined conditional
quality. The following metrics concern final outputs, not internal comparisons.

#### Kendall-τ, its ceiling and key-normalized τ

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

For each integer gap g=|a−b|>0, `quality_distance.csv.gz` pools inversions and available
pairs across valid outputs. Their ratio shows which key separations are
misordered. Equal-key pairs are excluded. Inversion counts are also summarized
per valid array.

#### Recall@k / Top-k

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

### 2.6 Run, save and rescore

From the repository root, after the setup in the [README](README.md):

```bash
python -m qant_sorting.run --output-dir results/reproduced
python -m qant_sorting.quality --results-dir results/reproduced
```

The sweep runs 24 datasets × 6 noise levels × 2 algorithms: 288 configurations
and 288,000 sorts. It checks comparison counts and every noiseless output.
`simulation_accuracy.csv` holds aggregate results and diagnostics;
`simulation_trial_outcomes.npz` holds all IDs and flags. The single
`simulation_metadata.json` records inputs, code hashes, settings and checks,
plus example failures under `failure_examples`.
Quality adds `quality_summary.csv`, `quality_recall.csv` and
`quality_distance.csv.gz`. Its `quality_metadata.json` also includes the
rescoring checks under `validation`.

Both commands write to `results/reproduced/` by default. Different output groups
can share this directory, but a command stops if any of its output files already
exists. Choose a new `--output-dir` when repeating a group.

The recorded findings are in [recorded results](#4-results). The independent official
CPU SDK check and conditional hardware accounting are explained in
[hardware mapping and resource costs](#3-hardware-mapping-and-resource-costs).

## 3. Hardware mapping and resource costs

The evaluated candidate uses a linear difference kernel with electronic
control. The sensitivity sweep runs in NumPy; the SDK control runs in the
official **CPU backend**. Neither is a physical photonic noise or timing test.

### 3.1 The trusted linear mapping

For P pairs, [`sdk.py`](qant_sorting/sdk.py) packs normalized keys into
X of shape (P,2), with W = [[1,−1]] of shape (1,2), and calls
`native.linear_fprop(X,W)` to compute XWᵀ. The SDK is pinned to version 2.3.1,
with public source commit `72a2d99f10240b6df3c6d0f636dfa0e2b5d38902`.
The retained primary sources are the
[Python API contracts](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/python/qant_native_computing_toolkit/_wrapper.py),
[linear implementation](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/src/linear.rs)
and [CPU backend](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/src/qant_driver_import/backend_cpu.rs).

| Work | Execution in the retained evaluation |
|---|---|
| Validate keys, normalize and pack pairs | Host Python/NumPy |
| Pair differences | NumPy in the noise sweep; official CPU SDK in the integration check |
| Bitonic signs, tie rules, swaps and record routing | Host |
| Rank bias, threshold, column sums, validity and placement | Host |
| Digital reference and quality metrics | Host, after sorting |

The SDK test uses BF16 interface arrays with **no added Gaussian noise and no
extra signed quantizer**. Its exhaustive pair and full-sort checks establish
software integration for the tested values. BF16 storage is not a measurement
of effective optical precision. The SDK control does not implement the noise
model from [method and noise model](#2-method-and-noise-model).

```bash
python -m pip install -r requirements.txt
python -m qant_sorting.install_sdk --no-deps
python -m qant_sorting.sdk
```

The installer checks the bundled toolkit archive. Vendor notices remain in
[`vendor/`](vendor/). Saved integration evidence includes
[`results/sdk_accuracy.csv`](results/sdk_accuracy.csv), with matching
`sdk_trial_outcomes.npz` and `sdk_metadata.json`. A new run writes these `sdk_`
files to `results/reproduced/`.

### 3.2 Native nonlinearity is an execution-boundary question

The pinned [nonlinear source](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/src/non_linear.rs)
and [hardware-driver declarations](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/src/qant_driver_import/backend_driver.rs)
establish the following narrow conclusions:

| Operation | What the inspected source establishes |
|---|---|
| `native.calc_scaled_periodic_nl_fprop` | A native driver path for y = v·tcos(u); the CPU substitute uses cosine |
| `ai.relu_fprop` | A host CPU max loop; the NPU ID is unused |
| Complete optical compare/exchange or unregenerated cascade | No demonstrated path in the inspected public interface |

The CPU cosine substitute is not a calibrated model of the real optical
transfer function. A native periodic primitive does not establish native
thresholding, stable routing or a complete optical sorter. The
[closed-driver boundary](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/doc/adr/0002-include-driver-via-c-dynamic-library.md)
limits public verification of internal conversion, buffering and regeneration.
An undocumented cascade is unverified, not proved impossible.

Mathematically, exact d=a−b permits `r=max(d,0)`, `min=a−r`, `max=b+r`.
Our signed quantizer can lose the magnitude needed by that identity: at 8 bits,
255/256 clips to 127/256, which reconstructs integer values 128 and 127 instead
of 0 and 255. The evaluated algorithms therefore route original records.
Replacing differences with nonlinear scores would require a new derivation of
scale, bias and thresholds; it is outside the retained experiment.

### 3.3 Count work separately from physical time

The complexity convention remains **C=(T,S,H,D)**: T is total scalar work for a
complete sort; S is peak logical storage in words for one batch; H is installed processing
positions at word granularity; D is consecutive optical stages without signal
regeneration. T includes arithmetic, decisions, accumulation and record movement.
An API call is not one unit of T, and a Bitonic software layer is not a measured
optical stage. Physical H and D require an established hardware implementation.

For N=2^m, K=m(m+1)/2. Pair counts are C_B=NK/2 for Bitonic and C_R=N² for rank,
giving total work Θ(N log²N) and Θ(N²), respectively. Here C_A denotes a pair
count, separately from the complexity tuple. With at most c pair rows per
software submission,

```math
q_B=K\left\lceil\frac{N/2}{c}\right\rceil,\qquad
q_R=\left\lceil\frac{N^2}{c}\right\rceil.
```

The cap is an application setting, not a demonstrated physical matrix size.
For one sort, BF16 features cost four logical bytes per pair and results cost
two. Reloading both weights adds four bytes per call: $U_A=4C_A+4q_A$ uploaded
and $V_A=2C_A$ downloaded. At N=256 with enough rows per call:

| Mapping | Pair differences | Calls | Total logical bytes, weights reloaded |
|---|---:|---:|---:|
| Bitonic | 4,608 | 36 | 27,792 |
| Full rank matrix | 65,536 | 1 | 393,220 |

These are logical payloads, not measured bus transactions. Rank can require
fewer submissions while doing more arithmetic and moving more data.

```bash
python -m qant_sorting.resources
```

Recorded counts and cap sensitivity are in
[`resources_counts.csv`](results/resources_counts.csv) and
[`resources_batch_sensitivity.csv`](results/resources_batch_sensitivity.csv).
New files use the `resources_` prefix in `results/reproduced/`. The recorded
payload-floor columns use the declared link ceiling in
[`resources_metadata.json`](results/resources_metadata.json) and exclude
protocol, software, arithmetic and host costs.

### 3.4 Keep latency and energy conditional

A model with serialized transfers and execution is

```math
t_A=q_A\ell+C_A t_{\mathrm{arith}}+\frac{U_A}{B_{\mathrm{up}}}
+\frac{V_A}{B_{\mathrm{down}}}+h_A.
```

The terms are call overhead, effective pair arithmetic time, upload/download
time and electronic control work. Shared per-pair time is a conditional
assumption: actual shapes can have different utilization. With weights reloaded,
define

```math
a=\ell+\frac{4}{B_{\mathrm{up}}},\qquad
\tau=t_{\mathrm{arith}}+\frac{4}{B_{\mathrm{up}}}+\frac{2}{B_{\mathrm{down}}}.
```

Rank is faster within this model only if

```math
(q_B-q_R)a>(C_R-C_B)\tau+h_R-h_B.
```

The recorded break-even ratio omits/equates host work only to isolate that
conditional trade-off. Effective bandwidth, launch overhead, kernel utilization,
transfer overlap and routing costs remain unmeasured. Fewer calls alone do not
establish a speedup.

Physical noise calibration would require the supported ranges, effective
precision, repeated-readout distribution, bias, drift and correlations. Energy
requires power integrated over a defined end-to-end interval,

```math
E_A=\int P_A(t)\,dt,
```

including the electronic work needed to meet the same output quality.
The retained evidence supplies no physical latency, throughput or
energy-efficiency verdict, and no established regeneration interval.

## 4. Results

The canonical algorithms are Bitonic and full N×N rank sorting, including
independent directed cells and self-comparisons. The following are recorded
simulation and CPU integration results. The Gaussian noise and signed
quantization are declared assumptions, detailed in [method and noise model](#2-method-and-noise-model).

### 4.1 Whole-array correctness

Each cell is **Bitonic / Rank** (%), from 1,000 saved inputs per setting.
Source: [`results/simulation_accuracy.csv`](results/simulation_accuracy.csv).

| Setting | η=0 | .05 | .10 | .15 | .20 | .25 |
|---|---:|---:|---:|---:|---:|---:|
| 4-bit, N=16, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 97.9 | 95.5 / 82.1 | 84.3 / 49.5 |
| 4-bit, N=16, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 99.6 / 97.7 | 95.1 / 75.5 | 87.9 / 35.2 |
| 8-bit, N=256, distinct | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 93.9 / 81.2 | 44.7 / 3.5 | 5.9 / 0.0 |
| 8-bit, N=256, duplicates allowed | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 | 95.5 / 72.4 | 54.8 / 1.2 | 10.4 / 0.0 |

The sweep contains **288 configurations and 288,000 sorts**, reusing 24,000
input arrays. At η=0, all 48,000 sorts are valid, correct and stable. Full outputs,
95% Wilson intervals, diagnostics and example failures remain available; the
table above is only a selection. “Duplicates allowed” means sampling with
replacement. Distinct inputs at maximum N cover the complete key domain.

### 4.2 Validity, stability and useful partial rankings

At **8 bits, N=256 and η=.25**, counts per 1,000 trials are:

| Inputs | Algorithm | Valid | Correct | Stable |
|---|---|---:|---:|---:|
| Distinct | Bitonic | 1,000 | 59 | 59 |
| Distinct | Rank | 0 | 0 | 0 |
| Duplicates allowed | Bitonic | 1,000 | 104 | 5 |
| Duplicates allowed | Rank | 0 | 0 | 0 |

Bitonic preserves records through swaps even when ordering fails. Rank failures
here are invalid rank permutations, retained without repair. Correct key order
and stable record order are different requirements when keys tie.

For the same condition, Bitonic's means over valid outputs are:

| Inputs | τ-b | τ-b ceiling | Key-normalized τ | Stable-ID Recall@10 | Tie-neutral Recall@10 |
|---|---:|---:|---:|---:|---:|
| Distinct | 0.999826 | 1.000000 | 0.999826 | 0.9988 | 0.9988 |
| Duplicates allowed | 0.997888 | 0.998046 | 0.999841 | 0.9978 | 0.9985 |

Mean inversion counts are 2.847 and 2.584, respectively. High partial ordering
quality can coexist with low whole-sort accuracy. Standard τ-b has a lower
ceiling with tied keys; the separately reported normalization makes this
explicit. Sources: [`quality_summary.csv`](results/quality_summary.csv)
and [`quality_recall.csv`](results/quality_recall.csv).

Rank has no valid outputs in either of these settings, so its conditional τ and
recall are undefined, shown as blank CSV fields. Both recall variants with
`mean_all_invalid_zero` are zero. For Bitonic here, conditional and all-trial
recall coincide because every output is valid. Recall selects the largest keys;
Recall@N checks record preservation only. The formulas and denominators are in
[method and noise model](#2-method-and-noise-model).

### 4.3 Evidence and reproduction

All retained files are directly in [`results/`](results/), grouped by prefix:

| Filename prefix | What it supports | Command |
|---|---|---|
| `simulation_` | 288,000 synthetic full-sort outcomes, counts and uncertainty | `python -m qant_sorting.run` |
| `quality_` | Independent rescoring of every saved outcome; τ, inversions, key-distance errors and both Recall@k variants | `python -m qant_sorting.quality` |
| `sdk_` | Official CPU SDK check: 65,792 ordered pairs and 48,000 correct, stable full sorts | `python -m qant_sorting.sdk` |
| `resources_` | Pair/call counts, logical bytes and conditional capacity trade-offs | `python -m qant_sorting.resources` |

The 13 retained files comprise seven tables, two raw archives and four metadata
files:

| File in `results/` | Purpose |
|---|---|
| `simulation_accuracy.csv` | One row per setting: full-sort accuracy, validity/stability counts, confidence intervals and comparison diagnostics |
| `simulation_trial_outcomes.npz` | Record IDs and validity/correctness/stability flags for every simulation trial; used for rescoring |
| `quality_summary.csv` | One row per setting: validity, correctness, stability, Kendall metrics and inversion statistics |
| `quality_recall.csv` | One row per setting and k: both recall conventions, valid-output statistics and all-trial utility |
| `quality_distance.csv.gz` | One row per setting and key gap: pair counts, inversions and inversion rate |
| `sdk_accuracy.csv` | One row per setting: SDK correctness/stability, pair/API-call counts and logical bytes |
| `sdk_trial_outcomes.npz` | Record IDs and validity/correctness/stability flags for every SDK trial |
| `resources_counts.csv` | One row per mapping and N: pair/call counts, logical bytes and conditional transfer floors |
| `resources_batch_sensitivity.csv` | One row per N and pair cap: calls per mapping and conditional overhead threshold |
| Four `*_metadata.json` files | One per command: settings, recorded provenance and assumptions; checks and failure examples where applicable |

The tables use different row units: summaries describe one setting, recall adds
k, and key-gap statistics add the distance. Separate tables avoid repeating
summary values for every cutoff or key gap.

Quality evaluation performs no new sorts. Its validation checks complete
coverage and agreement with every saved flag and accuracy count. By default,
it reads the retained `simulation_` files in `results/`. To score a fresh main
run, use `--results-dir results/reproduced`; its `quality_` output files can
share that directory with the simulation files.
The SDK control adds neither Gaussian noise nor the simulation's extra signed
quantizer; setup and its execution boundary are in [hardware mapping and resource costs](#3-hardware-mapping-and-resource-costs).

At N=256, rank uses 65,536 pair differences against Bitonic's 4,608. A sufficiently
large submission can contain the rank matrix; Bitonic has 36 dependent layers.
Capacity, data movement and electronic work therefore matter to any physical
comparison. These logical counts and the SDK CPU check establish no measured
photonic speed or energy advantage.

New runs default to `results/reproduced/` and use the same filename prefixes.
Retained metadata keeps its original generation environment, source hashes and
recorded filenames and paths, which can differ from the current layout. The
main-run duration records simulation execution time, not a hardware latency
benchmark.
