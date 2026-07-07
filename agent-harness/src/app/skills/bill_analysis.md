# Skill: Bill Analysis

## Purpose
Enables the agent to correctly identify when a patient's question requires parsing an uploaded bill, and to call the bill_parser tool to extract accurate structured data before answering.

## When to Use
- A patient has uploaded a bill (PDF or image) in the current conversation and asks any question about it (charges, balance, what something means, etc.)
- The patient references "my bill," "this charge," "what I owe," or similar, and a bill has been uploaded but not yet parsed in this conversation

## Instructions
1. If a bill has been uploaded but not yet parsed in this conversation, call bill_parser before responding to any question about its contents.
2. Never answer questions about specific charges, amounts, or line items from memory or general knowledge — always ground the answer in bill_parser's actual output.
3. If bill_parser fails or returns no usable data, say so plainly and ask the patient to try re-uploading, rather than guessing or fabricating numbers.
4. Once bill_parser has successfully returned data, hand off to the bill_explanation skill for how to present it.

## Output Format
This skill governs tool-calling behavior, not response formatting — see bill_explanation.md for how to present results to the patient.

## Constraints
- Never state a dollar amount, billing code, or line item that did not come from bill_parser's output.
- Do not re-parse a bill that has already been successfully parsed in the current conversation unless the patient uploads a new file.
