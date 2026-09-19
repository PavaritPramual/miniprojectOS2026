"""
OS Storage Mechanics and File System Metrics Module
Responsible for Student 2: Pawarit Pramuan

Key OS Concepts Implemented:
1. Logical File Size (EOF) vs Physical Allocation Size on Disk (Clusters).
2. Internal Fragmentation and Slack Space Calculation.
3. NTFS Resident File Detection (Files <= 600-700B reside directly in MFT 1024B record).
4. Circular Loop & Reparse Point Safety (Junctions / Symlinks).
"""

import math
from typing import Tuple

def calculate_physical_and_slack(logical_size: int, cluster_size: int = 4096) -> Tuple[int, int]:
    """
    Computes (physical_size, slack_space) according to OS Cluster Allocation rules.
    
    OS Rule:
    - Empty file (0 bytes): 0 physical bytes, 0 slack.
    - NTFS Resident File (<= 600 bytes): Stored directly inside the 1,024-byte MFT record.
      No external clusters are allocated on the disk volume.
      Hence, physical cluster allocation = 0 bytes!
    - Non-resident File (> 600 bytes):
      Allocated in whole cluster units (e.g. 4,096 bytes).
      physical_size = ceil(logical_size / cluster_size) * cluster_size
      slack_space = physical_size - logical_size
    """
    if logical_size == 0:
        return 0, 0

    # Resident file optimization on NTFS
    if logical_size <= 600:
        # Resident in MFT record, takes 0 external cluster bytes
        return 0, 0

    # Non-resident files allocated in cluster blocks
    num_clusters = math.ceil(logical_size / cluster_size)
    physical_size = num_clusters * cluster_size
    slack_space = physical_size - logical_size

    return physical_size, slack_space


def format_bytes(byte_count: int) -> str:
    """Formats bytes into human-readable string (B, KB, MB, GB, TB)."""
    if byte_count < 0:
        return "0 B"
    if byte_count < 1024:
        return f"{byte_count} B"
    elif byte_count < 1024**2:
        return f"{byte_count / 1024:.2f} KB"
    elif byte_count < 1024**3:
        return f"{byte_count / (1024**2):.2f} MB"
    elif byte_count < 1024**4:
        return f"{byte_count / (1024**3):.2f} GB"
    else:
        return f"{byte_count / (1024**4):.2f} TB"


def get_file_category(extension: str) -> str:
    """Categorizes file by extension into major groups for visualization."""
    ext = extension.lower().strip(".")
    
    categories = {
        "Media (Video/Audio)": {
            "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm",
            "mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"
        },
        "Images": {
            "jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "tiff", "ico", "psd", "raw"
        },
        "Documents & Books": {
            "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "txt", "md", "csv", "epub"
        },
        "Archives & Disk Images": {
            "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "img", "vhd", "vhdx"
        },
        "Code & Development": {
            "py", "js", "ts", "html", "css", "cpp", "c", "h", "hpp", "java", "cs", "go",
            "rs", "php", "json", "yaml", "yml", "xml", "sql", "sh", "bat", "ps1"
        },
        "Executables & Binaries": {
            "exe", "dll", "msi", "sys", "bin", "so", "dylib", "com"
        }
    }

    for cat_name, ext_set in categories.items():
        if ext in ext_set:
            return cat_name

    return "Others"
