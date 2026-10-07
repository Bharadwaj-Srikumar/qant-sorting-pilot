# Reading guide: the matched-width, six-level reference experiment.
# Data flow: validated integer keys -> normalized difference -> synthetic
# Gaussian disturbance -> fixed-point rounding/clipping -> electronic decision.
# Arrays normally have shape (trials, pairs); counters pool scalar comparisons.
# The callable returns measured differences, never repaired keys or a sorted array.
# This model uses delta_in = delta_out = 2**(-bits). The older model.py uses
# output step 2/2**bits and must not be substituted into this experiment.
# For sorter routing read sorting_schedules.py; for flags read metrics.py.
# Neither bit width nor synthetic eta is a measured Q.ANT converter specification.

"""The agreed equal-step, signed, saturating difference model.

This is a numerical sensitivity model, NOT a measured Q.ANT noise model.
For matched b-bit widths: input x/2**b; output step 1/2**b; signed output
codes -2**(b-1), ..., 2**(b-1)-1. Saturation loses magnitude but preserves
the sign without noise. The sorters therefore route original integer records.
"""

from dataclasses import dataclass

import numpy as np


# Contract: immutable description of the registered key/input/output widths.
# Only (4,4,4) and (8,8,8) are accepted. Separate fields make the experiment's
# assumption visible; they do not imply arbitrary mixed widths are implemented.
# Properties expose normalized steps, rather than physical volts or ADC ENOB.
@dataclass(frozen=True)
class Precision:
    """Keep the three settings separate, even in matched-width experiments.

    Unequal widths need a separately agreed normalization/quantization study.
    Reject them here instead of silently extending this experiment.
    """

    key_bits: int
    input_bits: int
    output_bits: int

    # Validate the complete width tuple after dataclass construction.
    # Rejecting unsupported combinations prevents silently changing input density,
    # output range, and noise scaling under the same experiment label.
    def __post_init__(self):
        widths = (self.key_bits, self.input_bits, self.output_bits)
        if any(type(width) is not int for width in widths):
            raise ValueError("Bit widths must be integers")
        if widths not in ((4, 4, 4), (8, 8, 8)):
            raise ValueError("This evaluation supports (4,4,4) and (8,8,8) only")

    # Return the unsigned input-key grid step, 1 / 2**input_bits.
    # Valid matched-width integer keys are exact multiples of this value.
    @property
    def delta_in(self):
        return 1 / 2**self.input_bits

    # Return the AGREED output step, 1 / 2**output_bits.
    # This is not the older model.py step 2 / 2**output_bits. The signed code range
    # is therefore [-1/2, 1/2-delta_out], not the full difference magnitude range.
    @property
    def delta_out(self):
        return 1 / 2**self.output_bits


# Stateful callable: one instance belongs to one experimental batch.
# It owns trial RNG streams and diagnostic counters accumulated over all calls,
# including the successive layers of a bitonic sort. Decisions depend only on
# the measured score; true-key comparisons below are diagnostic observations.
class NoisyDifference:
    """Normalize pairs, add Gaussian noise, then round and saturate.

    Inputs have shape (trials, comparisons). A separate RNG for every trial
    makes the result independent of how the runner groups trials into batches.
    Public runners validate the raw keys once before calling the sorters.
    """

    counter_names = (
        "comparisons", "saturations", "false_ties", "sign_reversals",
        "broken_true_ties",
    )

    # Inputs: Precision, dimensionless eta>=0, experiment seed components, and
    # absolute trial IDs. sigma=eta*delta_out converts eta into signal units.
    # Trial IDs must remain the same when a batch is split; resetting IDs per chunk
    # would repeat streams. eta=0 avoids RNG construction and leaves exact controls.
    # All event counters start at zero and later count scalar pair observations.
    def __init__(self, precision, eta=0.0, seed_context=(), trial_ids=()):
        if not np.isfinite(eta) or eta < 0:
            raise ValueError("eta must be finite and nonnegative")
        self.precision = precision
        self.eta = eta
        self.sigma = eta * precision.delta_out
        # Zero-noise controls need no random generators.
        self.rngs = [
            np.random.default_rng(np.random.SeedSequence([*seed_context, int(i)]))
            for i in trial_ids
        ] if eta else []
        for name in self.counter_names:
            setattr(self, name, 0)

    # Inputs a,b: equal-shaped raw key arrays, normally (trials, pairs).
    # The public runner validates key values before calling this internal kernel.
    # Return: same-shaped float array after noise, nearest-even rounding and clipping.
    # When eta>0, row count must match the configured per-trial generators.
    # Clipping preserves noiseless sign but destroys some magnitudes; this output
    # may guide record routing, but cannot safely reconstruct min/max by subtraction.
    def __call__(self, a, b):
        if a.shape != b.shape:
            raise ValueError("Both pair arrays must have the same shape")
        delta_in = self.precision.delta_in
        delta_out = self.precision.delta_out

        # Matched widths make every valid integer an exact input level.
        # Keeping the input round explicit shows the input quantizer boundary.
        qa = np.rint((a * delta_in) / delta_in) * delta_in
        qb = np.rint((b * delta_in) / delta_in) * delta_in
        noisy = qa - qb

        # eta measures standard deviation IN OUTPUT STEPS, not an offset.
        # Each comparison gets a fresh sample; zero noise draws no samples.
        if self.eta:
            if a.ndim != 2 or len(self.rngs) != a.shape[0]:
                raise ValueError("Noisy batches need one trial seed per input row")
            noisy = noisy + np.stack([
                rng.normal(0, self.sigma, a.shape[1:]) for rng in self.rngs
            ])

        # np.rint rounds to nearest, with exact halfway cases going to even.
        # b signed bits cover [-1/2, 1/2-delta_out] at the agreed common step.
        codes = np.rint(noisy / delta_out)
        half_levels = 2 ** (self.precision.output_bits - 1)
        low, high = -half_levels, half_levels - 1
        measured = np.clip(codes, low, high) * delta_out

        # Diagnostics inspect the true keys ONLY for recording errors.
        # They never change the measured comparison or repair a sort.
        self.comparisons += a.size
        self.saturations += int(np.count_nonzero((codes < low) | (codes > high)))
        self.false_ties += int(np.count_nonzero((a != b) & (measured == 0)))
        self.sign_reversals += int(np.count_nonzero(
            ((a > b) & (measured < 0)) | ((a < b) & (measured > 0))
        ))
        self.broken_true_ties += int(np.count_nonzero((a == b) & (measured != 0)))
        return measured
