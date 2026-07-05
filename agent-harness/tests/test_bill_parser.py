import unittest

from app.tools.bill_parser import _bill_flags, _line_item_total, _suggested_next_steps


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
