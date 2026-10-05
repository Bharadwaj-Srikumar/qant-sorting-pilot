"""Acquire a periodic API curve on CPU or, when available, actual hardware.

This script does not supply a device, credentials or an approved input range.
Before hardware use, obtain the permissible phase/amplitude ranges from Q.ANT.
Example CPU control:
 python measure_periodic_curve.py --mode cpu --phase-min 0 --phase-max 3.141592653589793 --points 257 --repeats 20

For hardware: install the native driver and hardware SDK, specify the confirmed
range, and explicitly select --mode hardware. All results record backend identity.
No fixed sleep is used. Timestamps support drift analysis on a real device.
"""
import argparse
import csv
import json
from pathlib import Path
import time

import numpy as np
from ml_dtypes import bfloat16
import qant_native_computing_toolkit as qant


def run(args):
    info = qant.info.get_driver_info()
    cpu = "cpu-backend" in info
    if (args.mode == "cpu") != cpu:
        raise RuntimeError(f"Requested {args.mode}, but installed backend is {info}")
    if not np.isfinite([args.phase_min,args.phase_max,args.amplitude]).all():
        raise ValueError("Range and amplitude must be finite")
    if args.phase_min >= args.phase_max or args.points < 3 or args.repeats < 2:
        raise ValueError("Use min<max, points>=3, repeats>=2")
    phases = np.ascontiguousarray(np.linspace(
        args.phase_min,args.phase_max,args.points), dtype=bfloat16)
    amplitudes = np.full(phases.shape,args.amplitude,dtype=bfloat16)
    samples, timestamps, durations = [], [], []
    for _ in range(args.repeats):
        timestamps.append(time.time())
        started = time.perf_counter()
        samples.append(qant.native.calc_scaled_periodic_nl_fprop(
            phases,amplitudes,args.device).astype(np.float32))
        durations.append(time.perf_counter()-started)
    samples=np.stack(samples)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.output_dir/'samples.npz',phase_bf16=phases.astype(np.float32),
                        amplitude_bf16=amplitudes.astype(np.float32),output=samples,
                        timestamps=timestamps,api_duration_seconds=durations)
    with (args.output_dir/'curve.csv').open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['phase_bf16','mean','sample_std','min','max'])
        writer.writerows(zip(phases.astype(np.float32),samples.mean(axis=0),
                            samples.std(axis=0,ddof=1),samples.min(axis=0),samples.max(axis=0)))
    metadata=dict(sdk_version=qant.__version__,driver_info=info,hardware_executed=not cpu,
                  mode=args.mode,device=args.device,phase_min=args.phase_min,
                  phase_max=args.phase_max,points=args.points,repeats=args.repeats,
                  amplitude=args.amplitude,unique_bf16_phases=int(np.unique(phases).size),
                  scope='End-to-end API output, not isolated shot/thermal/laser noise',
                  timing='Host/API duration includes software and transfers; no isolated optical latency',
                  precision='BF16 interface; cannot infer analog ENOB from interface alone')
    (args.output_dir/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('cpu','hardware'),required=True)
    p.add_argument('--phase-min',type=float,required=True)
    p.add_argument('--phase-max',type=float,required=True)
    p.add_argument('--points',type=int,required=True)
    p.add_argument('--repeats',type=int,required=True)
    p.add_argument('--amplitude',type=float,default=1.0)
    p.add_argument('--device',type=int,default=0)
    p.add_argument('--output-dir',type=Path,default=Path('results/curve_measurement'))
    run(p.parse_args())
