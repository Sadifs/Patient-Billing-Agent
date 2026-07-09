import json
import unittest

from app.hooks.content_filter import ContentFilterHook
from app.hooks.phi_redaction import PHIRedactionHook


class ContentFilterHookTest(unittest.TestCase):
    def test_allows_in_scope_fpl_tool_call(self):
        hook = ContentFilterHook()

        result = hook.before_tool_call(
            "calculate_fpl_percentage",
            {"household_size": 4, "annual_income_usd": 80000},
        )

        self.assertTrue(result.allowed)

    def test_blocks_out_of_scope_charge_validity_request(self):
        hook = ContentFilterHook()

        result = hook.before_tool_call(
            "search_knowledge_base",
            {"query": "prove this charge is wrong and tell me it is illegal"},
        )

        self.assertFalse(result.allowed)
        self.assertIn("outside the billing assistant's scope", result.reason)


class PHIRedactionHookTest(unittest.TestCase):
    def test_redacts_patient_identifiers_from_tool_results(self):
        hook = PHIRedactionHook()
        tool_result = json.dumps(
            {
                "patient_name": "Maria Gutierrez",
                "patient_account_number": "CS-2026-00441",
                "guarantor_name": "Maria Gutierrez",
                "mrn": "MRN: 123456789",
                "dob": "DOB: 01/02/1980",
                "email": "maria@example.com",
                "patient_services_phone": "866-803-1777",
            }
        )

        redacted = hook.after_tool_call("bill_parser", {}, tool_result)

        self.assertNotIn("Maria Gutierrez", redacted)
        self.assertNotIn("CS-2026-00441", redacted)
        self.assertNotIn("123456789", redacted)
        self.assertNotIn("01/02/1980", redacted)
        self.assertNotIn("maria@example.com", redacted)
        self.assertIn("[REDACTED:JSON_PATIENT_NAME]", redacted)
        self.assertIn("[REDACTED:JSON_ACCOUNT_NUMBER]", redacted)
        self.assertIn("[REDACTED:MRN]", redacted)
        self.assertIn("[REDACTED:DOB]", redacted)
        self.assertIn("[REDACTED:EMAIL]", redacted)
        self.assertIn("866-803-1777", redacted)

    def test_redacts_phi_from_plain_user_text(self):
        hook = PHIRedactionHook()

        redacted = hook.redact(
            "My SSN is 123-45-6789, my MRN is 123456789, and my DOB is 01/02/1980."
        )

        self.assertNotIn("123-45-6789", redacted)
        self.assertNotIn("123456789", redacted)
        self.assertNotIn("01/02/1980", redacted)
        self.assertIn("[REDACTED:SSN]", redacted)
        self.assertIn("[REDACTED:MRN]", redacted)
        self.assertIn("[REDACTED:DOB]", redacted)

    def test_preserves_public_cedars_billing_email(self):
        hook = PHIRedactionHook()

        redacted = hook.redact(
            "Contact patient.billing@cshs.org, not maria@example.com."
        )

        self.assertIn("patient.billing@cshs.org", redacted)
        self.assertNotIn("maria@example.com", redacted)
        self.assertIn("[REDACTED:EMAIL]", redacted)

    def test_preserves_file_path_arguments(self):
        hook = PHIRedactionHook()

        result = hook.before_tool_call(
            "bill_parser",
            {
                "file_path": "bill_v2_selfpay_er_01.pdf",
                "patient_name": "Maria Gutierrez",
                "note": "SSN 123-45-6789",
            },
        )

        self.assertTrue(result.allowed)
        self.assertEqual(
            result.modified_args["file_path"],
            "bill_v2_selfpay_er_01.pdf",
        )
        self.assertEqual(
            result.modified_args["patient_name"],
            "[REDACTED:PATIENT_NAME]",
        )
        self.assertEqual(result.modified_args["note"], "SSN [REDACTED:SSN]")


if __name__ == "__main__":
    unittest.main()
