# Reading guide: inspect evidence without silently filling missing outputs.
# Normal NPZ reads use NumPy with pickle disabled. The optional recovery path
# walks local ZIP headers when the archive directory is missing or incomplete.
# Only complete, size-checked and CRC-checked .npy members are returned.
# The audit records where reading stopped; complete_archive=False remains false
# even if many useful members survived. Absence is not a failed sorting trial.
# This is a read-only adapter for known research archives, not a general ZIP
# repair utility; unsupported compression/flags and ambiguous evidence are rejected.

"""Read existing NPZ evidence, optionally salvaging complete ZIP members.

The source is never modified. Salvage requires local-header sizes and CRC32;
missing members are never synthesized. This supports NumPy's seekable ZIP/ZIP64
writer, not arbitrary encrypted archives or data-descriptor ZIP streams.
"""

import io
from pathlib import Path
import struct
import zipfile
import zlib
import numpy as np


# Input archive path; return (dict of recovered NumPy arrays, audit dict).
# Walk consecutive local headers, including ZIP64 size extensions, and stop at
# the first incomplete header/member. Never search arbitrary later byte patterns
# for something that merely resembles a recoverable array.
# Reject encryption/data descriptors, unsupported methods, malformed sizes,
# incomplete deflate streams, CRC errors, duplicate names and unexpected paths.
# Every array uses allow_pickle=False and remains in memory; the source bytes
# are never changed. The audit always marks this recovery as an incomplete archive.
def recover_members(path):
    raw = Path(path).read_bytes()
    offset, arrays = 0, {}
    stop_reason = "end_of_file_without_central_directory"
    while offset < len(raw):
        if offset + 30 > len(raw) or raw[offset:offset+4] != b"PK\x03\x04":
            stop_reason = "incomplete_or_missing_local_header"
            break
        (_, version, flags, method, mtime, mdate, crc, compressed, size,
         name_len, extra_len) = struct.unpack_from("<IHHHHHIIIHH", raw, offset)
        header_end = offset + 30 + name_len + extra_len
        if header_end > len(raw):
            stop_reason = "incomplete_local_header"
            break
        name = raw[offset+30:offset+30+name_len].decode("utf-8")
        if flags & (1 | 8) or method not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError("Unsupported ZIP flags/compression; refuse ambiguous salvage")
        # ZIP64 stores large/unknown legacy size fields in an extra record. Interpret
        # that record before locating payload end; guessing size from the next header
        # would risk accepting partial or unrelated bytes.
        extra = raw[offset+30+name_len:header_end]
        cursor = 0
        while cursor + 4 <= len(extra):
            kind, length = struct.unpack_from("<HH", extra, cursor)
            field = extra[cursor+4:cursor+4+length]
            if len(field) != length:
                raise ValueError("Truncated ZIP extra field")
            cursor += 4 + length
            if kind == 1:
                if len(field) % 8:
                    raise ValueError("Malformed ZIP64 size field")
                values = iter(struct.unpack("<"+"Q"*(len(field)//8), field))
                if size == 0xffffffff:
                    size = next(values)
                if compressed == 0xffffffff:
                    compressed = next(values)
        end = header_end + compressed
        if end > len(raw):
            stop_reason = "incomplete_member:" + name
            break
        payload = raw[header_end:end]
        if method == zipfile.ZIP_DEFLATED:
            decoder = zlib.decompressobj(-15)
            payload = decoder.decompress(payload) + decoder.flush()
            if not decoder.eof or decoder.unused_data:
                raise ValueError("Incomplete or ambiguous compressed member")
        # Both decompressed byte length and CRC must match BEFORE NumPy parses an
        # array. A syntactically readable array alone is not sufficient evidence that
        # its contents survived truncation or corruption unchanged.
        if len(payload) != size or zlib.crc32(payload) & 0xffffffff != crc:
            raise ValueError("Size/CRC mismatch: " + name)
        if not name.endswith(".npy") or "/" in name or "\\" in name:
            raise ValueError("Unexpected NPZ member name")
        key = name[:-4]
        if key in arrays:
            raise ValueError("Duplicate evidence member")
        arrays[key] = np.load(io.BytesIO(payload), allow_pickle=False)
        offset = end
    return arrays, dict(mode="local_headers_crc_verified", complete_archive=False,
                        complete_members=len(arrays), source_bytes=len(raw),
                        consumed_bytes=offset, stop_reason=stop_reason)


# Read-only mapping-like adapter over a complete NPZ or recovered member dict.
# Use membership tests before access when evidence may be incomplete. Missing
# keys remain missing; this adapter never synthesizes flags or permutations.
# Call close after use to release the underlying file/NumPy ZIP handle.
class SavedOutputs:
    # Open the source and try normal pickle-free NumPy loading first.
    # Only a BadZipFile may trigger the explicitly allowed recovery path; other
    # exceptions close the handle and propagate. Store audit information alongside
    # the array mapping so callers cannot silently treat salvaged data as complete.
    def __init__(self, path, allow_incomplete=False):
        self.path = Path(path)
        self.handle = self.path.open("rb")
        try:
            self.arrays = np.load(self.handle, allow_pickle=False)
            self.audit = dict(mode="normal_npz", complete_archive=True,
                              complete_members=len(self.arrays.files))
        except zipfile.BadZipFile:
            self.handle.close()
            if not allow_incomplete:
                raise ValueError(f"Incomplete archive: {path}; use --allow-incomplete to audit recoverable members")
            self.arrays, self.audit = recover_members(path)
        except Exception:
            self.handle.close()
            raise

    # Answer whether a named array actually exists in the loaded evidence.
    # For partial archives this allows the caller to distinguish missing indices
    # from present flags instead of confusing missing evidence with failed sorting.
    def __contains__(self, key):
        return key in self.arrays

    # Return the requested saved array. Normal NPZ may decompress lazily;
    # recovered archives return the verified in-memory array. Missing keys raise
    # through the underlying mapping rather than returning a fabricated default.
    def __getitem__(self, key):
        return self.arrays[key]

    # Close the NumPy archive if it has a close method, then close the file handle.
    # The recovered dict has no resource method; its original handle was already
    # closed during fallback. Closing does not modify the source archive.
    def close(self):
        if hasattr(self.arrays, "close"):
            self.arrays.close()
        self.handle.close()
