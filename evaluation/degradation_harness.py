"""Photo-degradation testing harness (Professor Vo's parser-vs-gold
feedback, item 5 — "nice to have").

Rasterizes the line-item page of each of the 70 gold bill PDFs, generates
degraded variants at his exact specified levels, runs the existing,
UNCHANGED bill_parser OCR pipeline against each variant, and compares
extracted line items to the bill's own ground-truth JSON. This module
never modifies bill_parser.py or any production code path — it only
calls parse_bill_file() the same way the agent already does, on
synthetic degraded images.

Degradation variants, per Vo's literal spec:
    rotation: +2, +5, +10 degrees (one direction each — a symmetric
        operation, magnitude is what matters for OCR degradation)
    Gaussian blur: sigma 0.5, 1.0, 2.0
    JPEG quality: 90, 70, 50, 30
    combined: 5 degrees + blur sigma 1.0 + JPEG quality 50 (his named
        "realistic phone photo" variant)
    (11 variants total per bill, 70 bills = 770 runs)

Requires the agent-harness virtualenv (same as bill_parser itself) plus
the system `pdftoppm` binary (poppler) for PDF rasterization — chosen
over adding a new pip dependency (pdf2image/PyMuPDF) since poppler's
CLI tools were already present on this machine and this harness only
needs to run in a dev/CI environment, never in the production container.

    PYTHONPATH=agent-harness/src agent-harness/.venv/bin/python3 \\
        -m evaluation.degradation_harness --bills-dir synthetic-data/synthetic_bills_v2 \\
        --output evaluation/degradation_report.md
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_AGENT_HARNESS_SRC = Path(__file__).resolve().parents[1] / "agent-harness" / "src"
if str(_AGENT_HARNESS_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENT_HARNESS_SRC))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.tools.bill_parser import LowConfidenceOCRError, parse_bill_file  # noqa: E402

# NOTE on ceiling effect: recall is measured relative to each bill's own
# "clean" (undegraded) baseline, not an absolute 1.0. Bills with Revenue-
# code line items (e.g. "Revenue 0270") never reach 1.0 recall even on a
# perfect rasterization, because _extract_billing_codes doesn't recognize
# that code format at all — a pre-existing, unrelated gap in the code
# regex, not something OCR degradation or item 4's table-clustering work
# addresses. Confirmed live: bill_v2_selfpay_er_01's clean-variant recall
# is 0.75 (6/8), with the 2 "misses" being Revenue-coded items whose
# dollar amounts are actually parsed correctly — just not code-tagged.
# What matters for this harness is the trend as degradation increases
# relative to each bill's own clean baseline, not the absolute ceiling.

RASTER_DPI = 150
LINE_ITEMS_PAGE = 2  # confirmed: all 70 bills put the itemized table on page 2

AMOUNT_TOLERANCE = 0.01


@dataclass(frozen=True)
class DegradationVariant:
    name: str
    rotation_degrees: float = 0.0
    blur_sigma: float = 0.0
    jpeg_quality: int | None = None


VARIANTS: list[DegradationVariant] = [
    DegradationVariant("clean", ),
    DegradationVariant("rotation_2deg", rotation_degrees=2),
    DegradationVariant("rotation_5deg", rotation_degrees=5),
    DegradationVariant("rotation_10deg", rotation_degrees=10),
    DegradationVariant("blur_sigma_0.5", blur_sigma=0.5),
    DegradationVariant("blur_sigma_1.0", blur_sigma=1.0),
    DegradationVariant("blur_sigma_2.0", blur_sigma=2.0),
    DegradationVariant("jpeg_quality_90", jpeg_quality=90),
    DegradationVariant("jpeg_quality_70", jpeg_quality=70),
    DegradationVariant("jpeg_quality_50", jpeg_quality=50),
    DegradationVariant("jpeg_quality_30", jpeg_quality=30),
    DegradationVariant(
        "combined_realistic_phone_photo",
        rotation_degrees=5,
        blur_sigma=1.0,
        jpeg_quality=50,
    ),
]


def rasterize_line_items_page(pdf_path: Path, dpi: int = RASTER_DPI) -> Path:
    """Render the bill's line-items page (page 2) to a PNG via pdftoppm."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="degradation_raster_"))
    output_prefix = tmp_dir / "page"
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            str(dpi),
            "-png",
            "-f",
            str(LINE_ITEMS_PAGE),
            "-l",
            str(LINE_ITEMS_PAGE),
            str(pdf_path),
            str(output_prefix),
        ],
        check=True,
        capture_output=True,
    )
    rendered = tmp_dir / f"page-{LINE_ITEMS_PAGE}.png"
    if not rendered.exists():
        raise FileNotFoundError(f"pdftoppm did not produce expected output for {pdf_path}")
    return rendered


def apply_degradation(source_path: Path, variant: DegradationVariant, dest_path: Path) -> None:
    """Apply one degradation variant to a rasterized page image."""
    image = cv2.imread(str(source_path))
    if image is None:
        raise ValueError(f"Could not read image: {source_path}")

    if variant.rotation_degrees:
        height, width = image.shape[:2]
        center = (width / 2, height / 2)
        matrix = cv2.getRotationMatrix2D(center, variant.rotation_degrees, 1.0)
        image = cv2.warpAffine(
            image, matrix, (width, height),
            borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255),
        )

    if variant.blur_sigma:
        # kernel size derived from sigma, must be odd and positive
        kernel_size = max(3, int(2 * round(3 * variant.blur_sigma) + 1))
        image = cv2.GaussianBlur(image, (kernel_size, kernel_size), variant.blur_sigma)

    if variant.jpeg_quality is not None:
        success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, variant.jpeg_quality])
        if not success:
            raise ValueError(f"Failed to JPEG-encode variant {variant.name}")
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    cv2.imwrite(str(dest_path), image)


def _parsed_codes(item: dict[str, Any]) -> set[str]:
    """Parsed line items carry a list under 'billing_codes' (bill_parser's
    actual schema — confirmed live, not assumed), unlike gold's single
    'code' string."""
    return {str(c).strip().upper() for c in item.get("billing_codes") or []}


def _gold_code(item: dict[str, Any]) -> str | None:
    code = item.get("code")
    return str(code).strip().upper() if code else None


def compute_line_item_recall(
    parsed_line_items: list[dict[str, Any]], gold_line_items: list[dict[str, Any]]
) -> dict[str, Any]:
    """Field recall for one bill+variant: for each gold line item (matched
    by billing code), does a parsed line item carrying that code exist
    with an 'amount' within tolerance of gold's 'billed_amount'? This is
    deliberately narrow — it isolates whether OCR preserved the exact
    digits Vo's item 4 targets, not whether every cosmetic field matches.
    """
    parsed_by_code: dict[str, list[dict[str, Any]]] = {}
    for item in parsed_line_items:
        for code in _parsed_codes(item):
            parsed_by_code.setdefault(code, []).append(item)

    matched = 0
    amount_mismatches = 0
    missing_codes = 0
    for gold_item in gold_line_items:
        gold_key = _gold_code(gold_item)
        candidates = parsed_by_code.get(gold_key, []) if gold_key else []
        if not candidates:
            missing_codes += 1
            continue
        gold_amount = gold_item.get("billed_amount")
        found_amount_match = any(
            isinstance(candidate.get("amount"), (int, float))
            and gold_amount is not None
            and abs(candidate["amount"] - gold_amount) <= AMOUNT_TOLERANCE
            for candidate in candidates
        )
        if found_amount_match:
            matched += 1
        else:
            amount_mismatches += 1

    total = len(gold_line_items)
    return {
        "total_gold_items": total,
        "matched": matched,
        "missing_codes": missing_codes,
        "amount_mismatches": amount_mismatches,
        "recall": round(matched / total, 4) if total else None,
    }


@dataclass
class BillVariantResult:
    bill_name: str
    variant_name: str
    outcome: str  # "ok", "rejected_low_confidence", "error"
    recall: dict[str, Any] | None = None
    error_detail: str | None = None


@dataclass
class DegradationSummary:
    results: list[BillVariantResult] = field(default_factory=list)


def run_bill_through_variant(
    pdf_path: Path, gold_line_items: list[dict[str, Any]], variant: DegradationVariant
) -> BillVariantResult:
    work_dir = Path(tempfile.mkdtemp(prefix="degradation_variant_"))
    try:
        raster_path = rasterize_line_items_page(pdf_path)
        degraded_path = work_dir / f"{variant.name}.png"
        apply_degradation(raster_path, variant, degraded_path)

        try:
            parsed = parse_bill_file(str(degraded_path))
        except LowConfidenceOCRError as exc:
            return BillVariantResult(
                bill_name=pdf_path.stem, variant_name=variant.name,
                outcome="rejected_low_confidence", error_detail=str(exc),
            )

        recall = compute_line_item_recall(parsed.get("line_items", []), gold_line_items)
        return BillVariantResult(
            bill_name=pdf_path.stem, variant_name=variant.name,
            outcome="ok", recall=recall,
        )
    except Exception as exc:  # noqa: BLE001 - a single bad variant must not kill the sweep
        return BillVariantResult(
            bill_name=pdf_path.stem, variant_name=variant.name,
            outcome="error", error_detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_sweep(bills_dir: Path, variants: list[DegradationVariant] | None = None) -> DegradationSummary:
    variants = variants if variants is not None else VARIANTS
    summary = DegradationSummary()
    for pdf_path in sorted(bills_dir.glob("*.pdf")):
        json_path = pdf_path.with_suffix(".json")
        if not json_path.exists():
            continue
        with json_path.open(encoding="utf-8") as handle:
            gold = json.load(handle)
        gold_line_items = gold.get("summary_of_services", {}).get("line_items", [])
        if not gold_line_items:
            continue
        for variant in variants:
            summary.results.append(run_bill_through_variant(pdf_path, gold_line_items, variant))
    return summary


def format_report(summary: DegradationSummary) -> str:
    by_variant: dict[str, list[BillVariantResult]] = {}
    for result in summary.results:
        by_variant.setdefault(result.variant_name, []).append(result)

    lines = ["# Photo-degradation field recall\n"]
    lines.append("| Variant | Bills OK | Rejected (low confidence) | Errors | Avg line-item recall |")
    lines.append("|---|---|---|---|---|")
    variant_order = [v.name for v in VARIANTS]
    for variant_name in variant_order:
        results = by_variant.get(variant_name, [])
        ok = [r for r in results if r.outcome == "ok"]
        rejected = [r for r in results if r.outcome == "rejected_low_confidence"]
        errored = [r for r in results if r.outcome == "error"]
        recalls = [r.recall["recall"] for r in ok if r.recall and r.recall["recall"] is not None]
        avg_recall = round(sum(recalls) / len(recalls), 4) if recalls else None
        lines.append(
            f"| {variant_name} | {len(ok)} | {len(rejected)} | {len(errored)} | {avg_recall} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bills-dir", type=Path, default=Path("synthetic-data/synthetic_bills_v2"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--variant", action="append", help="Restrict to specific variant name(s)")
    args = parser.parse_args()

    variants = VARIANTS
    if args.variant:
        variants = [v for v in VARIANTS if v.name in args.variant]

    summary = run_sweep(args.bills_dir, variants=variants)
    report = format_report(summary)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote report to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
