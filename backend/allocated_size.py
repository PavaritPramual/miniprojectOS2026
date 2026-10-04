"""Read the disk allocation reported by Windows for one file."""

import ctypes
import os
from ctypes import wintypes
from typing import Optional


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _get_compressed_file_size = _kernel32.GetCompressedFileSizeW
    _get_compressed_file_size.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    _get_compressed_file_size.restype = wintypes.DWORD
else:
    _kernel32 = None
    _get_compressed_file_size = None


def get_allocated_file_size(path: str) -> Optional[int]:
    """Return allocated bytes, or None if Windows cannot measure the file."""
    if _get_compressed_file_size is None:
        return None

    high = wintypes.DWORD()
    ctypes.set_last_error(0)
    low = _get_compressed_file_size(os.path.abspath(path), ctypes.byref(high))
    error = ctypes.get_last_error()

    # INVALID_FILE_SIZE can also be a valid low word; only the last-error
    # value distinguishes that case from an actual API failure.
    if low == 0xFFFFFFFF and error != 0:
        return None
    return (high.value << 32) | low
