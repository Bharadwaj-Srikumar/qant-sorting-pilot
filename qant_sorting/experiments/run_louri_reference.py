"""Validate the canonical full-matrix rank implementation against source equations.

No reduced unordered-pair sorter is retained. Stable argsort is the independent
noiseless oracle. Adjacent-key controls expose the original unit bias's zero
raw noise margin; their exact diagonal is an explicitly labelled isolation
control, not the main sweep's measured/noisy diagonal.
"""
import argparse
import json
import math
from pathlib import Path
import platform
import numpy as np
from qant_sorting.comparison import NoisyDifference, Precision
from qant_sorting.io import file_hash, source_hashes, write_csv
from qant_sorting.louri_reference import louri_matrix_rank
from qant_sorting.metrics import reference_flags
from qant_sorting.paths import ROOT, INPUT_SHA256
from qant_sorting.sorting_schedules import rank_sort

SEED = 20261024


def verify_noiseless(corpus):
    """Check raw/matched source ranks and the callable adapter on every case."""
    cases = [('all_4bit_ordered_pairs',4,np.indices((16,16)).reshape(2,-1).T),
             ('all_8bit_ordered_pairs',8,np.indices((256,256)).reshape(2,-1).T),
             ('all_4bit_four_record_lists',4,np.indices((16,)*4).reshape(4,-1).T)]
    cases.extend((name,int(name.split('_')[0][1:]),corpus[name]) for name in corpus.files)
    counts={}
    for name,bits,raw in cases:
        batch_size=min(1024,max(1,1_000_000//raw.shape[1]**2))
        for start in range(0,len(raw),batch_size):
            keys=raw[start:start+batch_size].astype(np.int64)
            expected=np.argsort(keys,axis=1,kind='stable')
            ranks=np.argsort(expected,axis=1)+1
            actual=rank_sort(keys,NoisyDifference(Precision(bits,bits,bits)),bias_step=2.**(-bits))
            np.testing.assert_array_equal(actual[1],expected)
            if not reference_flags(keys,actual).all():
                raise AssertionError('Canonical noiseless rank failed')
            for quantization in ('none','matched'):
                source=louri_matrix_rank(keys,bits,quantization=quantization)
                np.testing.assert_array_equal(source.ranks_one_based,ranks)
                for a,b in zip(actual,source.result): np.testing.assert_array_equal(a,b)
        counts[name]=len(raw)
    return dict(arrays=sum(counts.values()),cases=counts,failures=0,
                checked=['source raw equations','source with matched quantizer','canonical N*N adapter','stable argsort'])


def boundary_controls():
    """Compare independent directed Gaussian errors with analytic probabilities.

    For [1,0] and exact diagonal: raw correct probability is Phi(1/eta)/2;
    matched rounding gives Phi(0.5/eta)**2. Validity also includes a reversed
    order and is tested separately. Floating-point roundoff is not hardware noise.
    """
    eta,samples=.25,100_000
    phi=lambda z:.5*math.erfc(-z/math.sqrt(2))
    keys=np.tile([1,0],(samples,1));rows=[];saved={}
    for bits in (4,8):
        errors=np.random.default_rng(np.random.SeedSequence([SEED,99,bits])).normal(
            0,eta*2.**(-bits),(samples,2,2))
        for quantization in ('none','matched'):
            correct=.5*phi(1/eta) if quantization=='none' else phi(.5/eta)**2
            reversed_order=.5*phi(-1/eta) if quantization=='none' else phi(-.5/eta)**2
            ref=louri_matrix_rank(keys,bits,errors=errors,quantization=quantization,diagonal='exact')
            flags=reference_flags(keys,ref.result)
            valid_count,correct_count,_=flags.sum(axis=0).tolist()
            for observed,expected in ((correct_count/samples,correct),(valid_count/samples,correct+reversed_order)):
                tolerance=6*math.sqrt(expected*(1-expected)/samples)+5/samples
                if abs(observed-expected)>tolerance: raise AssertionError('Gaussian boundary control failed')
            rows.append(dict(bits=bits,eta=eta,quantization=quantization,coupling='independent',
                diagonal='exact_isolation_control',samples=samples,valid=valid_count,correct=correct_count,
                analytic_correct=correct,analytic_valid=correct+reversed_order,check_passed=True))
            saved[f'b{bits}_{quantization}_flags']=flags
    return rows,saved


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'results/louri_reproduced')
    out=parser.parse_args().output_dir.resolve()
    if file_hash(ROOT/'data/inputs.npz')!=INPUT_SHA256: raise ValueError('Unexpected input corpus')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()): raise ValueError('Use an empty output directory')
    before=source_hashes()
    with np.load(ROOT/'data/inputs.npz',allow_pickle=False) as corpus:
        validation=verify_noiseless(corpus)
    rows,saved=boundary_controls()
    write_csv(out/'boundary_controls.csv',rows)
    np.savez_compressed(out/'boundary_outputs.npz',**saved)
    validation.update(analytic_boundary_controls=len(rows),boundary_pair_evaluations=sum(r['samples'] for r in rows))
    (out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    metadata=dict(seed=SEED,python=platform.python_version(),numpy=np.__version__,inputs_sha256=INPUT_SHA256,
        source_doi='10.1364/AO.34.003087',source_sha256=before,hardware_executed=False,
        boundary_noise='One independent full 2x2 Gaussian matrix per sample; seed [20261024,99,bits]; sigma=.25*2**(-bits); shared between quantizers',
        boundary_diagonal='Exact only to isolate off-diagonal threshold margins; main sorting sweep measures all diagonals',
        outputs_sha256={p.name:file_hash(p) for p in sorted(out.iterdir())})
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(validation,indent=2))


if __name__=='__main__':
    main()
