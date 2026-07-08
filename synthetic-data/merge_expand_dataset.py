"""Merge expanded v2 bills + 24 new v1 text cases into master validation CSV."""

import csv
import os

SRC = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(SRC, "synthetic_validation_dataset.csv")
V1_NEW = os.path.join(SRC, "synthetic_validation_dataset_v1_new24.csv")
V2_NEW = os.path.join(SRC, "synthetic_validation_dataset_v2_31_70.csv")

# Remove 12 v1 cases superseded by v2 coverage to reach 100 total (72 - 12 + 24 + 40 = 124)
# Target 100: remove 24 more — instead remove 36 total to hit 100 with 30 v1 + 70 v2
REMOVE = {
    "BILL-006", "BILL-009", "BILL-010", "BILL-013",  # covered by v2
    "ACT-001", "FA-005",  # collections / medi-cal covered
    "DOC-001", "DOC-004",  # edge doc parsing retained elsewhere
    "BILL-011", "BILL-012",  # generic code explainers
    "SAF-006", "ACT-005",  # low-priority duplicates
    # additional 12 to reach 100 total after +64 new rows
    "BILL-001", "BILL-002", "BILL-003", "BILL-004",
    "BILL-005", "BILL-007", "BILL-008",
    "DOC-002", "DOC-003", "DOC-005",
    "ACT-002", "ACT-003",
    "FA-001", "FA-002", "FA-003",
    "SAF-001", "SAF-002", "SAF-003",
    "ACT-004",
}

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def main():
    rows = read_csv(MASTER)
    v1_new = read_csv(V1_NEW)
    v2_new = read_csv(V2_NEW)
    fields = rows[0].keys()

    kept = [r for r in rows if r["case_id"] not in REMOVE]
    removed = len(rows) - len(kept)
    merged = kept + v1_new + v2_new

    # Trim to exactly 100 if over (keep all v2 + v1_new first)
    if len(merged) > 100:
        # prioritize: all v2 (70) + all v1_new (24) + fill from kept v1 up to 100
        v2_all = [r for r in merged if r["case_id"].startswith("DV2")]
        v1_all = [r for r in merged if not r["case_id"].startswith("DV2")]
        v1_new_ids = {r["case_id"] for r in v1_new}
        v1_new_rows = [r for r in v1_all if r["case_id"] in v1_new_ids]
        v1_old = [r for r in v1_all if r["case_id"] not in v1_new_ids]
        slots = 100 - len(v2_all) - len(v1_new_rows)
        merged = v2_all + v1_new_rows + v1_old[:max(0, slots)]

    with open(MASTER, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(merged)

    v2_count = sum(1 for r in merged if r["case_id"].startswith("DV2"))
    bills = sum(1 for r in merged if r.get("bill_doc_file", "N/A") != "N/A")
    print(f"Removed {removed} superseded v1 cases")
    print(f"Added {len(v1_new)} v1 text + {len(v2_new)} v2 document cases")
    print(f"Master CSV: {len(merged)} total rows, {v2_count} DV2, {bills} with bills")

if __name__ == "__main__":
    main()
