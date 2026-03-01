"""
Fiscal Pulse — PDF Parser
Fixed version: handles em-dash, multi-line splits, various state formats
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

    # Strategy 1: PDF header text — "At the end of December, 2024"
    m = re.search(
        r"At\s+the\s+end\s+of\s+([A-Za-z]+)[,\s]+(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        month_str = m.group(1).lower().strip()
        year = int(m.group(2))
        month_num = MONTH_PARSE_MAP.get(month_str)
        if month_num and 1 <= month_num <= 12:
            fy = make_fy(month_num, year)
            order = fy_month_order(month_num)
            return month_num, m.group(1).capitalize(), year, fy, order

    # Strategy 2: URL pattern — MKI-12-2024 or MKI-12-25
    url_lower = url.lower()
    m2 = re.search(r"mki-(\d{1,2})-(\d{2,4})(?:-|_|\.)", url_lower)
    if m2:
        month_num = int(m2.group(1))
        if not (1 <= month_num <= 12):
            return NULL
        yr_raw = m2.group(2)
        year = int("20" + yr_raw) if len(yr_raw) == 2 else int(yr_raw)
        month_name = list(MONTH_PARSE_MAP.keys())[
            [k for k in MONTH_PARSE_MAP if MONTH_PARSE_MAP[k] == month_num][0]
            if False else 0
        ]
        # Simpler approach
        month_name = [k.capitalize() for k, v in MONTH_PARSE_MAP.items()
                      if v == month_num and len(k) > 2][0]
        fy = make_fy(month_num, year)
        order = fy_month_order(month_num)
        return month_num, month_name, year, fy, order

    # Strategy 3: URL pattern — MKI-April-2024 or MKI-MAH-April-2025
    m3 = re.search(r"mki-(?:[a-z]+-)?([a-z]+)-(\d{4})(?:-|_|\.)", url_lower)
    if m3:
        month_str = m3.group(1)
        year = int(m3.group(2))
        month_num = MONTH_PARSE_MAP.get(month_str)
        if month_num and 1 <= month_num <= 12:
            month_name = month_str.capitalize()
            fy = make_fy(month_num, year)
            order = fy_month_order(month_num)
            return month_num, month_name, year, fy, order

    # Strategy 4: URL with full month name inside — MKI-December-2024
    m4 = re.search(r"mki-([a-z]{3,9})-(\d{4})", url_lower)
    if m4:
        month_str = m4.group(1)
        year = int(m4.group(2))
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
    - Replace em-dash (–, —) with regular hyphen
    - Collapse multiple spaces
    - Join multi-line number splits
    """
    # Replace all dash variants
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2212", "-")  # minus sign

    # Join lines where text wraps: if line ends without digits
    # and next line starts with digits → join them
    lines = text.split("\n")
    joined = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Check if this line has no trailing number and next line is all numbers
        if (i + 1 < len(lines)
                and line
                and not re.search(r"[\d\.\-]+\s*$", line)
                and re.match(r"^\s*[\-\d][\d\.,\s\-]+$", lines[i + 1])):
            joined.append(line + " " + lines[i + 1].strip())
            i += 2
        else:
            joined.append(line)
            i += 1

    return "\n".join(joined)


# ─────────────────────────────────────────────────────────
# NUMBER EXTRACTOR
# ─────────────────────────────────────────────────────────
def parse_num(s):
    """Clean string to float. Returns None for invalid."""
    if not s:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("--", "-", "", "NA", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────
# INDICATOR PATTERNS
# Each pattern extracts 4 groups: BE, Actuals, %Current, %Prev
# ─────────────────────────────────────────────────────────
PATTERNS = {
    "revenue_receipts": [
        r"(?:^|\n)\s*1\.\s+Revenue\s+Receipts\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "tax_revenue": [
        r"\(a\)\s+Tax\s+Revenue[^\n]*\n?\s*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(a\)\s+Tax\s+Revenue[^(]*?([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "sgst": [
        r"\(i\)\s+(?:SGST|GST|SGST\s*/\s*CGST[^\n]*?)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(i\)\s+(?:SGST|GST)[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "stamps_registration": [
        r"\(ii\)\s+Stamps\s+and\s+Registration[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(ii\)\s+Stamps[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "land_revenue": [
        r"\(iii\)\s+Land\s+Revenue[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "sales_tax": [
        r"\(iv\)\s+(?:Sales\s+Tax|Taxes\s+on\s+Sales)[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "state_excise": [
        r"\(v\)\s+State\s+Excise[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "union_taxes_share": [
        r"\(vi\)\s+State.s\s+Share\s+of\s+Union[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(vi\)\s+State.s\s+Share[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "other_taxes": [
        r"\(vii\)\s+Other\s+Taxes[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    # FIXED: em-dash variant
    "non_tax_revenue": [
        r"\(b\)\s+Non[\s\-]+Tax\s+Revenue[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(b\)\s+Non.Tax\s+Revenue[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    # FIXED: em-dash variant
    "grants_in_aid": [
        r"\(c\)\s+Grants[\s\-]+in[\s\-]+Aid[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(c\)\s+Grants.in.Aid[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "capital_receipts": [
        r"(?:^|\n)\s*2\.\s+Capital\s+Receipts\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    # FIXED: multi-line split — description on one line, numbers on next
    "recovery_loans": [
        r"\(a\)\s+Recovery\s+of\s+Loans\s+and\s+Advances[^\n]*\n\s*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(a\)\s+Recovery\s+of\s+Loans[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    # FIXED: multi-line split
    "borrowings": [
        r"\(c\)\s+Borrowings\s+and\s+Other\s+Liabilities[^\n]*\n\s*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(c\)\s+Borrowings[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "total_receipts": [
        r"(?:^|\n)\s*3\.\s+Total\s+Receipts[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "revenue_expenditure": [
        r"(?:^|\n)\s*4\.\s+Revenue\s+Expenditure[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "interest_payments": [
        r"\(b\)\s+Expenditure\s+on\s+Interest\s+Payments[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"\(b\)\s+Expenditure\s+on\s+Interest[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "salaries_wages": [
        r"\(c\)\s+Expenditure\s+on\s+Salaries[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "pension": [
        r"\(d\)\s+Expenditure\s+on\s+Pension[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "subsidy": [
        r"\(e\)\s+Expenditure\s+on\s+Subsidy[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "capital_expenditure": [
        r"(?:^|\n)\s*5\.\s+Capital\s+Expenditure[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "total_expenditure": [
        r"(?:^|\n)\s*7\.\s+Total\s+Expenditure[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "loans_advances_disbursed": [
        r"(?:^|\n)\s*8\.\s+Loans\s+and\s+Advances\s+Disbursed[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "revenue_surplus_deficit": [
        r"(?:^|\n)\s*9\.\s+Revenue\s+Surplus[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "fiscal_deficit": [
        r"(?:^|\n)\s*10\.\s+Fiscal\s+Surplus[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"(?:^|\n)\s*10\.\s+Fiscal\s+Deficit[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
    ],
    "primary_deficit": [
        r"(?:^|\n)\s*11\.\s+Primary\s+Deficit[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
        r"(?:^|\n)\s*11\.\s+Primary\s+Surplus[^\n]*([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)\s+([\-\d,\.]+)",
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
