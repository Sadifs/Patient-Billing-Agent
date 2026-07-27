import json
import unittest
from pathlib import Path

from app.tools.bill_parser import (
    ACCOUNT_NUMBER_PATTERN,
    GUARANTOR_NAME_PATTERN,
    GUARANTOR_NUMBER_PATTERN,
    PATIENT_NAME_PATTERN,
    PAY_BY_PHONE_PATTERN,
    PAY_ONLINE_PATTERN,
    SERVICE_DATE_PATTERN,
    TOTAL_DUE_PATTERN,
    LowConfidenceOCRError,
    _bill_flags,
    _build_provenance,
    _extract_bill_header_fields,
    _extract_guarantor_info,
    _extract_insurance_by_line_clustering,
    _extract_insurance_info,
    _line_item_duplicate_signals,
    _line_item_total,
    _looks_like_id,
    _math_consistency_check,
    _parse_amount,
    _parse_line_items_from_tables,
    _suggested_next_steps,
    bill_parser,
    parse_bill_file,
    parse_bill_pdf,
)

TESTDATA_DIR = Path(__file__).resolve().parent.parent / "testdata"


SAMPLE_BILL_TEXT = """
Cedars-Sinai Statement of Hospital and Physician Services
Cedars-Sinai Medical Center
Statement Date: 2026-04-01
Maria Gutierrez A l Pay Online: cedars-sinai.org/billing
l Pay by Phone: 866-803-1777
Account #: CS-2026-00441
Service Date: 2026-03-15
Primary Insurance: None on file P.O. Box 48750, Los Angeles, CA 90048
Secondary Insurance: None on file
Guarantor Name: Maria Gutierrez
Totals $19,000.00 $0.00 $0.00 $19,000.00
Total Amount Due: $19,000.00
Due Date: 2026-05-01 | Questions? Call 866-803-1777
For account information or to discuss financial assistance, call 866-803-1777,
Monday–Friday, 8:00 AM – 4:30 PM PT, or email patient.billing@cshs.org.
Patient: Maria Gutierrez Account #: CS-2026-00441 Service Date: 2026-03-15
Cedars-Sinai Medical Center, P.O. Box 48750, Los Angeles, CA 90048
"""


class ParseAmountTest(unittest.TestCase):
    def test_parses_parenthesized_amount_with_internal_spacing(self):
        """Real table cells from pdfplumber render credits as
        "( $9,120.00 )", not "($9,120.00)" — the space right inside the
        parens must not break negative-number parsing."""
        self.assertEqual(_parse_amount("( $9,120.00 )"), -9120.0)

    def test_parses_parenthesized_amount_without_internal_spacing(self):
        self.assertEqual(_parse_amount("($9,120.00)"), -9120.0)

    def test_parses_plain_positive_amount(self):
        self.assertEqual(_parse_amount("$600.00"), 600.0)


class BillParserHelperTest(unittest.TestCase):
    def test_extract_bill_header_fields(self):
        fields = _extract_bill_header_fields(SAMPLE_BILL_TEXT)

        self.assertEqual(fields["patient"]["patient_name"], "Maria Gutierrez")
        self.assertEqual(fields["patient"]["patient_account_number"], "CS-2026-00441")
        self.assertEqual(fields["patient"]["service_date"], "03/15/2026")
        self.assertEqual(fields["guarantor"]["guarantor_name"], "Maria Gutierrez")
        self.assertEqual(fields["insurance"]["primary"], "None on file")
        self.assertEqual(fields["insurance"]["secondary"], "None on file")
        self.assertEqual(fields["contact_info"]["phone"], "866-803-1777")
        self.assertEqual(fields["contact_info"]["online"], "cedars-sinai.org/billing")
        self.assertEqual(fields["contact_info"]["email"], "patient.billing@cshs.org")
        self.assertIn("Monday", fields["contact_info"]["hours"])
        self.assertIn("48750", fields["contact_info"]["mail"])
        self.assertEqual(fields["statement_date"], "04/01/2026")
        self.assertEqual(fields["due_date"], "05/01/2026")
        self.assertEqual(fields["facility_name"], "Cedars-Sinai Medical Center")
        self.assertEqual(fields["total_billed"], 19000.0)
        self.assertEqual(fields["total_insurance_payments"], 0.0)
        self.assertEqual(fields["total_adjustments"], 0.0)
        self.assertEqual(fields["outstanding_balance"], 19000.0)
        self.assertEqual(fields["patient_balance"], 19000.0)
        self.assertEqual(fields["total_amount_due"], 19000.0)

    def test_extract_bill_header_fields_insured_patient(self):
        text = """
David Chen A l Pay Online: cedars-sinai.org/billing
Account #: CS-2026-01154
Service Date: 2026-03-22
Primary Insurance: Anthem Blue Cross PPO P.O. Box 48750, Los Angeles, CA 90048
Secondary Insurance: None on file
Patient: David Chen Account #: CS-2026-01154 Service Date: 2026-03-22
Pay by Phone: 866-803-1777
"""
        fields = _extract_bill_header_fields(text)

        self.assertEqual(fields["patient"]["patient_name"], "David Chen")
        self.assertEqual(fields["patient"]["service_date"], "03/22/2026")
        self.assertEqual(fields["insurance"]["primary"], "Anthem Blue Cross PPO")
        self.assertEqual(fields["insurance"]["secondary"], "None on file")

    def test_parse_bill_pdf_includes_header_fields(self):
        result = parse_bill_pdf(
            "../synthetic-data/synthetic_bills_v2/bill_v2_selfpay_er_01.pdf"
        )

        self.assertEqual(result["patient"]["patient_name"], "Maria Gutierrez")
        self.assertEqual(result["patient"]["service_date"], "03/15/2026")
        self.assertEqual(result["insurance"]["primary"], "None on file")
        self.assertEqual(result["contact_info"]["phone"], "866-803-1777")
        self.assertEqual(result["facility_name"], "Cedars-Sinai Medical Center")
        self.assertEqual(result["statement_date"], "04/01/2026")
        self.assertEqual(result["due_date"], "05/01/2026")
        self.assertEqual(result["total_amount_due"], 19000.0)
        self.assertTrue(result["math_consistency"]["checked"])

    def test_parse_bill_pdf_includes_bill_level_totals(self):
        result = parse_bill_pdf(
            "../synthetic-data/synthetic_bills_v2/bill_v2_air_ambulance_transfer_44.pdf"
        )

        self.assertEqual(result["total_billed"], 31200.0)
        self.assertEqual(result["total_insurance_payments"], 9360.0)
        self.assertEqual(result["total_adjustments"], 0.0)
        self.assertEqual(result["outstanding_balance"], 21840.0)
        self.assertEqual(result["patient_balance"], 21840.0)
        self.assertEqual(result["total_amount_due"], 21840.0)
        self.assertEqual(result["statement_date"], "06/15/2026")
        self.assertEqual(result["due_date"], "07/15/2026")
        self.assertTrue(result["math_consistency"]["checked"])
        self.assertTrue(result["math_consistency"]["consistent"])
        self.assertEqual(result["math_consistency"]["summed_billed"], 31200.0)
        self.assertEqual(result["math_consistency"]["summed_patient_balance"], 21840.0)

    def test_parse_bill_pdf_handles_parenthesized_payment_plan_credit(self):
        """Regression test: bill_v2_selfpay_payment_plan_25 has a "Less:
        Payments Received" line item with a parenthesized negative amount,
        e.g. "( $9,120.00 )". _parse_amount previously stripped "$"/","
        but never the parens themselves, so float("( 9120.00 )") raised
        and the whole credit line silently parsed as None instead of
        -9120.0 — dropping the credit from sums entirely rather than
        subtracting it, which overcounted total_billed by exactly the
        credit amount ($77,520 summed vs the bill's real $68,400 total)."""
        result = parse_bill_pdf(
            "../synthetic-data/synthetic_bills_v2/bill_v2_selfpay_payment_plan_25.pdf"
        )

        self.assertEqual(result["total_amount_due"], 68400.0)
        self.assertTrue(result["math_consistency"]["checked"])
        self.assertTrue(result["math_consistency"]["consistent"])
        self.assertEqual(result["math_consistency"]["summed_billed"], 68400.0)

    def test_parse_bill_pdf_preserves_distinct_outstanding_and_patient_balance(self):
        """Regression test: bill_v2_intentionally_incorrect_math_13 is
        deliberately built so outstanding_balance (260.0, mathematically
        correct) differs from patient_balance/total_amount_due (960.0,
        the intentional error) — every other bill in the corpus has these
        equal. The summary "Totals" line correctly gives both as distinct
        values, but a later itemized "Totals" line (4 columns: billed/
        ins pmts/adj/patient bal) has no separate slot for outstanding
        balance, so _extract_bill_totals defaulted it to equal
        patient_balance — silently overwriting the real 260.0 with 960.0
        for this one bill. Fixed by letting a 3-amount line's distinct
        outstanding_balance take precedence over that default."""
        result = parse_bill_pdf(
            "../synthetic-data/synthetic_bills_v2/bill_v2_intentionally_incorrect_math_13.pdf"
        )

        self.assertEqual(result["outstanding_balance"], 260.0)
        self.assertEqual(result["patient_balance"], 960.0)
        self.assertFalse(result["math_consistency"]["consistent"])

    def test_parse_bill_pdf_fills_self_pay_zero_insurance_and_adjustments(self):
        """Regression test: self-pay bills render the itemized "Totals"
        line's "Ins Pmts" column as an em dash ("—") instead of "$0.00"
        since there's no insurance. _amounts_from_cell only recognizes
        real dollar-amount text, so the dash was silently skipped —
        collapsing what should be a 4-column line (billed/0/adjustments/
        patient_balance) down to 3 numeric matches, which then got
        misread as (billed, outstanding_balance, patient_balance),
        losing total_insurance_payments and total_adjustments entirely
        (both stayed None instead of their real values, 0.0 and
        $11,480.00 respectively for this bill)."""
        result = parse_bill_pdf(
            "../synthetic-data/synthetic_bills_v2/bill_v2_charity_partial_writeoff_68.pdf"
        )

        self.assertEqual(result["total_insurance_payments"], 0.0)
        self.assertEqual(result["total_adjustments"], 11480.0)

    def test_parse_bill_pdf_cleans_merged_insurance_address_noise(self):
        result = parse_bill_pdf(
            "../synthetic-data/synthetic_bills_v2/bill_v2_pediatric_er_appendectomy_29.pdf"
        )

        self.assertEqual(result["patient"]["patient_name"], "Emily Chen (minor)")
        self.assertEqual(
            result["guarantor"]["guarantor_name"],
            "David Chen (parent/guardian)",
        )
        self.assertEqual(
            result["guarantor"]["guarantor_account_number"],
            "GU-2026-09540",
        )
        self.assertEqual(
            result["insurance"]["primary"],
            "Anthem Blue Cross – PPO (parent employer-sponsored)",
        )
        self.assertNotIn("Pre.Od", result["insurance"]["primary"])
        self.assertNotIn("Box 48750", result["insurance"]["primary"])

    def test_flags_self_pay_collections_bill(self):
        line_items = [
            {"description": "Emergency Department", "amount": 4200.0},
            {"description": "Collections Fee (Agency Assessment)", "amount": 1260.0},
        ]

        flags = _bill_flags("Primary Insurance: None on file", line_items)

        self.assertTrue(flags["no_insurance_or_self_pay_signal"])
        self.assertTrue(flags["collections_signal"])
        self.assertTrue(flags["collections_fee_signal"])
        steps = _suggested_next_steps(flags)
        self.assertTrue(any("866-803-1777" in step for step in steps))
        self.assertTrue(any("pause collection activity" in step for step in steps))
        self.assertTrue(any("collections fee" in step for step in steps))

    def test_secondary_none_on_file_does_not_trigger_self_pay(self):
        line_items = [
            {"description": "Rheumatology Visit", "amount": 420.0},
            {"description": "Joint Injection", "amount": 680.0},
            {"description": "Pharmacy", "amount": 180.0},
        ]
        bill_text = (
            "Primary Insurance: CHAMPVA (VA family coverage)\n"
            "Secondary Insurance: None on file\n"
            "Total Insurance Payments: $1,024.00\n"
            "Total Adjustments: $0.00\n"
            "Patient Balance: $256.00"
        )

        flags = _bill_flags(bill_text, line_items)

        self.assertFalse(flags["no_insurance_or_self_pay_signal"])
        self.assertEqual(_suggested_next_steps(flags), [])

    def test_parses_insurance_payments_from_split_pdf_table(self):
        tables = [
            [
                ["Summary", "Billed/Pmts/Adjs", "Outstanding Balance Patient Balance"],
                ["New Activity Hospital Services", "$1,280.00", "$256.00 $256.00"],
                ["Totals", "$1,280.00", "$256.00 $256.00"],
            ],
            [
                ["Service", "Code", "Qty", "Billed", "Ins Pmts", "Adj Patient Bal"],
                ["Rheumatology Visit", "CPT 99214", "1", "$420.00", "$336.00", "$0.00 $84.00"],
                ["Joint Injection", "CPT 20610", "1", "$680.00", "$544.00", "$0.00 $136.00"],
                ["Pharmacy", "Revenue 0250", "1", "$180.00", "$144.00", "$0.00 $36.00"],
                ["Totals", "", "", "$1,280.00", "$1,024.00", "$0.00 $256.00"],
            ],
        ]

        items = _parse_line_items_from_tables(tables)

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["billed_amount"], 420.0)
        self.assertEqual(items[0]["insurance_payments"], 336.0)
        self.assertEqual(items[0]["adjustments"], 0.0)
        self.assertEqual(items[0]["patient_balance"], 84.0)
        self.assertEqual(items[1]["insurance_payments"], 544.0)
        self.assertEqual(items[2]["insurance_payments"], 144.0)

    def test_preserves_duplicate_same_day_line_items(self):
        tables = [
            [
                ["Service", "Code", "Qty", "Billed", "Ins Pmts", "Adj Patient Bal"],
                ["Ultrasound Abdomen", "CPT 76700", "1", "$1,200.00", "$960.00", "$0.00 $240.00"],
                ["Ultrasound Abdomen", "CPT 76700", "1", "$1,200.00", "$960.00", "$0.00 $240.00"],
                ["Radiologist Read", "CPT 76942", "1", "$480.00", "$384.00", "$0.00 $96.00"],
            ],
        ]

        items = _parse_line_items_from_tables(tables)
        duplicate_signals = _line_item_duplicate_signals(items)
        flags = _bill_flags("Primary Insurance: Kaiser – HMO", items)

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["description"], "Ultrasound Abdomen")
        self.assertEqual(items[1]["description"], "Ultrasound Abdomen")
        self.assertEqual(items[0]["patient_balance"], 240.0)
        self.assertEqual(items[1]["patient_balance"], 240.0)
        self.assertEqual(sum(item["patient_balance"] for item in items), 576.0)
        self.assertEqual(len(duplicate_signals), 1)
        self.assertEqual(duplicate_signals[0]["code"], "CPT 76700")
        self.assertEqual(duplicate_signals[0]["occurrences"], 2)
        self.assertTrue(flags["potential_duplicate_line_item_signal"])

    def test_extracts_primary_insurance_without_address_noise(self):
        text = (
            "Primary Insurance: Aetna – PPO P.O. Box 48750, Los Angeles, CA 90048\n"
            "Secondary Insurance: None on file\n"
        )

        insurance = _extract_insurance_info(text)

        self.assertEqual(insurance["primary"], "Aetna – PPO")
        self.assertEqual(insurance["secondary"], "None on file")

    def test_does_not_strip_legitimate_abbreviation_in_parenthetical(self):
        """Regression test: bill_v2_medicaid_outpatient_20's payer name is
        "Medi-Cal (Managed Care – L.A. Care Health Plan)". A former
        is_corrupted() heuristic ("2+ single-letter-period abbreviations",
        meant to catch "P.O." address bleed) also matched "L.A." here —
        two innocent abbreviation periods — and deleted the whole
        parenthetical, losing real plan detail. This is Professor Vo's
        second flagged concern in parser-vs-gold item 1B: over-stripping
        on suspicion rather than positive evidence of actual corruption."""
        insurance = _extract_insurance_info(
            "Primary Insurance: Medi-Cal (Managed Care – L.A. Care Health Plan)\n"
            "Secondary Insurance: None on file\n"
        )

        self.assertEqual(insurance["primary"], "Medi-Cal (Managed Care – L.A. Care Health Plan)")

    def test_extracts_bare_insurance_label_with_wrapped_payer_name(self):
        text = (
            "Patient: Sarah Kim DOB: 1982-11-05 Address: 3390 Account #: CS-2026-776203\n"
            "Roxbury Drive, Beverly Hills, CA 90210 Insurance: Anthem Date: 2026-06-18 "
            "Service Date: 2026-04-28 Service Type:\n"
            "Blue Cross PPO Policy #: XBP-44821-001 Status: Active Outpatient Surgery\n"
        )

        insurance = _extract_insurance_info(text)

        self.assertEqual(insurance["primary"], "Anthem Blue Cross PPO")
        self.assertIsNone(insurance["secondary"])

    def test_line_item_total(self):
        self.assertEqual(
            _line_item_total(
                [
                    {"amount": 4200.0},
                    {"amount": 1260.0},
                    {"amount": None},
                ]
            ),
            5460.0,
        )


class MathConsistencyCheckTest(unittest.TestCase):
    """Unit tests for the consistency check's own comparison/threshold logic,
    decoupled from real OCR accuracy (which is inherently variable) so the
    check's correctness can be verified with controlled inputs."""

    def test_flags_inconsistent_totals(self):
        text = "Total Amount Due: $600.00"
        line_items = [{"amount": 300.0}, {"amount": 9600.0}, {"amount": 2000.0}]

        result = _math_consistency_check(text, line_items)

        self.assertTrue(result["checked"])
        self.assertFalse(result["consistent"])
        self.assertEqual(result["stated_total"], 600.0)
        self.assertEqual(result["summed_total"], 11900.0)

    def test_passes_within_tolerance_for_minor_rounding(self):
        text = "Balance Due: $600.00"
        line_items = [{"amount": 300.0}, {"amount": 150.0}, {"amount": 149.50}]

        result = _math_consistency_check(text, line_items)

        self.assertTrue(result["checked"])
        self.assertTrue(result["consistent"])

    def test_uses_patient_balance_for_insured_bill_math(self):
        text = "Totals $1,500.00 $1,200.00 $0.00 $300.00\nTotal Amount Due: $300.00"
        line_items = [
            {
                "billed_amount": 1000.0,
                "insurance_payments": 800.0,
                "adjustments": 0.0,
                "patient_balance": 200.0,
                "amount": 1000.0,
            },
            {
                "billed_amount": 500.0,
                "insurance_payments": 400.0,
                "adjustments": 0.0,
                "patient_balance": 100.0,
                "amount": 500.0,
            },
        ]

        result = _math_consistency_check(text, line_items)

        self.assertTrue(result["checked"])
        self.assertTrue(result["consistent"])
        self.assertEqual(result["stated_total"], 300.0)
        self.assertEqual(result["summed_total"], 300.0)
        self.assertEqual(result["summed_billed"], 1500.0)
        self.assertEqual(result["summed_insurance_payments"], 1200.0)
        self.assertEqual(result["summed_patient_balance"], 300.0)
        self.assertEqual(result["row_reconciliation_violations"], [])

    def test_fails_when_outside_tolerance(self):
        text = "Patient Balance: $600.00"
        line_items = [{"amount": 300.0}, {"amount": 150.0}, {"amount": 100.0}]

        result = _math_consistency_check(text, line_items)

        self.assertTrue(result["checked"])
        self.assertFalse(result["consistent"])

    def test_unchecked_when_no_stated_total_found(self):
        text = "No total line here at all."
        line_items = [{"amount": 300.0}]

        result = _math_consistency_check(text, line_items)

        self.assertFalse(result["checked"])
        self.assertIsNone(result["consistent"])
        self.assertIsNone(result["stated_total"])


class PhotoBillParsingTest(unittest.TestCase):
    """Integration tests against real (downsized) test images — see
    testdata/bill_photo_*. These exercise the actual OCR pipeline, so
    they verify the pipeline runs and produces plausible structure, not
    exact field values (OCR output can shift slightly across Tesseract
    versions)."""

    def test_reads_legible_photo_without_crashing(self):
        result = parse_bill_file(str(TESTDATA_DIR / "bill_photo_legible.png"))

        self.assertEqual(result["source_type"], "photo")
        self.assertIn("Anthem", result["insurance"]["primary"])
        self.assertTrue(result["math_consistency"]["checked"])

    def test_reads_heic_photo_via_conversion(self):
        result = parse_bill_file(str(TESTDATA_DIR / "bill_photo_legible.heic"))

        self.assertEqual(result["source_type"], "photo")
        self.assertIn("Anthem", result["insurance"]["primary"])

    def test_rejects_unreadable_photo(self):
        with self.assertRaises(LowConfidenceOCRError):
            parse_bill_file(str(TESTDATA_DIR / "bill_photo_unreadable.png"))

    def test_rejects_unsupported_file_type(self):
        with self.assertRaises(ValueError):
            parse_bill_file(str(TESTDATA_DIR / "unsupported_file.gif"))

    def test_bill_parser_tool_gives_friendly_message_for_unreadable_photo(self):
        result = json.loads(
            bill_parser.handler({"file_path": str(TESTDATA_DIR / "bill_photo_unreadable.png")})
        )

        self.assertEqual(result["error_type"], "low_confidence_ocr")
        self.assertIn("retake", result["suggested_response"])

    def test_pdf_path_still_works_unchanged(self):
        """Guards against the PDF path regressing while adding photo support."""
        result = parse_bill_file(str(TESTDATA_DIR / "bill_commercial_outpatient_01.pdf"))

        self.assertEqual(result["source_type"], "pdf")
        self.assertIn("math_consistency", result)


class OCRLabelToleranceTest(unittest.TestCase):
    """These header-field patterns are the root-cause fix for OCR label
    noise: real photos this session showed OCR misreading "Patient:" as
    "Pationt", "Service Date:" as "Serve Date:", colons as semicolons,
    etc. Rather than patching each label as it turned up broken, every
    pattern here tolerates the same class of noise: a few dropped/altered
    letters after a stable prefix, and colon/semicolon interchangeably."""

    def test_patient_name_tolerates_ocr_typo_and_semicolon(self):
        match = PATIENT_NAME_PATTERN.search(
            "Pationt Name; JOHNNIE MOR Secondary Insurance: No Insurance on file"
        )
        self.assertEqual(match.group(1).strip(), "JOHNNIE MOR")

    def test_service_date_tolerates_ocr_typo_and_spelled_out_date(self):
        match = SERVICE_DATE_PATTERN.search("Serve Date: November 25, 2013\nNext line")
        self.assertEqual(match.group(1).strip(), "November 25, 2013")

    def test_service_date_stops_before_same_line_service_type_label(self):
        """Regression: commercial outpatient bills put Service Date and
        Service Type on one line. Capturing to EOL previously returned
        '04/28 Service Type:/2026' after normalize_date scrambled the
        polluted capture."""
        match = SERVICE_DATE_PATTERN.search(
            "Service Date: 2026-04-28 Service Type:\nBlue Cross PPO"
        )
        self.assertEqual(match.group(1).strip(), "2026-04-28")

        match = SERVICE_DATE_PATTERN.search(
            "Service Date: 04/28/2026 Service Type: Outpatient Surgery"
        )
        self.assertEqual(match.group(1).strip(), "04/28/2026")

    def test_service_date_does_not_span_into_unrelated_earlier_services_word(self):
        """Regression test: \\s* between the label and "Date" previously
        matched all the way from an unrelated "...Services" earlier in
        the text to a "Date:" line further down, grabbing the statement
        date instead of the real service date."""
        text = (
            "Cedars-Sinai Statement of Hospital and Physician Services\n"
            "Date: 2026-04-01\n"
            "Service Date: 2026-03-15\n"
        )
        match = SERVICE_DATE_PATTERN.search(text)
        self.assertEqual(match.group(1).strip(), "2026-03-15")

    def test_guarantor_name_tolerates_semicolon(self):
        match = GUARANTOR_NAME_PATTERN.search("Guarantor Name; Maria Gutierrez")
        self.assertEqual(match.group(1).strip(), "Maria Gutierrez")

    def test_guarantor_number_tolerates_ocr_typo(self):
        match = GUARANTOR_NUMBER_PATTERN.search("Guarentor #: GU-2026-01154")
        self.assertEqual(match.group(1), "GU-2026-01154")

    def test_account_number_matches_number_label_without_hash(self):
        """Real bills sometimes label this "Account Number:" rather than
        "Account #:", which the original pattern required literally."""
        match = ACCOUNT_NUMBER_PATTERN.search("Account Number: 22237958")
        self.assertEqual(match.group(1), "22237958")

    def test_pay_online_tolerates_semicolon_and_suffix_typo(self):
        match = PAY_ONLINE_PATTERN.search("Pay Onlne; cedars-sinai.org/billing")
        self.assertEqual(match.group(1), "cedars-sinai.org/billing")

    def test_pay_by_phone_tolerates_semicolon_and_suffix_typo(self):
        match = PAY_BY_PHONE_PATTERN.search("Pay by Phonne; 866-803-1777")
        self.assertEqual(match.group(1), "866-803-1777")

    def test_total_due_feeds_safety_net_even_with_ocr_typo(self):
        """TOTAL_DUE_PATTERN feeds _math_consistency_check directly — if
        this fails to match on noisy text, the safety net silently
        doesn't run at all rather than failing loudly, so it gets the
        same tolerance as the other header patterns."""
        for text in [
            "Total Amount Due: $600.00",
            "Total Amount Due : $600.00",
            "Totel Due: $600.00",
            "Balance Due; $600.00",
            "Patient Responsibility: $600.00",
        ]:
            match = TOTAL_DUE_PATTERN.search(text)
            self.assertIsNotNone(match, f"did not match: {text!r}")
            self.assertEqual(match.group(1), "600.00")


class LooksLikeIdTest(unittest.TestCase):
    """_looks_like_id guards against multi-column OCR bleed — e.g. reading
    "Account Number: Primary Insurance" when the real value sits in a
    different column than Tesseract expects. A real ID always has a
    digit; a bare word grabbed from a neighboring label doesn't."""

    def test_accepts_real_looking_ids(self):
        for value in ["CS-2026-00441", "22237958", "272", "GU-2026-01154"]:
            self.assertTrue(_looks_like_id(value), value)

    def test_rejects_pure_word_values(self):
        for value in ["Primary", "Insurance", "None"]:
            self.assertFalse(_looks_like_id(value), value)

    def test_extract_guarantor_info_drops_implausible_number(self):
        text = "Guarantor Number: Primary Insurance: UNITED HEALTHCARE"
        info = _extract_guarantor_info(text)
        self.assertIsNone(info["guarantor_account_number"])

    def test_extract_bill_header_fields_keeps_plausible_account_number(self):
        text = "Account Number: 22237958\nOther text"
        fields = _extract_bill_header_fields(text)
        self.assertEqual(fields["patient"]["patient_account_number"], "22237958")


class InsuranceColumnBleedTest(unittest.TestCase):
    """Regression tests for every bill found with the column-bleed bug
    Professor Vo flagged (parser-vs-gold feedback, item 1B): pdfplumber's
    default line-merging renders an insurance parenthetical and an
    unrelated P.O. Box address line (positioned ~0.4pt apart in these
    PDFs — well under the ~3pt default tolerance) as one interleaved
    line. _extract_insurance_by_line_clustering fixes this by grouping
    characters by their exact y-position instead of flattened text.

    Every one of these was independently confirmed corrupted via a full
    70-bill corpus scan before the fix, and confirmed clean with zero
    side effects on any other field afterward — these pin that result."""

    KNOWN_AFFECTED_BILLS = {
        "bill_v2_medicare_advantage_oon_66.pdf": "SCAN Health Plan – HMO (Medicare Advantage)",
        "bill_v2_medicare_advantage_pffs_32.pdf": "Alignment Health – PFFS (Medicare Advantage)",
        "bill_v2_medicare_advantage_snp_33.pdf": "Scan Health Plan – D-SNP (Dual Special Needs)",
        "bill_v2_secondary_insurance_cob_18.pdf": "Cigna – PPO (Commercial, employer-sponsored)",
        "bill_v2_medicare_advantage_copay_discrepancy_08.pdf": (
            "Kaiser Permanente Senior Advantage PPO (Medicare Advantage)"
        ),
        "bill_v2_eob_commercial_22.pdf": "UnitedHealthcare – Choice Plus PPO (employer-sponsored)",
        "bill_v2_selfpay_prompt_pay_64.pdf": "None on file (Self-pay – prompt pay discount applied)",
        "bill_v2_workers_comp_disputed_67.pdf": "State Compensation Insurance Fund (claim disputed)",
        "bill_v2_workers_comp_er_15.pdf": "State Compensation Insurance Fund (Workers Comp)",
        "bill_v2_international_selfpay_59.pdf": "None on file (International visitor – no US insurance)",
        "bill_v2_medicaid_share_of_cost_10.pdf": "Medi-Cal – Share of Cost Plan (California Medicaid)",
        "bill_v2_prior_auth_denial_30.pdf": "Kaiser Permanente – HMO (employer-sponsored)",
    }

    def test_all_known_affected_bills_extract_clean_insurance(self):
        for filename, expected in self.KNOWN_AFFECTED_BILLS.items():
            with self.subTest(filename=filename):
                result = parse_bill_file(
                    f"../synthetic-data/synthetic_bills_v2/{filename}"
                )
                self.assertEqual(result["insurance"]["primary"], expected)

    def test_line_clustering_returns_none_for_non_pdf_path(self):
        """Falls back cleanly (no exception) when given something that
        isn't a real PDF pdfplumber can open."""
        result = _extract_insurance_by_line_clustering(
            TESTDATA_DIR / "bill_photo_legible.png"
        )
        self.assertIsNone(result)

    def test_line_clustering_extracts_secondary_insurance_too(self):
        result = _extract_insurance_by_line_clustering(
            Path("../synthetic-data/synthetic_bills_v2/bill_v2_secondary_insurance_cob_18.pdf")
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result["secondary"])


def _json_date_to_parsed_format(raw: str | None) -> str | None:
    """Convert a bill JSON's "YYYY-MM-DD" date to the parser's "MM/DD/YYYY"
    output format, for direct comparison against parsed results."""
    if not raw:
        return None
    year, month, day = raw.split("-")
    return f"{month}/{day}/{year}"


class CorpusFieldRecallTest(unittest.TestCase):
    """Corpus-wide regression gate: parses every real bill PDF and checks
    key header fields directly against that bill's own source JSON (the
    ground truth the PDF was generated from) — not hand-labeled data, so
    this covers all 70 bills at effectively no authoring cost.

    This is the closest equivalent this repo has to Professor Vo's
    "core_field_recall... regression gate" (parser-vs-gold feedback,
    item 1) — there's no separate audit notebook or CI pipeline here, but
    this runs as part of the same test suite already run before every PR,
    and fails loudly if a future change regresses any bill's extraction."""

    FIELDS_TO_CHECK = [
        "facility_name",
        "statement_date",
        "due_date",
        "total_amount_due",
        "total_billed",
        "total_insurance_payments",
        "total_adjustments",
        "outstanding_balance",
        "patient_balance",
    ]

    @classmethod
    def setUpClass(cls):
        cls.bill_dir = Path("../synthetic-data/synthetic_bills_v2")
        cls.pdf_paths = sorted(cls.bill_dir.glob("*.pdf"))
        assert len(cls.pdf_paths) == 70, f"expected 70 bills, found {len(cls.pdf_paths)}"

    def _load_gold(self, json_path: Path) -> dict:
        with json_path.open() as f:
            return json.load(f)

    def test_header_fields_match_source_json_across_full_corpus(self):
        mismatches = []
        for pdf_path in self.pdf_paths:
            json_path = pdf_path.with_suffix(".json")
            gold = self._load_gold(json_path)
            result = parse_bill_file(str(pdf_path))

            gold_flat = {
                "facility_name": gold.get("facility", {}).get("name"),
                "statement_date": _json_date_to_parsed_format(gold.get("statement_date")),
                "due_date": _json_date_to_parsed_format(gold.get("due_date")),
                "total_amount_due": gold.get("total_amount_due"),
                **{
                    k: gold.get("summary_of_services", {}).get("totals", {}).get(k)
                    for k in [
                        "total_billed",
                        "total_insurance_payments",
                        "total_adjustments",
                        "outstanding_balance",
                        "patient_balance",
                    ]
                },
            }

            for field in self.FIELDS_TO_CHECK:
                expected = gold_flat.get(field)
                actual = result.get(field)
                if expected is not None and expected != actual:
                    mismatches.append(
                        (pdf_path.name, field, expected, actual)
                    )

        total_checks = len(self.pdf_paths) * len(self.FIELDS_TO_CHECK)
        recall = 1 - (len(mismatches) / total_checks)
        if mismatches:
            detail = "\n".join(
                f"  {name}: {field} expected={expected!r} actual={actual!r}"
                for name, field, expected, actual in mismatches
            )
            self.fail(
                f"core_field_recall={recall:.4f} "
                f"({len(mismatches)}/{total_checks} field checks failed):\n{detail}"
            )

    def test_insurance_and_guarantor_match_source_json_across_full_corpus(self):
        """Separate from the numeric/date header fields above since these
        are the two fields with known historical fragility (column-bleed
        corruption, OCR label noise) — tracked on their own so a future
        regression here is unambiguous about which subsystem broke."""
        mismatches = []
        for pdf_path in self.pdf_paths:
            json_path = pdf_path.with_suffix(".json")
            gold = self._load_gold(json_path)
            result = parse_bill_file(str(pdf_path))

            checks = [
                ("insurance.primary", gold.get("insurance", {}).get("primary"), result["insurance"].get("primary")),
                ("insurance.secondary", gold.get("insurance", {}).get("secondary"), result["insurance"].get("secondary")),
                ("guarantor.guarantor_name", gold.get("guarantor", {}).get("guarantor_name"), result["guarantor"].get("guarantor_name")),
            ]
            for field, expected, actual in checks:
                if expected is not None and expected != actual:
                    mismatches.append((pdf_path.name, field, expected, actual))

        total_checks = len(self.pdf_paths) * 3
        recall = 1 - (len(mismatches) / total_checks)
        if mismatches:
            detail = "\n".join(
                f"  {name}: {field} expected={expected!r} actual={actual!r}"
                for name, field, expected, actual in mismatches
            )
            self.fail(
                f"insurance/guarantor field_recall={recall:.4f} "
                f"({len(mismatches)}/{total_checks} field checks failed):\n{detail}"
            )


class BuildProvenanceTest(unittest.TestCase):
    """Unit tests for _build_provenance, decoupled from a real bill file so
    each scenario (PDF/photo, consistent/inconsistent, high/low OCR
    confidence) can be tested with controlled inputs."""

    def test_pdf_fields_get_deterministic_confidence_and_no_warnings(self):
        header_fields = {
            "total_billed": 100.0,
            "total_amount_due": 100.0,
        }
        math_consistency = {"consistent": True}

        provenance = _build_provenance(header_fields, "pdf", 1.0, math_consistency)

        self.assertEqual(provenance["total_billed"]["method"], "text_regex")
        self.assertEqual(provenance["total_billed"]["confidence"], 1.0)
        self.assertEqual(provenance["total_billed"]["warnings"], [])

    def test_reconciliation_failure_flags_every_tracked_field(self):
        header_fields = {"total_billed": 100.0, "patient_balance": 50.0}
        math_consistency = {"consistent": False}

        provenance = _build_provenance(header_fields, "pdf", 1.0, math_consistency)

        for field_name in ("total_billed", "patient_balance"):
            self.assertIn("fails_total_reconciliation", provenance[field_name]["warnings"])

    def test_photo_fields_use_ocr_method_and_real_confidence(self):
        header_fields = {"total_amount_due": 600.0}
        math_consistency = {"consistent": True}

        provenance = _build_provenance(header_fields, "photo", 0.85, math_consistency)

        self.assertEqual(provenance["total_amount_due"]["method"], "ocr")
        self.assertEqual(provenance["total_amount_due"]["confidence"], 0.85)
        self.assertEqual(provenance["total_amount_due"]["warnings"], [])

    def test_low_confidence_photo_gets_flagged_even_when_consistent(self):
        """A photo can clear the hard OCR_MIN_CONFIDENCE gate (get parsed
        at all) while still being mediocre enough that its numbers deserve
        a "double check this" flag, independent of whether the math
        happens to reconcile."""
        header_fields = {"total_amount_due": 600.0}
        math_consistency = {"consistent": True}

        provenance = _build_provenance(header_fields, "photo", 0.50, math_consistency)

        self.assertIn("low_ocr_confidence", provenance["total_amount_due"]["warnings"])

    def test_untracked_and_missing_fields_are_excluded(self):
        header_fields = {"total_billed": None, "facility_name": "Cedars-Sinai"}
        math_consistency = {"consistent": True}

        provenance = _build_provenance(header_fields, "pdf", 1.0, math_consistency)

        self.assertNotIn("total_billed", provenance)
        self.assertNotIn("facility_name", provenance)

    def test_parse_bill_file_attaches_provenance_for_real_pdf(self):
        result = parse_bill_file(
            "../synthetic-data/synthetic_bills_v2/bill_v2_selfpay_er_01.pdf"
        )

        self.assertIn("_provenance", result)
        self.assertEqual(result["_provenance"]["total_amount_due"]["method"], "text_regex")
        self.assertEqual(result["_provenance"]["total_amount_due"]["warnings"], [])

    def test_parse_bill_file_flags_provenance_on_intentionally_broken_bill(self):
        result = parse_bill_file(
            "../synthetic-data/synthetic_bills_v2/bill_v2_intentionally_incorrect_math_13.pdf"
        )

        for field_name in ("total_billed", "patient_balance", "total_amount_due"):
            self.assertIn(
                "fails_total_reconciliation",
                result["_provenance"][field_name]["warnings"],
            )


if __name__ == "__main__":
    unittest.main()
