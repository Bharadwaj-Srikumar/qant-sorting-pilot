# Hardware mapping and the limits of the evidence

The evaluated candidate uses a linear difference kernel with electronic
control. The sensitivity sweep runs in NumPy; the SDK control runs in the
official **CPU backend**. Neither is a physical photonic noise or timing test.

## 1. The trusted linear mapping

For P pairs, [`sdk.py`](../qant_sorting/sdk.py) packs normalized keys into
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
model from [METHOD.md](METHOD.md).

```bash
python -m pip install -r requirements/sdk.txt
python -m tools.install_sdk --no-deps
python -m qant_sorting.sdk
```

The installer checks the bundled toolkit archive. Vendor notices remain in
[`vendor/`](../vendor/). Saved integration evidence is in
[`results/sdk/`](../results/sdk/); a new run uses `results/sdk_reproduced/`.

## 2. Native nonlinearity is an execution-boundary question

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

## 3. Count work separately from physical time

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
two. Reloading both weights adds four bytes per call: U_A=4C_A+4q_A uploaded
and V_A=2C_A downloaded. At N=256 with enough rows per call:

| Mapping | Pair differences | Calls | Total logical bytes, weights reloaded |
|---|---:|---:|---:|
| Bitonic | 4,608 | 36 | 27,792 |
| Full rank matrix | 65,536 | 1 | 393,220 |

These are logical payloads, not measured bus transactions. Rank can require
fewer submissions while doing more arithmetic and moving more data.

```bash
python -m qant_sorting.resources
```

[`results/resources/`](../results/resources/) contains recorded counts and cap
sensitivity; new files go to `results/resources_reproduced/`. The recorded
payload-floor columns use the declared link ceiling in `validation.json` and
exclude protocol, software, arithmetic and host costs.

## 4. Keep latency and energy conditional

A model with serialized transfers and execution is

```math
t_A=q_A\ell+C_A t_{arith}+U_A/B_{up}+V_A/B_{down}+h_A.
```

The terms are call overhead, effective pair arithmetic time, upload/download
time and electronic control work. Shared per-pair time is a conditional
assumption: actual shapes can have different utilization. With weights reloaded,
set a=ℓ+4/B_up and τ=t_arith+4/B_up+2/B_down. Rank is faster within this model
only if

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
E_A=∫P_A(t)dt, including the electronic work needed to meet the same output
quality. The retained evidence supplies no physical latency, throughput or
energy-efficiency verdict, and no established regeneration interval.
