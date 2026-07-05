"""PHI redaction hook.

This hook removes obvious patient identifiers from tool results before those
results are fed back into the language model. It intentionally focuses on
patient-specific identifiers and avoids blanket phone-number redaction so the
agent can still provide Cedars-Sinai Patient Services contact information.
"""

from __future__ import annotations

import re
from typing import Any

from agent_harness import Hook, HookResult


class PHIRedactionHook(Hook):
    """Redact common PHI patterns from tool arguments and results."""

    def __init__(self) -> None:
        self.sensitive_keys = {
            "account_number",
            "date_of_birth",
            "dob",
            "email",
            "guarantor_account_number",
            "guarantor_name",
            "medical_record_number",
            "mrn",
            "patient_account_number",
            "patient_name",
            "patient_phone",
            "phone_number",
            "ssn",
        }
        self.patterns: list[tuple[str, re.Pattern]] = [
            ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
            (
                "MRN",
                re.compile(
                    r"\b(?:MRN|medical record number)\s*(?:is|=|:|#|-)?\s*[A-Z0-9-]{5,20}\b",
                    re.IGNORECASE,
                ),
            ),
            (
                "DOB",
                re.compile(
                    r"\b(?:DOB|date of birth)\s*(?:is|=|:|#|-)?\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
                    re.IGNORECASE,
                ),
            ),
            (
                "EMAIL",
                re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
            ),
            (
                "PATIENT_PHONE",
                re.compile(
                    r"\b(?:patient|guarantor)\s*(?:phone|telephone|mobile|cell)[:\s#-]*(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
                    re.IGNORECASE,
                ),
            ),
            (
                "PATIENT_ACCOUNT",
                re.compile(
                    r"\b(?:patient\s*)?account(?:\s*number|\s*#)?[:\s#-]*[A-Z0-9-]{5,30}\b",
                    re.IGNORECASE,
                ),
            ),
            (
                "GUARANTOR_ACCOUNT",
                re.compile(
                    r"\bguarantor\s*(?:account\s*)?(?:number|#)?[:\s#-]*[A-Z0-9-]{5,30}\b",
                    re.IGNORECASE,
                ),
            ),
            (
                "JSON_PATIENT_NAME",
                re.compile(r'("(?:patient|guarantor)_name"\s*:\s*")([^"]+)(")', re.IGNORECASE),
            ),
            (
                "JSON_ACCOUNT_NUMBER",
                re.compile(
                    r'("(?:(?:patient|guarantor)_)?account_number"\s*:\s*")([^"]+)(")',
                    re.IGNORECASE,
                ),
            ),
        ]

    def before_tool_call(self, tool_name: str, args: dict[str, Any]) -> HookResult:
        """Redact PHI in tool arguments while preserving filenames/paths."""
        redacted_args = {
            key: self._redact_argument(key, value)
            for key, value in args.items()
        }
        return HookResult(allowed=True, modified_args=redacted_args)

    def after_tool_call(self, tool_name: str, args: dict[str, Any], result: str) -> str:
        """Redact PHI from tool output before it reaches the model."""
        return self.redact(result)

    def redact(self, value: Any) -> Any:
        """Redact PHI in strings, lists, and dictionaries."""
        if isinstance(value, str):
            return self._redact_text(value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            return {
                key: (
                    f"[REDACTED:{self._redaction_label_for_key(key)}]"
                    if self._is_sensitive_key(key)
                    else self.redact(item)
                )
                for key, item in value.items()
            }
        return value

    def _redact_text(self, text: str) -> str:
        redacted = text
        for pattern_name, pattern in self.patterns:
            if pattern_name.startswith("JSON_"):
                redacted = pattern.sub(rf"\1[REDACTED:{pattern_name}]\3", redacted)
            else:
                redacted = pattern.sub(f"[REDACTED:{pattern_name}]", redacted)
        return redacted

    def _is_sensitive_key(self, key: str) -> bool:
        normalized = key.lower().strip()
        return normalized in self.sensitive_keys

    def _redaction_label_for_key(self, key: str) -> str:
        return key.upper()

    def _redact_argument(self, key: str, value: Any) -> Any:
        if key in {"file_path", "path", "filename"}:
            return value
        if self._is_sensitive_key(key):
            return f"[REDACTED:{self._redaction_label_for_key(key)}]"
        return self.redact(value)
