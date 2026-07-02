"""Tool for estimating Federal Poverty Level percentage.

The result is a screening estimate only. It helps the agent explain possible
financial-assistance next steps without confirming eligibility or approval.
"""

from __future__ import annotations

import json

from agent_harness import tool

FPL_YEAR = 2026
FPL_BASE_USD = 15_960
FPL_ADDITIONAL_PERSON_USD = 5_680


@tool(
    name="calculate_fpl_percentage",
    description=(
        "Estimate a patient's Federal Poverty Level percentage from annual "
        "household income and household size. Use this only after the user "
        "has provided both values. If either value is missing, ask the user "
        "for the missing information instead of calling this tool."
    ),
    parameters={
        "type": "object",
        "properties": {
            "annual_income_usd": {
                "type": "number",
                "description": "Current total annual household income in US dollars.",
                "minimum": 0,
            },
            "household_size": {
                "type": "integer",
                "description": "Number of people in the household.",
                "minimum": 1,
            },
        },
        "required": ["annual_income_usd", "household_size"],
    },
)
def calculate_fpl(args: dict) -> str:
    """Return estimated FPL percentage and possible assistance tier."""
    annual_income = args.get("annual_income_usd")
    household_size = args.get("household_size")

    if annual_income is None:
        return json.dumps({"error": "annual_income_usd is required"})

    if household_size is None:
        return json.dumps({"error": "household_size is required"})

    if isinstance(annual_income, bool) or not isinstance(annual_income, (int, float)):
        return json.dumps({"error": "annual_income_usd must be a number"})

    if annual_income < 0:
        return json.dumps({"error": "annual_income_usd cannot be negative"})

    if isinstance(household_size, bool) or not isinstance(household_size, int):
        return json.dumps({"error": "household_size must be a whole number"})

    if household_size < 1:
        return json.dumps({"error": "household_size must be at least 1"})

    fpl_100_percent = (
        FPL_BASE_USD
        + ((household_size - 1) * FPL_ADDITIONAL_PERSON_USD)
    )
    raw_percentage = annual_income / fpl_100_percent * 100
    fpl_percentage = round(raw_percentage, 1)
    fpl_percentage_precise = round(raw_percentage, 3)
    near_boundary = any(abs(raw_percentage - boundary) <= 1 for boundary in (400, 600))

    if raw_percentage <= 400:
        assistance_tier = "Charity Care candidate"
        guidance = "Consider applying for Cedars-Sinai Charity Care."
    elif raw_percentage <= 600:
        assistance_tier = "Discount Payment candidate"
        guidance = "Consider applying for the Cedars-Sinai Discount Payment program."
    else:
        assistance_tier = "Above standard FAP threshold"
        guidance = (
            "Ask Cedars-Sinai about payment plans and whether a hardship "
            "review is available."
        )

    if near_boundary:
        percentage_explanation = (
            f"The precise estimated FPL percentage is {fpl_percentage_precise}%. "
            f"The rounded display value is {fpl_percentage}%, but the tier should "
            "be interpreted using the precise estimate."
        )
    else:
        percentage_explanation = f"The estimated FPL percentage is {fpl_percentage}%."

    return json.dumps(
        {
            "fpl_year": FPL_YEAR,
            "annual_income_usd": annual_income,
            "household_size": household_size,
            "fpl_100_percent_usd": fpl_100_percent,
            "fpl_percentage": fpl_percentage,
            "fpl_percentage_precise": fpl_percentage_precise,
            "near_boundary": near_boundary,
            "percentage_explanation": percentage_explanation,
            "assistance_tier": assistance_tier,
            "guidance": guidance,
            "disclaimer": (
                "This is a screening estimate only and does not confirm "
                "financial-assistance eligibility or approval."
            ),
        }
    )
