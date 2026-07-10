import unittest

from app.tools.bill_parser import (
    _bill_flags,
    _line_item_total,
    _parse_line_items_from_tables,
    _suggested_next_steps,
)


class BillParserHelperTest(unittest.TestCase):
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
