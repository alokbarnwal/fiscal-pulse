"""
Fiscal Pulse — Audit Parser
Compares current pdf_parser.py output against naive line-by-line extraction
to identify which states/indicators have regex pattern bugs.

Usage:
    python audit_parser.py              # audit all active states
    python audit_parser.py Chhattisgarh # audit single state

Output:
    audit_report.csv — detailed comparison (state, indicator, field, expected, got, match)
    Console summary   — which states/indicators have mismatches
"""

import re
import sys
import time
import logging
import pandas as pd

from pdf_parser import download_pdf, extract_text, normalize_text, extract_indicators, parse_num
from pipeline import get_pdf_urls
from config import STATES, INDICATOR_IDS, INDICATOR_NAMES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# INDICATOR LINE SEARCH KEYWORDS
# Each entry: (indicator_id, line_prefixes, line_keywords)
# line_prefixes: number/letter anchors at line start  e.g. "1.", "(a)"
# line_keywords: text to match in the line
# ─────────────────────────────────────────────────────────
INDICATOR_LINE_SPECS = [
    ("revenue_receipts",        ["1."],       ["revenue receipts"]),
    ("tax_revenue",             ["(a)"],      ["tax revenue"]),
    ("sgst",                    ["(i)"],      ["sgst", "gst"]),
    ("stamps_registration",     ["(ii)"],     ["stamps"]),
    ("land_revenue",            ["(iii)"],    ["land revenue"]),
    ("sales_tax",               ["(iv)"],     ["sales tax", "taxes on sales"]),
    ("state_excise",            ["(v)"],      ["state excise"]),
    ("union_taxes_share",       ["(vi)"],     ["state's share", "states share", "state.s share"]),
    ("other_taxes",             ["(vii)"],    ["other taxes"]),
    ("non_tax_revenue",         ["(b)"],      ["non-tax revenue", "non tax revenue"]),
    ("grants_in_aid",           ["(c)"],      ["grants-in-aid", "grants in aid", "grants"]),
    ("capital_receipts",        ["2."],       ["capital receipts"]),
    ("recovery_loans",          ["(a)"],      ["recovery of loans"]),
    ("borrowings",              ["(c)"],      ["borrowings"]),
    ("total_receipts",          ["3."],       ["total receipts"]),
    ("revenue_expenditure",     ["4."],       ["revenue expenditure"]),
    ("interest_payments",       ["(b)"],      ["interest payments", "expenditure on interest"]),
    ("salaries_wages",          ["(c)"],      ["salaries"]),
    ("pension",                 ["(d)"],      ["pension"]),
    ("subsidy",                 ["(e)"],      ["subsidy"]),
    ("capital_expenditure",     ["5."],       ["capital expenditure"]),
    ("total_expenditure",       ["7."],       ["total expenditure"]),
    ("loans_advances_disbursed",["8."],       ["loans and advances disbursed"]),
    ("revenue_surplus_deficit", ["9."],       ["revenue surplus", "revenue deficit"]),
    ("fiscal_deficit",          ["10."],      ["fiscal"]),
    ("primary_deficit",         ["11."],      ["primary"]),
]

# Map from ind_id to spec for fast lookup
_SPEC_MAP = {ind_id: (prefixes, keywords)
             for ind_id, prefixes, keywords in INDICATOR_LINE_SPECS}


def _extract_numbers_from_line(line):
    """Return all numeric tokens (including negatives) from a line."""
    tokens = re.findall(r"-?[\d,]+\.?\d*", line)
    cleaned = []
    for t in tokens:
        v = parse_num(t)
        if v is not None:
            cleaned.append(v)
    return cleaned


def _strip_parentheticals(line):
    """Remove parenthetical expressions like (1+2), (a+b+c), (4+ 5) from line."""
    return re.sub(r"\([^)]*\)", "", line)


def simple_extract(text):
    """
    Naive line-by-line extraction of indicator values.
    Strips parenthetical labels before pulling numbers.
    Returns {indicator_id: {be, actuals, pct_current, pct_prev}} or empty fields if not found.
    """
    text = normalize_text(text)
    lines = text.split("\n")
    results = {}

    for ind_id in INDICATOR_IDS:
        prefixes, keywords = _SPEC_MAP.get(ind_id, ([], []))
        results[ind_id] = {"be": None, "actuals": None, "pct_current": None, "pct_prev": None}

        for i, line in enumerate(lines):
            line_lower = line.lower().strip()

            # Check prefix match
            prefix_match = any(line_lower.startswith(p.lower()) for p in prefixes)
            if not prefix_match:
                continue

            # Check keyword match
            keyword_match = any(kw in line_lower for kw in keywords)
            if not keyword_match:
                continue

            # Found the indicator line — strip parentheticals and extract numbers
            clean_line = _strip_parentheticals(line)
            nums = _extract_numbers_from_line(clean_line)

            if len(nums) >= 4:
                # Standard case: 4+ numbers on same line → [BE, actuals, pct_curr, pct_prev]
                results[ind_id] = {
                    "be":          nums[0],
                    "actuals":     nums[1],
                    "pct_current": nums[2],
                    "pct_prev":    nums[3],
                }
            elif len(nums) == 1 and i + 1 < len(lines):
                # Multi-line case: one number (pct_prev) on this line, rest on next line
                # e.g. Chhattisgarh fiscal/primary deficit format
                pct_prev_val = nums[0]
                next_line = lines[i + 1]
                next_nums = _extract_numbers_from_line(_strip_parentheticals(next_line))
                if len(next_nums) >= 3:
                    results[ind_id] = {
                        "be":          next_nums[0],
                        "actuals":     next_nums[1],
                        "pct_current": next_nums[2],
                        "pct_prev":    pct_prev_val,
                    }
            elif len(nums) < 4 and i + 1 < len(lines):
                # Partial numbers — check next line
                next_line = lines[i + 1]
                combined = nums + _extract_numbers_from_line(_strip_parentheticals(next_line))
                if len(combined) >= 4:
                    results[ind_id] = {
                        "be":          combined[0],
                        "actuals":     combined[1],
                        "pct_current": combined[2],
                        "pct_prev":    combined[3],
                    }

            break  # Stop after first matching line

    return results


def _vals_match(a, b, tol=0.01):
    """Return True if both are None, or both are close floats."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def audit_state(state_name, slug, url_type):
    """
    Audit one state: compare current parser vs naive extractor.
    Returns list of comparison rows.
    """
    log.info(f"\n[AUDIT] {state_name}")

    urls = get_pdf_urls(state_name, slug, url_type)
    if not urls:
        log.warning(f"  [{state_name}] No PDF URLs found — skipping")
        return []

    url = urls[0]
    log.info(f"  Latest PDF: {url}")

    pdf_bytes = download_pdf(url)
    if not pdf_bytes:
        log.warning(f"  [{state_name}] PDF download failed")
        return []

    raw_text = extract_text(pdf_bytes)
    if not raw_text:
        log.warning(f"  [{state_name}] Text extraction failed")
        return []

    # Print first 50 lines for visibility on Chhattisgarh
    norm_text = normalize_text(raw_text)
    log.info(f"  Extracted {len(raw_text)} chars raw, {len(norm_text)} chars normalized")

    # Run both extractors
    parsed   = extract_indicators(raw_text)   # current regex patterns
    expected = simple_extract(raw_text)        # naive line-by-line

    rows = []
    fields = ["be", "actuals", "pct_current", "pct_prev"]

    for ind_id in INDICATOR_IDS:
        p = parsed.get(ind_id, {})
        e = expected.get(ind_id, {})

        for field in fields:
            got_val      = p.get(field)
            expected_val = e.get(field)
            match        = _vals_match(got_val, expected_val)

            rows.append({
                "state":        state_name,
                "indicator_id": ind_id,
                "field":        field,
                "expected":     expected_val,
                "got":          got_val,
                "match":        match,
                "pdf_url":      url,
            })

    ok_count = sum(1 for r in rows if r["match"])
    log.info(f"  {ok_count}/{len(rows)} fields match")

    return rows


def print_raw_text(state_name, slug, url_type, n_lines=80):
    """Debug helper: print raw PDF text for a state."""
    urls = get_pdf_urls(state_name, slug, url_type)
    if not urls:
        print(f"No URLs found for {state_name}")
        return
    pdf_bytes = download_pdf(urls[0])
    if not pdf_bytes:
        print("Download failed")
        return
    text = normalize_text(extract_text(pdf_bytes))
    print(f"\n{'='*60}")
    print(f"RAW TEXT — {state_name} | {urls[0]}")
    print('='*60)
    for i, line in enumerate(text.split("\n")[:n_lines], 1):
        print(f"{i:3d}: {line}")


def main():
    # Allow single-state mode: python audit_parser.py "Chhattisgarh"
    target_state = sys.argv[1] if len(sys.argv) > 1 else None

    all_rows = []

    for name, slug, url_type, category, avail in STATES:
        if not avail:
            continue
        if target_state and name.lower() != target_state.lower():
            continue

        rows = audit_state(name, slug, url_type)
        all_rows.extend(rows)
        time.sleep(1.5)

    if not all_rows:
        log.warning("No audit rows collected.")
        return

    df = pd.DataFrame(all_rows)
    df.to_csv("audit_report.csv", index=False)
    log.info(f"\nAudit report saved to audit_report.csv ({len(df)} rows)")

    # ── Summary ──────────────────────────────────────────
    mismatches = df[df["match"] == False]
    print(f"\n{'='*60}")
    print(f"AUDIT SUMMARY")
    print(f"{'='*60}")
    print(f"Total field checks : {len(df)}")
    print(f"Matches            : {len(df) - len(mismatches)}")
    print(f"Mismatches         : {len(mismatches)}")

    if len(mismatches) == 0:
        print("\n✅ All fields match! Parser is correct for all audited states.")
        return

    print(f"\n{'─'*60}")
    print("MISMATCH DETAILS (by state + indicator):")
    print(f"{'─'*60}")

    summary = mismatches.groupby(["state", "indicator_id", "field"]).apply(
        lambda x: x[["expected", "got"]].iloc[0]
    ).reset_index()

    for _, row in summary.iterrows():
        print(f"  {row['state']:<20} {row['indicator_id']:<30} {row['field']:<12} "
              f"expected={row['expected']}  got={row['got']}")

    print(f"\n{'─'*60}")
    print("STATES WITH MISMATCHES:")
    for state in sorted(mismatches["state"].unique()):
        state_miss = mismatches[mismatches["state"] == state]
        bad_inds = state_miss["indicator_id"].unique()
        print(f"  {state}: {len(state_miss)} mismatches across {len(bad_inds)} indicators")
        for ind in bad_inds:
            print(f"    - {ind}")


if __name__ == "__main__":
    main()
