"""
merge_validation_datasets.py
============================
Combines v1 and v2 validation CSVs into a single combined dataset.

    cd synthetic-data/
    python3 merge_validation_datasets.py

Outputs: synthetic_validation_dataset_combined.csv (60 cases)
"""

import csv
import os

SRC = os.path.dirname(os.path.abspath(__file__))
V1_CSV = os.path.join(SRC, "synthetic_validation_dataset.csv")
V2_CSV = os.path.join(SRC, "synthetic_validation_dataset_v2.csv")
OUT_CSV = os.path.join(SRC, "synthetic_validation_dataset_combined.csv")


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


TARGET_V1_CASES = 45
TARGET_V2_CASES = 15
TARGET_COMBINED_CASES = 60


def main():
    fields_v1, rows_v1 = load_csv(V1_CSV)
    fields_v2, rows_v2 = load_csv(V2_CSV)

    if fields_v1 != fields_v2:
        raise SystemExit(
            "Column mismatch between v1 and v2 CSVs.\n"
            f"  v1 only: {set(fields_v1) - set(fields_v2)}\n"
            f"  v2 only: {set(fields_v2) - set(fields_v1)}"
        )

    v1_ids = {r["case_id"] for r in rows_v1}
    v2_ids = {r["case_id"] for r in rows_v2}
    overlap = v1_ids & v2_ids
    if overlap:
        raise SystemExit(f"Duplicate case_id(s): {sorted(overlap)}")

    combined = rows_v1 + rows_v2

    if len(rows_v1) + len(rows_v2) != TARGET_COMBINED_CASES:
        raise SystemExit(
            f"Expected {TARGET_COMBINED_CASES} combined cases "
            f"({len(rows_v1)} v1 + {len(rows_v2)} v2), got {len(combined)}"
        )
    if len(rows_v1) != TARGET_V1_CASES:
        raise SystemExit(f"Expected {TARGET_V1_CASES} v1 cases, got {len(rows_v1)}")
    if len(rows_v2) != TARGET_V2_CASES:
        raise SystemExit(f"Expected {TARGET_V2_CASES} v2 cases, got {len(rows_v2)}")

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields_v1)
        writer.writeheader()
        writer.writerows(combined)

    print(f"Combined dataset written: {OUT_CSV}")
    print(f"  v1 cases: {len(rows_v1)}")
    print(f"  v2 cases: {len(rows_v2)}")
    print(f"  total:    {len(combined)}  (target: {TARGET_COMBINED_CASES})")


if __name__ == "__main__":
    main()
