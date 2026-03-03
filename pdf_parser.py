"""
Fiscal Pulse — PDF Parser
Fixed version: handles em-dash, multi-line splits, various state formats,
%, (-) negatives, spaced month names, label variations, partial-column rows,
Sikkim (ii)SGST, Tripura spaced-digit BEs, and Tamil Nadu/Arunachal Pradesh
partial salaries/subsidy data across all states.
"""

import re
import io
import logging
import requests
import pdfplumber

from config import (
    HEADERS, INDICATORS, INDICATOR_IDS,
    MONTH_PARSE_MAP, make_fy, fy_month_order,
    DQ_OK, DQ_PARSE_ERROR, DQ_PDF_ERROR
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# PATTERN HELPERS
# ─────────────────────────────────────────────────────────
# Number capture: handles regular, negative with -, and Jharkhand (-) prefix
_N  = r'((?:\(-\)\s*)?-?[\d,\.]+)'
# Separator: horizontal whitespace only ([ \t]) so pattern can't cross line boundaries.
# Optionally absorbs a % sign between columns (Rajasthan format).
_S  = r'[ \t]*%?[ \t]+'
# 4-number group suffix used in every indicator pattern.
# Leading [ \t] (horizontal whitespace) ensures:
#   1. Pattern cannot cross line boundaries via \s matching \n
#   2. [^\n]* cannot consume part of the first number (number must start after space)
_N4 = f'[ \\t]{_N}{_S}{_N}{_S}{_N}{_S}{_N}'
# Optional 4th number — for indicators where pct_prev may be absent (e.g. Odisha grants_in_aid)
_N4_opt = f'[ \\t]{_N}{_S}{_N}{_S}{_N}(?:{_S}{_N})?'
# Flexible: 1 required number + 3 optional — for rows with partial data (e.g. Arunachal/Tamil Nadu
# salaries where only BE is present, or only BE+actuals with no pct columns).
# Uses non-greedy [^\n]*? so the regex finds the FIRST numbers after the label (not the last).
# Include the full suffix here; callers must NOT add their own [^\n]* before it.
_Nflex = f'[^\\n]*?[ \\t]{_N}(?:{_S}{_N})?(?:{_S}{_N})?(?:{_S}{_N})?'


# ─────────────────────────────────────────────────────────
# PDF DOWNLOAD
# ─────────────────────────────────────────────────────────
def download_pdf(url, timeout=30):
    """Download PDF bytes from URL. Returns bytes or None."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception as e:
        log.error(f"Download failed [{url}]: {e}")
        return None


def extract_text(pdf_bytes):
    """Extract text from first page of PDF."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return ""
            return pdf.pages[0].extract_text() or ""
    except Exception as e:
        log.error(f"PDF text extraction error: {e}")
        return ""


# ─────────────────────────────────────────────────────────
# DATE PARSING FROM PDF
# ─────────────────────────────────────────────────────────
def parse_date_from_text(text, url=""):
    """
    Extract (calendar_month, month_name, calendar_year, fy, fy_order)
    from PDF text header or URL fallback.
    Returns None tuple on failure.
    """
    NULL = (None, None, None, None, None)

    def _resolve(month_str, year_str):
        """Convert month string + year int to result tuple."""
        # Strip internal spaces: "A p r i l" → "april"
        m = re.sub(r'\s+', '', month_str).lower()
        yr = int(year_str)
        month_num = MONTH_PARSE_MAP.get(m)
        if month_num and 1 <= month_num <= 12:
            fy = make_fy(month_num, yr)
            order = fy_month_order(month_num)
            return month_num, m.capitalize(), yr, fy, order
        return None

    # Strategy 1: "At the end of December, 2024" or "A p r i l , 2025-2026"
    m = re.search(
        r"At\s+the\s+end\s+of\s+((?:[A-Za-z]\s*){3,10})[,\s]+(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        res = _resolve(m.group(1), m.group(2))
        if res:
            return res

    # Strategy 2: "As at the end of May -2025" (Tamil Nadu style)
    m2b = re.search(
        r"As\s+at\s+the\s+end\s+of\s+([A-Za-z]+)\s*[-,]?\s*(\d{4})",
        text, re.IGNORECASE
    )
    if m2b:
        res = _resolve(m2b.group(1), m2b.group(2))
        if res:
            return res

    # Strategy 3: URL pattern — MKI-12-2024 or MKI-12-25
    url_lower = url.lower()
    m3 = re.search(r"mki-(\d{1,2})-(\d{2,4})(?:-|_|\.)", url_lower)
    if m3:
        month_num = int(m3.group(1))
        if not (1 <= month_num <= 12):
            return NULL
        yr_raw = m3.group(2)
        year = int("20" + yr_raw) if len(yr_raw) == 2 else int(yr_raw)
        month_name = [k.capitalize() for k, v in MONTH_PARSE_MAP.items()
                      if v == month_num and len(k) > 2][0]
        fy = make_fy(month_num, year)
        order = fy_month_order(month_num)
        return month_num, month_name, year, fy, order

    # Strategy 4: URL — MKI-April-2024 or MKI-MAH-April-2025
    m4 = re.search(r"mki-(?:[a-z]+-)?([a-z]+)-(\d{4})(?:-|_|\.)", url_lower)
    if m4:
        month_str = m4.group(1)
        year = int(m4.group(2))
        month_num = MONTH_PARSE_MAP.get(month_str)
        if month_num and 1 <= month_num <= 12:
            fy = make_fy(month_num, year)
            order = fy_month_order(month_num)
            return month_num, month_str.capitalize(), year, fy, order

    # Strategy 5: URL — MKI-December-2024
    m5 = re.search(r"mki-([a-z]{3,9})-(\d{4})", url_lower)
    if m5:
        month_str = m5.group(1)
        year = int(m5.group(2))
        month_num = MONTH_PARSE_MAP.get(month_str)
        if month_num and 1 <= month_num <= 12:
            fy = make_fy(month_num, year)
            order = fy_month_order(month_num)
            return month_num, month_str.capitalize(), year, fy, order

    return NULL


# ─────────────────────────────────────────────────────────
# TEXT NORMALIZER
# ─────────────────────────────────────────────────────────
def normalize_text(text):
    """
    Normalize PDF extracted text:
    - Replace em-dash variants with regular hyphen
    - Replace ellipsis and special symbols
    - Join multi-line number splits (pass 1: next line is all-numbers)
    - Join multi-line description wraps (pass 2: label continues to next line)
    """
    # Replace dash variants
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2212", "-")   # minus sign
    text = text.replace("\u2026", "")    # horizontal ellipsis → remove

    # ── Pass 0 ────────────────────────────────────────────
    # Collapse spaced-digit numbers: "1 0 7 4 9 . 4 0" → "10749.40"
    # Tripura PDFs render some BE values as space-separated individual digits.
    # Matches 3+ single digits separated by single spaces, with optional decimal part.
    # Requires 3+ digits to avoid collapsing unrelated single-digit tokens.
    text = re.sub(
        r'(?<!\d)(\d(?:[ ]\d){2,})([ ]\.[ ](\d(?:[ ]\d)*))?(?![\d.])',
        lambda m: (
            m.group(1).replace(' ', '')
            + ('.' + m.group(3).replace(' ', '') if m.group(3) else '')
        ),
        text,
    )

    lines = text.split("\n")

    # ── Pass 1 ────────────────────────────────────────────
    # Join lines where text ends without digits and next line is all-numbers
    # e.g. "Recovery of Loans and Advances\n100.00 0.03 0.03 0.01"
    joined = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if (i + 1 < len(lines)
                and line
                and not re.search(r"[\d\.\-]+\s*$", line)
                and re.match(r"^\s*[\-\d][\d\.,\s\-]+$", lines[i + 1])):
            joined.append(line + " " + lines[i + 1].strip())
            i += 2
        else:
            joined.append(line)
            i += 1

    # ── Pass 2 ────────────────────────────────────────────
    # Join labeled items whose description wraps across lines.
    # Handles: "(c) Grants –in-Aid and\nContribution 16000.00 29.62 0.19 22.58"
    # and 3-line wraps: "(a) Recovery of Loans and\nAdvances (Non debt Capital\nReceipts) 134.00"
    # Rule: current line starts with item marker, doesn't end with a number;
    #       collect continuation lines (up to 3) until one ends with a number.
    _ITEM_START = re.compile(r'^\s*(?:\d+\.?|\([a-zA-Z\d\+]+\))\s+')
    result2 = []
    i = 0
    while i < len(joined):
        line = joined[i]
        if _ITEM_START.match(line) and not re.search(r'[\d,\.]+\s*$', line):
            # Try to collect continuation lines
            combined = line
            j = i + 1
            found = False
            while j < len(joined) and j <= i + 3:
                next_l = joined[j]
                # Stop if we hit a new item label
                if _ITEM_START.match(next_l):
                    break
                combined += ' ' + next_l.strip()
                if re.search(r'[\d,\.]+\s*$', next_l):
                    found = True
                    j += 1
                    break
                j += 1
            if found and j > i + 1:
                result2.append(combined)
                i = j
            else:
                result2.append(line)
                i += 1
        else:
            result2.append(line)
            i += 1

    return "\n".join(result2)


# ─────────────────────────────────────────────────────────
# NUMBER EXTRACTOR
# ─────────────────────────────────────────────────────────
def parse_num(s):
    """Clean string to float. Returns None for invalid."""
    if not s:
        return None
    s = str(s).replace(",", "").strip()
    # Jharkhand-style negative: (-) prefix
    if s.startswith('(-)') or s.startswith('(-) '):
        s = '-' + s[3:].strip()
    if s in ("--", "-", "", "NA", "N/A", "$", ".."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────
# INDICATOR PATTERNS
# Each list has patterns in priority order; first match wins.
# All patterns capture 4 groups: BE, Actuals, %Current, %Prev
# _N4 = (number)(sep)(number)(sep)(number)(sep)(number)
#   where sep = \s*%?\s+  — handles both "5.76" and "5.76%"
#   and number = (?:\(-\)\s*)?-?[\d,\.]+  — handles (-) prefix
# ─────────────────────────────────────────────────────────
PATTERNS = {
    # ── Revenue Receipts ──────────────────────────────────
    "revenue_receipts": [
        # Standard: "1. Revenue Receipts BE actuals ..."  (greedy [^\n]*)
        rf"(?:^|\n)\s*1\.?\s+Revenue\s+Receipts[^\n]*{_N4}",
        # Tamil Nadu: "(1) Revenue Receipts ..."
        rf"(?:^|\n)\s*\(1\)\s+Revenue\s+Receipts[^\n]*{_N4}",
    ],

    # ── Tax Revenue ───────────────────────────────────────
    "tax_revenue": [
        rf"\(a\)\s*Tax\s+Revenue[^\n]*{_N4}",
        rf"[aA]\)\s*Tax\s+Revenue[^\n]*{_N4}",
        # Karnataka: numbers on next line after formula "(i+ii+iii+iv+v+vi+vii)"
        rf"\(a\)\s*Tax\s+Revenue[^\n]*\n[^\n]*{_N4}",
    ],

    # ── SGST / GST ────────────────────────────────────────
    "sgst": [
        # Standard (i) prefix with various abbreviations
        rf"(?:\(i\)|i\))\s*(?:SGST|GST|SGST\s*/\s*CGST(?:\s*/\s*IGST)?)[^\n]*{_N4}",
        # G.S.T. (Manipur)
        rf"\(i\)\s*G\.S\.T\.[^\n]*{_N4}",
        # "G S T" spaced letters (Odisha)
        rf"\(i\)\s*G\s+S\s+T[^\n]*{_N4}",
        # "Goods and Service(s) Tax" (Tamil Nadu, Meghalaya)
        rf"(?:\(i\)|i\))\s*Goods\s+and\s+Services?\s+Tax[^\n]*{_N4}",
        # "State Goods & Service Tax" (Gujarat)
        rf"\(i\)\s*State\s+Goods\s+(?:&|and)\s+Services?\s+Tax[^\n]*{_N4}",
        # Assam Roman numeral: "I State Goods and Services Tax"
        rf"(?:^|\n)\s*I\s+(?:State\s+)?Goods\s+and\s+Services?\s+Tax[^\n]*{_N4}",
        rf"(?:^|\n)\s*I\s+(?:SGST|GST)[^\n]*{_N4}",
        # Sikkim: uses (ii) SGST (with (i) being CGST) — 3-column format (no pct_prev)
        rf"\(ii\)\s*SGST[^\n]*{_N4_opt}",
    ],

    # ── Stamps & Registration ─────────────────────────────
    "stamps_registration": [
        rf"(?:\(ii\)|ii\))\s*Stamps\s+and\s+Registration[^\n]*{_N4}",
        rf"\(ii\)\s*Stamps[^\n]*{_N4}",
        # Assam Roman: "III Stamps and Registration"
        rf"(?:^|\n)\s*III\s+Stamps[^\n]*{_N4}",
    ],

    # ── Land Revenue ──────────────────────────────────────
    "land_revenue": [
        rf"(?:\(iii\)|iii\))\s*Land\s+Revenue[^\n]*{_N4}",
        # Assam Roman: "II Land Revenue"
        rf"(?:^|\n)\s*II\s+Land\s+Revenue[^\n]*{_N4}",
    ],

    # ── Sales Tax ─────────────────────────────────────────
    "sales_tax": [
        rf"(?:\(iv\)|iv\))\s*(?:Sales\s+Tax|Taxes\s+on\s+Sales)[^\n]*{_N4}",
        # Meghalaya: "Sale Tax" (singular)
        rf"\(iv\)\s*Sale\s+Tax[^\n]*{_N4}",
        # Tamil Nadu / Assam: "Taxes on Sales, Trade etc"
        rf"\(iv\)\s*Taxes\s+on\s+Sales[^\n]*{_N4}",
        # Assam Roman: "V Taxes on Sales"
        rf"(?:^|\n)\s*V\s+(?:Sales?\s+Tax|Taxes\s+on\s+Sales)[^\n]*{_N4}",
    ],

    # ── State Excise ──────────────────────────────────────
    "state_excise": [
        rf"(?:\(v\)|v\))\s*State\s+Excise[^\n]*{_N4}",
        # Assam Roman: "IV State Excise"
        rf"(?:^|\n)\s*IV\s+State\s+Excise[^\n]*{_N4}",
    ],

    # ── State Share of Union Taxes ────────────────────────
    "union_taxes_share": [
        # Apostrophe variants: State's / States / State`s (. matches any char)
        rf"(?:\(vi\)|vi\))\s*State.s\s+Share\s+of\s+Union[^\n]*{_N4}",
        rf"\(vi\)\s*State.s\s+Share[^\n]*{_N4}",
        # Without apostrophe: "State Share of Union Taxes" (Meghalaya)
        rf"\(vi\)\s*State\s+Share\s+of\s+Union[^\n]*{_N4}",
        rf"\(vi\)\s*State\s+Share[^\n]*{_N4}",
        # Assam Roman: "VI State's Share ..."
        rf"(?:^|\n)\s*VI\s+State[^\n]*{_N4}",
    ],

    # ── Other Taxes ───────────────────────────────────────
    "other_taxes": [
        rf"(?:\(vii\)|vii\))\s*Other\s+Taxes[^\n]*{_N4}",
        # Assam Roman: "VII Other Taxes and Duties"
        rf"(?:^|\n)\s*VII\s+Other\s+Taxes[^\n]*{_N4}",
    ],

    # ── Non-Tax Revenue ───────────────────────────────────
    # em-dash "Non –Tax" → after normalize becomes "Non -Tax"
    "non_tax_revenue": [
        rf"(?:\(b\)|b\))\s*Non[\s\-]+Tax\s+Revenue[^\n]*{_N4}",
        rf"(?:\(b\)|b\))\s*Non.Tax\s+Revenue[^\n]*{_N4}",
    ],

    # ── Grants-in-Aid ─────────────────────────────────────
    # Variants: "Grant-in-Aid", "Grants-in-Aid", "Grants in aid", "Grants –in-Aid"
    "grants_in_aid": [
        rf"(?:\(c\)|c\))\s*Grants?\s*[\-\s]+in[\-\s]+Aid[^\n]*{_N4}",
        rf"(?:\(c\)|c\))\s*Grants?\s*in\s+aid[^\n]*{_N4}",
        # Odisha: only 3 numbers (pct_prev column absent) — optional 4th
        rf"\(c\)\s*Grants?-in-Aid[^\n]*{_N4_opt}",
    ],

    # ── Capital Receipts ──────────────────────────────────
    "capital_receipts": [
        rf"(?:^|\n)\s*2\.?\s+Capital\s+Receipts[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(2\)\s+Capital\s+Receipts[^\n]*{_N4}",
    ],

    # ── Recovery of Loans ─────────────────────────────────
    "recovery_loans": [
        rf"(?:\(a\)|a\))\s*Recovery\s+of\s+Loans\s+(?:and|&)\s+Advances[^\n]*{_N4}",
        rf"\(a\)\s*Recovery\s+of\s+Loans[^\n]*{_N4}",
    ],

    # ── Borrowings ────────────────────────────────────────
    # "Borrowings" vs "Borrowing" (Manipur singular), "and" vs "&"
    "borrowings": [
        rf"(?:\(c\)|c\))\s*Borrowings?\s+(?:and|&)\s+Other\s+Liabilities[^\n]*{_N4}",
        rf"\(c\)\s*Borrowings?[^\n]*{_N4}",
    ],

    # ── Total Receipts ────────────────────────────────────
    "total_receipts": [
        rf"(?:^|\n)\s*3\.?\s+Total\s+Receipts[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(3\)\s+Total\s+Receipts[^\n]*{_N4}",
    ],

    # ── Revenue Expenditure ───────────────────────────────
    "revenue_expenditure": [
        rf"(?:^|\n)\s*4\.?\s+Revenue\s+Expenditure[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(4\)\s+Revenue\s+Expenditure[^\n]*{_N4}",
        # Haryana: "Revenue Expenditure\n4 148416.59..." → joined by normalize_text
        # as "Revenue Expenditure 4 148416.59..." — fallback without leading "4."
        rf"Revenue\s+Expenditure[^\n]*{_N4}",
    ],

    # ── Interest Payments ─────────────────────────────────
    "interest_payments": [
        rf"(?:\(b\)|b\))\s*Expenditure\s+on\s+Interest\s+Payments?[^\n]*{_N4}",
        rf"\(b\)\s*Expenditure\s+on\s+Interest[^\n]*{_N4}",
    ],

    # ── Salaries & Wages ──────────────────────────────────
    "salaries_wages": [
        # Standard: 4 columns present
        rf"(?:\(c\)|c\))\s*Expenditure\s+on\s+Salaries[^\n]*{_N4}",
        # Fallback: partial data — Arunachal Pradesh has only BE+actuals (no pct columns);
        # Tamil Nadu has only BE (actuals marked "$" which isn't a number).
        # Handles "Salaries/Wages" and "Salaries and Wages" variants.
        # _Nflex already includes non-greedy skip; do NOT add [^\n]* before it.
        rf"\(c\)\s*Expenditure\s+on\s+Salaries{_Nflex}",
    ],

    # ── Pension ───────────────────────────────────────────
    "pension": [
        rf"(?:\(d\)|d\))\s*Expenditure\s+on\s+[Pp]ension[^\n]*{_N4}",
    ],

    # ── Subsidy ───────────────────────────────────────────
    "subsidy": [
        # Standard: 4 columns present
        rf"(?:\(e\)|e\))\s*Expenditure\s+on\s+Subsidy[^\n]*{_N4}",
        # Fallback: Tamil Nadu reports only BE (actuals marked "$").
        # Arunachal Pradesh uses ".." (no data) so even this fallback returns None there.
        # _Nflex already includes non-greedy skip; do NOT add [^\n]* before it.
        rf"\(e\)\s*Expenditure\s+on\s+Subsidy{_Nflex}",
    ],

    # ── Capital Expenditure ───────────────────────────────
    "capital_expenditure": [
        rf"(?:^|\n)\s*5\.?\s+Capital\s+Expenditure[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(5\)\s+Capital\s+Expenditure[^\n]*{_N4}",
    ],

    # ── Total Expenditure ─────────────────────────────────
    "total_expenditure": [
        rf"(?:^|\n)\s*7\.?\s+Total\s+Expenditure[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(7\)\s+Total\s+Expenditure[^\n]*{_N4}",
        rf"(?:^|\n)\s*9\.?\s+Total\s+Expenditure[^\n]*{_N4}",
    ],

    # ── Loans & Advances Disbursed ────────────────────────
    # "Loans" vs "Loan" singular (Odisha)
    "loans_advances_disbursed": [
        rf"(?:^|\n)\s*8\.?\s+Loans?\s+and\s+Advances?\s+Disbursed[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(8\)\s+Loans?\s+and\s+Advances?\s+Disbursed[^\n]*{_N4}",
        rf"(?:^|\n)\s*7\.?\s+Loans?\s+(?:&|and)\s+Advances?\s+[Dd]isbursed[^\n]*{_N4}",
    ],

    # ── Revenue Surplus / Deficit ─────────────────────────
    "revenue_surplus_deficit": [
        rf"(?:^|\n)\s*9\.?\s+Revenue\s+(?:Surplus|Deficit)[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(9\)\s+Revenue\s+(?:Surplus|Deficit)[^\n]*{_N4}",
        rf"(?:^|\n)\s*10\.?\s+Revenue\s+(?:Surplus|Deficit)[^\n]*{_N4}",
    ],

    # ── Fiscal Deficit ────────────────────────────────────
    # Bihar: "10. Fiscal /Surplus(+)/Deficit (-)" — has "/" before Surplus
    "fiscal_deficit": [
        rf"(?:^|\n)\s*10\.?\s+Fiscal\s+(?:Surplus|Deficit)[^\n]*{_N4}",
        rf"(?:^|\n)\s*10\.?\s+Fiscal[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(10\)\s+Fiscal[^\n]*{_N4}",
        rf"(?:^|\n)\s*11\.?\s+Fiscal[^\n]*{_N4}",
    ],

    # ── Primary Deficit ───────────────────────────────────
    "primary_deficit": [
        rf"(?:^|\n)\s*11\.?\s+Primary\s+(?:Deficit|Surplus)[^\n]*{_N4}",
        rf"(?:^|\n)\s*\(11\)\s+Primary\s+(?:Deficit|Surplus)[^\n]*{_N4}",
        rf"(?:^|\n)\s*12\.?\s+Primary\s+(?:Deficit|Surplus)[^\n]*{_N4}",
        rf"(?:^|\n)\s*.*?Primary\s+Deficit[^\n]+\n\s*([-+\d\.]+)\s+([-+\d\.]+)\s+([-+\d\.]+)\n.*?(?:\+|[a-zA-Z])\s*(\d+\.\d+)",
    ],
}


def extract_indicators(text):
    """
    Extract all indicators from normalized PDF text.
    Returns dict: {indicator_id: {be, actuals, pct_current, pct_prev, found}}
    """
    text = normalize_text(text)
    results = {}

    for ind_id in INDICATOR_IDS:
        patterns = PATTERNS.get(ind_id, [])
        found = False

        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                results[ind_id] = {
                    "be":          parse_num(m.group(1)),
                    "actuals":     parse_num(m.group(2)),
                    "pct_current": parse_num(m.group(3)),
                    "pct_prev":    parse_num(m.group(4)),
                    "found":       True,
                }
                found = True
                break

        if not found:
            results[ind_id] = {
                "be": None, "actuals": None,
                "pct_current": None, "pct_prev": None,
                "found": False,
            }

    total_found = sum(1 for v in results.values() if v["found"])
    log.debug(f"Extracted {total_found}/{len(INDICATOR_IDS)} indicators")

    # Special patch for Andhra Pradesh Primary Deficit where the first number wraps to previous line
    ap_pd_match = re.search(r"Primary\s+Deficit.*?Surplus\s+([\d\.]+)\s*\n\s*([-+\d\.]+)\s+([-+\d\.]+)\s+([-+\d\.]+)", text, re.IGNORECASE)
    if ap_pd_match and not results["primary_deficit"]["found"]:
        results["primary_deficit"] = {
            "found": True,
            "raw": ap_pd_match.group(0),
            "be": parse_num(ap_pd_match.group(2)),
            "actuals": parse_num(ap_pd_match.group(3)),
            "pct_current": parse_num(ap_pd_match.group(4)),
            "pct_prev": parse_num(ap_pd_match.group(1)),
        }

    return results


def parse_pdf_full(url, timeout=30):
    """
    Full pipeline: download → extract text → parse date → extract indicators.
    Returns dict with all data or error info.
    """
    pdf_bytes = download_pdf(url, timeout)
    if not pdf_bytes:
        return {"status": DQ_PDF_ERROR, "url": url}

    text = extract_text(pdf_bytes)
    if not text:
        return {"status": DQ_PDF_ERROR, "url": url, "reason": "empty text"}

    cal_month, month_name, cal_year, fy, fy_order = parse_date_from_text(text, url)
    if not cal_month:
        return {"status": DQ_PARSE_ERROR, "url": url, "reason": "date parse failed"}

    indicators = extract_indicators(text)
    found_count = sum(1 for v in indicators.values() if v["found"])

    return {
        "status": DQ_OK if found_count > 10 else DQ_PARSE_ERROR,
        "url": url,
        "calendar_month": cal_month,
        "month_name": month_name,
        "calendar_year": cal_year,
        "fy": fy,
        "fy_month_order": fy_order,
        "indicators": indicators,
        "found_count": found_count,
    }
