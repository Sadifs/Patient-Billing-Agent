import unittest

from app.server import (
    _clean_duplicate_sensitive_notice,
    _clean_internal_tool_text,
    _message_has_phi,
    _sensitive_info_notice,
    _technical_fallback_message,
)


class ServerHelperTest(unittest.TestCase):
    def test_detects_phi_in_user_message(self):
        self.assertTrue(_message_has_phi("My SSN is 123-45-6789."))
        self.assertFalse(_message_has_phi("Can you explain my bill?"))

    def test_removes_model_sensitive_notice_before_prefixing(self):
        model_text = (
            "You do not need to share sensitive identifiers such as your SSN "
            "or MRN here. Your bill shows a balance."
        )

        cleaned = _clean_duplicate_sensitive_notice(model_text)
        final_text = _sensitive_info_notice() + cleaned

        self.assertEqual(final_text.count("You do not need to share"), 1)
        self.assertIn("Your bill shows a balance.", final_text)

    def test_financial_assistance_fallback_takes_priority_over_bill_word(self):
        fallback = _technical_fallback_message("Can I get help paying my bill?")

        self.assertIn("financial-assistance answer", fallback)
        self.assertIn("household size", fallback)
        self.assertNotIn("sensitive details", fallback)

    def test_removes_internal_tool_syntax_from_response_text(self):
        model_text = (
            "The total amount you owe is $52,000.00.\n\n"
            "Also, I will call the calculate_fpl_percentage function once I "
            "have the required information.\n\n"
            "<function.calculate_fpl_percentage is pending household size and annual income>"
        )

        cleaned = _clean_internal_tool_text(model_text)

        self.assertIn("The total amount you owe is $52,000.00.", cleaned)
        self.assertNotIn("calculate_fpl_percentage", cleaned)
        self.assertNotIn("<function.", cleaned)


if __name__ == "__main__":
    unittest.main()
