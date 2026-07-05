"""Scope and safety guard for tool calls.

The billing assistant may explain bills, estimate FPL, search billing policy,
and suggest next steps. It should not use tools to support requests that ask
for medical advice, legal conclusions, insurance coverage determinations, or
other actions outside the capstone scope.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_harness import Hook, HookResult

logger = logging.getLogger(__name__)


class ContentFilterHook(Hook):
    """Block tool calls whose arguments suggest an out-of-scope request."""

    def __init__(self, blocked_terms: list[str] | None = None) -> None:
        default_terms = [
            # Medical diagnosis/treatment.
            "diagnose",
            "diagnosis",
            "treatment plan",
            "should i take",
            "medication dosage",
            "medical advice",
            # Legal conclusions.
            "legal advice",
            "sue",
            "lawsuit",
            "malpractice",
            "illegal",
            "violate the law",
            # Final billing/coverage determinations.
            "definitely correct",
            "definitely incorrect",
            "prove this charge is wrong",
            "is this charge valid",
            "guarantee approval",
            "guarantee forgiveness",
            "coverage decision",
            "claim is valid",
            "claim is invalid",
            # Data exposure or unsafe handling.
            "social security number",
            "full date of birth",
            "bank account",
            "credit card",
            "password",
            "api key",
        ]
        self.blocked_terms = [t.lower() for t in (blocked_terms or default_terms)]

    def before_tool_call(self, tool_name: str, args: dict[str, Any]) -> HookResult:
        """Block tool use for requests the agent should not fulfill."""
        args_str = str(args).lower()
        for term in self.blocked_terms:
            if term in args_str:
                return HookResult(
                    allowed=False,
                    reason=(
                        "This request is outside the billing assistant's scope. "
                        "I can explain bill information, estimate financial-"
                        "assistance screening, and suggest questions to ask "
                        "Cedars-Sinai or an insurer, but I cannot make medical, "
                        "legal, coverage, or final charge-validity decisions."
                    ),
                )
        return HookResult(allowed=True)
