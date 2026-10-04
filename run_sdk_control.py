"""Optional software-integration control using Q.ANT's official CPU backend.

This is separate from the Gaussian sweep: BF16 SDK arithmetic receives no
extra fixed-point quantizer or added noise. It verifies the API mapping only.
It is deliberately guarded against accidental execution on a hardware driver.
"""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from input_validation import validate_keys
from metrics import reference_flags
from sdk_mapping import SdkDifference, backend_identity
from sorting_schedules import bitonic_sort, rank_sort

ROOT = Path(__file__).resolve().parent


def main():
    identity = backend_identity()
    if identity["sdk_version"] != "2.3.1" or not identity["driver_info"].startswith("cpu-backend;"):
        raise RuntimeError("This control requires the pinned official 2.3.1 CPU backend")

    # Exhaustive pair checks cover all possible pairs in both key domains.
    for bits in (4, 8):
        a, b = np.meshgrid(np.arange(2**bits), np.arange(2**bits), indexing="ij")
        if not np.array_equal(SdkDifference(bits)(a, b), (a - b) / 2**bits):
            raise AssertionError("The CPU backend did not reproduce exact pair differences")

    output = ROOT / "results/sdk_reproduced"
    output.mkdir(parents=True, exist_ok=True)
    rows, outcomes = [], {}
    with np.load(ROOT / "data/inputs.npz") as corpus:
        with np.load(ROOT / "results/sdk_reference/trial_outcomes.npz") as reference:
            for dataset in corpus.files:
                bit_tag, n_tag, family = dataset.split("_", 2)
                bits, n = int(bit_tag[1:]), int(n_tag[1:])
                data = validate_keys(corpus[dataset], bits)
                for name, sort in (("bitonic", bitonic_sort), ("rank", rank_sort)):
                    flags, indices = [], []
                    pair_count = api_calls = payload = 0
                    for start in range(0, len(data), 64):
                        batch = data[start:start + 64]
                        difference = SdkDifference(bits)
                        result = sort(batch, difference)
                        flags.append(reference_flags(batch, result))
                        indices.append(result[1])
                        counts = difference.counts
                        pair_count += counts.pair_differences
                        api_calls += counts.api_calls
                        payload += counts.feature_bytes + counts.weight_bytes + counts.output_bytes
                    flags = np.concatenate(flags)
                    indices = np.concatenate(indices).astype(np.int16)
                    key = f"{dataset}_sdk_cpu_{name}"
                    for suffix, actual in (("_flags", flags), ("_indices", indices)):
                        if not np.array_equal(actual, reference[key + suffix]):
                            raise AssertionError(f"Changed SDK control result: {key + suffix}")
                        outcomes[key + suffix] = actual
                    if not flags.all():
                        raise AssertionError("A noiseless SDK control failed")
                    m = n.bit_length() - 1
                    expected = n * m * (m + 1) // 4 if name == "bitonic" else n * (n - 1) // 2
                    if pair_count != len(data) * expected:
                        raise AssertionError("SDK pair count differs from the algorithm")
                    rows.append(dict(
                        mapping=name, key_bits=bits, n=n, family=family,
                        trials=len(data), correct_sorts=int(flags[:, 1].sum()),
                        stable_sorts=int(flags[:, 2].sum()), pair_differences=pair_count,
                        api_calls_batched_trials=api_calls, logical_payload_bytes=payload,
                    ))
                print(f"{dataset}: SDK CPU verified", flush=True)

    with (output / "accuracy.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    np.savez_compressed(output / "trial_outcomes.npz", **outcomes)
    metadata = dict(
        **identity, hardware_executed=False, added_noise=False,
        executions=sum(row["trials"] for row in rows), matched_arrays=len(outcomes),
        inputs_sha256=hashlib.sha256((ROOT / "data/inputs.npz").read_bytes()).hexdigest(),
        source_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in ROOT.glob("*.py")},
        scope="Official CPU API control, not optical accuracy, throughput or power measurement.",
    )
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Verified {metadata['executions']:,} SDK CPU sorting executions.")


if __name__ == "__main__":
    main()
