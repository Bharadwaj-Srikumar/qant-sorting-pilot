# Reading guide: LEGACY experiment retained for historical reproducibility.
# This file backs evaluate.py/validate.py and the initial three-architecture report.
# It uses output step 2/2**output_bits. Current comparison.py uses 1/2**bits;
# the different steps produce different ties even without added noise.
# Do not use old quantized results as if they came from the later matched-step run.
# run_sort is the checked public entry point; Difference is the internal kernel.
# Beyette and Desmulliez share a numerical shuffle schedule and paired noise here;
# their equal outputs do not imply equal physical time, space or optical depth.

"""Declared numerical model, not a calibration of Q.ANT hardware.

RAW keys are checked before encoding. For maximum key M and input levels L:
    u = key * (1 - 1/L) / M
    q = rint(L*u) / L
For the agreed equal-width cases M=L-1, u=key/L and q=u exactly.
The signed output has step h=2/2**output_bits and includes zero:
    result = clip(rint((qa-qb+noise)/h), -Lout/2, Lout/2-1)*h.
Input errors are rejected. Output saturation is a separate modeled ADC effect.
"""
import numbers
import numpy as np


# Input: a nonempty one-dimensional list or rectangular two-dimensional batch,
# plus an integer key width from 1 to 30. Return a separate int64 array.
# Object conversion preserves original element types until each is checked;
# otherwise a string or boolean could silently become an accepted integer.
# Whole finite real values such as 3.0 are allowed, but fractions/NaN/infinity,
# booleans, strings, negatives and values above 2**key_bits-1 raise ValueError.
# Error locations are zero-based. Shape/network and physical-range checks remain
# the responsibility of the caller that selects a sorting architecture.
def validate_keys(keys, key_bits):
    """Accept a nonempty 1-D array or batch of whole, finite numbers.

    Indexes in errors are zero-based. Integral floats (e.g. 3.0) are accepted;
    strings and booleans are not numeric keys. Return an independent int64 array.
    The initial experiment only uses 4/8 bits; supported key widths are 1..30.
    """
    if not isinstance(key_bits, int) or isinstance(key_bits, bool) or not 1 <= key_bits <= 30:
        raise ValueError('key_bits must be an integer from 1 to 30')
    a = np.asarray(keys, dtype=object)
    if a.ndim not in (1, 2) or 0 in a.shape:
        raise ValueError('keys must be a nonempty array or a rectangular batch of arrays')
    maximum = 2**key_bits - 1
    for index, value in np.ndenumerate(a):
        location = ('input index %d' % index[0] if a.ndim == 1 else
                    'array index %d, key index %d' % index)
        ok = not isinstance(value, (bool, np.bool_)) and (
            isinstance(value, numbers.Integral) or
            (isinstance(value, numbers.Real) and np.isfinite(float(value))
             and float(value).is_integer()))
        if not ok or not 0 <= value <= maximum:
            raise ValueError(f'{location}: key {value!r} must be a finite whole number in range [0, {maximum}]')
    return a.astype(np.int64)


# Legacy stateful difference model with separate key/input/output widths.
# Modes: ideal bypasses quantizers; quantized uses input/output grids; and
# quantized_noise additionally adds Gaussian noise in OUTPUT-step units.
# Counters pool pair events across calls, and RNGs persist across sorter layers.
# The output step is 2/Lout, so adjacent matched-width keys can round to zero
# without noise. This intentional historical assumption is not the current model.
class Difference:
    """Quantize a raw-key subtraction and collect diagnostic event counts.

    Each trial has its own seeded random stream. Results therefore do not
    depend on how the runner splits trials into memory-sized batches.
    Different comparison schedules use independent noise streams. Beyette
    and Desmulliez intentionally receive the SAME stream and schedule.
    """
    # Prepare the legacy normalization scale (1-1/Lin)/(2**key_bits-1), output
    # step 2/Lout, valid mode and one stream per supplied absolute trial ID.
    # Input/output widths support 1..30 here; public run_sort validates key width.
    # noise_lsb is nonnegative standard deviation in output-code steps, not an offset.
    # Constructing a new instance resets diagnostic counts and stream positions.
    def __init__(self, key_bits, input_bits, output_bits, mode='ideal',
                 noise_lsb=0.25, seed_context=(0,), trial_ids=(0,)):
        for name, value in [('input_bits', input_bits), ('output_bits', output_bits)]:
            if not isinstance(value, int) or not 1 <= value <= 30:
                raise ValueError(f'{name} must be an integer from 1 to 30')
        if mode not in ('ideal', 'quantized', 'quantized_noise'):
            raise ValueError('unknown mode')
        if not np.isfinite(noise_lsb) or noise_lsb < 0:
            raise ValueError('noise_lsb must be finite and nonnegative')
        self.maximum = 2**key_bits-1
        self.input_levels = 2**input_bits
        self.output_levels = 2**output_bits
        self.scale = (1-1/self.input_levels)/self.maximum
        self.step = 2/self.output_levels
        self.mode, self.noise_lsb = mode, noise_lsb
        self.rngs = [np.random.default_rng(np.random.SeedSequence([*seed_context, int(i)]))
                     for i in trial_ids]
        self.comparisons = self.false_ties = self.sign_reversals = self.saturations = 0

    # Internal raw-key kernel, called after public validation. Return a score array
    # matching a,b; ideal mode returns the integer difference directly.
    # Other modes quantize each normalized input, optionally perturb their difference,
    # then round/clip signed output codes. Counters observe false ties and reversed
    # signs against true keys only after the score is formed; they never repair it.
    # Only noisy mode needs the batch-row count to match the stored trial generators.
    def __call__(self, a, b):
        """Internal kernel; the public run_sort entry validates raw inputs once."""
        self.comparisons += a.size
        if self.mode == 'ideal':
            return a-b
        qa = np.rint((a*self.scale)*self.input_levels)/self.input_levels
        qb = np.rint((b*self.scale)*self.input_levels)/self.input_levels
        noisy = qa-qb
        if self.mode == 'quantized_noise':
            if len(self.rngs) != a.shape[0]:
                raise ValueError('one noise generator is required per trial')
            noisy = noisy + np.stack([rng.normal(0, self.noise_lsb*self.step, a.shape[1:])
                                     for rng in self.rngs])
        codes = np.rint(noisy/self.step)  # nearest even, including exact half steps
        low, high = -self.output_levels//2, self.output_levels//2-1
        self.saturations += int(np.count_nonzero((codes < low) | (codes > high)))
        measured = np.clip(codes, low, high)*self.step
        self.false_ties += int(np.count_nonzero((a != b) & (measured == 0)))
        self.sign_reversals += int(np.count_nonzero(((a > b) & (measured < 0)) |
                                                  ((a < b) & (measured > 0))))
        return measured


# Checked legacy entry point: validate/copy raw keys, promote one row to a
# batch, select a supported architecture and construct its Difference instance.
# Return ((values, original_indices, valid_mask), model), allowing the runner
# to save both output correctness and accumulated comparator diagnostics.
# Beyette/Desmulliez both use shuffle_sort; Louri uses the legacy rank_sort.
# If trial_ids is omitted, rows are numbered from zero; batched reproduction
# must pass absolute IDs explicitly so RNG sequences remain unchanged.
def run_sort(keys, architecture, key_bits, input_bits, output_bits, mode='ideal',
             noise_lsb=0.25, seed_context=(0,), trial_ids=None):
    """Public checked interface. Outputs always have shape (trials, N).

    Returns (values, original_indices, valid_mask), plus the Difference model.
    Rank rows with colliding ranks are marked invalid and filled with -1.
    """
    from sorting import shuffle_sort, rank_sort
    a = validate_keys(keys, key_bits)
    if a.ndim == 1:
        a = a[None, :]
    if architecture not in ('Beyette', 'Desmulliez', 'Louri'):
        raise ValueError('architecture must be Beyette, Desmulliez, or Louri')
    if trial_ids is None:
        trial_ids = range(len(a))
    model = Difference(key_bits, input_bits, output_bits, mode, noise_lsb,
                       seed_context, trial_ids)
    fn = rank_sort if architecture == 'Louri' else shuffle_sort
    return fn(a, model), model
