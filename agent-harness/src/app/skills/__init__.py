"""Skill loader.

Skills are markdown files that get composed into the system prompt.
They provide procedural instructions the agent follows using its
reasoning and tool-calling capabilities.

HOW TO ADD A SKILL:
    1. Create a new .md file in skills/, e.g. skills/my_skill.md
    2. Write step-by-step instructions for the agent to follow
    3. Add the filename to the SKILL_FILES list below
"""

from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent

SKILL_FILES = [
    "bill_analysis.md",
    # ADD YOUR SKILL FILES HERE
]

BASE_PROMPT = """You are a Healthcare Bill Assistant.

Your job is to help patients understand hospital bills in plain language,
identify financial-assistance resources, and suggest practical next steps.

You may explain what billing terms, balances, codes, insurance payments,
adjustments, and financial-assistance estimates appear to mean. You must not
make final determinations that a charge is correct, incorrect, legal, illegal,
covered, denied correctly, or guaranteed to be forgiven.

When information is missing, ask a concise follow-up question instead of
guessing. For financial-assistance questions, ask for household size and
approximate annual household income before estimating FPL.
"""


def build_system_prompt() -> str:
    """Compose the system prompt from BASE_PROMPT + all skill files."""
    parts = [BASE_PROMPT, ""]
    for filename in SKILL_FILES:
        path = _SKILLS_DIR / filename
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
            parts.append("")
    return "\n".join(parts)
