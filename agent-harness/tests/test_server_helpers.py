import unittest

from app.server import (
    _clean_duplicate_sensitive_notice,
    _message_has_phi,
    _sensitive_info_notice,
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


if __name__ == "__main__":
    unittest.main()
