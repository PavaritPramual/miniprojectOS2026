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
    normalized = os.path.abspath(path)
    if not normalized.startswith("\\\\?\\"):
        normalized = ("\\\\?\\UNC\\" + normalized[2:] if normalized.startswith("\\\\")
                      else "\\\\?\\" + normalized)
    low = _get_compressed_file_size(normalized, ctypes.byref(high))
    error = ctypes.get_last_error()

    # INVALID_FILE_SIZE can also be a valid low word; only the last-error
    # value distinguishes that case from an actual API failure.
    if low == 0xFFFFFFFF and error != 0:
        return None
    return (high.value << 32) | low


def allocation_error_message() -> str:
    """Describe the last allocation call on this thread, without guessing a size."""
    code = ctypes.get_last_error() if os.name == "nt" else 0
    reasons = {
        2: "ไฟล์ถูกลบหรือไม่พบไฟล์แล้ว",
        3: "ไม่พบตำแหน่งโฟลเดอร์แล้ว",
        5: "Windows ไม่อนุญาตให้อ่านข้อมูลพื้นที่ของไฟล์",
        32: "โปรแกรมอื่นเปิดไฟล์โดยไม่อนุญาตให้ใช้ร่วมกัน",
        33: "โปรแกรมอื่นล็อกไฟล์อยู่",
        206: "ตำแหน่งไฟล์ยาวเกินที่ Windows รองรับ",
        1920: "Windows เข้าถึงไฟล์นี้ไม่ได้ อาจเป็นรายการพิเศษหรือลิงก์ที่เปิดไม่ได้",
    }
    return reasons.get(code, "Windows อ่านพื้นที่บนดิสก์ไม่ได้") + (f" (Windows error {code})" if code else "")
