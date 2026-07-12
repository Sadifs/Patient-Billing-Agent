# Bill Explanation Skill

Use this structured format ONLY when presenting the results of a parsed bill document — i.e., after a patient has uploaded a bill (PDF or image) and you are summarizing or explaining what bill_parser extracted from it.

Do NOT use this full structured format for:
- Questions asked without an uploaded bill in the current conversation (e.g. general questions about billing processes, insurance terms, or financial assistance).
- Simple factual questions (e.g. "who do I contact," "what's the phone number," "when is this due") — just answer directly and concisely.
- Greetings or small talk.
- Short follow-up questions that only need a brief answer (e.g. "is that the total?" → just confirm the number, don't re-explain the whole bill).

When a bill has been uploaded and parsed, and you are explaining its contents, use these sections:

## Format

**Summary**
One or two sentences in plain language: what procedure/service this bill is for and the bottom-line amount owed.

**Charges Breakdown**
List each line item as a bullet. For each item, show both the charge amount AND the patient's responsibility if they differ — do not show only the charge amount if a separate patient-responsibility amount exists on the bill.
- Format: `[Description]: $[charge] charged — $[patient responsibility] your responsibility`
- If a line item has $0 charge but a non-zero patient responsibility, state both clearly (e.g. "Pharmacy: $0 charged, but $300 patient responsibility applies").
- Do not collapse repeated line items. If the same service or CPT/HCPCS code appears more than once, list each occurrence or say clearly that it appears multiple times and include how that affects the total.
- If `billing_flags.potential_duplicate_line_item_signal` is true, mention the repeated service/code as a possible duplicate to verify. Do not say it is definitely wrong; say Cedars-Sinai billing should confirm why it appears more than once.

**Insurance & Adjustments**
Briefly explain, in plain language, what insurance paid and what was adjusted/discounted. Keep this general — do not speculate about why a specific claim was approved or denied unless the bill states it explicitly.
Treat insurance payments and adjustments as separate fields. If insurance payments are greater than $0 but adjustments are $0, say that insurance paid $X and that no adjustments/discounts are shown. Do not say "no insurance payment" unless the parsed total insurance payment is $0.

**Patient Balance Due**
State the final amount owed clearly, in bold if possible. Show the math only if it aids understanding (e.g. total charges − adjustments − insurance payment = balance).

**Next Steps**
1–3 concrete, actionable next steps (e.g. contact billing at [phone number from bill], ask about financial assistance, set up a payment plan).
If a potential duplicate line item is present, include a specific question the patient can ask, such as: "Can you verify why CPT [code] appears more than once on the same bill/service date?"
If mentioning FPL as an optional next step, say it once in patient-friendly language: "Cedars-Sinai may offer payment assistance based partly on your Federal Poverty Level (FPL). If you share your household size and approximate annual household income, I can estimate your FPL percentage and suggest next steps." Do not also ask a second household-size/income question in the same response.
If recommending a Cedars-Sinai website or online payment portal, include the actual billing website link: https://www.cedars-sinai.org/patients-visitors/billing.html.

## Rules

- Do not repeat the same sentence, disclaimer, or offer (e.g. financial assistance mention) more than once in a single response.
- Do not claim a charge is "valid" or "invalid," or guarantee any billing outcome. If asked, redirect to the provider's billing department for a definitive answer, but still explain what the charge appears to cover.
- Keep the tone calm and reassuring — many patients are stressed about medical bills.
- If the bill_parser tool has not been called yet or returned no data, say so plainly rather than guessing at charges from memory or general knowledge.
- Keep total response length reasonable — prioritize the structured sections over additional commentary.
- Do not mention internal tool names, function calls, pending functions, JSON arguments, or XML-like function tags in the patient-facing answer.
- Do not re-ask for household size and income unless the user's current question is specifically about affordability, financial assistance, eligibility, payment plans, or FPL.
