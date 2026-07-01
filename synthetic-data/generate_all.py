"""
generate_all.py
===============
Regenerate all synthetic data (v1 CSV, v2 bills + CSV, combined dataset).

    cd synthetic-data/
    python3 generate_all.py
"""

import os
import subprocess
import sys

SRC = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    ("generate_final.py", "v1 validation CSV"),
    ("generate_v2_bills.py", "v2 bill JSON (evaluator + agent)"),
    ("generate_v2_csv.py", "v2 validation CSV"),
    ("merge_validation_datasets.py", "combined v1 + v2 CSV"),
]


def main():
    os.chdir(SRC)
    for script, label in STEPS:
        print(f"\n{'='*60}\n  Running {script} — {label}\n{'='*60}")
        result = subprocess.run([sys.executable, script], check=False)
        if result.returncode != 0:
            raise SystemExit(f"{script} failed with exit code {result.returncode}")
    print(f"\n{'='*60}\n  All generation steps complete.\n{'='*60}\n")


if __name__ == "__main__":
    main()
