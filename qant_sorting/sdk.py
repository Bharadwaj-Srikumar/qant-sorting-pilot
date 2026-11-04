import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from qant_sorting.comparison import validate_keys
from qant_sorting.evaluation import reference_flags
from qant_sorting.run import INPUT_SHA256, ROOT, file_hash, prepare_output_directory, source_hashes, write_csv
from qant_sorting.sorters import bitonic_sort, rank_sort


def _load_sdk():
    from ml_dtypes import bfloat16
    import qant_native_computing_toolkit as qant

    return qant, bfloat16


@dataclass
class CallCounts:
    api_calls: int = 0
    pair_differences: int = 0
    feature_bytes: int = 0
    weight_bytes: int = 0
    output_bytes: int = 0
    largest_pair_batch: int = 0


class SdkDifference:
    def __init__(self, key_bits, device_id=0):
        if key_bits not in (4, 8):
            raise ValueError("This registered pilot accepts 4-bit or 8-bit key domains")
        self.key_bits = key_bits
        self.device_id = device_id
        self.denominator = 2 ** key_bits
        self._qant, self._bfloat16 = _load_sdk()
        self.weights = np.array([[1, -1]], dtype=self._bfloat16)
        self.counts = CallCounts()

    def __call__(self, a, b):
        if a.shape != b.shape:
            raise ValueError("The two pair arrays must have the same shape")
        features = np.empty((a.size, 2), dtype=self._bfloat16)
        features[:, 0] = a.ravel() / self.denominator
        features[:, 1] = b.ravel() / self.denominator
        result = self._qant.native.linear_fprop(features, self.weights, self.device_id)
        if result.shape != (a.size, 1) or result.dtype != np.dtype(self._bfloat16):
            raise AssertionError("Unexpected SDK output contract")
        c = self.counts
        c.api_calls += 1
        c.pair_differences += a.size
        c.feature_bytes += features.nbytes
        c.weight_bytes += self.weights.nbytes
        c.output_bytes += result.nbytes
        c.largest_pair_batch = max(c.largest_pair_batch, a.size)
        return result.astype(np.float32).reshape(a.shape)


def backend_identity():
    qant, _ = _load_sdk()
    return {"sdk_version": qant.__version__, "driver_info": qant.info.get_driver_info()}


def run(output_directory):
    identity = backend_identity()
    if identity["sdk_version"] != "2.3.1" or not identity["driver_info"].startswith("cpu-backend;"):
        raise RuntimeError("This control requires the pinned official 2.3.1 CPU backend")
    if file_hash(ROOT / "data/inputs.npz") != INPUT_SHA256:
        raise ValueError("Unexpected input corpus")
    output = prepare_output_directory(output_directory, (
        "sdk_accuracy.csv", "sdk_trial_outcomes.npz", "sdk_metadata.json",
    ))
    before = source_hashes()
    for bits in (4, 8):
        a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing="ij")
        np.testing.assert_array_equal(SdkDifference(bits)(a, b), (a-b)/2**bits)

    rows, outcomes = [], {}
    with np.load(ROOT / "data/inputs.npz", allow_pickle=False) as corpus:
        for dataset in corpus.files:
            bit_tag, n_tag, family = dataset.split("_", 2)
            bits, n = int(bit_tag[1:]), int(n_tag[1:])
            data = validate_keys(corpus[dataset], bits)
            for name in ("bitonic", "rank"):
                flags, indices = [], []
                difference = SdkDifference(bits)
                batch_size = min(64, max(1, 1_000_000 // (n*n)))
                for start in range(0, len(data), batch_size):
                    batch = data[start:start+batch_size]
                    if name == "rank":
                        result = rank_sort(batch, difference, bias_step=2.**(-bits))
                    else:
                        result = bitonic_sort(batch, difference)
                    flags.append(reference_flags(batch, result))
                    indices.append(result[1])
                flags = np.concatenate(flags)
                indices = np.concatenate(indices).astype(np.int16)
                key = f"{dataset}_sdk_cpu_{name}"
                outcomes[key + "_flags"], outcomes[key + "_indices"] = flags, indices
                if not flags.all():
                    raise AssertionError("Noiseless SDK sort disagrees with stable argsort")
                m = n.bit_length() - 1
                expected = n*m*(m+1)//4 if name == "bitonic" else n*n
                c = difference.counts
                if c.pair_differences != len(data) * expected:
                    raise AssertionError("The SDK did not evaluate the required number of cells")
                rows.append(dict(
                    mapping=name, key_bits=bits, n=n, family=family, trials=len(data),
                    correct_sorts=int(flags[:, 1].sum()), stable_sorts=int(flags[:, 2].sum()),
                    pair_differences=c.pair_differences, api_calls_batched_trials=c.api_calls,
                    logical_payload_bytes=c.feature_bytes + c.weight_bytes + c.output_bytes,
                    trial_batch_size=batch_size,
                ))
            print(f"{dataset}: SDK CPU verified", flush=True)

    write_csv(output / "sdk_accuracy.csv", rows)
    np.savez_compressed(output / "sdk_trial_outcomes.npz", **outcomes)
    metadata = dict(
        **identity, hardware_executed=False, added_noise=False, extra_quantizer=False,
        executions=sum(r["trials"] for r in rows), inputs_sha256=INPUT_SHA256,
        rank="N*N SDK differences including diagonal; host subtracts delta*U, thresholds >=0 and sums columns",
        scope="CPU software integration; no NPU timing, optical noise or measured bus traffic",
        source_sha256=before, outputs_sha256=file_hash(output / "sdk_trial_outcomes.npz"),
    )
    (output / "sdk_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Verified {metadata['executions']:,} complete SDK CPU sorts.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate the Q.ANT CPU SDK mapping.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/reproduced")
    args = parser.parse_args(argv)
    run(args.output_dir)



from importlib.util import find_spec
import unittest


SDK_AVAILABLE = all(find_spec(name) is not None for name in (
    "qant_native_computing_toolkit", "ml_dtypes",
))


@unittest.skipUnless(SDK_AVAILABLE, "official Q.ANT CPU SDK and ml_dtypes are not installed")
class SdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        identity = backend_identity()
        if identity["sdk_version"] != "2.3.1" or not identity["driver_info"].startswith("cpu-backend;"):
            raise RuntimeError("SDK tests require the pinned official 2.3.1 CPU backend")

    def test_all_pairs_match_the_declared_normalization(self):
        for bits in (4, 8):
            a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing="ij")
            a.flags.writeable = b.flags.writeable = False
            model = SdkDifference(bits)
            result = model(a, b)
            np.testing.assert_array_equal(result, (a-b)/2**bits)
            self.assertEqual(result.dtype, np.dtype(np.float32))
            self.assertEqual(model.counts.api_calls, 1)
            self.assertEqual(model.counts.pair_differences, a.size)
            self.assertEqual(model.counts.feature_bytes, 4*a.size)
            self.assertEqual(model.counts.output_bytes, 2*a.size)
            self.assertEqual(model.counts.weight_bytes, 4)

    def test_both_sorters_keep_original_records_and_stable_ties(self):
        for bits in (4, 8):
            keys = np.array([[3, 1, 3, 0], [2**bits-1, 0, 2**bits-1, 1]])
            original = keys.copy()
            expected = np.argsort(keys, axis=1, kind="stable")
            for sorter, pairs, calls in ((bitonic_sort, 12, 3), (rank_sort, 32, 1)):
                model = SdkDifference(bits)
                if sorter is rank_sort:
                    values, indices, valid = sorter(keys, model, bias_step=2.**(-bits))
                else:
                    values, indices, valid = sorter(keys, model)
                np.testing.assert_array_equal(indices, expected)
                np.testing.assert_array_equal(values, np.take_along_axis(keys, expected, axis=1))
                self.assertTrue(valid.all())
                self.assertEqual(model.counts.pair_differences, pairs)
                self.assertEqual(model.counts.api_calls, calls)
                np.testing.assert_array_equal(keys, original)

    def test_strided_inputs_and_accumulated_counts(self):
        for bits in (4, 8):
            keys = np.arange(24).reshape(4, 6) % 2**bits
            original = keys.copy()
            keys.flags.writeable = False
            model = SdkDifference(bits)
            for a, b in ((keys[::2, ::2], keys[1::2, 1::2]), (keys.T, keys[::-1].T)):
                result = model(a, b)
                self.assertEqual(result.shape, a.shape)
                np.testing.assert_array_equal(result, (a-b)/2**bits)
            np.testing.assert_array_equal(keys, original)
            self.assertEqual(model.counts, CallCounts(
                api_calls=2, pair_differences=30, feature_bytes=120,
                weight_bytes=8, output_bytes=60, largest_pair_batch=24,
            ))

    def test_full_rank_matrix_submits_both_directions_and_diagonal(self):
        keys = np.array([[3, 1, 3, 0]])
        model = SdkDifference(4)
        submitted = []

        def observed(a, b):
            submitted.append((a.copy(), b.copy()))
            return model(a, b)

        result = rank_sort(keys, observed, bias_step=1/16)
        self.assertEqual(len(submitted), 1)
        np.testing.assert_array_equal(submitted[0][0], [[3, 1, 3, 0]*4])
        np.testing.assert_array_equal(submitted[0][1], [[3]*4 + [1]*4 + [3]*4 + [0]*4])
        self.assertEqual(model.counts.pair_differences, 16)
        self.assertEqual(model.counts.api_calls, 1)
        np.testing.assert_array_equal(result[1], [[3, 1, 0, 2]])


if __name__ == "__main__":
    main()
