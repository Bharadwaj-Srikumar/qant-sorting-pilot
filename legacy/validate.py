# Reading guide: LEGACY model/source checks used by evaluate.py.
# The source examples reproduce arithmetic and schedules, not physical devices.
# This validator deliberately predicts adjacent-key false ties for the older
# 2/L output step; it must not be used as the expected behavior for comparison.py.
# Assertions combine literature examples, exhaustive small inputs, key-validation
# failures and seeded batching invariance. validate returns a JSON-ready report.
# Direct CLI execution prints the report; evaluate.py decides where to save it.

"""Independent source examples, analytic controls, and input/model checks.

Run: python validate.py. Assertions fail loudly; results are also saved by the
main sweep. A reproduced source equation is not a measured device validation.
"""
import itertools, json
import numpy as np
from model import Difference, run_sort, validate_keys
from sorting import shuffle_schedule, shuffle_sort, compact_bitonic_layers


# Run legacy source-example arithmetic and model controls; return a report dict.
# Independent expectations include fixed-shuffle traces, biased-matrix ranks,
# exhaustive small binary inputs, ideal stable ordering, ReLU identities and the
# old quantizer's exact adjacent-pair failure counts. Reject malformed raw keys
# and check that changing batch partition preserves seeded noisy outcomes.
# Assertions stop at the first contradiction; reported historical time formulas
# are source arithmetic, not executed-device measurements or modern benchmarks.
def validate():
    result={}
    # Source: Beyette Eq.1 p.8165 and section3.C p.8171.
    result['Beyette']={
        'source':'Eq.1 and section3.C: P=m^2-m+1; page-oriented completion P+w-1 cycles',
        'N8_w3_P':7,'N8_w3_completion_cycles':9,
        'status':'Equation reproduced; no hardware timing measurement'}
    assert len(shuffle_schedule(8)[1])==7
    # Source: Desmulliez Fig.3 p.5080; Eq.8 and projected 1024-key case.
    x=np.array([[4,8,1,3,2,7,5,6]]);trace=[]
    y,ids,v=shuffle_sort(x,Difference(4,4,4),trace)
    assert trace[0]['output_first_example']==[4,8,3,1,2,7,6,5]
    assert len(trace)==7 and trace[1]['operation']=='bypass'
    assert y.tolist()==[[1,2,3,4,5,6,7,8]]
    t=91*(8+2)/100e6
    result['Desmulliez']={'figure3_trace':trace,'projected_N1024_w8_F100MHz_us':t*1e6,
        'projected_Mbit_s':1024*8/t/1e6,'projected_million_keys_s':1024/t/1e6,
        'status':'Figure and design-point arithmetic reproduced; whole-system 100MHz not measured'}
    assert abs(t*1e6-9.1)<1e-12
    # Source: Louri Eqs.3-7, Figure4; reproduces original full biased matrix.
    x=np.array([7,8,2,8,5]);delta=x[None,:]-x[:,None]
    bias=np.tril(np.ones((5,5),dtype=int),-1)
    ranks=(delta-bias>=0).sum(axis=0)
    assert ranks.tolist()==[3,4,1,5,2]
    (y,ids,v),_=run_sort(x,'Louri',4,4,4)
    assert y.tolist()==[[2,5,7,8,8]] and ids.tolist()==[[2,4,0,1,3]]
    result['Louri']={'paper_one_based_ranks':ranks.tolist(),
        'hybrid_zero_based_ranks':(ranks-1).tolist(),
        'reported_component_full_cycle_ns':3*.1+2*10+3*13.3,
        'reported_component_pipeline_period_ns':2*.1+10+2*13.3,
        'detector_ns_from_stated_10pJ_1point5mW':10e-12/1.5e-3*1e9,
        'detector_ns_reported':13.33,
        'status':'Original matrix example reproduced. Pairwise noisy adaptation differs physically. Detector factor-of-two discrepancy remains unresolved.'}
    # Exhaustive binary inputs establish wiring for three small network sizes.
    for n in [2,4,8]:
        keys=np.array(list(itertools.product([0,1],repeat=n)))
        expected=np.argsort(keys,axis=1,kind='stable')
        for arch in ['Beyette','Desmulliez','Louri']:
            (y,ids,v),_=run_sort(keys,arch,4,4,4)
            assert v.all() and np.array_equal(ids,expected)
    # Every requested length, endpoints, duplicates, reverse and all-equal cases.
    rng=np.random.default_rng(930)
    for b in [4,8]:
        for exponent in range(1,b+1):
            n=2**exponent;M=2**b-1
            keys=rng.integers(0,M+1,(8,n))
            keys=np.vstack([keys,np.zeros(n,int),np.full(n,M),
                            np.arange(n),np.arange(n)[::-1]])
            for arch in ['Beyette','Desmulliez','Louri']:
                (y,ids,v),_=run_sort(keys,arch,b,b,b)
                assert v.all() and np.array_equal(ids,np.argsort(keys,axis=1,kind='stable'))
            k=exponent*(exponent+1)//2
            schedule=shuffle_schedule(n)[1]
            assert len(compact_bitonic_layers(n))==k
            assert sum(s['active'] for s in schedule)==k
    result['ideal_checks']='PASS: binary exhaustive N2/4/8; endpoints, duplicates, reverse and all-equal arrays at every sweep size'
    # ReLU is a mathematical alternative, not the evaluated noisy implementation.
    a,b=np.meshgrid(np.arange(16),np.arange(16));r=np.maximum(a-b,0)
    assert np.array_equal(a-r,np.minimum(a,b)) and np.array_equal(b+r,np.maximum(a,b))
    result['relu_identity']='PASS on all 256 pairs from 0..15; no optical nonlinearity is simulated'
    # Explicit quantizer prediction: adjacent non-equal integers map to zero.
    result['quantizer_controls']={}
    for b in [4,8]:
        L=2**b;a,c=np.meshgrid(np.arange(L),np.arange(L),indexing='ij')
        model=Difference(b,b,b,'quantized')
        d=model(a,c)
        assert np.all(d[np.abs(a-c)==1]==0)
        assert model.false_ties==2*(L-1)
        assert np.array_equal(np.rint(np.arange(L)*model.scale*L)/L,np.arange(L)/L)
        # Original index 0 precedes index 1 on a measured tie.
        predicted_swap=d>0
        actual_swap=a>c
        wrong=np.count_nonzero((predicted_swap!=actual_swap)&(a!=c))
        assert wrong==L-1
        result['quantizer_controls'][str(b)]={
            'ordered_distinct_pairs':L*(L-1),'wrong_N2_comparisons':int(wrong),
            'exact_N2_distinct_success':1-wrong/(L*(L-1)),
            'input_step':1/L,'output_step':2/L,
            'false_ties_all_ordered_pairs':model.false_ties,
            'output_saturation_events_all_ordered_pairs':model.saturations}
    # Raw data errors include the location and allowed range; never silently clip.
    errors=[]
    for keys,b in [([0,16],4),([0,-1],4),([0,1.5],4),([0,float('nan')],4),
                   ([0,float('inf')],4),([0,True],4),([0,'3'],4),([0,10**100],4),([[0,1],[2,256]],8)]:
        try:validate_keys(keys,b)
        except ValueError as exc:
            s=str(exc);assert 'index' in s and 'range' in s;errors.append(s)
        else:raise AssertionError('invalid key accepted')
    assert validate_keys([0.,15.],4).tolist()==[0,15]
    result['input_errors']=errors
    # Seeding is independent of batching, including multiple bitonic layers.
    keys=rng.integers(0,16,(5,8))
    for arch in ['Beyette','Desmulliez','Louri']:
        full,_=run_sort(keys,arch,4,4,4,'quantized_noise',seed_context=(81,),trial_ids=range(5))
        first,_=run_sort(keys[:2],arch,4,4,4,'quantized_noise',seed_context=(81,),trial_ids=range(2))
        last,_=run_sort(keys[2:],arch,4,4,4,'quantized_noise',seed_context=(81,),trial_ids=range(2,5))
        assert all(np.array_equal(a,np.concatenate([b,c])) for a,b,c in zip(full,first,last))
    result['noise_batch_invariance']='PASS'
    return result


# Direct execution starts this file's command-line/test entry point.
# Importing helpers does not run THIS block; the module reading guide
# identifies any other top-level file loading or writing separately.
if __name__=='__main__':
    print(json.dumps(validate(),indent=2))
