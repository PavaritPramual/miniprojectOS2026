"""Run isolated backend checks; opt into WSL mocks and/or the compiled C scanner."""
import argparse
from datetime import datetime
import os
import ntpath
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wsl", action="store_true")
    parser.add_argument("--real-scanner-wsl-path", help="compiled C executable path inside Ubuntu; opts into real C HTTP checks")
    parser.add_argument("--drive", help="optional Windows drive root to scan and cancel (requires --real-scanner-wsl-path)")
    parser.add_argument("--output", default="docs/results/backend-tests.txt")
    args = parser.parse_args()
    if args.drive and not args.real_scanner_wsl_path:
        parser.error("--drive requires --real-scanner-wsl-path")
    if args.drive:
        drive, tail = ntpath.splitdrive(args.drive)
        if len(drive) != 2 or drive[1] != ":" or not drive[0].isalpha() or tail not in ("\\", "/"):
            parser.error("--drive must be a local Windows drive root, for example D:\\")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["CORESPACE_TEST_WSL"] = "1" if args.wsl else "0"
    env["CORESPACE_TEST_REAL_C"] = "1" if args.real_scanner_wsl_path else "0"
    env.pop("CORESPACE_TEST_DRIVE", None)
    if args.real_scanner_wsl_path:
        env["CORESPACE_SCANNER_WSL_PATH"] = args.real_scanner_wsl_path
        env["CORESPACE_WSL_DISTRO"] = "Ubuntu"
    if args.drive:
        env["CORESPACE_TEST_DRIVE"] = args.drive
    command = [sys.executable, "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-v"]
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    header = (f"Run: {datetime.now().astimezone().isoformat()}\nPython: {sys.version.split()[0]}\n"
              f"OS: {platform.platform()}\nWSL tests requested: {args.wsl}\n"
              f"Real C scanner requested: {args.real_scanner_wsl_path or 'no'}\n"
              f"Real drive cancellation requested: {args.drive or 'no'}\n"
              "tests.test_wsl uses controlled Python mocks; tests.test_real_scanner uses compiled C when opted in.\n"
              "Databases and fixtures are temporary; Explorer is mocked in API unit tests.\n\n")
    output = Path(args.output)
    if not output.is_absolute(): output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(header + result.stdout, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(result.stdout)
    print(f"Evidence: {output}")
    return result.returncode


if __name__ == "__main__": sys.exit(main())
