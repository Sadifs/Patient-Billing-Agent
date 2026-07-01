"""
generate_v2_pdfs.py
===================
Generates PDF versions of v2 synthetic bills matching the Cedars-Sinai
sample bill layout (knowledge-docs/sample_bill_pdf.pdf).

    cd synthetic-data/
    python3 generate_v2_pdfs.py

Writes PDFs to synthetic_bills_v2/ alongside each JSON file.
Requires: reportlab
"""

import json
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

SRC       = os.path.dirname(os.path.abspath(__file__))
BILLS_DIR = os.path.join(SRC, "synthetic_bills_v2")

# Colors matching Cedars-Sinai sample bill
PURPLE       = HexColor("#5C3472")
LIGHT_PURPLE = HexColor("#EDE7F6")
ROW_ALT      = HexColor("#EDE7F6")
LIGHT_GRAY   = HexColor("#EEEEEE")
DARK_GRAY    = HexColor("#333333")
WHITE        = colors.white
BLACK        = colors.black

PAGE_W, PAGE_H = letter   # 612 x 792 pts
L  = 40          # left margin
R  = 572         # right margin
W  = R - L       # usable width (532)
MID = L + W // 2 # horizontal midpoint (306)


def money(v):
    if v == 0:    return "$0.00"
    if v < 0:     return f"( ${abs(v):,.2f} )"
    return f"${v:,.2f}"


def circle_label(c, cx, cy, r, letter):
    """Filled purple circle with white letter. Saves/restores canvas state."""
    c.saveState()
    c.setFillColor(PURPLE)
    c.circle(cx, cy, r, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", r * 1.2)
    c.drawCentredString(cx, cy - r * 0.40, letter)
    c.restoreState()


def draw_page1(c, bill):
    patient   = bill["patient"]
    guarantor = bill["guarantor"]
    insurance = bill["insurance"]
    totals    = bill["summary_of_services"]["totals"]
    ps        = bill["patient_services"]

    # ══════════════════════════════════════════════════════════════════
    # HEADER BAR  (y: 724 – 792)
    # ══════════════════════════════════════════════════════════════════
    c.setFillColor(PURPLE)
    c.rect(0, PAGE_H - 68, PAGE_W, 68, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(L, PAGE_H - 28, "Cedars-")
    c.setFont("Helvetica", 17)
    c.drawString(L + 62, PAGE_H - 28, "Sinai")
    c.setFont("Helvetica", 8)
    c.drawString(L, PAGE_H - 43, "P.O. Box 48954")
    c.drawString(L, PAGE_H - 53, "Los Angeles, CA 90048-0954")

    c.setFont("Helvetica-BoldOblique", 9)
    c.drawRightString(R, PAGE_H - 24, "Statement of Hospital and Physician Services")
    c.setFont("Helvetica", 8.5)
    c.drawRightString(R, PAGE_H - 36, f"Date:  {bill['statement_date']}")
    c.drawRightString(R, PAGE_H - 47, f"Page 1 of 2")

    # ══════════════════════════════════════════════════════════════════
    # PATIENT ADDRESS  (left column, below header)
    # ══════════════════════════════════════════════════════════════════
    y_pat = PAGE_H - 90
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(L, y_pat, patient["patient_name"])
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 9)
    c.drawString(L, y_pat - 14, f"Account #:     {patient['patient_account_number']}")
    c.drawString(L, y_pat - 27, f"Service Date:  {patient['service_date']}")

    # ══════════════════════════════════════════════════════════════════
    # CONTACT OPTIONS BOX  (right column, section A)
    # ══════════════════════════════════════════════════════════════════
    bx = MID + 8
    bw = R - bx
    by = PAGE_H - 72   # top of box (just below header)
    bh = 65

    c.setFillColor(LIGHT_PURPLE)
    c.roundRect(bx, by - bh, bw, bh, 4, fill=1, stroke=0)

    circle_label(c, bx - 9, by - 9, 8, "A")

    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 8.5)
    c.drawString(bx + 10, by - 16, "●  Pay Online: cedars-sinai.org/billing")
    c.drawString(bx + 10, by - 28, f"●  Pay by Phone: {ps['phone']}")
    c.drawString(bx + 10, by - 40, "●  Written Correspondence:")
    c.drawString(bx + 20, by - 51, "Cedars-Sinai Medical Center")
    c.drawString(bx + 20, by - 62, "P.O. Box 48750, Los Angeles, CA 90048")

    # ══════════════════════════════════════════════════════════════════
    # INSURANCE INFO  (left column)
    # ══════════════════════════════════════════════════════════════════
    y_ins = y_pat - 44
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 9)
    c.drawString(L, y_ins,      f"Primary Insurance:    {insurance['primary']}")
    c.drawString(L, y_ins - 13, f"Secondary Insurance:  {insurance['secondary']}")

    # ══════════════════════════════════════════════════════════════════
    # GUARANTOR ACCOUNT INFORMATION BOX  (right column, section B)
    # ══════════════════════════════════════════════════════════════════
    gx = MID + 8
    gy = by - bh - 5   # sits just below contact box
    gh = 38

    c.setFillColor(PURPLE)
    c.rect(gx, gy - gh, gw := R - gx, gh, fill=1, stroke=0)

    circle_label(c, gx - 9, gy - 9, 8, "B")

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(gx + 10, gy - 14, "GUARANTOR ACCOUNT INFORMATION")
    c.setFont("Helvetica", 8.5)
    c.drawString(gx + 10, gy - 26, f"Guarantor Name:    {guarantor['guarantor_name']}")
    c.drawString(gx + 10, gy - 37, f"Guarantor #:       {guarantor['guarantor_account_number']}")

    # ══════════════════════════════════════════════════════════════════
    # SUMMARY TABLE  (section D, full width)
    # ══════════════════════════════════════════════════════════════════
    # Start below whichever section ends lower (insurance left vs guarantor box right)
    y_below_left  = y_ins - 26        # bottom of insurance info
    y_below_right = gy - gh - 4       # bottom of guarantor box
    ty = min(y_below_left, y_below_right) - 18   # table top

    col_w = [W * 0.40, W * 0.20, W * 0.22, W * 0.18]
    rh = 22

    # D label
    circle_label(c, L + 8, ty + 10, 8, "D")
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(L + 20, ty + 6, "Summary")

    # Header row
    c.setFillColor(PURPLE)
    c.rect(L, ty - rh, W, rh, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 9)
    hdrs = ["Summary", "Billed/Pmts/Adjs", "Outstanding Balance", "Patient Balance"]
    xp = L
    for i, (h, cw) in enumerate(zip(hdrs, col_w)):
        cy2 = ty - rh + 7
        if i == 0:
            c.drawString(xp + 6, cy2, h)
        else:
            c.drawCentredString(xp + cw / 2, cy2, h)
        xp += cw

    # Hospital services data row
    ry = ty - rh * 2
    c.setFillColor(ROW_ALT)
    c.rect(L, ry, W, rh, fill=1, stroke=0)
    c.setFillColor(PURPLE)
    c.setFont("Helvetica", 9.5)
    c.drawString(L + 6, ry + 7, "New Activity Hospital Services")
    xp = L + col_w[0]
    for val, cw in zip(
        [totals["total_billed"], totals["outstanding_balance"], totals["patient_balance"]],
        col_w[1:]
    ):
        c.drawCentredString(xp + cw / 2, ry + 7, money(val))
        xp += cw

    # Totals row
    ry -= rh
    c.setFillColor(LIGHT_GRAY)
    c.rect(L, ry, W, rh, fill=1, stroke=0)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(L + 6, ry + 7, "Totals")
    xp = L + col_w[0]
    for val, cw in zip(
        [totals["total_billed"], totals["outstanding_balance"], totals["patient_balance"]],
        col_w[1:]
    ):
        c.drawCentredString(xp + cw / 2, ry + 7, money(val))
        xp += cw

    # Table border + column dividers
    c.setStrokeColor(PURPLE)
    c.setLineWidth(0.6)
    c.rect(L, ry, W, ty - ry, fill=0, stroke=1)
    xp = L + col_w[0]
    for cw in col_w[1:-1]:
        c.line(xp, ry, xp, ty)
        xp += cw

    table_bottom = ry

    # ══════════════════════════════════════════════════════════════════
    # TOTAL AMOUNT DUE  (section E)
    # ══════════════════════════════════════════════════════════════════
    due_y = table_bottom - 34

    circle_label(c, L + 8, due_y + 4, 8, "E")
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(L + 22, due_y, "Total Amount Due :")
    c.setFillColor(PURPLE)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(L + 248, due_y, money(bill["total_amount_due"]))

    # ══════════════════════════════════════════════════════════════════
    # INFO BOXES — G (thank you) and F (patient services)
    # ══════════════════════════════════════════════════════════════════
    info_top = due_y - 22
    box_h    = 115
    lw = MID - L - 4
    rw = R - MID - 4

    # Left box — G
    c.setFillColor(LIGHT_GRAY)
    c.roundRect(L, info_top - box_h, lw, box_h, 4, fill=1, stroke=0)

    circle_label(c, L + 10, info_top - 10, 8, "G")

    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(L + 24, info_top - 14,
                 "Thank you for choosing us for your healthcare needs.")
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(L + 10, info_top - 27,
                 "This statement explains the current status of your accounts.")
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 8.5)
    for i, ln in enumerate([
        "•  If you have insurance not reflected here, contact us.",
        "•  Contractual discounts and payments are reflected in",
        "    this statement.",
        "•  The balance remaining is your responsibility and is",
        "    due in full on the date indicated.",
        "•  We offer financial assistance for eligible patients.",
    ]):
        c.drawString(L + 10, info_top - 40 - i * 11, ln)

    # Right box — F
    c.setFillColor(LIGHT_PURPLE)
    c.roundRect(MID + 4, info_top - box_h, rw, box_h, 4, fill=1, stroke=0)

    circle_label(c, MID + 14, info_top - 10, 8, "F")

    c.setFillColor(PURPLE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MID + 26, info_top - 14, "Patient Services")

    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 8.5)
    for i, ln in enumerate([
        "For account information or to discuss financial",
        f"assistance, call {ps['phone']},",
        f"{ps['hours']},",
        "or email patient.billing@cshs.org.",
        "",
        "Please note: there may be additional billing",
        "charges not yet posted.",
        "",
        "Your Account Detail is on the following page.",
    ]):
        c.drawString(MID + 10, info_top - 28 - i * 10, ln)

    info_bottom = info_top - box_h

    # ══════════════════════════════════════════════════════════════════
    # REMITTANCE STUB  (section H)
    # ══════════════════════════════════════════════════════════════════
    stub_top = info_bottom - 16

    # Dashed cut line
    c.setStrokeColor(DARK_GRAY)
    c.setLineWidth(0.5)
    c.setDash(5, 3)
    c.line(L, stub_top, R, stub_top)
    c.setDash()

    # H circle label
    circle_label(c, L + 10, stub_top - 12, 8, "H")

    # Stub logo
    c.setFillColor(PURPLE)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(L + 24, stub_top - 16, "Cedars-")
    c.setFont("Helvetica", 13)
    c.drawString(L + 78, stub_top - 16, "Sinai")

    # Stub details (left)
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 9)
    c.drawString(L + 24, stub_top - 30, f"Statement Date:    {bill['statement_date']}")
    c.drawString(L + 24, stub_top - 43, f"Guarantor Number:  {guarantor['guarantor_account_number']}")

    c.setFont("Helvetica", 8)
    c.drawString(L, stub_top - 58,
                 "☐  Check here if your address or insurance information has changed.")
    c.drawString(L + 16, stub_top - 69, "Please indicate changes on the back of this page.")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(L, stub_top - 82, "Make check payable to Cedars-Sinai")
    c.setFont("Helvetica", 8)
    for i, ln in enumerate(["CEDARS-SINAI", "FILE 1108", "1801 WEST OLYMPIC BLVD", "PASADENA, CA 91199-1108"]):
        c.drawString(L, stub_top - 95 - i * 11, ln)

    # Stub payment section (right)
    px = MID + 8
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(px, stub_top - 14, f"Guarantor Name")
    c.drawRightString(R, stub_top - 14, "Due Date")
    c.setFont("Helvetica", 9)
    c.drawString(px, stub_top - 26, guarantor["guarantor_name"])
    c.drawRightString(R, stub_top - 26, bill["due_date"])

    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(px + 65, stub_top - 44, "Amount Now Due")
    c.drawCentredString(px + 195, stub_top - 44, "Amount I Am Paying")

    c.setStrokeColor(BLACK)
    c.setLineWidth(1)
    c.rect(px + 5,   stub_top - 74, 120, 24, fill=0, stroke=1)
    c.rect(px + 135, stub_top - 74, 120, 24, fill=0, stroke=1)

    c.setFillColor(PURPLE)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(px + 65, stub_top - 63, money(bill["total_amount_due"]))

    c.setFillColor(BLACK)
    c.setFont("Helvetica", 8)
    c.drawString(px + 5, stub_top - 84, "Select One:  □ Payment Enclosed   □ Charge")
    c.drawString(px + 5, stub_top - 95,
                 "□ VISA  □ Mastercard  □ Discover  □ Amex")
    c.setFont("Helvetica", 8)
    c.drawString(px + 5, stub_top - 108, "Card #: _______________________________  Exp: ________")
    c.drawString(px + 5, stub_top - 119, "Print Cardholder's Name: _____________________________")
    c.drawString(px + 5, stub_top - 130, "Signature: ___________________________________________")

    # Barcode number (machine-readable guarantor account for check processing)
    acct = guarantor["guarantor_account_number"].replace("GU-", "").replace("-", "")
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 7)
    c.drawString(L, 30, "Remittance ID:")
    c.setFont("Helvetica", 9)
    c.drawString(L, 18, f"{'0'*10}{acct}{'0'*10}")


def draw_page2(c, bill):
    patient     = bill["patient"]
    line_items  = bill["summary_of_services"]["line_items"]
    totals      = bill["summary_of_services"]["totals"]
    payments    = bill.get("payment_detail", {}).get("insurance_payments", [])
    adjustments = bill.get("payment_detail", {}).get("adjustments", [])
    ps          = bill["patient_services"]

    # ── Header ───────────────────────────────────────────────────────
    c.setFillColor(PURPLE)
    c.rect(0, PAGE_H - 68, PAGE_W, 68, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(L, PAGE_H - 28, "Cedars-")
    c.setFont("Helvetica", 17)
    c.drawString(L + 62, PAGE_H - 28, "Sinai")
    c.setFont("Helvetica", 8)
    c.drawString(L, PAGE_H - 43, "P.O. Box 48954")
    c.drawString(L, PAGE_H - 53, "Los Angeles, CA 90048-0954")

    c.setFont("Helvetica-BoldOblique", 9)
    c.drawRightString(R, PAGE_H - 24, "Statement of Hospital and Physician Services")
    c.setFont("Helvetica", 8.5)
    c.drawRightString(R, PAGE_H - 36, f"Date:  {bill['statement_date']}")
    c.drawRightString(R, PAGE_H - 47, "Page 2 of 2")

    # Patient strip
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 9)
    c.drawString(L, PAGE_H - 84,
        f"Patient: {patient['patient_name']}     "
        f"Account #: {patient['patient_account_number']}     "
        f"Service Date: {patient['service_date']}")

    # Section title
    c.setFillColor(PURPLE)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(L, PAGE_H - 104, "Account Detail")
    c.setStrokeColor(PURPLE)
    c.setLineWidth(1.2)
    c.line(L, PAGE_H - 108, R, PAGE_H - 108)

    # ── Line items table ─────────────────────────────────────────────
    col_w = [W*0.30, W*0.12, W*0.06, W*0.13, W*0.13, W*0.13, W*0.13]
    hdrs  = ["Service", "Code", "Qty", "Billed", "Ins Pmts", "Adj", "Patient Bal"]
    rh    = 18
    ty    = PAGE_H - 120

    # Header row
    c.setFillColor(PURPLE)
    c.rect(L, ty - rh, W, rh, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8.5)
    xp = L
    for i, (h, cw) in enumerate(zip(hdrs, col_w)):
        if i == 0:
            c.drawString(xp + 4, ty - rh + 5, h)
        else:
            c.drawCentredString(xp + cw / 2, ty - rh + 5, h)
        xp += cw

    # Determine if this bill has insurance on file
    ins_primary = bill.get("insurance", {}).get("primary", "")
    has_insurance = ins_primary not in ("", "None", "None / Self-Pay", "Self-Pay", "N/A")

    # Data rows
    ry = ty - rh
    for i, item in enumerate(line_items):
        c.setFillColor(ROW_ALT if i % 2 == 0 else WHITE)
        c.rect(L, ry - rh, W, rh, fill=1, stroke=0)

        name = item["service_name"]
        if len(name) > 36:
            name = name[:35] + "…"
        code_str = f"{item['code_type']} {item['code']}"

        c.setFillColor(DARK_GRAY)
        c.setFont("Helvetica", 8.5)
        xp = L
        c.drawString(xp + 4, ry - rh + 5, name);                                               xp += col_w[0]
        c.drawCentredString(xp + col_w[1]/2, ry - rh + 5, code_str);                           xp += col_w[1]
        c.drawCentredString(xp + col_w[2]/2, ry - rh + 5, str(item["quantity"]));              xp += col_w[2]
        c.drawRightString(xp + col_w[3] - 4, ry - rh + 5, money(item["billed_amount"]));       xp += col_w[3]
        ins_display = money(item["insurance_payments"]) if has_insurance else "—"
        c.drawRightString(xp + col_w[4] - 4, ry - rh + 5, ins_display);                        xp += col_w[4]
        c.drawRightString(xp + col_w[5] - 4, ry - rh + 5, money(item["adjustments"]));         xp += col_w[5]
        c.drawRightString(xp + col_w[6] - 4, ry - rh + 5, money(item["patient_balance"]))
        ry -= rh

    # Totals row
    c.setFillColor(PURPLE)
    c.rect(L, ry - rh, W, rh, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(L + 4, ry - rh + 5, "Totals")
    xp = L + col_w[0] + col_w[1] + col_w[2]
    total_vals = [totals["total_billed"], totals["total_insurance_payments"],
                  totals["total_adjustments"], totals["patient_balance"]]
    for idx, (val, cw) in enumerate(zip(total_vals, col_w[3:])):
        display = ("—" if (idx == 1 and not has_insurance) else money(val))
        c.drawRightString(xp + cw - 4, ry - rh + 5, display)
        xp += cw
    ry -= rh

    # Table border + column lines
    c.setStrokeColor(PURPLE)
    c.setLineWidth(0.5)
    c.rect(L, ry, W, ty - ry, fill=0, stroke=1)
    xp = L + col_w[0]
    for cw in col_w[1:-1]:
        c.line(xp, ry, xp, ty)
        xp += cw

    # ── Payment detail ────────────────────────────────────────────────
    if payments or adjustments:
        ry -= 22
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(L, ry, "Payment & Adjustment Detail")
        c.setStrokeColor(PURPLE)
        c.setLineWidth(0.8)
        c.line(L, ry - 4, R, ry - 4)
        ry -= 18

        c.setFont("Helvetica", 9)
        for pmt in payments:
            c.setFillColor(DARK_GRAY)
            c.drawString(L, ry, pmt["payer_name"])
            ref = pmt.get("check_or_ref_number", "")
            c.drawRightString(R, ry,
                f"{money(pmt['payment_amount'])}     {pmt['payment_date']}     Ref: {ref}")
            ry -= 14

        for adj in adjustments:
            desc = adj.get("description", adj.get("reason", "Adjustment"))
            amt  = adj.get("amount", adj.get("adjustment_amount", 0))
            c.setFillColor(DARK_GRAY)
            c.drawString(L, ry, desc)
            c.drawRightString(R, ry, money(amt))
            ry -= 14

    # ── Footer ────────────────────────────────────────────────────────
    ry -= 20
    c.setStrokeColor(LIGHT_GRAY)
    c.setLineWidth(0.6)
    c.line(L, ry + 12, R, ry + 12)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(L, ry, "Total Amount Due:")
    c.setFillColor(PURPLE)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(L + 190, ry, money(bill["total_amount_due"]))
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 8.5)
    c.drawString(L, ry - 16,
        f"Due Date: {bill['due_date']}   |   Questions? Call {ps['phone']}  ({ps['hours']})")


def validate_math(bill, fname):
    items = bill["summary_of_services"]["line_items"]
    t     = bill["summary_of_services"]["totals"]
    intentional = "_intentional_error_note" in bill

    sum_billed = round(sum(i["billed_amount"]     for i in items), 2)
    expected_os = round(t["total_billed"] - t["total_insurance_payments"] - t["total_adjustments"], 2)

    ok = True
    if abs(sum_billed - t["total_billed"]) > 0.02:
        print(f"  ⚠  {fname}: line items billed {sum_billed} ≠ total_billed {t['total_billed']}")
        ok = False
    if not intentional and abs(expected_os - t["outstanding_balance"]) > 0.02:
        print(f"  ⚠  {fname}: outstanding {t['outstanding_balance']} ≠ billed−ins−adj {expected_os}")
        ok = False
    if not intentional and abs(bill["total_amount_due"] - t["patient_balance"]) > 0.02:
        print(f"  ⚠  {fname}: total_amount_due {bill['total_amount_due']} ≠ patient_balance {t['patient_balance']}")
        ok = False
    if ok:
        print(f"  ✓ math OK  →  {fname.replace('.json', '.pdf')}")
    return ok


def generate_pdf(json_path, pdf_path):
    with open(json_path) as f:
        bill = json.load(f)
    validate_math(bill, os.path.basename(json_path))
    c = canvas.Canvas(pdf_path, pagesize=letter)
    draw_page1(c, bill)
    c.showPage()
    draw_page2(c, bill)
    c.showPage()
    c.save()


def main():
    files = sorted(f for f in os.listdir(BILLS_DIR) if f.endswith(".json"))
    print(f"Generating PDFs for {len(files)} v2 bills...\n")
    for fname in files:
        generate_pdf(
            os.path.join(BILLS_DIR, fname),
            os.path.join(BILLS_DIR, fname.replace(".json", ".pdf"))
        )
    print(f"\nDone — {len(files)} PDFs written to synthetic_bills_v2/")


if __name__ == "__main__":
    main()
