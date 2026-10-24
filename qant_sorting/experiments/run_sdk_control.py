"""CPU-SDK integration for Bitonic and Louri's full difference matrix.

Every N*N rank cell, including both directions and the diagonal, is submitted
through linear_fprop. Bias, threshold, column sums and placement run on the
host. CPU integration does not establish photonic hardware performance.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from qant_sorting.io import file_hash, source_hashes, write_csv
from qant_sorting.input_validation import validate_keys
from qant_sorting.metrics import reference_flags
from qant_sorting.sdk_mapping import SdkDifference, backend_identity
from qant_sorting.sorting_schedules import bitonic_sort, rank_sort
from qant_sorting.paths import ROOT, INPUT_SHA256


def main():
    """Check every pair and all saved lists against independent stable argsort."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'results/sdk_reproduced')
    args = parser.parse_args()
    identity = backend_identity()
    if identity['sdk_version'] != '2.3.1' or not identity['driver_info'].startswith('cpu-backend;'):
        raise RuntimeError('This control requires the pinned official 2.3.1 CPU backend')
    if file_hash(ROOT/'data/inputs.npz') != INPUT_SHA256:
        raise ValueError('Unexpected input corpus')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    before = source_hashes()
    for bits in (4, 8):
        a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing='ij')
        np.testing.assert_array_equal(SdkDifference(bits)(a, b), (a-b)/2**bits)
    rows, outcomes = [], {}
    with np.load(ROOT/'data/inputs.npz', allow_pickle=False) as corpus:
        for dataset in corpus.files:
            bit_tag, n_tag, family = dataset.split('_', 2)
            bits, n = int(bit_tag[1:]), int(n_tag[1:])
            data = validate_keys(corpus[dataset], bits)
            for name in ('bitonic', 'rank'):
                flags, indices = [], []
                pair_count = api_calls = payload = 0
                # Limit the largest full-matrix temporary, preserving trial order.
                batch_size = min(64, max(1, 1_000_000//(n*n)))
                for start in range(0, len(data), batch_size):
                    batch = data[start:start+batch_size]
                    difference = SdkDifference(bits)
                    result = (rank_sort(batch, difference, bias_step=2.**(-bits)) if name == 'rank'
                              else bitonic_sort(batch, difference))
                    flags.append(reference_flags(batch, result))
                    indices.append(result[1])
                    c = difference.counts
                    pair_count += c.pair_differences
                    api_calls += c.api_calls
                    payload += c.feature_bytes+c.weight_bytes+c.output_bytes
                flags, indices = np.concatenate(flags), np.concatenate(indices).astype(np.int16)
                key = f'{dataset}_sdk_cpu_{name}'
                outcomes[key+'_flags'], outcomes[key+'_indices'] = flags, indices
                if not flags.all():
                    raise AssertionError('Noiseless SDK sort disagrees with stable argsort')
                m = n.bit_length()-1
                expected = n*m*(m+1)//4 if name == 'bitonic' else n*n
                if pair_count != len(data)*expected:
                    raise AssertionError('The SDK did not evaluate the required number of cells')
                rows.append(dict(mapping=name, key_bits=bits, n=n, family=family, trials=len(data),
                    correct_sorts=int(flags[:, 1].sum()), stable_sorts=int(flags[:, 2].sum()),
                    pair_differences=pair_count, api_calls_batched_trials=api_calls,
                    logical_payload_bytes=payload, trial_batch_size=batch_size))
            print(f'{dataset}: SDK CPU verified', flush=True)
    write_csv(output/'accuracy.csv', rows)
    np.savez_compressed(output/'trial_outcomes.npz', **outcomes)
    metadata = dict(**identity, hardware_executed=False, added_noise=False, extra_quantizer=False,
        executions=sum(r['trials'] for r in rows), inputs_sha256=INPUT_SHA256,
        rank='N*N SDK differences including diagonal; host subtracts delta*U, thresholds >=0 and sums columns',
        scope='CPU software integration; no NPU timing, optical noise or measured bus traffic',
        source_sha256=before, outputs_sha256=file_hash(output/'trial_outcomes.npz'))
    (output/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(f"Verified {metadata['executions']:,} complete SDK CPU sorts.")


if __name__ == '__main__':
    main()
