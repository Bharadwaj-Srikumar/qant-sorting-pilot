# From keys to a sorting decision

## 1. Validate and represent each key

The experiment keeps `key_bits`, `input_bits` and `output_bits` separate,
but uses matched settings `(4,4,4)` and `(8,8,8)`. Write their common value as
`b`, with `L = 2**b` and `delta = 1/L`.

Valid keys are whole numbers from 0 through `L-1`. An invalid input is rejected
before any comparison, with its position and required range.

The earlier declared-range normalization was

\[
u(x)=\frac{x}{2^{b_{key}}-1}\left(1-2^{-b_{in}}\right).
\]

For matched widths it simplifies exactly to `u(x) = x/L`. Input rounding gives

\[
\widehat{x}=\Delta_{in}\operatorname{round}_{even}
\left(\frac{u(x)}{\Delta_{in}}\right)=\frac{x}{L}.
\]

Every permitted integer is represented exactly in these two cases. The scale
depends on the declared key range, not the minimum/maximum of a particular array.

## 2. Calculate one difference

\[
d=\widehat{a}-\widehat{b}
=\begin{bmatrix}1&-1\end{bmatrix}
\begin{bmatrix}\widehat{a}\\\widehat{b}\end{bmatrix}.
\]

This two-input dot product is the arithmetic operation proposed for a photonic
linear kernel. A full compare/exchange is nonlinear and is not just this MVM.

The generic noise simulation performs subtraction in NumPy. The separate SDK
control uses `linear_fprop(X,W)` with pair rows in `X` and `W = [[1,-1]]`.

## 3. Add noise in output-step units

\[
\epsilon\sim\mathcal{N}(0,(\eta\Delta_{out})^2),\qquad d_n=d+\epsilon.
\]

`eta=0.25` means a standard deviation of one quarter of an output step.
It does **not** mean every comparison receives an offset of `+0.25`.

The sweep assumes independent Gaussian samples between comparison events and
between mappings. This is a sensitivity assumption, not a measured Q.ANT noise
distribution. Equal seeds across positive eta values pair random draws by event
position; bitonic may compare different records after an earlier decision changes.

## 4. Round and saturate the output

\[
c=\operatorname{round}_{even}(d_n/\Delta_{out}),\qquad
\widetilde{d}=\Delta_{out}\min(L/2-1,\max(-L/2,c)).
\]

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

## 5. Use the decision in either sorter

| Step | Pipelined-bitonic adaptation | Rank adaptation |
|---|---|---|
| Select pairs | Fixed pairs in each Batcher layer | Every unordered pair `(i,j)`, with `i<j` |
| Arithmetic | One difference per pair | One difference per pair |
| Decide | Sign; original index resolves measured zero | Positive means `i` is larger; otherwise `j` is larger |
| Update | Exchange original keys **and indices** electronically | Increment the larger record's integer rank electronically |
| Continue | Finish a layer before the next dependent layer | Accumulate all pair decisions |
| Output | Final record order | Place each original record at its unique rank |
| Failure | Preserved records can be in the wrong order | Repeated ranks invalidate the output; unique ranks can still be wrong |

Both mappings keep original records exact. Neither rebuilds keys from noisy
differences. Neither includes an optical nonlinear cascade or hidden digital repair.

## 6. Count work consistently

For `N=2**m`, the active bitonic network has `K=m(m+1)/2` layers and `N/2`
pairs per layer. Thus `C_B=NK/2` comparisons and total sequential comparison
work `Theta(N log² N)`. Layer depth is `Theta(log² N)` and is a different quantity.

Rank sorting uses `C_R=N(N-1)/2` pair differences. Every outcome updates one
rank, so its comparison and accumulation work is `Theta(N²)`. Final placement
and the occupancy check use `Theta(N)` work. The current implementation stores
the pair outcomes, requiring quadratic auxiliary storage per trial; the batch
size multiplies the host memory requirement.

These are algorithmic counts under fixed-width, unit-cost operations. Neither
Python wall-clock duration nor parallel layer depth is substituted for total
sorting time in the established complexity convention. Physical module counts
and regeneration depth require an explicitly supported hardware mapping.

## 7. Score complete outputs

- **Valid:** every original record is present once, with its unchanged key.
- **Correct:** valid and all keys appear in ascending order.
- **Stable:** correct and equal-key records retain their original order.

The reported accuracy is the fraction of **entire input arrays** correctly
sorted. The digital reference exists only in scoring. It never feeds decisions
back to the mappings. Wilson intervals describe trial sampling uncertainty;
100% observed over 1,000 trials is not a claim of universally noiseless behavior.
