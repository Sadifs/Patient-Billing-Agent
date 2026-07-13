import unittest

from app.server import (
    _clean_duplicate_sensitive_notice,
    _clean_internal_tool_text,
    _direct_billing_website_answer,
    _direct_call_prep_answer,
    _direct_charity_care_coverage_answer,
    _direct_charity_care_definition_answer,
    _direct_fpl_definition_answer,
    _direct_fpl_answer,
    _direct_legal_boundary_answer,
    _direct_payment_plan_answer,
    _extract_fpl_inputs,
    _fpl_context_message,
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

    def test_extracts_household_size_and_income_for_fpl(self):
        inputs = _extract_fpl_inputs(
            "Household size: 5, household income: $115,000"
        )

        self.assertEqual(inputs["household_size"], 5)
        self.assertEqual(inputs["annual_income_usd"], 115000)

    def test_extracts_income_with_k_suffix(self):
        inputs = _extract_fpl_inputs("household size is 1 and annual income is 30k")

        self.assertEqual(inputs["household_size"], 1)
        self.assertEqual(inputs["annual_income_usd"], 30000)

    def test_extracts_household_size_from_natural_phrasing(self):
        inputs = _extract_fpl_inputs("my income is 40k and i have 2 people in my household")

        self.assertEqual(inputs["household_size"], 2)
        self.assertEqual(inputs["annual_income_usd"], 40000)

    def test_extracts_household_size_family_of(self):
        inputs = _extract_fpl_inputs("family of 3, income is $60,000")

        self.assertEqual(inputs["household_size"], 3)
        self.assertEqual(inputs["annual_income_usd"], 60000)

    def test_extracts_household_size_just_me(self):
        inputs = _extract_fpl_inputs("it's just me, i earn $25,000")

        self.assertEqual(inputs["household_size"], 1)
        self.assertEqual(inputs["annual_income_usd"], 25000)

    def test_extracts_fpl_inputs_across_history(self):
        history = [{"role": "user", "content": "household size is 3"}]
        inputs = _extract_fpl_inputs("my income is $45,000", history)

        self.assertEqual(inputs["household_size"], 3)
        self.assertEqual(inputs["annual_income_usd"], 45000)

    def test_direct_fpl_answer_uses_history_for_missing_input(self):
        history = [{"role": "user", "content": "household size is 2"}]
        answer = _direct_fpl_answer("my income is $40,000", history)

        self.assertIsNotNone(answer)
        self.assertIn("household of 2", answer)

    def test_direct_fpl_answer_ignores_unrelated_follow_up_history(self):
        history = [
            {
                "role": "user",
                "content": "My household size is 7 and my household annual income is $1,200,000.",
            }
        ]

        answer = _direct_fpl_answer(
            "I don't think all the information on my bill is correct",
            history,
        )

        self.assertIsNone(answer)

    def test_fpl_context_ignores_unrelated_follow_up_history(self):
        history = [
            {
                "role": "user",
                "content": "My household size is 7 and my household annual income is $1,200,000.",
            }
        ]

        context = _fpl_context_message(
            "I don't think all the information on my bill is correct",
            history,
        )

        self.assertIsNone(context)

    def test_direct_fpl_answer_uses_calculated_values(self):
        answer = _direct_fpl_answer(
            "Household size: 5, household income: $115,000"
        )

        self.assertLess(answer.index("**Summary**"), answer.index("**FPL Calculation Breakdown**"))
        self.assertLess(answer.index("**FPL Calculation Breakdown**"), answer.index("**What This Means**"))
        self.assertLess(answer.index("**What This Means**"), answer.index("**Next Steps**"))
        self.assertIn("household of 5", answer)
        self.assertIn("- Household size: 5", answer)
        self.assertIn("- Annual household income: $115,000", answer)
        self.assertIn("$38,680", answer)
        self.assertIn("297.3%", answer)
        self.assertIn("charity care candidate", answer)
        self.assertIn("does not guarantee approval", answer)
        self.assertIn("applying is worth asking about", answer)
        self.assertNotIn("may not qualify", answer.lower())

    def test_direct_fpl_answer_handles_above_threshold_case(self):
        answer = _direct_fpl_answer(
            "My household size is 7 and my household annual income is $1,200,000."
        )

        self.assertIn("- Household size: 7", answer)
        self.assertIn("- Annual household income: $1,200,000", answer)
        self.assertIn("$50,040", answer)
        self.assertIn("2398.1%", answer)
        self.assertIn("above the standard Cedars-Sinai financial-assistance income thresholds", answer)
        self.assertIn("payment plans or hardship review options", answer)
        self.assertNotIn("you may be a above", answer.lower())
        self.assertNotIn("applying is worth asking about", answer)

    def test_direct_fpl_definition_answer_explains_term(self):
        answer = _direct_fpl_definition_answer("What is FPL?")

        self.assertIn("Federal Poverty Level", answer)
        self.assertIn("household income", answer)
        self.assertIn("household size", answer)
        self.assertIn("Cedars-Sinai makes the final decision", answer)
        self.assertNotIn("technical issue", answer.lower())

    def test_direct_fpl_definition_handles_common_variations(self):
        self.assertIsNotNone(_direct_fpl_definition_answer("What does FPL mean?"))
        self.assertIsNotNone(_direct_fpl_definition_answer("define FPL"))
        self.assertIsNone(_direct_fpl_definition_answer("Household size is 5"))

    def test_direct_charity_care_definition_answer_explains_term(self):
        answer = _direct_charity_care_definition_answer(
            "What is Cedars-Sinai Charity Care?"
        )

        self.assertIn("**Summary**", answer)
        self.assertIn("financial-assistance option", answer)
        self.assertIn("Cedars-Sinai Patient Financial Services", answer)
        self.assertIn("cannot approve Charity Care", answer)
        self.assertNotIn("estimated FPL", answer)

    def test_charity_care_definition_takes_priority_over_fpl_history(self):
        history = [
            {
                "role": "user",
                "content": "My family household size is 5 and my annual household income is $120,000",
            }
        ]

        answer = _direct_charity_care_definition_answer(
            "What is Cedars-Sinai Charity Care?"
        )
        fpl_answer = _direct_fpl_answer("What is Cedars-Sinai Charity Care?", history)

        self.assertIn("financial-assistance option", answer)
        self.assertIn("310.2%", fpl_answer)
        self.assertNotIn("310.2%", answer)

    def test_direct_charity_care_coverage_answer_does_not_recalculate_fpl(self):
        answer = _direct_charity_care_coverage_answer(
            "Will they pay for all of my bill if I qualify?"
        )

        self.assertIn("**Summary**", answer)
        self.assertIn("does not automatically mean the entire bill", answer)
        self.assertIn("What To Ask Cedars-Sinai", answer)
        self.assertIn("pause activity", answer)
        self.assertNotIn("estimated FPL", answer)
        self.assertNotIn("310.2%", answer)

    def test_direct_billing_website_answer_gives_actual_link(self):
        answer = _direct_billing_website_answer("Where is their online portal?")

        self.assertIn("**Billing Website**", answer)
        self.assertIn("https://www.cedars-sinai.org/patients-visitors/billing.html", answer)
        self.assertIn("866-803-1777", answer)
        self.assertIn("patient.billing@cshs.org", answer)
        self.assertNotIn("search for", answer.lower())

    def test_direct_payment_plan_answer_is_cedars_specific(self):
        answer = _direct_payment_plan_answer("How do I set up a payment plan?")

        self.assertIn("**How**", answer)
        self.assertIn("**What To Say**", answer)
        self.assertIn("**What You May Need**", answer)
        self.assertIn("866-803-1777", answer)
        self.assertIn("estimate your FPL percentage", answer)

    def test_direct_call_prep_lists_specific_bill_fields(self):
        answer = _direct_call_prep_answer(
            "What information might I need if I contact them?"
        )

        self.assertIn("**What You May Need**", answer)
        self.assertIn("Patient account number", answer)
        self.assertIn("Guarantor name", answer)
        self.assertIn("Statement date", answer)
        self.assertIn("Service date", answer)
        self.assertIn("CPT, HCPCS, or revenue codes", answer)
        self.assertIn("Explanation of Benefits", answer)
        self.assertIn("official phone number", answer)

    def test_direct_legal_boundary_answer_stays_practical(self):
        answer = _direct_legal_boundary_answer("Can I sue them for this?")

        self.assertIn("I can’t give legal advice", answer)
        self.assertIn("Contact Cedars-Sinai Patient Financial Services", answer)
        self.assertIn("Explanation of Benefits", answer)
        self.assertIn("qualified legal professional", answer)
        self.assertIn("866-803-1777", answer)

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

    def test_removes_redaction_placeholders_from_response_text(self):
        model_text = (
            "Have your bill handy, including the service date, patient name, "
            "and the [REDACTED:PATIENT_ACCOUNT]."
        )

        cleaned = _clean_internal_tool_text(model_text)

        self.assertIn("patient account number shown on the bill", cleaned)
        self.assertNotIn("[REDACTED:", cleaned)


if __name__ == "__main__":
    unittest.main()
