"""Run the agreed 4/8-bit experiment and save reproducible numerical evidence.

Usage: python evaluate.py [--config config.json] [--output results]
Ground-truth digital sorting checks correctness; it is not timed as a CPU baseline.
"""
from pathlib import Path
import argparse, csv, hashlib, json, math, platform, time
import numpy as np
from model import run_sort

ROOT = Path(__file__).resolve().parent
ARCHITECTURES = ['Beyette', 'Desmulliez', 'Louri']


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def wilson(count, trials):
    """Two-sided 95% Wilson interval for a Bernoulli success probability."""
    p, z = count/trials, 1.959963984540054
    den = 1+z*z/trials
    mid = (p+z*z/(2*trials))/den
    half = z*math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/den
    return max(0.,mid-half), min(1.,mid+half)


def main(config_path=ROOT/'config.json', output=ROOT/'results'):
    from validate import validate
    cfg = json.loads(Path(config_path).read_text())
    # Fail rather than silently ignore a configuration option this model cannot implement.
    supported = dict(rounding='nearest_even', output_saturation=True,
                     normalization='fixed_declared_range_to_unsigned_grid',
                     tie_rule='original_index', rank_repair=False)
    for setting, value in supported.items():
        if cfg.get(setting) != value:
            raise ValueError(f'{setting} must be {value!r} for this model')
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    validation = validate()
    start = time.perf_counter()
    rows, resources, failures, datasets, flags = [], [], [], {}, {}
    trial_count = cfg['trials']
    assert trial_count > 0 and cfg['batch_size'] > 0
    for case in cfg['precision_cases']:
        b, ib, ob = (case[k] for k in ['key_bits','input_bits','output_bits'])
        for n in case['sizes']:
            assert n >= 2 and n & (n-1) == 0
            m = n.bit_length()-1; k=m*(m+1)//2; p=m*m-m+1
            for arch in ARCHITECTURES:
                resources.append(dict(architecture=arch,key_bits=b,n=n,
                    pair_differences=n*(n-1)//2 if arch=='Louri' else n*k//2,
                    comparison_rounds=1 if arch=='Louri' else k,
                    source_shuffle_steps='' if arch=='Louri' else p,
                    source_bypass_steps='' if arch=='Louri' else p-k,
                    dependency_note='Electronic rank counting and placement follow comparisons' if arch=='Louri'
                    else 'Electronic decisions and exchanges after every active layer'))
            for family_id, family in enumerate(cfg['families']):
                data_seed=[cfg['master_seed'],b,n,family_id,0]
                rng=np.random.default_rng(np.random.SeedSequence(data_seed))
                if family=='distinct':
                    keys=np.array([rng.choice(2**b,n,replace=False) for _ in range(trial_count)])
                elif family=='duplicates_allowed':
                    keys=rng.integers(0,2**b,(trial_count,n))
                else:
                    raise ValueError('unknown input family')
                dataset_id=f'b{b}_n{n}_{family}'
                datasets[dataset_id]=keys.astype('<i8')
                dataset_hash=hashlib.sha256(datasets[dataset_id].tobytes()).hexdigest()
                truth=np.sort(keys,axis=1)
                truth_indices=np.argsort(keys,axis=1,kind='stable')
                for mode_id, mode in enumerate(cfg['modes']):
                    paired=None
                    for arch in ARCHITECTURES:
                        correct=np.zeros(trial_count,bool);stable=correct.copy();valid=correct.copy()
                        totals=dict(comparisons=0,false_ties=0,sign_reversals=0,saturations=0)
                        stream=2 if arch=='Louri' else 1
                        context=[cfg['master_seed'],b,ib,ob,n,family_id,mode_id,stream]
                        failure=None
                        outputs=[]
                        for offset in range(0,trial_count,cfg['batch_size']):
                            stop=min(trial_count,offset+cfg['batch_size'])
                            (y,ids,v),model=run_sort(keys[offset:stop],arch,b,ib,ob,mode,
                                cfg['noise_output_lsb'],context,range(offset,stop))
                            correct[offset:stop]=v & np.all(y==truth[offset:stop],axis=1)
                            stable[offset:stop]=v & np.all(ids==truth_indices[offset:stop],axis=1)
                            valid[offset:stop]=v
                            for metric in totals:totals[metric]+=getattr(model,metric)
                            outputs.append((y,ids,v))
                            if failure is None and np.any(~correct[offset:stop]):
                                j=int(np.flatnonzero(~correct[offset:stop])[0])
                                failure=dict(trial_index=offset+j,input=keys[offset+j].tolist(),
                                    expected=truth[offset+j].tolist(),output=y[j].tolist(),
                                    output_indices=ids[j].tolist(),valid=bool(v[j]))
                        if arch=='Beyette':paired=outputs
                        elif arch=='Desmulliez':
                            assert all(np.array_equal(a,b) for aa,bb in zip(paired,outputs)
                                       for a,b in zip(aa,bb))
                        count=int(correct.sum());lo,hi=wilson(count,trial_count)
                        row_id=f'{dataset_id}_{mode}_{arch}'
                        flags[row_id]=np.column_stack([correct,stable,valid])
                        rows.append(dict(case_id=row_id,architecture=arch,key_bits=b,input_bits=ib,
                            output_bits=ob,key_min=0,key_max=2**b-1,n=n,family=family,mode=mode,
                            noise_output_lsb=cfg['noise_output_lsb'] if mode=='quantized_noise' else 0,
                            trials=trial_count,correct_sorts=count,success_fraction=count/trial_count,
                            ci_low=lo,ci_high=hi,stable_sorts=int(stable.sum()),
                            stable_success=float(stable.mean()),valid_outputs=int(valid.sum()),
                            valid_output_fraction=float(valid.mean()),**totals,
                            input_sha256=dataset_hash,noise_seed_context=json.dumps(context)))
                        if failure:failures.append(dict(case_id=row_id,**failure))
                print(f'Completed {b}-bit N={n}, {family}',flush=True)
    assert all(r['correct_sorts']==trial_count and r['stable_sorts']==trial_count
               for r in rows if r['mode']=='ideal')
    validation['sweep_all_ideal_correct_and_stable']=True
    validation['sweep_paired_bitonic_outputs_equal']=True
    write_csv(out/'precision.csv',rows);write_csv(out/'resources.csv',resources)
    np.savez_compressed(out/'inputs.npz',**datasets)
    np.savez_compressed(out/'trial_outcomes.npz',**flags)
    (out/'failures.json').write_text(json.dumps(failures,indent=2))
    (out/'config.json').write_text(json.dumps(cfg,indent=2))
    (out/'validation.json').write_text(json.dumps(validation,indent=2))
    metadata=dict(python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),
        configurations=len(rows),executions=len(rows)*trial_count,input_arrays=len(datasets)*trial_count,
        elapsed_runner_seconds=time.perf_counter()-start,
        timing_note='Runner wall time only; NOT predicted or measured hardware sorting latency.',
        source_code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(ROOT.glob('*.py'))})
    (out/'run_metadata.json').write_text(json.dumps(metadata,indent=2))
    print(f'Saved {len(rows)} rows, {len(rows)*trial_count:,} architecture executions.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'config.json')
    p.add_argument('--output',type=Path,default=ROOT/'results');args=p.parse_args()
    main(args.config,args.output)
