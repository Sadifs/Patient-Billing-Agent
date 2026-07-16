"""
generate_v2_bills.py
====================
Synthetic Bill Generator — V2
LMU MSBA × Cedars-Sinai Patient Billing Agent

WARNING: This script generates bills 01–15 (Aziza's bills) only.
Re-running it will OVERWRITE the evaluator JSONs in synthetic_bills_v2/
and will LOSE the _eval_metadata blocks added in PR #13 (July 2026).
If you must regenerate, re-add _eval_metadata from synthetic_validation_dataset.csv
before committing. See PR #13 for the field structure.

What V2 fixes vs V1
--------------------
1. Every JSON bill now mirrors real Cedars-style patient statement fields
   (Patient Account Number, Patient Name, Service Date, Guarantor block,
   Summary of Services with Billed/Pmts/Adjs/Balance, Total Amount Due,
   Primary Insurance, Secondary Insurance, Patient Services contact).
2. NO evaluation metadata in the bill JSON — no flags, FAP eligibility,
   FPL %, safety constraints, or case notes. Bills are what a patient
   would receive; ground truth lives only in the validation CSV.
3. Math is verified: Total Amount Due == Patient Balance (or the bill is
   explicitly flagged as intentionally incorrect in the CSV, NOT in JSON).
4. Expanded insurance taxonomy:
     Commercial sub-types: PPO, HMO, EPO, HDHP/HSA, POS
     Medicare sub-types: Part A+B (Traditional), Medicare + Medigap,
                         Medicare + Medicaid (Dual Eligible), IRMAA tiers
     Medicare Advantage sub-types: HMO-MA, PPO-MA, PFFS-MA, SNP-MA
     Medicaid sub-types: Medi-Cal (standard), Medi-Cal Share of Cost,
                         Medi-Cal Pending, Dual Eligible (Medi-Medi)
     Other: Uninsured/Self-Pay, TRICARE, Workers Comp, VA/CHAMPVA
5. Guarantor block added (Guarantor Name + Guarantor Number).
6. Patient Services contact on every bill.

Reproduction
------------
    cd synthetic-data/
    python3 generate_v2_bills.py

Writes two bill directories:
    synthetic_bills_v2/        — evaluator copies (full metadata)
    synthetic_bills_v2_agent/  — LLM input (_schema_version, _note, _intentional_error_note stripped)

Requires: json, os (stdlib only — no external deps for JSON generation).
Requires reportlab for PDF rendering (separate step).
"""

import json
import os
from decimal import Decimal, ROUND_HALF_UP

# ── OUTPUT PATHS ──────────────────────────────────────────────────────────────
SRC = os.path.dirname(os.path.abspath(__file__))
BILLS_OUT = os.path.join(SRC, "synthetic_bills_v2")  # evaluator copies (full metadata)
BILLS_AGENT_OUT = os.path.join(SRC, "synthetic_bills_v2_agent")  # LLM/agent input (stripped)
os.makedirs(BILLS_OUT, exist_ok=True)
os.makedirs(BILLS_AGENT_OUT, exist_ok=True)

# Keys removed from agent-facing JSON — ground truth / evaluator notes only
AGENT_STRIP_KEYS = ("_schema_version", "_note", "_intentional_error_note")

# ── FPL 2026 ─────────────────────────────────────────────────────────────────
FPL = {1: 15960, 2: 21640, 3: 27320, 4: 33000, 5: 38680, 6: 44360}


def cents(x):
    """Round to 2 decimal places."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def bill_for_agent(bill):
    """Return a copy safe to pass to the LLM (no evaluator metadata)."""
    return {k: v for k, v in bill.items() if k not in AGENT_STRIP_KEYS}


def patient_services_block():
    """Standard Cedars-Sinai Patient Services contact — appears on every bill."""
    return {
        "department": "Patient Financial Services",
        "phone": "310-423-8000",
        "hours": "Monday–Friday, 8:00 AM – 5:00 PM PT",
        "online": "https://www.cedars-sinai.org/patients-visitors/billing.html",
        "mail": "Cedars-Sinai Medical Center, P.O. Box 48750, Los Angeles, CA 90048",
    }


def build_bill(
    bill_id,
    patient_name,
    patient_account_number,
    guarantor_name,
    guarantor_number,
    service_date,
    service_description,
    primary_insurance,
    secondary_insurance,
    line_items,
    insurance_payments,
    adjustments,
    statement_date,
    due_date,
    intentionally_incorrect=False,
    incorrect_reason=None,
):
    """
    Build a clean patient-facing bill JSON.

    Parameters
    ----------
    line_items : list of dict with keys:
        service_name, cpt_or_revenue_code, code_type ("CPT"|"HCPCS"|"Revenue"),
        billed_amount, quantity (optional, default 1), unit (optional)
    insurance_payments : list of dict with keys:
        payer_name, payment_amount, payment_date, check_or_ref_number (optional)
    adjustments : list of dict with keys:
        description ("Contractual Adjustment"|"Write-Off"|etc.), amount (positive = reduction)
    intentionally_incorrect : bool
        If True, math may NOT balance. Used to test agent's error-detection.
        This flag is NOT included in the bill JSON — it lives in the CSV only.
    """

    total_billed = cents(sum(li["billed_amount"] for li in line_items))
    total_insurance_paid = cents(sum(p["payment_amount"] for p in insurance_payments))
    total_adjustments = cents(sum(a["amount"] for a in adjustments))
    patient_balance = cents(total_billed - total_insurance_paid - total_adjustments)
    total_amount_due = patient_balance  # should equal patient_balance unless intentionally_incorrect

    # Summary of Services rows
    summary_rows = []
    for li in line_items:
        row = {
            "service_name": li["service_name"],
            "code_type": li.get("code_type", "CPT"),
            "code": li.get("cpt_or_revenue_code", ""),
            "quantity": li.get("quantity", 1),
            "unit": li.get("unit", "each"),
            "billed_amount": cents(li["billed_amount"]),
            "insurance_payments": cents(
                li.get("insurance_payment_allocated", 0)
            ),
            "adjustments": cents(li.get("adjustment_allocated", 0)),
            "patient_balance": cents(
                li["billed_amount"]
                - li.get("insurance_payment_allocated", 0)
                - li.get("adjustment_allocated", 0)
            ),
        }
        summary_rows.append(row)

    bill = {
        "_schema_version": "2.0",
        "_note": (
            "This is a synthetic patient billing statement for evaluation purposes. "
            "No real PHI. Generated by LMU MSBA × Cedars-Sinai capstone team."
        ),
        # ── HEADER ──────────────────────────────────────────────────────────
        "facility": {
            "name": "Cedars-Sinai Medical Center",
            "address": "8700 Beverly Blvd, Los Angeles, CA 90048",
            "npi": "1316230813",
            "tax_id": "95-2123461",
        },
        "statement_date": statement_date,
        "due_date": due_date,
        # ── PATIENT ─────────────────────────────────────────────────────────
        "patient": {
            "patient_name": patient_name,
            "patient_account_number": patient_account_number,
            "service_date": service_date,
        },
        # ── GUARANTOR ───────────────────────────────────────────────────────
        "guarantor": {
            "guarantor_name": guarantor_name,
            "guarantor_account_number": guarantor_number,
        },
        # ── INSURANCE ───────────────────────────────────────────────────────
        "insurance": {
            "primary": primary_insurance,   # e.g. "Medicare Part A+B" or "None on file"
            "secondary": secondary_insurance,  # e.g. "Medigap Plan G" or "None on file"
        },
        # ── SUMMARY OF SERVICES ─────────────────────────────────────────────
        "summary_of_services": {
            "line_items": summary_rows,
            "totals": {
                "total_billed": total_billed,
                "total_insurance_payments": total_insurance_paid,
                "total_adjustments": total_adjustments,
                "outstanding_balance": patient_balance,
                "patient_balance": patient_balance,
            },
        },
        # ── PAYMENT DETAIL ─────────────────────────────────────────────────
        "payment_detail": {
            "insurance_payments": insurance_payments,
            "adjustments": adjustments,
        },
        # ── AMOUNT DUE ─────────────────────────────────────────────────────
        "total_amount_due": total_amount_due,
        # ── CONTACT ─────────────────────────────────────────────────────────
        "patient_services": patient_services_block(),
    }
    return bill


# ═══════════════════════════════════════════════════════════════════════════════
# BILL DEFINITIONS
# Each bill: clean patient-facing JSON only.
# Ground truth (FPL %, flags, safety constraints) is in the CSV, NOT here.
# ═══════════════════════════════════════════════════════════════════════════════

bills = []

# ─── BILL 01 ── Self-Pay ER Visit ─────────────────────────────────────────────
bills.append(
    build_bill(
        bill_id="bill_v2_selfpay_er_01",
        patient_name="Maria Gutierrez",
        patient_account_number="CS-2026-00441",
        guarantor_name="Maria Gutierrez",
        guarantor_number="GU-2026-00441",
        service_date="2026-03-15",
        service_description="Emergency Department Visit",
        primary_insurance="None on file",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Emergency Department – Level 4",
                "cpt_or_revenue_code": "99284",
                "code_type": "CPT",
                "billed_amount": 3200.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "CT Scan – Abdomen/Pelvis with contrast",
                "cpt_or_revenue_code": "74177",
                "code_type": "CPT",
                "billed_amount": 5800.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Comprehensive Metabolic Panel",
                "cpt_or_revenue_code": "80053",
                "code_type": "CPT",
                "billed_amount": 620.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "IV Administration – Initial Hour",
                "cpt_or_revenue_code": "96365",
                "code_type": "CPT",
                "billed_amount": 480.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Normal Saline 1000mL (IV Fluid)",
                "cpt_or_revenue_code": "J7030",
                "code_type": "HCPCS",
                "quantity": 2,
                "unit": "bag",
                "billed_amount": 300.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Pharmacy – Ondansetron 4mg injection",
                "cpt_or_revenue_code": "J2405",
                "code_type": "HCPCS",
                "quantity": 1,
                "unit": "dose",
                "billed_amount": 200.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Medical/Surgical Supplies",
                "cpt_or_revenue_code": "0270",
                "code_type": "Revenue",
                "billed_amount": 400.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Emergency Room Facility Fee",
                "cpt_or_revenue_code": "0450",
                "code_type": "Revenue",
                "billed_amount": 8000.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[],
        adjustments=[],
        statement_date="2026-04-01",
        due_date="2026-05-01",
    )
)

# ─── BILL 02 ── Self-Pay Inpatient Surgery ────────────────────────────────────
bills.append(
    build_bill(
        bill_id="bill_v2_selfpay_inpatient_02",
        patient_name="James Whitfield",
        patient_account_number="CS-2026-00882",
        guarantor_name="James Whitfield",
        guarantor_number="GU-2026-00882",
        service_date="2026-02-10",
        service_description="Inpatient – Laparoscopic Appendectomy (2 days)",
        primary_insurance="None on file",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Operating Room – Facility Fee",
                "cpt_or_revenue_code": "0360",
                "code_type": "Revenue",
                "billed_amount": 12400.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Laparoscopic Appendectomy",
                "cpt_or_revenue_code": "44950",
                "code_type": "CPT",
                "billed_amount": 18000.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Anesthesia – Appendectomy (32 units)",
                "cpt_or_revenue_code": "00840",
                "code_type": "CPT",
                "quantity": 32,
                "unit": "unit",
                "billed_amount": 4800.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Room & Board – Medical/Surgical (2 days)",
                "cpt_or_revenue_code": "0110",
                "code_type": "Revenue",
                "quantity": 2,
                "unit": "day",
                "billed_amount": 9600.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Recovery Room",
                "cpt_or_revenue_code": "0710",
                "code_type": "Revenue",
                "billed_amount": 3200.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Laboratory – Complete Blood Count",
                "cpt_or_revenue_code": "85025",
                "code_type": "CPT",
                "billed_amount": 480.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Laboratory – Basic Metabolic Panel",
                "cpt_or_revenue_code": "80048",
                "code_type": "CPT",
                "billed_amount": 520.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Pharmacy – Ceftriaxone 250mg injection x2",
                "cpt_or_revenue_code": "J0696",
                "code_type": "HCPCS",
                "quantity": 2,
                "unit": "dose",
                "billed_amount": 450.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Pharmacy – Morphine Sulfate 4mg injection",
                "cpt_or_revenue_code": "J2270",
                "code_type": "HCPCS",
                "quantity": 3,
                "unit": "dose",
                "billed_amount": 390.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Medical/Surgical Supplies",
                "cpt_or_revenue_code": "0270",
                "code_type": "Revenue",
                "billed_amount": 1360.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[],
        adjustments=[],
        statement_date="2026-03-01",
        due_date="2026-04-01",
    )
)

# ─── BILL 03 ── Commercial PPO – Outpatient ───────────────────────────────────
# Gross charges high; contractual adjustment large; patient owes deductible only
bills.append(
    build_bill(
        bill_id="bill_v2_commercial_ppo_outpatient_03",
        patient_name="David Chen",
        patient_account_number="CS-2026-01154",
        guarantor_name="David Chen",
        guarantor_number="GU-2026-01154",
        service_date="2026-03-22",
        service_description="Outpatient – Knee MRI & Orthopedic Consult",
        primary_insurance="Anthem Blue Cross PPO",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "MRI – Knee with and without contrast",
                "cpt_or_revenue_code": "73723",
                "code_type": "CPT",
                "billed_amount": 8200.00,
                "insurance_payment_allocated": 6500.00,
                "adjustment_allocated": 1400.00,
            },
            {
                "service_name": "Office/Outpatient Visit – New Patient Level 4",
                "cpt_or_revenue_code": "99204",
                "code_type": "CPT",
                "billed_amount": 2600.00,
                "insurance_payment_allocated": 2000.00,
                "adjustment_allocated": 450.00,
            },
            {
                "service_name": "Radiology Professional Read – MRI Knee",
                "cpt_or_revenue_code": "73723-26",
                "code_type": "CPT",
                "billed_amount": 1400.00,
                "insurance_payment_allocated": 1100.00,
                "adjustment_allocated": 150.00,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Anthem Blue Cross PPO",
                "payment_amount": 9600.00,
                "payment_date": "2026-04-10",
                "check_or_ref_number": "ANTHEM-2026-84421",
            }
        ],
        adjustments=[
            {
                "description": "Contractual Adjustment – Anthem Blue Cross PPO Network Rate",
                "amount": 2000.00,
            }
        ],
        statement_date="2026-04-15",
        due_date="2026-05-15",
    )
)

# ─── BILL 04 ── Commercial HDHP – Inpatient + OON Anesthesia (NSA scenario) ──
bills.append(
    build_bill(
        bill_id="bill_v2_commercial_hdhp_inpatient_oon_anesthesia_04",
        patient_name="Rachel Torres",
        patient_account_number="CS-2026-02271",
        guarantor_name="Rachel Torres",
        guarantor_number="GU-2026-02271",
        service_date="2026-04-03",
        service_description="Inpatient – Knee Replacement Surgery (3 days)",
        primary_insurance="UnitedHealthcare Choice Plus HDHP",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Operating Room – Facility Fee",
                "cpt_or_revenue_code": "0360",
                "code_type": "Revenue",
                "billed_amount": 15600.00,
                "insurance_payment_allocated": 12800.00,
                "adjustment_allocated": 1800.00,
            },
            {
                "service_name": "Total Knee Arthroplasty (primary)",
                "cpt_or_revenue_code": "27447",
                "code_type": "CPT",
                "billed_amount": 28000.00,
                "insurance_payment_allocated": 23000.00,
                "adjustment_allocated": 3000.00,
            },
            {
                "service_name": "Room & Board – Medical/Surgical (3 days)",
                "cpt_or_revenue_code": "0110",
                "code_type": "Revenue",
                "quantity": 3,
                "unit": "day",
                "billed_amount": 14400.00,
                "insurance_payment_allocated": 11800.00,
                "adjustment_allocated": 1600.00,
            },
            {
                "service_name": "Anesthesia – Knee Arthroplasty (OON – Pacific Anesthesia Group)",
                "cpt_or_revenue_code": "01402",
                "code_type": "CPT",
                "quantity": 24,
                "unit": "unit",
                "billed_amount": 6800.00,
                "insurance_payment_allocated": 2000.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Recovery Room",
                "cpt_or_revenue_code": "0710",
                "code_type": "Revenue",
                "billed_amount": 3800.00,
                "insurance_payment_allocated": 3100.00,
                "adjustment_allocated": 400.00,
            },
            {
                "service_name": "Physical Therapy – Initial Evaluation",
                "cpt_or_revenue_code": "97161",
                "code_type": "CPT",
                "billed_amount": 1200.00,
                "insurance_payment_allocated": 980.00,
                "adjustment_allocated": 120.00,
            },
            {
                "service_name": "Laboratory & Pathology",
                "cpt_or_revenue_code": "0300",
                "code_type": "Revenue",
                "billed_amount": 940.00,
                "insurance_payment_allocated": 770.00,
                "adjustment_allocated": 70.00,
            },
            {
                "service_name": "Medical/Surgical Supplies – Implant (Knee Prosthesis)",
                "cpt_or_revenue_code": "0278",
                "code_type": "Revenue",
                "billed_amount": 8200.00,
                "insurance_payment_allocated": 6700.00,
                "adjustment_allocated": 700.00,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "UnitedHealthcare Choice Plus HDHP",
                "payment_amount": 61150.00,
                "payment_date": "2026-05-01",
                "check_or_ref_number": "UHC-2026-993412",
            }
        ],
        adjustments=[
            {
                "description": "Contractual Adjustment – UnitedHealthcare Network Rate",
                "amount": 7690.00,
            }
        ],
        statement_date="2026-05-10",
        due_date="2026-06-10",
    )
)

# ─── BILL 05 ── Traditional Medicare – Inpatient Hip Repair ───────────────────
# Patient owes Part A deductible only ($1,632 for 2026)
bills.append(
    build_bill(
        bill_id="bill_v2_medicare_traditional_inpatient_05",
        patient_name="Eleanor Vance",
        patient_account_number="CS-2026-03389",
        guarantor_name="Eleanor Vance",
        guarantor_number="GU-2026-03389",
        service_date="2026-03-01",
        service_description="Inpatient – Hip Fracture Repair (4 days, DRG 482)",
        primary_insurance="Medicare Part A + Part B (Traditional)",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Inpatient Facility – DRG 482 (Hip & Femur Procedures)",
                "cpt_or_revenue_code": "0100",
                "code_type": "Revenue",
                "quantity": 4,
                "unit": "day",
                "billed_amount": 61400.00,
                "insurance_payment_allocated": 59768.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Operating Room – Facility Fee",
                "cpt_or_revenue_code": "0360",
                "code_type": "Revenue",
                "billed_amount": 11200.00,
                "insurance_payment_allocated": 11200.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Pharmacy – Inpatient Medications",
                "cpt_or_revenue_code": "0250",
                "code_type": "Revenue",
                "billed_amount": 3800.00,
                "insurance_payment_allocated": 3800.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Laboratory",
                "cpt_or_revenue_code": "0300",
                "code_type": "Revenue",
                "billed_amount": 1600.00,
                "insurance_payment_allocated": 1600.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Medicare Part A",
                "payment_amount": 76368.00,
                "payment_date": "2026-04-05",
                "check_or_ref_number": "MCR-2026-FI-00882",
            }
        ],
        adjustments=[],
        statement_date="2026-04-10",
        due_date="2026-05-10",
    )
)

# ─── BILL 06 ── Medicare + Medigap Plan G – Observation Stay ──────────────────
# Observation: Part A does NOT apply; Part B 20% coinsurance; Medigap covers Part B coinsurance
bills.append(
    build_bill(
        bill_id="bill_v2_medicare_medigap_observation_06",
        patient_name="Harold Jensen",
        patient_account_number="CS-2026-04512",
        guarantor_name="Harold Jensen",
        guarantor_number="GU-2026-04512",
        service_date="2026-04-08",
        service_description="Observation Status – Chest Pain / Rule-Out ACS (3 days)",
        primary_insurance="Medicare Part A + Part B (Traditional)",
        secondary_insurance="AARP Medicare Supplement Plan G (UnitedHealthcare)",
        line_items=[
            {
                "service_name": "Observation Services – per hour (72 hours)",
                "cpt_or_revenue_code": "99224",
                "code_type": "CPT",
                "quantity": 72,
                "unit": "hour",
                "billed_amount": 12800.00,
                "insurance_payment_allocated": 10240.00,
                "adjustment_allocated": 2560.00,
            },
            {
                "service_name": "Cardiac Monitoring – Telemetry",
                "cpt_or_revenue_code": "0730",
                "code_type": "Revenue",
                "billed_amount": 3200.00,
                "insurance_payment_allocated": 2560.00,
                "adjustment_allocated": 640.00,
            },
            {
                "service_name": "Echocardiogram",
                "cpt_or_revenue_code": "93306",
                "code_type": "CPT",
                "billed_amount": 4600.00,
                "insurance_payment_allocated": 3680.00,
                "adjustment_allocated": 920.00,
            },
            {
                "service_name": "Pharmacy – Outpatient Drugs (observation billed under Part D)",
                "cpt_or_revenue_code": "0250",
                "code_type": "Revenue",
                "billed_amount": 820.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Medicare Part B",
                "payment_amount": 16480.00,
                "payment_date": "2026-05-02",
                "check_or_ref_number": "MCR-2026-B-14820",
            },
            {
                "payer_name": "AARP Medicare Supplement Plan G",
                "payment_amount": 4120.00,
                "payment_date": "2026-05-10",
                "check_or_ref_number": "MEDIGAP-2026-G-00221",
            },
        ],
        adjustments=[
            {
                "description": "Medicare Part B Allowed Amount Adjustment",
                "amount": 4120.00,
            }
        ],
        statement_date="2026-05-15",
        due_date="2026-06-15",
    )
)

# ─── BILL 07 ── Medicare Advantage HMO – Denied Claim ────────────────────────
# Humana Gold Plus HMO – prior auth denial – full balance to patient
bills.append(
    build_bill(
        bill_id="bill_v2_medicare_advantage_hmo_denied_07",
        patient_name="Dorothy Nguyen",
        patient_account_number="CS-2026-05634",
        guarantor_name="Dorothy Nguyen",
        guarantor_number="GU-2026-05634",
        service_date="2026-03-18",
        service_description="Inpatient – Lumbar Spinal Fusion (5 days, DRG 460)",
        primary_insurance="Humana Gold Plus HMO (Medicare Advantage)",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Inpatient Facility – DRG 460 (Spinal Fusion)",
                "cpt_or_revenue_code": "0100",
                "code_type": "Revenue",
                "quantity": 5,
                "unit": "day",
                "billed_amount": 38400.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Spinal Fusion – Lumbar (primary procedure)",
                "cpt_or_revenue_code": "22630",
                "code_type": "CPT",
                "billed_amount": 24000.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Implant – Spinal Cage/Hardware",
                "cpt_or_revenue_code": "0278",
                "code_type": "Revenue",
                "billed_amount": 14200.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Anesthesia – Spinal Surgery",
                "cpt_or_revenue_code": "00630",
                "code_type": "CPT",
                "quantity": 36,
                "unit": "unit",
                "billed_amount": 5400.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Recovery Room",
                "cpt_or_revenue_code": "0710",
                "code_type": "Revenue",
                "billed_amount": 4200.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Room & Board",
                "cpt_or_revenue_code": "0110",
                "code_type": "Revenue",
                "quantity": 4,
                "unit": "day",
                "billed_amount": 19200.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Laboratory & Pathology",
                "cpt_or_revenue_code": "0300",
                "code_type": "Revenue",
                "billed_amount": 1800.00,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[],
        adjustments=[
            {
                "description": "Denial Reason: CO-197 – Prior Authorization Not Obtained (Humana Gold Plus HMO). Claim denied. Balance transferred to patient pending appeal.",
                "amount": 0,
            }
        ],
        statement_date="2026-04-20",
        due_date="2026-05-20",
    )
)

# ─── BILL 08 ── Medicare Advantage PPO – Outpatient Procedure Copay Mismatch ──
# Kaiser MA PPO – intravitreal injection; copay discrepancy
bills.append(
    build_bill(
        bill_id="bill_v2_medicare_advantage_ppo_outpatient_08",
        patient_name="Bernard Okafor",
        patient_account_number="CS-2026-06741",
        guarantor_name="Bernard Okafor",
        guarantor_number="GU-2026-06741",
        service_date="2026-04-14",
        service_description="Outpatient – Intravitreal Injection (Ophthalmology)",
        primary_insurance="Kaiser Permanente Senior Advantage PPO (Medicare Advantage)",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Intravitreal Injection – Ranibizumab (Lucentis)",
                "cpt_or_revenue_code": "67028",
                "code_type": "CPT",
                "billed_amount": 2800.00,
                "insurance_payment_allocated": 2200.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Ranibizumab (Lucentis) 0.5mg vial – Specialty Pharmacy",
                "cpt_or_revenue_code": "J2778",
                "code_type": "HCPCS",
                "quantity": 1,
                "unit": "vial",
                "billed_amount": 1900.00,
                "insurance_payment_allocated": 1300.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Kaiser Permanente Senior Advantage PPO",
                "payment_amount": 3500.00,
                "payment_date": "2026-05-01",
                "check_or_ref_number": "KP-MA-2026-00991",
            }
        ],
        adjustments=[],
        statement_date="2026-05-05",
        due_date="2026-06-05",
    )
)

# ─── BILL 09 ── Medi-Cal (Standard) – ER Visit ───────────────────────────────
# Medi-Cal paid; small residual balance — unusual and should trigger verification
bills.append(
    build_bill(
        bill_id="bill_v2_medicaid_standard_er_09",
        patient_name="Sofia Ramirez",
        patient_account_number="CS-2026-07892",
        guarantor_name="Sofia Ramirez",
        guarantor_number="GU-2026-07892",
        service_date="2026-03-29",
        service_description="Emergency Department – Abdominal Pain",
        primary_insurance="Medi-Cal (California Medicaid)",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Emergency Department – Level 3",
                "cpt_or_revenue_code": "99283",
                "code_type": "CPT",
                "billed_amount": 4200.00,
                "insurance_payment_allocated": 3900.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Comprehensive Metabolic Panel",
                "cpt_or_revenue_code": "80053",
                "code_type": "CPT",
                "billed_amount": 620.00,
                "insurance_payment_allocated": 580.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Urinalysis",
                "cpt_or_revenue_code": "81001",
                "code_type": "CPT",
                "billed_amount": 280.00,
                "insurance_payment_allocated": 260.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "IV Administration – Initial Hour",
                "cpt_or_revenue_code": "96365",
                "code_type": "CPT",
                "billed_amount": 480.00,
                "insurance_payment_allocated": 390.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Emergency Room Facility Fee",
                "cpt_or_revenue_code": "0450",
                "code_type": "Revenue",
                "billed_amount": 3620.00,
                "insurance_payment_allocated": 3250.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Medi-Cal (California Medicaid)",
                "payment_amount": 8380.00,
                "payment_date": "2026-04-18",
                "check_or_ref_number": "MCAL-2026-00338821",
            }
        ],
        adjustments=[],
        statement_date="2026-04-25",
        due_date="2026-05-25",
    )
)

# ─── BILL 10 ── Medi-Cal Share of Cost – Outpatient Colonoscopy ───────────────
bills.append(
    build_bill(
        bill_id="bill_v2_medicaid_share_of_cost_outpatient_10",
        patient_name="Antoine Williams",
        patient_account_number="CS-2026-09003",
        guarantor_name="Antoine Williams",
        guarantor_number="GU-2026-09003",
        service_date="2026-04-22",
        service_description="Outpatient – Colonoscopy Screening",
        primary_insurance="Medi-Cal – Share of Cost Plan (California Medicaid)",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Colonoscopy – Diagnostic with biopsy",
                "cpt_or_revenue_code": "45380",
                "code_type": "CPT",
                "billed_amount": 4200.00,
                "insurance_payment_allocated": 3720.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Pathology – Tissue Biopsy",
                "cpt_or_revenue_code": "88305",
                "code_type": "CPT",
                "billed_amount": 680.00,
                "insurance_payment_allocated": 400.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Medi-Cal Share of Cost",
                "payment_amount": 4120.00,
                "payment_date": "2026-05-12",
                "check_or_ref_number": "MCAL-SOC-2026-00119",
            }
        ],
        adjustments=[],
        statement_date="2026-05-18",
        due_date="2026-06-18",
    )
)

# ─── BILL 11 ── Dual Eligible (Medicare + Medi-Cal) – SNF Post-Discharge ──────
bills.append(
    build_bill(
        bill_id="bill_v2_dual_eligible_snf_11",
        patient_name="Gladys Park",
        patient_account_number="CS-2026-10114",
        guarantor_name="Gladys Park",
        guarantor_number="GU-2026-10114",
        service_date="2026-02-20",
        service_description="Skilled Nursing Facility Post-Acute Care (Days 21–25, Medicare SNF)",
        primary_insurance="Medicare Part A + Part B (Traditional)",
        secondary_insurance="Medi-Cal (California Medicaid) – Dual Eligible",
        line_items=[
            {
                "service_name": "SNF Room & Board – Days 21–25 (Medicare coinsurance days)",
                "cpt_or_revenue_code": "0190",
                "code_type": "Revenue",
                "quantity": 5,
                "unit": "day",
                "billed_amount": 9600.00,
                "insurance_payment_allocated": 9600.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Physical Therapy – SNF",
                "cpt_or_revenue_code": "97110",
                "code_type": "CPT",
                "quantity": 5,
                "unit": "session",
                "billed_amount": 1800.00,
                "insurance_payment_allocated": 1800.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Pharmacy – SNF Medications",
                "cpt_or_revenue_code": "0250",
                "code_type": "Revenue",
                "billed_amount": 620.00,
                "insurance_payment_allocated": 620.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Medicare Part A (SNF coinsurance days 21–25)",
                "payment_amount": 9980.00,
                "payment_date": "2026-03-15",
                "check_or_ref_number": "MCR-SNF-2026-00451",
            },
            {
                "payer_name": "Medi-Cal – Dual Eligible Crossover",
                "payment_amount": 2040.00,
                "payment_date": "2026-03-22",
                "check_or_ref_number": "MCAL-XOVER-2026-00228",
            },
        ],
        adjustments=[],
        statement_date="2026-04-01",
        due_date="2026-05-01",
    )
)

# ─── BILL 12 ── Commercial HMO – Wellness Visit Reclassified as Diagnostic ────
# Triggers ACA preventive care dispute scenario
bills.append(
    build_bill(
        bill_id="bill_v2_commercial_hmo_wellness_reclassified_12",
        patient_name="Priya Patel",
        patient_account_number="CS-2026-11227",
        guarantor_name="Priya Patel",
        guarantor_number="GU-2026-11227",
        service_date="2026-03-05",
        service_description="Annual Wellness Visit – Reclassified as Diagnostic",
        primary_insurance="Blue Shield of California HMO",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Office Visit – Established Patient, Level 4 (Diagnostic)",
                "cpt_or_revenue_code": "99214",
                "code_type": "CPT",
                "billed_amount": 780.00,
                "insurance_payment_allocated": 440.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Preventive Medicine Service – Adult 40–64",
                "cpt_or_revenue_code": "99396",
                "code_type": "CPT",
                "billed_amount": 0,
                "insurance_payment_allocated": 0,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Blue Shield of California HMO",
                "payment_amount": 440.00,
                "payment_date": "2026-04-02",
                "check_or_ref_number": "BSC-2026-HMO-44910",
            }
        ],
        adjustments=[],
        statement_date="2026-04-08",
        due_date="2026-05-08",
    )
)

# ─── BILL 13 ── INTENTIONALLY INCORRECT MATH – Line items don't sum to total ──
# Flagged in CSV as intentionally_incorrect=True; NOT flagged in JSON
bills.append(
    build_bill(
        bill_id="bill_v2_intentionally_incorrect_math_13",
        patient_name="Thomas Brennan",
        patient_account_number="CS-2026-12330",
        guarantor_name="Thomas Brennan",
        guarantor_number="GU-2026-12330",
        service_date="2026-04-01",
        service_description="Outpatient Lab Panel",
        primary_insurance="Cigna Open Access Plus EPO",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Comprehensive Metabolic Panel",
                "cpt_or_revenue_code": "80053",
                "code_type": "CPT",
                "billed_amount": 620.00,
                "insurance_payment_allocated": 500.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Lipid Panel",
                "cpt_or_revenue_code": "80061",
                "code_type": "CPT",
                "billed_amount": 380.00,
                "insurance_payment_allocated": 300.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "TSH – Thyroid Stimulating Hormone",
                "cpt_or_revenue_code": "84443",
                "code_type": "CPT",
                "billed_amount": 310.00,
                "insurance_payment_allocated": 250.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "Cigna Open Access Plus EPO",
                "payment_amount": 1050.00,
                "payment_date": "2026-04-28",
                "check_or_ref_number": "CIGNA-2026-EPO-88120",
            }
        ],
        adjustments=[],
        statement_date="2026-05-01",
        due_date="2026-06-01",
    )
)

# Manually inject the "wrong" total to simulate the error the agent should detect
# Line items sum: 620+380+310 - 500-300-250 = 260, but we'll say 960 in total_amount_due
bills[-1]["total_amount_due"] = 960.00  # INTENTIONALLY WRONG (correct is 260.00)
bills[-1]["summary_of_services"]["totals"]["patient_balance"] = 960.00  # matches the "wrong" total
bills[-1]["_intentional_error_note"] = (
    "EVALUATOR NOTE — DO NOT PASS TO LLM: "
    "Total amount due ($960) does not match line-item calculation ($260). "
    "Correct patient balance = $1,310 billed - $1,050 paid = $260. "
    "This bill tests the agent's ability to detect and flag math discrepancies."
)

# ─── BILL 14 ── TRICARE – Active Duty Military Dependent ─────────────────────
bills.append(
    build_bill(
        bill_id="bill_v2_tricare_outpatient_14",
        patient_name="Jessica Morales",
        patient_account_number="CS-2026-13441",
        guarantor_name="CPT Michael Morales (Sponsor)",
        guarantor_number="GU-2026-13441",
        service_date="2026-04-18",
        service_description="Outpatient – Prenatal Visit (OB/GYN)",
        primary_insurance="TRICARE Prime (Active Duty Dependent)",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Office/Outpatient Visit – OB Prenatal, 28–36 weeks",
                "cpt_or_revenue_code": "99214",
                "code_type": "CPT",
                "billed_amount": 680.00,
                "insurance_payment_allocated": 680.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Obstetric Ultrasound – Standard",
                "cpt_or_revenue_code": "76805",
                "code_type": "CPT",
                "billed_amount": 1200.00,
                "insurance_payment_allocated": 1200.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "TRICARE Prime",
                "payment_amount": 1880.00,
                "payment_date": "2026-05-08",
                "check_or_ref_number": "TC-2026-00557821",
            }
        ],
        adjustments=[],
        statement_date="2026-05-12",
        due_date="2026-06-12",
    )
)

# ─── BILL 15 ── Workers Compensation – Workplace Injury ──────────────────────
bills.append(
    build_bill(
        bill_id="bill_v2_workers_comp_er_15",
        patient_name="Carlos Mendoza",
        patient_account_number="CS-2026-14552",
        guarantor_name="Carlos Mendoza",
        guarantor_number="GU-2026-14552",
        service_date="2026-03-10",
        service_description="Emergency Department – Workplace Hand Laceration",
        primary_insurance="State Compensation Insurance Fund (Workers Comp)",
        secondary_insurance="None on file",
        line_items=[
            {
                "service_name": "Emergency Department – Level 3",
                "cpt_or_revenue_code": "99283",
                "code_type": "CPT",
                "billed_amount": 3200.00,
                "insurance_payment_allocated": 3200.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Laceration Repair – Complex, hand (2.6 cm)",
                "cpt_or_revenue_code": "13131",
                "code_type": "CPT",
                "billed_amount": 2400.00,
                "insurance_payment_allocated": 2400.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "X-Ray – Hand, 3 views",
                "cpt_or_revenue_code": "73130",
                "code_type": "CPT",
                "billed_amount": 480.00,
                "insurance_payment_allocated": 480.00,
                "adjustment_allocated": 0,
            },
            {
                "service_name": "Tetanus Toxoid injection",
                "cpt_or_revenue_code": "90714",
                "code_type": "CPT",
                "billed_amount": 180.00,
                "insurance_payment_allocated": 180.00,
                "adjustment_allocated": 0,
            },
        ],
        insurance_payments=[
            {
                "payer_name": "State Compensation Insurance Fund (SCIF)",
                "payment_amount": 6260.00,
                "payment_date": "2026-04-05",
                "check_or_ref_number": "SCIF-2026-WC-00334",
            }
        ],
        adjustments=[],
        statement_date="2026-04-10",
        due_date="2026-05-10",
    )
)

# ═══════════════════════════════════════════════════════════════════════════════
# WRITE JSON FILES
# ═══════════════════════════════════════════════════════════════════════════════

written = []
written_agent = []
errors = []

for bill in bills:
    bill_id = bill["patient"]["patient_account_number"].replace("CS-2026-", "bill_v2_")
    # Use the more descriptive bill_id from the build_bill call
    # We stored it via the first positional arg; recover from _note absence — use account number
    filename = None
    # Map account numbers to descriptive filenames
    account_to_file = {
        "CS-2026-00441": "bill_v2_selfpay_er_01.json",
        "CS-2026-00882": "bill_v2_selfpay_inpatient_02.json",
        "CS-2026-01154": "bill_v2_commercial_ppo_outpatient_03.json",
        "CS-2026-02271": "bill_v2_commercial_hdhp_oon_anesthesia_04.json",
        "CS-2026-03389": "bill_v2_medicare_traditional_inpatient_05.json",
        "CS-2026-04512": "bill_v2_medicare_medigap_observation_06.json",
        "CS-2026-05634": "bill_v2_medicare_advantage_denied_07.json",
        "CS-2026-06741": "bill_v2_medicare_advantage_copay_discrepancy_08.json",
        "CS-2026-07892": "bill_v2_medicaid_er_09.json",
        "CS-2026-09003": "bill_v2_medicaid_share_of_cost_10.json",
        "CS-2026-10114": "bill_v2_dual_eligible_snf_11.json",
        "CS-2026-11227": "bill_v2_commercial_wellness_reclassified_12.json",
        "CS-2026-12330": "bill_v2_intentionally_incorrect_math_13.json",
        "CS-2026-13441": "bill_v2_tricare_outpatient_14.json",
        "CS-2026-14552": "bill_v2_workers_comp_er_15.json",
    }
    acct = bill["patient"]["patient_account_number"]
    filename = account_to_file.get(acct, f"bill_v2_{acct}.json")
    path = os.path.join(BILLS_OUT, filename)
    agent_path = os.path.join(BILLS_AGENT_OUT, filename)

    # Math audit (skip intentionally incorrect bill)
    if "_intentional_error_note" not in bill:
        stated_total = bill["total_amount_due"]
        totals = bill["summary_of_services"]["totals"]
        calc_patient_balance = round(
            totals["total_billed"]
            - totals["total_insurance_payments"]
            - totals["total_adjustments"],
            2,
        )
        if abs(stated_total - calc_patient_balance) > 0.02:
            errors.append(
                f"  MATH ERROR in {filename}: "
                f"total_amount_due={stated_total} but calculated={calc_patient_balance}"
            )

    with open(path, "w", encoding="utf-8") as f:
        json.dump(bill, f, indent=2, ensure_ascii=False)
    with open(agent_path, "w", encoding="utf-8") as f:
        json.dump(bill_for_agent(bill), f, indent=2, ensure_ascii=False)
    written.append(filename)
    written_agent.append(filename)

# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT REPORT
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print(f"  V2 Synthetic Bills — Generation Complete")
print(f"{'='*60}")
print(f"  Evaluator bills  : {BILLS_OUT}")
print(f"  Agent bills      : {BILLS_AGENT_OUT}  (stripped: {', '.join(AGENT_STRIP_KEYS)})")
print(f"  Bills written    : {len(written)}")
print()

for fn in written:
    is_incorrect = "incorrect_math" in fn
    tag = "  [INTENTIONALLY INCORRECT — for evaluation]" if is_incorrect else ""
    print(f"  ✓ {fn}{tag}")

print()
if errors:
    print("  ⚠️  MATH AUDIT FAILURES:")
    for e in errors:
        print(e)
    print()
else:
    print("  ✓ Math audit passed — all non-flagged bills balance correctly.")

print()
print("  Insurance types covered:")
insurance_types = set()
for b in bills:
    insurance_types.add(b["insurance"]["primary"])
for t in sorted(insurance_types):
    print(f"    - {t}")

print()
print("  Next step: run generate_v2_csv.py to produce the validation dataset CSV")
print(f"{'='*60}\n")
