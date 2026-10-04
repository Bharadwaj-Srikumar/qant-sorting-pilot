# Q.ANT: what this code does and does not establish

The pinned official SDK is 2.3.1, source commit
`72a2d99f10240b6df3c6d0f636dfa0e2b5d38902` in the
[Q.ANT toolkit repository](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit).
The bundled CPU release retains its vendor licenses.

| Evidence | Permitted conclusion | Still unverified |
|---|---|---|
| `linear_fprop(X,W)` on the official CPU backend | Software accepts tested BF16 pair rows and computes `X @ W.T` | Supported physical shapes, internal padding/tiling and physical rate |
| `X` has shape `(pairs,2)`, `W` has shape `(1,2)` | Each submitted row represents a normalized subtraction | Whether this small kernel uses a real NPU efficiently |
| Exhaustive 4/8-bit pair checks and saved full-sort CPU checks | These values produce exact differences in the pinned CPU arithmetic | Effective optical precision, bias, tails and drift |
| BF16 arrays and counted SDK calls | Logical payload and number of software submissions | Actual PCIe transactions, cache behavior and launch latency |
| Gaussian noise sweep | Sensitivity to specified comparison noise | Whether Q.ANT meets any selected eta budget |

The public [Q.ANT product information](https://qant.com/photonic-computing/)
was used in the preceding research for a PCIe Gen4 x8 reference. Its directional
line-rate ceiling is approximately 15.754 GB/s after line coding. This is not
measured application bandwidth. Published GOPS figures are not pair-comparison
throughput. Reported conversion resolution is not effective optical precision.

## Logical counts for one sort

With pair-submission cap `c`, the number of calls is

\[
q_B=K\left\lceil\frac{N/2}{c}\right\rceil,\qquad
q_R=\left\lceil\frac{N(N-1)/2}{c}\right\rceil.
\]

The cap is an application setting; it is not a claimed physical matrix size.
BF16 features require four bytes per pair and results require two. Reloading
the two weights contributes four bytes per call. Weight reuse is an accounting
endpoint, not demonstrated device behavior.

For N=256, with enough rows per call:

| Mapping | Pair differences | Calls | Logical bytes, weights reloaded |
|---|---:|---:|---:|
| Bitonic | 4,608 | 36 | 27,792 |
| Rank | 32,640 | 1 | 195,844 |

Rank can save submissions while doing more pair arithmetic and transferring
more data. Neither count alone selects the faster or more efficient algorithm.

## Conditional timing, not a hardware prediction

For serialized transfers and execution, write

\[
t_A=q_A\ell+C_A t_{arith}+U_A/B_{up}+V_A/B_{down}+h_A.
\]

Here `ell` is per-call overhead, `t_arith` is an effective per-pair arithmetic
time, `U,V` are logical bytes and `h` is electronic control work. Shared per-pair
time is a conditional model assumption; different kernel shapes may behave
differently. None of the unknown times is replaced with an invented measurement.

The script sweeps every integer pair cap from 1 through `N(N-1)/2`. With weights
reloaded, define `a=ell+4/B_up` and `tau=t_arith+4/B_up+2/B_down`. Rank is faster
within this model only if

\[
(q_B-q_R)a>(C_R-C_B)\tau+h_R-h_B.
\]

The CSV threshold omits/equates host work solely to isolate that conditional
comparison. Bandwidth has domain `0 < B_eff <= B_peak`; there is no empirically
justified finite range for call overhead or arithmetic time yet. Actual overlap,
padding, transfers and electronic routing must be measured before reporting
latency, throughput or energy per sort.

## Next hardware questions

1. Confirm real-device support and efficiency for the pair-difference kernel,
   relevant batch sizes, BF16 conversion and readout.
2. Measure repeated equal/adjacent-key differences across ranges and operating
   rates: bias, standard deviation, tails, temporal/channel correlation and drift.
3. Convert that distribution to the actual output-step units and rerun full
   sorts. The simulated eta=0.10 result is a candidate budget, not a hardware fact.
4. Measure end-to-end calls, transfers and electronic operations under a defined
   timing boundary; compare with a digital baseline.
5. Investigate supported native nonlinear functions and regeneration intervals
   without assuming that an exposed software function proves optical cascading.

Power and energy-efficiency conclusions follow after these boundaries and
measurements are established. This cleanup changes no physical capability claim.
