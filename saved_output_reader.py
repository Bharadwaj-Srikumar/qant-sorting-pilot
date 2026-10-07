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


class SavedOutputs:
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

    def __contains__(self, key):
        return key in self.arrays

    def __getitem__(self, key):
        return self.arrays[key]

    def close(self):
        if hasattr(self.arrays, "close"):
            self.arrays.close()
        self.handle.close()
