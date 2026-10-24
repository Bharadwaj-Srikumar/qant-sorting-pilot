"""Score the complete CURRENT Bitonic/full-matrix output archive without rerunning sorts.

Invalid permutations have undefined tau/recall. A separately named recall field
assigns invalid outputs zero utility. Every saved flag and CSV count must agree
with independent scoring; missing members fail instead of being repaired.
"""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import platform
import numpy as np
from qant_sorting.io import file_hash, source_hashes, write_csv
from qant_sorting.paths import ROOT, INPUT_SHA256
from qant_sorting.ranking_quality import prepare_keys, score_saved_order


def statistics(values,prefix):
    """Summarize only finite values; an empty conditional population stays blank."""
    values=values[np.isfinite(values)]
    if not len(values): return {prefix+s:None for s in ('_mean','_median','_min','_p05')}
    return dict(zip((prefix+s for s in ('_mean','_median','_min','_p05')),
                    map(float,(np.mean(values),np.median(values),np.min(values),np.quantile(values,.05)))))


def run(args):
    root,output=args.project_dir.resolve(),args.output_dir.resolve()
    paths=[root/'data/inputs.npz']+[root/'results/reference'/n for n in ('accuracy.csv','metadata.json','trial_outcomes.npz')]
    hashes={str(p.relative_to(root)):file_hash(p) for p in paths}
    if hashes['data/inputs.npz']!=INPUT_SHA256: raise ValueError('Unexpected input corpus')
    source_metadata=json.loads(paths[2].read_text())
    if source_metadata.get('revision')!='thesis_full_matrix_20261024':
        raise ValueError('Quality requires the current full-matrix experiment')
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()): raise ValueError('Use an empty output directory')
    summaries,recalls,distances=[],[],[]
    with paths[1].open(newline='') as handle: rows=list(csv.DictReader(handle))
    with np.load(paths[0],allow_pickle=False) as corpus, np.load(paths[3],allow_pickle=False) as outputs:
        prepared={name:prepare_keys(corpus[name],int(name.split('_')[0][1:])) for name in corpus.files}
        for row in rows:
            bits,n,eta=int(row['key_bits']),int(row['n']),float(row['eta'])
            dataset=f"b{bits}_n{n}_{row['family']}"
            mapping='bitonic' if 'bitonic' in row['mapping'].lower() else 'rank'
            tag='zero' if eta==0 else f'noise{round(100*eta):03d}'
            case=f'{dataset}_{tag}_{mapping}'
            result=score_saved_order(prepared[dataset],outputs[case+'_indices'])
            flags=result['flags'];np.testing.assert_array_equal(flags,outputs[case+'_flags'])
            valid,correct,stable=flags.sum(axis=0).tolist();trials=len(flags)
            if [valid,correct,stable]!=[int(row[k]) for k in ('valid_outputs','correct_sorts','stable_sorts')]:
                raise AssertionError('Saved accuracy disagrees with rescoring')
            fields=dict(dataset=dataset,key_bits=bits,n=n,family=row['family'],eta=eta,mapping=mapping)
            summary=dict(**fields,trials=trials,valid_outputs=valid,invalid_outputs=trials-valid,
                correct_sorts=correct,stable_sorts=stable,whole_sort_accuracy=correct/trials,
                tau_defined_outputs=int(np.isfinite(result['tau_b']).sum()),
                comparable_pairs_valid=int(result['distance_pairs'].sum()),
                inverted_pairs_valid=int(result['distance_inversions'].sum()))
            for metric in ('tau_b','tau_b_ceiling','tau_key_normalized'):
                summary.update(statistics(result[metric],metric))
            summary.update(statistics(result['inversions'][flags[:,0]],'inversions_valid'))
            summaries.append(summary)
            for gap,den in enumerate(result['distance_pairs']):
                if den:
                    errors=int(result['distance_inversions'][gap])
                    distances.append(dict(**fields,key_distance=gap,valid_outputs=valid,
                        pairs_at_distance=int(den),inverted_pairs=errors,inversion_rate=errors/int(den)))
            for k,variants in result['recall'].items():
                recall=dict(**fields,k=k,selection='largest',full_set_control=(k==n),
                            trials=trials,valid_outputs=valid,invalid_outputs=trials-valid)
                for variant,values in variants.items():
                    finite=values[np.isfinite(values)]
                    recall[variant+'_mean_valid']=float(finite.mean()) if len(finite) else None
                    recall[variant+'_min_valid']=float(finite.min()) if len(finite) else None
                    recall[variant+'_mean_all_invalid_zero']=float(np.nansum(values)/trials)
                recalls.append(recall)
    write_csv(output/'summary.csv',summaries);write_csv(output/'recall.csv',recalls)
    with (output/'distance.csv.gz').open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed:
            with io.TextIOWrapper(compressed,encoding='utf-8',newline='') as text:
                writer=csv.DictWriter(text,fieldnames=list(distances[0]));writer.writeheader();writer.writerows(distances)
    for p in paths:
        if file_hash(p)!=hashes[str(p.relative_to(root))]: raise AssertionError('Source outputs changed')
    validation=dict(evaluated_cases=len(rows),evaluated_outputs=sum(r['trials'] for r in summaries),
                    complete_coverage=True,missing_cases=[],saved_flags_and_counts_reproduced=True,
                    distance_rows=len(distances),new_sorter_executions=0)
    metadata=dict(python=platform.python_version(),numpy=np.__version__,source_sha256=hashes,
        evaluation_code_sha256=source_hashes(),
        kendall='tau_b(true keys, output positions); ceiling sqrt(M/C); tau_key=1-2*I/M is a distinct normalization',
        distances='Unequal-key inversions of VALID final outputs, pooled by exact integer key gap',
        recall='Largest k; stable-ID and tie-neutral boundary conventions; k=N is only a full-set control',
        invalid_policy='Undefined conditional quality; mean_all_invalid_zero explicitly assigns zero utility',
        scope='Synthetic sorting quality, not hardware performance or PRISM task quality',
        input_dependence='The same 24000 input arrays are reused across noise levels and architectures')
    for name,value in (('validation.json',validation),('metadata.json',metadata)):
        (output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(validation,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=ROOT)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'results/ranking_quality_reproduced')
    run(parser.parse_args())
