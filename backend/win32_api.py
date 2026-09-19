"""
Win32 Low-Level API Wrapper for High-Performance File System Operations
Module for Student 1: Saran Papornchai & Student 2: Pawarit Pramuan

Demonstrates OS Concepts:
- Direct Win32 C-API calls via ctypes (releases Python GIL during I/O)
- FindFirstFileExW with FIND_FIRST_EX_LARGE_FETCH (64KB kernel buffer)
- FindExInfoBasic to bypass DOS 8.3 short name lookup
- GetDiskFreeSpaceW for exact Cluster / Allocation Unit geometry
- Reparse Point detection (Junctions, Symlinks) to prevent infinite loops
"""

import ctypes
from ctypes import wintypes
import os
import sys

# Win32 Constants
MAX_PATH = 260
FILE_ATTRIBUTE_READONLY = 0x00000001
FILE_ATTRIBUTE_HIDDEN = 0x00000002
FILE_ATTRIBUTE_SYSTEM = 0x00000004
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_ARCHIVE = 0x00000020
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400  # Reparse point (Junction / Symlink)

# FINDEX_INFO_LEVELS
FindExInfoStandard = 0
FindExInfoBasic = 1  # Skips 8.3 short name querying for faster traversal

# FINDEX_SEARCH_OPS
FindExSearchNameMatch = 0
FindExSearchLimitToDirectories = 1

# Additional Flags for FindFirstFileExW
FIND_FIRST_EX_CASE_SENSITIVE = 1
FIND_FIRST_EX_LARGE_FETCH = 2  # Uses a larger 64KB internal search buffer in the kernel

# Reparse Tags
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # Junction
IO_REPARSE_TAG_SYMLINK = 0xA000000C      # Symbolic link

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]

class WIN32_FIND_DATAW(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", FILETIME),
        ("ftLastAccessTime", FILETIME),
        ("ftLastWriteTime", FILETIME),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("dwReserved0", wintypes.DWORD),  # Reparse tag when FILE_ATTRIBUTE_REPARSE_POINT
        ("dwReserved1", wintypes.DWORD),
        ("cFileName", wintypes.WCHAR * MAX_PATH),
        ("cAlternateFileName", wintypes.WCHAR * 14),
    ]

# Setup kernel32 bindings
if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _FindFirstFileExW = kernel32.FindFirstFileExW
    _FindFirstFileExW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.INT,
        ctypes.c_void_p,
        wintypes.INT,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _FindFirstFileExW.restype = wintypes.HANDLE

    _FindNextFileW = kernel32.FindNextFileW
    _FindNextFileW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    _FindNextFileW.restype = wintypes.BOOL

    _FindClose = kernel32.FindClose
    _FindClose.argtypes = [wintypes.HANDLE]
    _FindClose.restype = wintypes.BOOL

    _GetDiskFreeSpaceW = kernel32.GetDiskFreeSpaceW
    _GetDiskFreeSpaceW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    _GetDiskFreeSpaceW.restype = wintypes.BOOL

    _GetLogicalDriveStringsW = kernel32.GetLogicalDriveStringsW
    _GetLogicalDriveStringsW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    _GetLogicalDriveStringsW.restype = wintypes.DWORD

    _GetDriveTypeW = kernel32.GetDriveTypeW
    _GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _GetDriveTypeW.restype = wintypes.UINT
else:
    kernel32 = None


def get_cluster_size(path: str) -> int:
    """
    Retrieves the exact cluster / allocation unit size (in bytes) for the volume hosting `path`.
    Uses GetDiskFreeSpaceW. Standard NTFS default is 4,096 bytes (4 KB).
    """
    if not kernel32:
        return 4096

    # Extract drive root (e.g., 'C:\\')
    drive_root = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive_root.endswith("\\"):
        drive_root += "\\"

    sectors_per_cluster = wintypes.DWORD()
    bytes_per_sector = wintypes.DWORD()
    free_clusters = wintypes.DWORD()
    total_clusters = wintypes.DWORD()

    success = _GetDiskFreeSpaceW(
        drive_root,
        ctypes.byref(sectors_per_cluster),
        ctypes.byref(bytes_per_sector),
        ctypes.byref(free_clusters),
        ctypes.byref(total_clusters),
    )

    if success:
        return sectors_per_cluster.value * bytes_per_sector.value
    return 4096


def get_system_drives() -> list[dict]:
    """
    Enumerates all logical drives and their capacity and free space.
    """
    drives = []
    if not kernel32:
        return drives

    buffer_len = 512
    buf = ctypes.create_unicode_buffer(buffer_len)
    result = _GetLogicalDriveStringsW(buffer_len, buf)

    if result == 0:
        return drives

    raw_str = buf[:result]
    drive_letters = [d for d in raw_str.split("\x00") if d]


    for d in drive_letters:
        drive_type = _GetDriveTypeW(d)
        # DRIVE_FIXED = 3, DRIVE_REMOVABLE = 2, DRIVE_REMOTE = 4, DRIVE_CDROM = 5, DRIVE_RAMDISK = 6
        type_str = "Fixed (HDD/SSD)" if drive_type == 3 else ("Removable" if drive_type == 2 else "Other")

        cluster_size = get_cluster_size(d)

        # Get total and free space using standard shutil or ctypes
        try:
            free_bytes_available = ctypes.c_ulonglong()
            total_number_of_bytes = ctypes.c_ulonglong()
            total_number_of_free_bytes = ctypes.c_ulonglong()

            if kernel32.GetDiskFreeSpaceExW(
                d,
                ctypes.byref(free_bytes_available),
                ctypes.byref(total_number_of_bytes),
                ctypes.byref(total_number_of_free_bytes),
            ):
                total_bytes = total_number_of_bytes.value
                free_bytes = total_number_of_free_bytes.value
                used_bytes = total_bytes - free_bytes
            else:
                total_bytes, used_bytes, free_bytes = 0, 0, 0
        except Exception:
            total_bytes, used_bytes, free_bytes = 0, 0, 0

        drives.append({
            "path": d,
            "type": type_str,
            "drive_type_code": drive_type,
            "cluster_size": cluster_size,
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "free_bytes": free_bytes,
            "percent_used": round((used_bytes / total_bytes * 100), 1) if total_bytes > 0 else 0
        })

    return drives


def fast_scan_directory(dir_path: str):
    """
    Generator yielding (name, is_dir, is_reparse, size_bytes) using
    FindFirstFileExW with FIND_FIRST_EX_LARGE_FETCH and FindExInfoBasic.
    
    Significantly faster than os.listdir because:
    1. Bypasses short 8.3 filename retrieval (FindExInfoBasic).
    2. Utilizes 64KB kernel search buffer (FIND_FIRST_EX_LARGE_FETCH).
    3. Lowers Ring 3 -> Ring 0 context switches.
    """
    if not kernel32:
        # Fallback to os.scandir if not on windows
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        is_reparse = entry.is_symlink()
                        size = entry.stat(follow_symlinks=False).st_size if not is_dir else 0
                        yield (entry.name, is_dir, is_reparse, size)
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            return
        return

    # Windows extended path prefix support for long paths (> 260 chars)
    normalized = os.path.abspath(dir_path)
    if not normalized.startswith("\\\\?\\"):
        if normalized.startswith("\\\\"):
            search_pattern = "\\\\?\\UNC\\" + normalized[2:] + "\\*"
        else:
            search_pattern = "\\\\?\\" + normalized + "\\*"
    else:
        search_pattern = normalized + "\\*"

    find_data = WIN32_FIND_DATAW()
    handle = _FindFirstFileExW(
        search_pattern,
        FindExInfoBasic,
        ctypes.byref(find_data),
        FindExSearchNameMatch,
        None,
        FIND_FIRST_EX_LARGE_FETCH,
    )

    if handle == INVALID_HANDLE_VALUE:
        return

    try:
        while True:
            name = find_data.cFileName
            if name != "." and name != "..":
                attrs = find_data.dwFileAttributes
                is_dir = bool(attrs & FILE_ATTRIBUTE_DIRECTORY)
                is_reparse = bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
                file_size = (find_data.nFileSizeHigh << 32) | find_data.nFileSizeLow
                yield (name, is_dir, is_reparse, file_size)

            if not _FindNextFileW(handle, ctypes.byref(find_data)):
                break
    finally:
        _FindClose(handle)
