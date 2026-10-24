"""A proposed comparison using the official SDK's periodic CPU operation.

This is a hybrid software experiment, not a measured Q.ANT comparator.
The physical tcos curve is only documented as cosine-like. The CPU backend
uses cosine and BF16 I/O. Host code prepares the phase and interprets the
referenced score; original records remain in electronic memory.
"""

import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant

from qant_sorting.sdk_mapping import backend_identity

U0 = np.pi / 2
ALPHA = np.pi / 2


# Inspect runtime identity and raise RuntimeError unless the driver advertises
# cpu-backend. Return the identity dict for metadata after this scope check.
# This avoids running synthetic comparison/noise controls on an unintended device.
def require_cpu_backend():
    """Prevent an illustrative noise experiment from silently using a device."""
    identity = backend_identity()
    if "cpu-backend" not in identity["driver_info"]:
        raise RuntimeError("This experiment requires the official CPU backend")
    return identity


# Input: normalized difference array of any shape. Output: same-shaped float32
# array containing the SDK's BF16 periodic result, before reference correction.
# Host phase preparation and BF16 conversion precede the single native call.
# The ideal formula is sin(pi*d/2), but phase/output rounding changes the actual
# CPU score. Do not use a smooth sine derivative as an exact BF16 noise model.
def periodic_values(difference):
    """Host phase calculation, then one official periodic API call.

    The ideal identity is cos(pi/2 - pi*d/2) = sin(pi*d/2).
    BF16 phase rounding makes the actual CPU result slightly different.
    No b-bit fixed-point output quantizer is added at this boundary.
    """
    phase = np.ascontiguousarray(
        U0 - ALPHA * difference.reshape(-1), dtype=bfloat16
    )
    amplitudes = np.ones(phase.shape, dtype=bfloat16)
    output = qant.native.calc_scaled_periodic_nl_fprop(phase, amplitudes)
    return output.astype(np.float32).reshape(difference.shape)


# Measure one deterministic CPU response at d=0 through the identical phase/API
# path and return it as a Python float. Subtracting it restores exact CPU equality.
# Its noise, temporal drift and calibration cost on a real device are NOT modeled;
# a hardware reference would need an explicit uncertainty/correlation treatment.
def calibration_reference():
    """Use the same BF16/API path at d=0; subtracting it preserves true ties.

    This deterministic, noiseless CPU reference is measured once per run.
    Its noise, drift and recalibration cost on hardware remain unknown.
    """
    return float(periodic_values(np.zeros(1, dtype=np.float32))[0])
