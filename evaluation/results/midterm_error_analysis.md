# Midterm Error Analysis

This summary is based on `midterm_agent_evaluation_scoring.csv`, which contains
28 live-agent evaluations scored by human reviewers with LLM assistance.

## Dataset Coverage

- Total evaluated cases: 28
- Financial Assistance: 10
- Billing Understanding: 10
- Action Planning: 4
- Safety: 2
- Document Parsing: 2

## Score Summary

- Semantic correctness average: 0.749; reviewer pass rate: 22 of 28
- Groundedness average: 0.869; reviewer pass rate: 25 of 28
- Required coverage average: 0.596; reviewer pass rate: 11 of 28
- Hallucination cases: 2 of 28
- Text differentiation average: 4.0 out of 5; reviewer pass rate: 22 of 28
- Safety pass rate: 23 of 28
- Overall pass rate: 21 of 28

## Main Error Patterns

### 1. Required Coverage Was The Largest Gap

The agent often answered with correct facts but missed required case-specific
next steps. Common omissions included:

- Tell the patient not to pay until a suspicious balance is verified.
- Ask Cedars-Sinai to pause collections or place a balance on hold during
  review.
- Compare the bill with an Explanation of Benefits (EOB).
- Ask about FAP/Charity Care when the case suggests affordability support.
- Give a specific documentation checklist.

Recommended fix:

- Strengthen prompt rules and regression tests for required next steps by case
  category.

### 2. Some Responses Were Grounded But Too Generic

Several responses stayed safe and mostly factual, but did not use the most
important fact pattern in the case. Examples include:

- Work-related injury cases where Workers Comp paid the full balance.
- TRICARE or zero-balance cases where the agent should clearly say no payment
  is due.
- Medi-Cal cases where a patient balance may be unusual and should be verified
  before payment.

Recommended fix:

- Add scenario-specific guidance for zero-balance, Workers Comp, Medi-Cal,
  coordination-of-benefits, and denied/out-of-network cases.

### 3. Hallucination Was Infrequent But High Impact

The evaluation found 2 hallucination cases. The most important pattern was the
agent inventing household income or household size when the patient did not
provide it.

Recommended fix:

- Add regression tests that confirm the agent asks for missing household size
  and income instead of inventing values.
- Keep FPL calculation deterministic and tool-grounded.

### 4. Safety Failures Were Mostly Boundary Issues

Safety failures were not usually from malicious behavior. They were mostly cases
where the agent should have been more explicit about limits:

- Do not decide whether a bill is correct, invalid, illegal, or legally owed.
- Do not advise payment before verification when the case is suspicious.
- Do not provide final insurance coverage determinations.

Recommended fix:

- Continue expanding deterministic safety helpers for repeated high-risk
  phrasings.
- Pair each safety helper with a regression test.

### 5. Document Parsing Errors Affect Downstream Quality

The document parsing cases showed that when extracted bill text is ambiguous,
the agent needs to avoid guessing and explain what needs verification. This was
handled well in some cases, but parsing quality remains a key dependency.

Recommended fix:

- Continue parser tests for line-item math, service dates, payer fields, and
  image/PDF extraction.
- Add parser-level checks before prompt-level fixes when the source data is
  wrong or incomplete.

## Recommended Backlog

1. Add required-next-step templates by category.
2. Add no-pay-before-verification guidance for suspicious balances.
3. Add FPL missing-input regression tests.
4. Strengthen zero-balance and Workers Comp handling.
5. Add Medi-Cal balance verification guidance.
6. Continue parser regression tests for new document formats.
