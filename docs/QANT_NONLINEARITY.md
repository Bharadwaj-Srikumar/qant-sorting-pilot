# Q.ANT nonlinearity: source-verified boundary, 5 October 2026

The current sorting results use **linear differences and host decisions**. They do
not evaluate a photonic nonlinear compare-and-exchange (C&E) kernel. The public
SDK supports a native periodic operation, while its ReLU implementation runs
on the CPU. An earlier description of ReLU as natively optical is withdrawn.

## 1. What the official source establishes

Audit target: SDK 2.3.1, commit
`72a2d99f10240b6df3c6d0f636dfa0e2b5d38902` (8 September 2026).
It was the `latest` branch head when checked on 5 October 2026.

| Operation | Inspected implementation | Conclusion |
|---|---|---|
| `native.linear_fprop` | `src/linear.rs` calls the matrix/vector driver | Documented NPU-driver path for linear arithmetic; CPU control validates software integration |
| `native.calc_scaled_periodic_nl_fprop` | `src/non_linear.rs` calls `driver_scaled_periodic_nl`; the hardware backend declares `qant_driver_scaled_periodic_nl_npu` | Native periodic operation exposed to the NPU driver |
| `ai.relu_fprop` | `src/non_linear.rs` iterates over host values and evaluates `max(x,0)`; `_npu_id` is unused | Host CPU implementation, also when using a hardware-backed toolkit build |
| `ai.calc_kan_layer_fprop` | NPU multiplication and periodic calls, with CPU phase addition and CPU summation | Composite hybrid implementation, not an all-optical chain |
| Native complete C&E / optical stage cascade | No corresponding primitive or demonstrated path in the inspected public interface | Not established by these sources; this is not proof of physical impossibility |

Pinned primary sources:

- [Nonlinear implementations](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/src/non_linear.rs)
- [Native hardware-driver declarations](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/src/qant_driver_import/backend_driver.rs)
- [Python API contracts](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/python/qant_native_computing_toolkit/_wrapper.py)
- [CPU stand-in](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/src/qant_driver_import/backend_cpu.rs)
- [Why the hardware driver is not open source](https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/blob/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902/doc/adr/0002-include-driver-via-c-dynamic-library.md)

The periodic API specifies `y = v*tcos(u)`, with a cosine-like, 2*pi-periodic
function in [-1,1]. The CPU stand-in uses cosine. That stand-in is not a
calibrated model of the real transfer function, noise, loss or optical depth.
Native nonlinear arithmetic does not by itself establish optical routing or
cascading without electronic regeneration. The closed driver also prevents a
complete public audit of physical conversion and buffering boundaries.

## 2. Correct mathematics, with execution locations

For normalized keys a and b, an exact numerical C&E decomposition is:

    d = a - b
    r = ReLU(d) = max(d, 0)
    minimum = a - r
    maximum = b + r

`d` has an NPU-driver mapping. In the inspected SDK, `r` runs on the host CPU.
The additions/subtractions in our check also run on the host. At (10,9) with
8-bit encoding, d=r=1/256; the outputs are 9/256 and 10/256.
This checks numerical min/max values only. Stable record routing and payload
identity require an additional policy and are handled by the existing baseline.

The existing saturating comparator cannot supply exact min/max magnitudes.
At 8 bits, (255,0) produces d=255/256, clipped to 127/256. Substituting that
clipped value into the identity gives key values (128,127), not (0,255).
Bitonic avoids this problem by routing original records from the sign. The
full Louri matrix uses the measured difference followed by an explicit bias,
threshold and column sum; it also routes original records. See
[LOURI_REFERENCE.md](LOURI_REFERENCE.md) for its quantization conditions.

## 3. Separate, executed CPU check

After installing `requirements/sdk.txt` in a Python 3.12 virtual environment
and running `python -m qant_sorting install-sdk --no-deps`, run:

```bash
python -m qant_sorting nonlinearity
```

Output: `results/nonlinearity_reproduced/checks.json`.
The saved check for this revision is `validation/nonlinearity_check.json`.
All 256 ordered 4-bit pairs and all 65,536 ordered 8-bit pairs, including
equal keys, produced exact numerical min/max values. There was no additional
noise or fixed-point clipping. This is not another full-sort experiment.

## 4. Assumptions and next decisions

No native ReLU, native threshold, all-optical C&E, measured noise level or
regeneration interval is newly assumed. The six-level Gaussian sweep uses the full directed Louri matrix. Its eta is tied to the difference-output step and cannot be carried
over to a nonlinear output without a new scale/noise definition.

The periodic pair construction and affine phase control have now been tested
in the official CPU backend; see [PERIODIC_FEASIBILITY.md](PERIODIC_FEASIBILITY.md).
The host-phase construction is numerically correct for the tested pairs; the
BF16 affine construction produces 40 false ties among the 8-bit pairs. Neither
establishes a host-free cascade. Periodic scores are not passed directly into
Louri's difference-bias equation: that requires a new threshold derivation.
The periodic work therefore remains a bounded pair-feasibility study. A native
hardware sorter would require supported transfer and routing boundaries first.

Only after the execution path is established can repeated hardware measurements
calibrate bias, noise, drift and correlations. A variable optical-regeneration
experiment requires evidence of a supported cascade. If unavailable, report
the hybrid boundary and investigate its cost. Energy conclusions require
end-to-end timing and power under the same correctness requirement.
