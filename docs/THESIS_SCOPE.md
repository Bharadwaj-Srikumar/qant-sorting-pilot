# Scope and implementation decision

The two evaluated architectures are **Bitonic** and **Louri's full matrix rank
sorter**. The full matrix is the canonical rank implementation throughout code,
SDK integration, experiments, complexity/resource descriptions and the report.

The decision prioritizes traceability to the source architecture. Reducing rank
sorting to one unordered comparison per pair preserves noiseless ordering but
forces complementary pair decisions. That changes the noise model. The reduced
implementation and its result sets have therefore been removed from the current
tree; they are not presented as another active thesis architecture.

## Exact boundary

- Louri: N² directed difference observations, including self-comparisons;
  normalized lower-triangular unit bias; threshold >=0; column sums; one-based
  source ranks converted to zero-based output positions.
- Main sensitivity model: independent Gaussian cell errors, including diagonal;
  matched input/output steps; quantization before exact electronic bias.
  These are declared assumptions, not calibrated physical noise.
- Q.ANT path: every pair is submitted to the pinned official linear CPU backend.
  Bias, threshold, rank sums and record routing stay on the host.
- Periodic/affine functions: separate feasibility evidence. A nonlinear score
  cannot replace a difference without rederiving the bias/threshold contract.
- Complexity stays C=(T,S,H,D). T counts real-RAM-like scalar work, not physical
  seconds or the number of submitted SDK calls.

## Evidence retained

The repository keeps the literature foundations for all five architectures,
current complete sorting outputs, independent quality metrics, the measured CPU
baseline, linear/nonlinear SDK source audits, pair feasibility results, resource
conditions and the hardware measurement plan. Negative results remain visible.
The CPU baseline's original measurement date/environment remain unchanged.

## Next work

1. Obtain supported input ranges, capacity, bias/threshold precision and noise
   covariance from Q.ANT, or maintain explicit sensitivity ranges if unavailable.
2. Test a GPU baseline with the same stable record contract and separate kernel
   time from end-to-end transfers.
3. Evaluate physical latency/energy only with a documented complete data path and
   comparable output quality. Do not infer speed from fewer API submissions.
4. Write the English thesis around the source equations, current mapping,
   numerical limits and conditions for a useful implementation.
