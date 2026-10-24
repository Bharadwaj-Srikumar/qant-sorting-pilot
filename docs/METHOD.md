# From keys to a sorting decision

## 1. Validate and represent each key

The experiment keeps `key_bits`, `input_bits` and `output_bits` separate,
but uses matched settings `(4,4,4)` and `(8,8,8)`. Write their common value as
`b`, with `L = 2**b` and `delta = 1/L`.

Valid keys are whole numbers from 0 through `L-1`. An invalid input is rejected
before any comparison, with its position and required range.

The earlier declared-range normalization was

```math
u(x)=\frac{x}{2^{b_{key}}-1}\left(1-2^{-b_{in}}\right).
```

For matched widths it simplifies exactly to `u(x) = x/L`. Input rounding gives

```math
\widehat{x}=\Delta_{in}\mathrm{round}_{even}
\left(\frac{u(x)}{\Delta_{in}}\right)=\frac{x}{L}.
```

Every permitted integer is represented exactly in these two cases. The scale
depends on the declared key range, not the minimum/maximum of a particular array.

## 2. Calculate one difference

```math
d=\widehat{a}-\widehat{b}
=\begin{bmatrix}1&-1\end{bmatrix}
\begin{bmatrix}\widehat{a}\\\widehat{b}\end{bmatrix}.
```

This two-input dot product is the arithmetic operation proposed for a photonic
linear kernel. A full compare/exchange is nonlinear and is not just this MVM.

The generic noise simulation performs subtraction in NumPy. The separate SDK
control uses `linear_fprop(X,W)` with pair rows in `X` and `W = [[1,-1]]`.

## 3. Add noise in output-step units

```math
\epsilon\sim\mathcal{N}(0,(\eta\Delta_{out})^2),\qquad d_n=d+\epsilon.
```

`eta=0.25` means a standard deviation of one quarter of an output step.
It does **not** mean every comparison receives an offset of `+0.25`.

The sweep assumes independent Gaussian samples between comparison events and
between mappings. This is a sensitivity assumption, not a measured Q.ANT noise
distribution. Equal seeds across positive eta values pair random draws by event
position; bitonic may compare different records after an earlier decision changes.

## 4. Round and saturate the output

```math
c=\mathrm{round}_{even}(d_n/\Delta_{out}),\qquad
\widetilde{d}=\Delta_{out}\min(L/2-1,\max(-L/2,c)).
```

With `delta_in = delta_out = 1/L`, the signed output range is
`[-1/2, 1/2-delta]`. Large differences saturate. Without noise, their sign stays
correct: the negative limit is negative, the positive limit is positive, and
zero stays zero. This suffices for comparison, but not for reconstructing exact
min/max magnitudes from the saturated difference.

Example: at 8 bits, keys 10 and 9 become `10/256` and `9/256`. Their difference
is `1/256`. With no noise, the output code is `round_even(1)=1`, so the measured
difference is positive and 10 is greater. If one noise sample is `-0.6/256`,
the output code is `round_even(0.4)=0`: a false tie. The sorter uses its index
tie rule; it does not consult the original keys to correct that decision.

## 5. Use differences in the two architectures

| Step | Bitonic | Full Louri rank matrix |
|---|---|---|
| Pairs | N/2 pairs in each dependent layer | Every directed cell (i,j), including i=j: N² |
| Arithmetic | Normalized difference | D[i,j] = Δ(x[j]−x[i]) |
| Decision | Sign and original-index tie rule | Subtract Δ below diagonal, then threshold >=0 |
| Accumulation | Swap original records | Sum threshold columns, then subtract 1 from source ranks |
| Output | Final record permutation | Place only if all ranks uniquely cover 0..N−1 |
| Failure | Valid records can be incorrectly ordered | Rank collisions/out-of-range positions invalidate the output |

The [Louri guide](LOURI_REFERENCE.md) shows all 16 entries for N=4. Both directions
are measured separately. Noisy self-comparisons are not restored. The unit bias
resolves noiseless equality; it cannot repair contradictory noisy votes.

A difference callback must return scores in the declared difference units.
`rank_sort(keys, difference, bias_step=2.0**(-bits))` requires the bias step
explicitly. A cosine/sine score cannot be substituted without a new derivation.

## 6. Count work consistently

For N=2**m, Bitonic uses K=m(m+1)/2 dependent layers and N/2 comparisons per
layer: C_B=NK/2 and total scalar work Θ(N log²N). Parallel depth is distinct.
Louri evaluates C_R=N² difference/threshold cells and sums N columns of N
entries: total scalar work Θ(N²), with Θ(N²) materialized matrix/pair storage
per trial. Final validity/placement work is Θ(N).

These counts assume fixed-width unit-cost arithmetic. The established real-RAM-like
T counts the scalar work of a complete sort. It is not the number of SDK calls,
parallel stages or measured seconds. No additional complexity axis is introduced.

## 7. Score complete outputs

- **Valid:** every original record is present once, with its unchanged key.
- **Correct:** valid and all keys appear in ascending order.
- **Stable:** correct and equal-key records retain their original order.

The reported accuracy is the fraction of **entire input arrays** correctly
sorted. The digital reference exists only in scoring. It never feeds decisions
back to the mappings. Wilson intervals describe trial sampling uncertainty;
100% observed over 1,000 trials is not a claim of universally noiseless behavior.

## 8. Nonlinear C&E: a separate mathematical check

For exact normalized differences, `r = ReLU(a-b)` gives `min = a-r` and
`max = b+r`. The SDK ReLU executes on the CPU. The new exhaustive pair check
validates these arithmetic identities with the official CPU backend, without
our additional sign-only quantizer or noise. It does not replace the original
record-routing algorithms or their measured results.

At 8 bits, the sign-only quantizer maps `255/256` to `127/256`. Reconstructing
min/max from that clipped magnitude gives key values 128 and 127 instead of
0 and 255. Correct signs therefore do not prove correct min/max magnitudes.
See [the source audit](QANT_NONLINEARITY.md) before developing a native nonlinear
mapping. Its output scale and noise model require a separate definition.
