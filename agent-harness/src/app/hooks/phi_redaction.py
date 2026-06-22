"""PHI redaction hook for patient billing workflows.

This hook redacts obvious Protected Health Information (PHI) from tool
arguments and tool results. It is intentionally pattern-based and conservative:
it catches high-risk identifiers such as SSNs, MRNs, account numbers, dates of
birth, phone numbers, and emails without trying to infer patient names.
"""

from __future__ import annotations

import re
from typing import Any

from agent_harness import Hook, HookResult


class PHIRedactionHook(Hook):
    """Redact common PHI patterns before and after tool execution."""

    def __init__(self) -> None:
        self.patterns: list[tuple[str, re.Pattern[str]]] = [
            ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
            (
                "DOB",
                re.compile(
                    r"\b(?:dob|date\s+of\s+birth|birth\s+date)"
                    r"\s*[:#-]?\s*"
                    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
                    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
                    re.IGNORECASE,
                ),
            ),
            (
                "MRN",
                re.compile(r"\b(?:mrn|medical\s+record\s*(?:number|#)?)\s*[:#-]?\s*[A-Z0-9-]{5,20}\b", re.IGNORECASE),
            ),
            (
                "ACCOUNT_NUMBER",
                re.compile(r"\b(?:account|acct)\s*(?:number|#|no\.?)?\s*[:#-]?\s*[A-Z0-9-]{5,24}\b", re.IGNORECASE),
            ),
            (
                "PHONE",
                re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)"),
            ),
            (
                "EMAIL",
                re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
            ),
        ]

    def before_tool_call(self, tool_name: str, args: dict[str, Any]) -> HookResult:
        """Redact PHI before tool arguments reach tools, logs, or RAG search."""
        redacted_args = self.redact_value(args)
        if redacted_args != args:
            return HookResult(allowed=True, modified_args=redacted_args)
        return HookResult(allowed=True)

    def after_tool_call(self, tool_name: str, args: dict[str, Any], result: str) -> str:
        """Redact PHI from tool output before it enters model context."""
        return self.redact_text(result)

    def redact_value(self, value: Any) -> Any:
        """Recursively redact strings inside dictionaries and lists."""
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {key: self.redact_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact_value(item) for item in value)
        return value

    def redact_text(self, text: str) -> str:
        redacted = text
        for pattern_name, pattern in self.patterns:
            redacted = pattern.sub(f"[REDACTED:{pattern_name}]", redacted)
        return redacted
