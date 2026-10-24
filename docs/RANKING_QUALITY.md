# Quality of current saved sorting outputs

The evaluator reads all **288 configurations / 288,000 outputs** from the current
Bitonic and full-matrix Louri reference. There are no missing cases and no sorter
is rerun. Original record IDs reconstruct keys from the immutable input corpus.

## Validity comes first

- **Valid:** each original record occurs exactly once, with its original key.
- **Correct:** valid, and all keys are nondecreasing.
- **Stable:** correct, and equal keys retain original record order.

Bitonic swaps records and therefore preserves validity. Full-matrix rank sorting
can produce colliding or out-of-range ranks; these outputs retain `-1` markers.
Conditional ranking metrics are undefined for invalid output, not zero or perfect.

## Kendall tau and key-distance errors

Let C=N(N−1)/2 be the number of **unordered pairs used to evaluate an output**,
M the number with unequal keys, and I their inversions. This metric pair count
is separate from Louri's N² internal comparison cells.

```math
\tau_b=\frac{M-2I}{\sqrt{CM}},\qquad
\tau_{\mathrm{ceiling}}=\sqrt{M/C},\qquad
\tau_{\mathrm{key}}=1-\frac{2I}{M}.
```

Because keys can tie but output positions do not, perfect ordering can have
standard tau-b below one. The separately named key-normalized value removes that
ceiling. All-equal lists have undefined tau. Tests compare tau-b against SciPy.

For each integer gap g=|a−b|, the evaluator counts final-output inversions and
available unequal-key pairs in valid outputs. Their ratio shows which separations
are confused. These are output errors, not counts of noisy internal comparisons.

## Recall@k

Top-k means the k **largest** keys: the suffix of an ascending output.
Stable-ID recall requires the exact reference records; tie-neutral recall allows
interchangeable keys at the selection boundary while still requiring all larger
keys. Both variants are saved for k in {1,5,10,32,N} where applicable.
Recall@N is a record-preservation control, not evidence of correct sorting.

CSV fields ending in `mean_valid` condition on valid output. The additional
`mean_all_invalid_zero` explicitly assigns failed output zero utility. Report
both coverage and conditional quality; they answer different questions.

## Current evidence

At 8-bit N=256, distinct keys and η=.25, Bitonic has 1,000 valid outputs but only
59 fully correct sorts. Ranking quality can still be high because most errors
are near-neighbour swaps. Louri has **zero valid outputs** under this condition;
its conditional tau and recall are therefore blank, and its all-trial utility
recall is zero. This is the declared independent-cell noise model, not a device test.

`results/ranking_quality/` contains `summary.csv`, `recall.csv`, `distance.csv.gz`,
metadata and complete-coverage validation. Every saved flag and accuracy count
is independently cross-checked.

```bash
python -m qant_sorting quality
```

This writes `results/ranking_quality_reproduced/`. Source outputs remain intact.
These generic sorting metrics do not establish PRISM task recall or a hardware advantage.
