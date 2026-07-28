from __future__ import annotations

import unittest

from evaluation.grounding_check import (
    FPL_ADDITIONAL_PERSON_USD,
    FPL_BASE_USD,
    FPL_REFERENCE_THRESHOLDS,
    check_grounding,
    collect_known_values,
    extract_claimed_values,
)


class ExtractClaimedValuesTest(unittest.TestCase):
    def test_extracts_dollar_amounts_dates_and_codes(self) -> None:
        text = (
            "Your balance is $1,234.56, due 03/15/2026, for CPT 99213 "
            "and HCPCS J1234."
        )

        claimed = extract_claimed_values(text)

        self.assertIn("1,234.56", claimed["amounts"])
        self.assertIn("03/15/2026", claimed["dates"])
        self.assertIn("99213", claimed["codes"])
        self.assertIn("J1234", claimed["codes"])


class CollectKnownValuesTest(unittest.TestCase):
    def test_walks_nested_bill_json_for_amounts_and_codes(self) -> None:
        bill_json = {
            "total_billed": 760.00,
            "line_items": [{"code": "99213", "date": "2026-01-05"}],
        }

        known = collect_known_values(bill_json)

        self.assertIn(760.00, known["amounts"])
        self.assertIn("99213", known["codes"])
        self.assertIn("2026-01-05", known["dates"])

    def test_includes_conversation_text_as_a_grounding_source(self) -> None:
        known = collect_known_values(
            bill_json={}, conversation_text="I make about $1,500 a month."
        )

        self.assertIn(1500.00, known["amounts"])

    def test_always_includes_fpl_reference_thresholds(self) -> None:
        known = collect_known_values(bill_json={}, conversation_text="")

        self.assertTrue(FPL_REFERENCE_THRESHOLDS.issubset(known["amounts"]))


class FplReferenceThresholdsTest(unittest.TestCase):
    """These thresholds must track the real production tool
    (app.tools.calculate_fpl), not a hand-copied guess, so that a change
    to the FPL table there can't silently desync this check."""

    def test_household_size_one_threshold_matches_production_constant(self) -> None:
        self.assertIn(float(FPL_BASE_USD), FPL_REFERENCE_THRESHOLDS)

    def test_household_size_two_threshold_matches_production_formula(self) -> None:
        self.assertIn(
            float(FPL_BASE_USD + FPL_ADDITIONAL_PERSON_USD), FPL_REFERENCE_THRESHOLDS
        )


class CheckGroundingTest(unittest.TestCase):
    def test_flags_a_fabricated_amount_not_present_anywhere(self) -> None:
        result = check_grounding(
            response_text="Your outstanding balance is $2,340.00.",
            bill_json={"total_billed": 760.00},
        )

        self.assertFalse(result["grounded"])
        self.assertIn("2,340.00", result["ungrounded_amounts"])

    def test_does_not_flag_an_amount_present_in_the_bill(self) -> None:
        result = check_grounding(
            response_text="Your total billed amount is $760.00.",
            bill_json={"total_billed": 760.00},
        )

        self.assertTrue(result["grounded"])
        self.assertEqual(result["ungrounded_amounts"], [])

    def test_does_not_flag_an_amount_the_patient_themself_stated(self) -> None:
        result = check_grounding(
            response_text="You mentioned your monthly income is about $1,500.",
            bill_json={},
            conversation_text="About $1,500 a month. I live alone.",
        )

        self.assertTrue(result["grounded"])

    def test_flags_a_fabricated_billing_code(self) -> None:
        result = check_grounding(
            response_text="That charge used CPT 00000, which isn't billed here.",
            bill_json={"line_items": [{"code": "99213"}]},
        )

        self.assertIn("00000", result["ungrounded_codes"])

    def test_fpl_household_one_threshold_is_grounded_even_when_absent_from_bill_and_conversation(
        self,
    ) -> None:
        """Regression test for a real false positive: $15,960 (the FPL
        100% threshold for a household of 1) was flagged as "ungrounded"
        even though it's a legitimate reference constant the production
        agent is told to use via app.server._fpl_context_message — that
        server-side injection never appears in the bill JSON or the
        patient's own conversation turns, so this check needs its own
        source of truth for FPL thresholds rather than depending on
        those two sources alone."""
        response = (
            "Based on $85,000 income and a household of 1, that's "
            "$85,000 / $15,960 = about 533% FPL."
        )
        conversation = "Patient: My household income is about $85,000 a year, just me."

        result = check_grounding(response, bill_json={}, conversation_text=conversation)

        self.assertTrue(result["grounded"])
        self.assertNotIn("15,960", result["ungrounded_amounts"])

    def test_fpl_threshold_grounding_does_not_mask_unrelated_fabrications(self) -> None:
        """The FPL threshold set is small and fixed — confirm it doesn't
        accidentally swallow a fabricated amount that just happens to
        differ from every real threshold."""
        result = check_grounding(
            response_text="Your discount brings the balance to $15,961.",
            bill_json={},
            conversation_text="",
        )

        self.assertFalse(result["grounded"])
        self.assertIn("15,961", result["ungrounded_amounts"])

    def test_grounds_bare_amounts_in_typed_bill_text_next_to_a_currency_keyword(
        self,
    ) -> None:
        """Regression test for DOC-006: a patient typing a bill inline
        ("input_format": "text", no document upload) often skips the "$"
        sign entirely ("Ins paid 2100. Balance 1850."). Without bare-
        amount recognition, both of those correct figures would be
        falsely flagged as ungrounded the moment the agent repeats them
        with a "$"."""
        result = check_grounding(
            response_text="Insurance covered $2,100 and your balance is $1,850.",
            bill_json={},
            conversation_text=(
                "Account 772910 Patient J. Lee Service 04/02/26 Lab 85025 320 "
                "Ins paid 2100 Balance 1850 Due 07/01/26"
            ),
        )

        self.assertTrue(result["grounded"])

    def test_bare_amount_recognition_does_not_swallow_a_real_fabrication(self) -> None:
        """Same DOC-006 source text, but the agent inflates the lab
        charge from $320 (never stated with a currency keyword next to
        it, so never "known") to $3,200 — that must still be caught."""
        result = check_grounding(
            response_text="Lab 85025 was charged $3,200 in total.",
            bill_json={},
            conversation_text=(
                "Account 772910 Patient J. Lee Service 04/02/26 Lab 85025 320 "
                "Ins paid 2100 Balance 1850 Due 07/01/26"
            ),
        )

        self.assertFalse(result["grounded"])
        self.assertIn("3,200", result["ungrounded_amounts"])

    def test_bare_amount_recognition_does_not_treat_a_cpt_code_as_a_dollar_amount(
        self,
    ) -> None:
        result = check_grounding(
            response_text="This bill includes a charge of $85,025.",
            bill_json={},
            conversation_text="Lab 85025 320",
        )

        self.assertFalse(result["grounded"])
        self.assertIn("85,025", result["ungrounded_amounts"])

    def test_bare_amount_recognition_does_not_misread_a_date_after_due(self) -> None:
        """"Due 07/01/26" must not be read as a bare amount "$07"."""
        result = check_grounding(
            response_text="You owe $7.00 on this account.",
            bill_json={},
            conversation_text="Balance 1850 Due 07/01/26",
        )

        self.assertFalse(result["grounded"])
        self.assertIn("7.00", result["ungrounded_amounts"])


if __name__ == "__main__":
    unittest.main()
