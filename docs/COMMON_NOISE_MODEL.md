# Shared signal, noise, and quantization model

As of 24 October 2026

## Findings and purpose

The earlier comparison of “5.9% versus 100% correct” compares different noise
injection points, signal spacings, and rounding rules. It is **not evidence of
a photonic noise advantage**. The shared model separates these differences. It
explains when a comparison decision reverses, produces a false tie, or breaks
a true tie.

With identical disturbances and rounding before the transformation, the shared
controls produce **identical decisions for direct and ideal periodic
comparison**. With a common output quantizer, the selected 8-bit controls also
produce very similar results. This does not establish general equivalence of
real devices: hardware data on transfer characteristics, conversion, noise,
calibration, and cost are still missing.

This is **one model with deliberately varied settings**. The implementation uses
Float64 and does not call the SDK. The complexity model **C = (T, S, H, D)**
remains unchanged; the quantities below describe signals and evaluation settings.

## 1. One signal path for both variants

For integer keys a,b ranging from 0 to 2^b−1:

```math
\Delta=2^{-b},\qquad x_a=a\Delta,\quad x_b=b\Delta,
\qquad d=x_a-x_b=(a-b)\Delta.
```

`bits` denotes the key width in the code. The inputs used already lie exactly
on this grid. Input rounding to Δ therefore leaves them unchanged. For other
input values, such rounding would need to be modelled explicitly.

The shared pipeline is:

```math
z=\mathrm{clip}_{[-1,1]}
  Q_{q_{\rm pre}}(d+b_{\rm in}+\sigma_{\rm in} Z_{\rm in}),
```

```math
y=\mathrm{clip}_{[-1,1]}Q_{q_{\rm out}}
  \big((1+\epsilon_g)g(z)+b_{\rm out}+\sigma_{\rm out}Z_{\rm out}\big).
```

For Bitonic, the electronics interpret `sign(y)` and resolve y=0 using the
original index. Louri uses only the direct transfer function: y is followed by
the triangular bias −ΔU, the inclusive threshold ≥0, and column summation.
Each of the N² cells receives its own disturbance, including the diagonal.
Original keys remain unchanged; incorrect ranks are not repaired.

- **σ_in:** effective disturbance of the difference before the transfer function.
  It currently combines input/MVM errors; it is not a measured individual
  modulator value. For separate input errors,
  Var(e_a−e_b)=Var(e_a)+Var(e_b)−2Cov(e_a,e_b).
- **σ_out:** additional readout disturbance after the transfer function, in the
  normalized output unit defined below.
- **b_in, b_out:** fixed residual offsets during a run, for example after
  calibration. This represents sensitivity to drift, not a time-dependent drift
  model. An offset is not redrawn for each comparison.
- **ε_g:** relative gain error; set to zero in the current run. An implementation
  option does not itself constitute experimental evidence of its effect.
- **Z_in, Z_out:** independent standard normal variables, sampled anew for each
  comparison. Temporal and channel correlations are neither calibrated nor
  simulated in the current sweep.

Clipping to [−1,1] keeps the ideal sine on a monotone branch and prevents sign
reversal caused by periodic folding under overdrive. This is an **assumed model
boundary**, not a confirmed hardware feature. Exceedances before clipping are
counted. In contrast, the main experiment in `results/reference/` uses the signed
b-bit limit [−1/2,1/2−Δ]. These different quantizers are explicit sensitivity
controls and must not be treated as identical channels.

## 2. Signal spacing and normalization

Two functions are compared:

```math
g_{\rm direct}(d)=d,\qquad
g_{\rm periodic}(d)=\frac{\sin(\alpha d)}{\alpha},
\qquad \alpha=\pi/2.
```

Both have slope 1 at the comparison boundary d=0. Division by α defines the
**output unit**. For the same numerical σ_out to be comparable, actual output
noise must also be divided by the same gain. This assumes neither a free
amplifier nor identical devices. Equal normalized σ_out values are an explicitly
assumed control condition here.

For key distance m=|a−b|, the ideal signal's distance to the zero threshold is
mΔ or sin(αmΔ)/α, respectively. In general, adjacent signal levels are separated
by g((m+1)Δ)−g(mΔ); this spacing is not constant for the sine. The distance from
±Δ to zero is particularly relevant to the comparison decision.

| Quantity | 4 bits | 8 bits |
|---|---:|---:|
| Key spacing Δ | 0.0625 | 0.00390625 |
| Direct: distance to zero for m=1 | 0.0625 | 0.00390625 |
| Normalized sine: distance to zero for m=1 | approx. 0.0623996 | approx. 0.00390623 |
| Assumed standard deviation 0.25Δ | 0.015625 | 0.0009765625 |

A nonlinearity also transforms existing input noise. For small disturbances
without effective quantization or clipping, approximately:

```math
\mathrm{Var}(y\mid d)\approx
 (1+\epsilon_g)^2[g'(d)]^2\sigma_{\rm in}^2+\sigma_{\rm out}^2,
```

provided the two disturbances are independent. Near zero, the unnormalized
sin(αd) increases both the signal spacing **and** the input noise by approximately
α. A larger slope alone therefore does not improve their ratio. Gain can help
against fixed readout noise added later, but actual gain, range, noise injection
point, and cost must be known.

## 3. Quantization is a decision rule

```math
Q_q(v)=q\,\mathrm{roundToEven}(v/q),\qquad Q_0(v)=v.
```

With q_out=Δ, [−Δ/2,+Δ/2] maps to the zero code. Exact halfway values round to the
even code; in particular, ±Δ/2 both become zero. A positive adjacent-key
difference d=Δ therefore has only **Δ/2 margin to a false tie**, even though its
distance to zero is Δ. A coarser grid protects true ties better but can merge
unequal keys.

Quantizers are evaluated deterministically. **No additional independent
“quantization noise” q²/12** is added: that approximation is not generally
justified at the decision thresholds that matter here.

q_pre=0 is the default without intermediate rounding. q_pre=Δ, q_out=0 is used
only as a control: sign(g(Q_Δ(d+e)))=sign(Q_Δ(d+e)) for both monotone,
sign-preserving functions. This does not model a demonstrated Q.ANT cascade
without a host round trip. q_out=0 means no additional fixed output rounding
and no tolerance band. With continuous noise, d=0 is then classified as unequal
with probability 1.

**Grid spacing is not hardware resolution:** key width, simulated quantization
grid, BF16 data type, and physical ENOB are distinct quantities. The symmetric
model range [−1,1] with step Δ contains more than 2^b codes; this does not imply
a b-bit ADC. Actual code count, asymmetry, overdrive, and conversion require
separate evidence.

## 4. Explaining the earlier difference

For the earlier direct/upstream path with d=Δ and σ=0.25Δ:

```math
P(\text{false tie})=
\Phi(-2)-\Phi(-6)\approx 2.275\%,
```

```math
P(\text{sign reversal})=\Phi(-6)\approx9.87\cdot10^{-10}.
```

For true ties, the probability of being broken after this rounding is
2Φ(−2)≈4.550%. A false tie does not always cause an incorrect binary sorting
decision: that depends on the original index. An array requires many such
decisions; pair probabilities must not be extrapolated to an array success rate
without a dependence model.

In the earlier output scenario, σ=0.25Δ was added **after** the unnormalized
periodic signal, with no subsequent fixed grid. For 8 bits:

| Earlier path | Distance / corresponding σ | Meaning |
|---|---:|---|
| Direct difference to zero | 4 | σ in difference units |
| Direct difference to rounding boundary | 2 | Entry into the false zero code |
| Ideal unnormalized sine to zero | approx. 6.283 | σ in unnormalized score units |
| Saved official CPU result to zero | approx. 7.996 | Smallest unequal score after BF16 and reference correction |

The last value follows from `results/periodic/pair_checks.json`:
0.007808685302734375 / 0.0009765625. It is a **CPU software value**, not a hardware
signal margin. BF16 phase rounding makes the transfer characteristic stepwise;
a smooth sine derivative does not describe these CPU steps. The new Float64
model isolates the modelling assumptions and does not replace the SDK check.

This confirms and refines the supervisor's objection. “About 6σ” describes the
ideal earlier sine case; the saved CPU implementation has a different margin.
Neither is directly comparable with the 2σ rounding boundary.

## 5. Evidence and explicitly assumed parameters

| Parameter / statement | Use / value | Evidence status |
|---|---|---|
| Key width and normalization | b=4/8, Δ=2^−b | Defined experiment; saved corpus |
| Ideal periodic function | sin(πd/2)/(π/2) | Mathematical control function; not a measured tcos characteristic |
| Native API and CPU BF16 | Periodic tcos API; CPU computes cosine | Documented SDK source version 2.3.1 [2]; no ENOB evidence |
| σ_in/Δ, σ_out/Δ | Each 0 or 0.25 | Assumed sensitivity values, matching the earlier η endpoint |
| q_pre/Δ | 0 or 1 | Assumed switch isolating intermediate rounding |
| q_out/Δ | 0; 0.5; 1; 2 | Assumed resolution sensitivity; not a DAC/ADC specification |
| b_out/Δ | −0.25; 0; +0.25 | Assumed fixed residual offsets |
| b_in, ε_g | 0 in the saved run | Effects excluded from this run; code supports later variation |
| Gaussianity, independence | Independent samples per comparison/stage | Control assumption; not an established Q.ANT distribution |
| Signal limits | [−1,1], symmetric clipping | Control assumption; actual allowable ranges unknown |
| Reference uncertainty | Not separately estimated yet | To be included explicitly in the offset/readout budget once data are available |
| RIN/shot/thermal noise, error propagation | Structural basis of the model | López-March et al. [1], Section 2, Eqs. 6–9, pp. 6–8 |
| RIN −145 dB/Hz, 1550 nm, 400 kHz laser linewidth | Source context only | Measurement setup in [1], p. 8; **not imported into the sorting simulation** |
| Q.ANT bandwidth, photocurrents, thermal PSD, covariances | Unknown; no numerical value inserted | Manufacturer data or measurements required |

### Connection to a physical model

[1] separates noise sources and propagates photocurrent fluctuations through
the transfer function. It studies a different silicon PIP arrangement; its
normalized variance plots do not supply a universal absolute σ for our sorter
comparison. We adopt the **model structure**, not an apparently device-specific
noise number.

For a single photodiode with white, one-sided spectral densities, a suitable
parameterization is:

```math
\mathrm{Var}(\delta I)=B_{\rm eq}
 \left(S_{I,\rm th}+2q_e I+10^{\mathrm{RIN}_{\rm dB/Hz}/10} I^2\right).
```

I: amperes; B_eq: equivalent noise bandwidth in Hz; S_I,th: A²/Hz;
10^(RIN/10): 1/Hz; q_e: elementary charge. The result is in A².
`receiver_current_variance` implements this formula only with explicitly supplied
values. Because supported device parameters are unavailable, it is **not used**
to parameterize the current sorting runs. Laser linewidth is not electrical
noise bandwidth; RIN per Hz alone is not a variance.

For conversion into our signal quantity, first-order propagation gives
Var(s)≈JΣ_IJᵀ; the Jacobian J includes the receiver transfer and normalization.
`projected_variance` accepts the full covariance matrix. A differential receiver
requires positive branch currents and their correlations: the shot term must
not use a signed difference current. A common RIN component may partially
cancel depending on the design. Additional channel, phase, and calibration
errors must be included without double counting. The small-signal approximation
does not automatically hold near singularities, saturation, or large disturbances.

A measured reference is itself noisy:
Var(y−y_ref)=Var(y)+Var(y_ref)−2Cov(y,y_ref). If a reference is measured once and
stored, its error is shared across comparisons, rather than independently
redrawn each time. A time series is needed to distinguish these effects.

## 6. Completed controls and results

The current run in `results/common_noise/` contains:

- 280 pair cases with 28 million decisions; all 182 analytically checkable cases passed.
- 108 complete sorting configurations with 10,800 evaluations on the first
  100 lists of each selected dataset.
- Bitonic uses both direct and ideal periodic transfer functions. The complete
  Louri matrix uses only direct differences, including independently disturbed
  diagonal entries; its bias is applied after the channel.
- All 18 noiseless sorting configurations are correct and stable.
- `sort_outputs.npz` stores indices and flags; `sort_quality.csv` reports
  validity, correctness, stability, conditional ranking quality, and recall,
  including an explicitly defined variant that scores invalid outputs as zero.

A periodic transfer function must not be inserted into the Louri matrix without
re-deriving the bias/threshold relationship. Equality of signs for two transfer
functions alone does not prove that relationship.

Reproduction: `python -m qant_sorting common-noise`. The default output directory
is `results/common_noise_reproduced/`. The run does not modify saved evidence.
