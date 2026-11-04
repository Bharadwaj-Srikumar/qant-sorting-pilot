"""Map both sorters to the official Q.ANT linear CPU backend.

Each pair becomes one BF16 row [a/2**bits, b/2**bits] with weights [1,-1].
The SDK returns the difference; decisions and record routing stay on the host.
Run python -m qant_sorting.sdk to check every pair and the saved input corpus.
CPU integration does not establish optical noise, hardware speed or a cascade.
"""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from qant_sorting.comparison import validate_keys
from qant_sorting.evaluation import reference_flags
from qant_sorting.run import INPUT_SHA256, ROOT, file_hash, source_hashes, write_csv
from qant_sorting.sorters import bitonic_sort, rank_sort


def _load_sdk():
    """Load the separate SDK environment only when an SDK operation is needed."""
    from ml_dtypes import bfloat16
    import qant_native_computing_toolkit as qant

    return qant, bfloat16


@dataclass
class CallCounts:
    """Count logical API buffers and calls, not measured bus traffic."""

    api_calls: int = 0
    pair_differences: int = 0
    feature_bytes: int = 0
    weight_bytes: int = 0
    output_bytes: int = 0
    largest_pair_batch: int = 0


class SdkDifference:
    """Adapt equally shaped key arrays to X=(pairs,2), W=(1,2), Y=X@W.T.

    The official CPU backend uses BF16 products, FP32 accumulation and BF16
    output. Key multiples of 1/16 or 1/256 are exactly representable in BF16.
    Only linear_fprop runs here; swaps, thresholds and rank sums stay on host.
    Accepted CPU batch shapes do not establish a physical device's capacity.
    """

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
        """Normalize and pack pairs, call the SDK, then restore the pair shape."""
        if a.shape != b.shape:
            raise ValueError("The two pair arrays must have the same shape")
        features = np.stack((a, b), axis=-1).reshape(-1, 2)
        features = np.ascontiguousarray(features / self.denominator, dtype=self._bfloat16)
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
        # Widen the returned score for host decisions; do not recompute it.
        return result.astype(np.float32).reshape(a.shape)


def backend_identity():
    """Report the installed SDK and driver; a device ID alone proves neither."""
    qant, _ = _load_sdk()
    return {"sdk_version": qant.__version__, "driver_info": qant.info.get_driver_info()}


def run(output_directory):
    """Verify all 4/8-bit pairs and both full sorters through the pinned CPU SDK."""
    identity = backend_identity()
    if identity["sdk_version"] != "2.3.1" or not identity["driver_info"].startswith("cpu-backend;"):
        raise RuntimeError("This control requires the pinned official 2.3.1 CPU backend")
    if file_hash(ROOT / "data/inputs.npz") != INPUT_SHA256:
        raise ValueError("Unexpected input corpus")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty output directory")
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
                pair_count = api_calls = payload = 0
                # Bound the full-matrix temporary without changing trial order.
                batch_size = min(64, max(1, 1_000_000 // (n*n)))
                for start in range(0, len(data), batch_size):
                    batch = data[start:start+batch_size]
                    difference = SdkDifference(bits)
                    if name == "rank":
                        result = rank_sort(batch, difference, bias_step=2.**(-bits))
                    else:
                        result = bitonic_sort(batch, difference)
                    flags.append(reference_flags(batch, result))
                    indices.append(result[1])
                    c = difference.counts
                    pair_count += c.pair_differences
                    api_calls += c.api_calls
                    payload += c.feature_bytes + c.weight_bytes + c.output_bytes
                flags = np.concatenate(flags)
                indices = np.concatenate(indices).astype(np.int16)
                key = f"{dataset}_sdk_cpu_{name}"
                outcomes[key + "_flags"], outcomes[key + "_indices"] = flags, indices
                if not flags.all():
                    raise AssertionError("Noiseless SDK sort disagrees with stable argsort")
                m = n.bit_length() - 1
                expected = n*m*(m+1)//4 if name == "bitonic" else n*n
                if pair_count != len(data) * expected:
                    raise AssertionError("The SDK did not evaluate the required number of cells")
                rows.append(dict(
                    mapping=name, key_bits=bits, n=n, family=family, trials=len(data),
                    correct_sorts=int(flags[:, 1].sum()), stable_sorts=int(flags[:, 2].sum()),
                    pair_differences=pair_count, api_calls_batched_trials=api_calls,
                    logical_payload_bytes=payload, trial_batch_size=batch_size,
                ))
            print(f"{dataset}: SDK CPU verified", flush=True)

    write_csv(output / "accuracy.csv", rows)
    np.savez_compressed(output / "trial_outcomes.npz", **outcomes)
    metadata = dict(
        **identity, hardware_executed=False, added_noise=False, extra_quantizer=False,
        executions=sum(r["trials"] for r in rows), inputs_sha256=INPUT_SHA256,
        rank="N*N SDK differences including diagonal; host subtracts delta*U, thresholds >=0 and sums columns",
        scope="CPU software integration; no NPU timing, optical noise or measured bus traffic",
        source_sha256=before, outputs_sha256=file_hash(output / "trial_outcomes.npz"),
    )
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Verified {metadata['executions']:,} complete SDK CPU sorts.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/sdk_reproduced")
    args = parser.parse_args(argv)
    run(args.output_dir)


if __name__ == "__main__":
    main()
