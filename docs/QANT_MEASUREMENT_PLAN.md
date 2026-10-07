# Hardware evidence and measurement plan, 5 October 2026

## Common-model parameter needs, 7 October 2026

The [common noise model](COMMON_NOISE_MODEL.md) now distinguishes upstream
disturbance, readout disturbance, quantization and residual calibration offsets.
Its numerical settings are assumptions. To replace them, request the signal
normalization and measured transfer together with each variance, equivalent
noise bandwidth, converter step/range/rounding, and repeat-sample timestamps.
For receiver-based estimates, branch photocurrents, responsivity/transfer gain,
thermal current PSD, RIN spectrum and covariance are needed. Laser linewidth
is not the receiver noise bandwidth. A one-time reference error must be treated
as shared across comparisons, with drift and recalibration recorded separately.
BF16 interface support alone does not supply any of these noise or ENOB values.

## What was obtained from public sources

- Official SDK contracts and source: native periodic API and BF16 I/O;
  CPU cosine implementation; separate hardware-driver path; host ReLU.
- Q.ANT current product page and Generation 2 brochure: PCIe Gen4 x8,
  vendor 8 GOPS figure and 150 W NPU figure. These do not give comparator
  latency, energy per sort, effective resolution or physical batch limits.
- Brochure p.8 describes BF16 support. Its p.5 transistor comparison refers
  to CMOS 8-bit integer precision, not a calibrated Q.ANT 8-bit ENOB result.
- The current website and brochure disagree on NPS rack height (4U/2U) and
  operating temperature limit (35/30 degrees C). These are not used in the
  sorting model; ask for a version-specific datasheet rather than reconcile
  them by assumption.

Sources, inspected 5 October 2026:
https://qant.com/photonic-computing/
https://qant.com/wp-content/uploads/2026/06/20260617-Q.ANT-NPU-Generation-2.pdf
https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit/tree/72a2d99f10240b6df3c6d0f636dfa0e2b5d38902
https://qant.com/contact/

These sources do not supply the comparator-specific phase interval, actual
tcos transfer table, output error distribution, drift covariance, calibration
interval, or complete host-device timing. No physical measurements are claimed.

## Concrete questions and proposed measurements

| Quantity needed | Why needed | Measurement / evidence request |
|---|---|---|
| Permissible u and v ranges, units, per-channel calibration | Phase range of the proposed comparator must be legal | Version-specific API/driver contract and device datasheet |
| f(u), zero crossing, monotone interval, residual model error | Determine u0, alpha and minimum key-pair margin | Dense phase sweep plus all actually encoded key-difference levels, both directions |
| Input/output resolution and rounding, converter settings | BF16 I/O alone does not specify optical precision | Code histograms, repeated levels near zero crossing, DAC/ADC and scaling descriptions |
| Repeated-output noise by signal level/channel | Estimate error probability instead of imposing eta | Repeated fixed inputs; empirical distributions and tails; not only one Gaussian fit |
| Offset and gain drift, time/channel correlation | A single reference may become invalid | Interleave d=0 reference and unequal pairs, retain timestamps, repeat across loads/temperature |
| Supported dimensions, independent capacity of linear/periodic calls | Rank requires wide batches; bitonic dependent layers | Device API tests at confirmed dimensions and buffers, with error/status logging |
| Call/transfer latency and possible fusion/caching | Two native API calls may add host conversion overhead | Cold/warm latency, actual transfer counters and driver execution trace |
| Optical cascades or compulsory regeneration | Establish physical D rather than infer it from API calls | Hardware diagram and supported fused/cascade path, with measured fidelity |

## Ready measurement script and completed CPU control

measure_periodic_curve.py records raw samples, BF16 input codes, mean/std,
range, timestamps, SDK/backend identity and end-to-end API call durations.
It rejects a requested hardware mode when only the CPU backend is installed.
The valid hardware phase/amplitude range must be confirmed by Q.ANT first.

Completed CPU control: phase [0,pi], amplitude 1, 257 requested points,
20 repeats. BF16 leaves 237 distinct phase codes. Deterministic CPU results
cannot characterize physical noise or drift. Evidence: results/periodic_curve_cpu/.

Example CPU reproduction:
```bash
python measure_periodic_curve.py --mode cpu --phase-min 0 --phase-max 3.141592653589793 --points 257 --repeats 20 --output-dir results/periodic_curve_cpu
```

For actual hardware, replace the SDK/driver with the supported hardware
installation and explicitly select --mode hardware with the manufacturer-
confirmed range. Run within the capacity/Q.ANT-approved experimental setup.
No physical device or authenticated remote NPU session is available here.

## How to judge feasibility

First agree a full-sort correctness target and whether stable duplicate order
is required. Calibrate u0/alpha/deadband from the physical curve. Replay the
same saved inputs and record failures. Use measured multi-channel and time-
correlated errors in both sorters. Compare resource/latency costs only at
the same achieved correctness. A scalar sigma cannot establish these facts.

For a fixed symmetric deadband tau and unequal-pair minimum margin m,
bounded output error below min(tau,m-tau) preserves the three-way decision,
provided reference/calibration error is included in that bound. Choosing
tau=m/2 balances the two worst-case margins. Gaussian noise is unbounded;
it gives probabilities rather than a deterministic guarantee. Do not transfer
the CPU value m to a physical tcos curve without measurement.

Energy evaluation follows calibrated mappings, measured execution boundaries
and power traces. The vendor power/throughput figures alone are insufficient.
