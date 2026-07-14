import unittest

from app.tools.bill_parser import (
    _bill_flags,
    _extract_bill_header_fields,
    _extract_insurance_info,
    _line_item_duplicate_signals,
    _line_item_total,
    _parse_line_items_from_tables,
    _suggested_next_steps,
    parse_bill_pdf,
)


SAMPLE_BILL_TEXT = """
Cedars-Sinai Statement of Hospital and Physician Services
Date: 2026-04-01
Maria Gutierrez A l Pay Online: cedars-sinai.org/billing
l Pay by Phone: 866-803-1777
Account #: CS-2026-00441
Service Date: 2026-03-15
Primary Insurance: None on file P.O. Box 48750, Los Angeles, CA 90048
Secondary Insurance: None on file
Guarantor Name: Maria Gutierrez
For account information or to discuss financial assistance, call 866-803-1777,
Monday–Friday, 8:00 AM – 4:30 PM PT, or email patient.billing@cshs.org.
Patient: Maria Gutierrez Account #: CS-2026-00441 Service Date: 2026-03-15
Cedars-Sinai Medical Center, P.O. Box 48750, Los Angeles, CA 90048
"""


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


if __name__ == "__main__":
    unittest.main()
