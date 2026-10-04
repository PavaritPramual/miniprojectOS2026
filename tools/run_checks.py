"""Run isolated backend tests and save evidence; --wsl opts into Ubuntu mock processes."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wsl", action="store_true")
    parser.add_argument("--output", default="docs/results/backend-tests.txt")
    args = parser.parse_args()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["CORESPACE_TEST_WSL"] = "1" if args.wsl else "0"
    command = [sys.executable, "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-v"]
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    header = (f"Run: {datetime.now().astimezone().isoformat()}\nPython: {sys.version.split()[0]}\n"
              f"OS: {platform.platform()}\nWSL tests requested: {args.wsl}\n"
              "WSL executable is a controlled Python mock, not the group's C scanner.\n"
              "Databases and process scripts are temporary; Explorer is mocked.\n\n")
    output = Path(args.output)
    if not output.is_absolute(): output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(header + result.stdout, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(result.stdout)
    print(f"Evidence: {output}")
    return result.returncode


if __name__ == "__main__": sys.exit(main())
