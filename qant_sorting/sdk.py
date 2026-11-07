"""Validate sorting through the official Q.ANT SDK CPU backend.

The SDK computes normalized pair differences for a software-integration control.
Counters describe logical API payloads; this module does not time NPU hardware.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from qant_sorting.comparison import validate_keys
from qant_sorting.evaluation import reference_flags
from qant_sorting.run import INPUT_SHA256, ROOT, file_hash, prepare_output_directory, source_hashes, write_csv
from qant_sorting.sorters import bitonic_sort, rank_sort


def _load_sdk():
    """Load the optional SDK and its bfloat16 type only when needed."""
    from ml_dtypes import bfloat16
    import qant_native_computing_toolkit as qant

    return qant, bfloat16


@dataclass
class CallCounts:
    """Accumulate API calls, pair counts, and logical payload sizes in bytes.

    Weight bytes are counted on every call, alongside feature and output bytes.
    """

    api_calls: int = 0
    pair_differences: int = 0
    feature_bytes: int = 0
    weight_bytes: int = 0
    output_bytes: int = 0
    largest_pair_batch: int = 0


class SdkDifference:
    """Compute normalized pair differences using the SDK's [1, -1] projection."""

    def __init__(self, key_bits, device_id=0):
        """Set the key normalization, SDK device, weights, and counters."""
        if key_bits not in (4, 8):
            raise ValueError("This registered pilot accepts 4-bit or 8-bit key domains")
        self.key_bits = key_bits
        self.device_id = device_id
        self.denominator = 2 ** key_bits
        self._qant, self._bfloat16 = _load_sdk()
        self.weights = np.array([[1, -1]], dtype=self._bfloat16)
        self.counts = CallCounts()

    def __call__(self, a, b):
        """Return (a - b) / 2**key_bits and record the logical SDK payload."""
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
    """Return the SDK version and driver identification for validation."""
    qant, _ = _load_sdk()
    return {"sdk_version": qant.__version__, "driver_info": qant.info.get_driver_info()}


def run(output_directory):
    """Verify exhaustive pairs and corpus sorts with the pinned CPU backend."""
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
    """Parse command-line options and run the SDK CPU control."""
    parser = argparse.ArgumentParser(description="Evaluate the Q.ANT CPU SDK mapping.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/reproduced")
    args = parser.parse_args(argv)
    run(args.output_dir)


if __name__ == "__main__":
    main()
