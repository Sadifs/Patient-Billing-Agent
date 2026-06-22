"""Safety and scope guard hook for patient billing tool calls.

The patient billing agent can explain bills, surface financial-assistance
resources, and suggest next steps. It should not use tools to produce legal or
medical advice, determine whether a charge is correct, guarantee eligibility,
or follow prompt-injection instructions.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agent_harness import Hook, HookResult

logger = logging.getLogger(__name__)


class SafetyScopeGuardHook(Hook):
    """Block tool calls that would push the agent outside project scope."""

    DEFAULT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
        (
            "prompt_injection",
            re.compile(
                r"\b(ignore|forget|override)\b.{0,40}\b(previous|prior|system|developer)\b.{0,40}\b(instruction|prompt|message|rule)s?\b",
                re.IGNORECASE,
            ),
            "I cannot follow instructions that ask me to ignore or override system rules.",
        ),
        (
            "system_prompt_extraction",
            re.compile(r"\b(system prompt|developer message|hidden instructions|reveal your instructions)\b", re.IGNORECASE),
            "I cannot reveal or use hidden system instructions.",
        ),
        (
            "destructive_operation",
            re.compile(r"\b(drop\s+table|delete\s+from|truncate\s+table|rm\s+-rf|curl\s+.+\|\s*sh)\b", re.IGNORECASE),
            "I cannot run or assist with destructive operations.",
        ),
        (
            "charge_correctness_determination",
            re.compile(
                r"\b(?:is|are|was|were|tell me if|determine if|prove)\b.{0,40}\b(charge|charges|bill|billing|coded|code)\b.{0,40}\b(correct|incorrect|wrong|right|valid|invalid|fraudulent|illegal)\b",
                re.IGNORECASE,
            ),
            "I can explain bill terms and suggest verification steps, but I cannot determine whether a charge is correct, legal, or valid.",
        ),
        (
            "eligibility_guarantee",
            re.compile(
                r"\b(guarantee|confirm|promise|certify|approve|approved|definitely qualifies?|definitely eligible)\b.{0,50}\b(financial assistance|charity care|fap|discount|eligib|qualif)\b",
                re.IGNORECASE,
            ),
            "I can estimate likely assistance pathways, but I cannot guarantee eligibility or approval.",
        ),
        (
            "legal_advice",
            re.compile(
                r"\b(should i sue|can i sue|lawsuit|legal advice|statute of limitations|refuse to pay|ignore (?:the )?bill|do i legally have to pay)\b",
                re.IGNORECASE,
            ),
            "I can suggest billing-office questions and dispute options, but I cannot provide legal advice.",
        ),
        (
            "medical_advice",
            re.compile(
                r"\b(diagnose|diagnosis|prescribe|medication advice|medical advice|should i take|is this treatment necessary|was this medically necessary)\b",
                re.IGNORECASE,
            ),
            "I can explain billing language, but I cannot provide medical advice or decide medical necessity.",
        ),
    ]

    def __init__(
        self,
        blocked_terms: list[str] | None = None,
        extra_patterns: list[tuple[str, re.Pattern[str], str]] | None = None,
    ) -> None:
        self.blocked_terms = [term.lower() for term in (blocked_terms or [])]
        self.patterns = [*self.DEFAULT_PATTERNS, *(extra_patterns or [])]

    def before_tool_call(self, tool_name: str, args: dict[str, Any]) -> HookResult:
        """Block unsafe tool calls before tool execution."""
        args_text = self._flatten_args(args)
        lowered = args_text.lower()

        for term in self.blocked_terms:
            if term and term in lowered:
                logger.info("Blocked tool %s due to configured term %s", tool_name, term)
                return HookResult(
                    allowed=False,
                    reason=(
                        "This request is outside the patient billing agent's allowed scope. "
                        "I can explain bills, identify resources, and suggest next steps."
                    ),
                )

        for policy_name, pattern, reason in self.patterns:
            if pattern.search(args_text):
                logger.info("Blocked tool %s due to policy %s", tool_name, policy_name)
                return HookResult(allowed=False, reason=reason)

        return HookResult(allowed=True)

    def _flatten_args(self, value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(f"{key} {self._flatten_args(item)}" for key, item in value.items())
        if isinstance(value, (list, tuple, set)):
            return " ".join(self._flatten_args(item) for item in value)
        return str(value)


class ContentFilterHook(SafetyScopeGuardHook):
    """Backward-compatible name for the safety/scope guard hook."""
