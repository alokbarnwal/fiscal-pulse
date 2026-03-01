"""
Fiscal Pulse — Main Pipeline
Run modes:
  python pipeline.py --mode historical   ← 2 years backfill
  python pipeline.py --mode update       ← latest month only
  python pipeline.py --mode state --state "Chhattisgarh"
"""

import os, sys, re, json, time, logging, argparse
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from pathlib import Path

from config import (
    STATES, ACTIVE_STATES, HEADERS, REQUEST_DELAY,
    DATA_DIR, STATES_DIR, MASTER_CSV, METADATA_JSON, TRACKER_JSON,
    INPUTS_DIR, GSDP_FILE, MANUAL_OVERRIDES, OUTPUTS_DIR, OFFICE_EXCEL, LOG_FILE,
    INDICATOR_IDS, INDICATOR_NAMES, INDICATOR_GROUP, INDICATOR_SUBGROUP,
    MASTER_COLUMNS, MONTH_NAMES, DQ_OK, DQ_PARSE_ERROR, DQ_PDF_ERROR,
    DQ_MISSING, DQ_MANUAL, DQ_NA,
    get_state_url, state_to_filename, make_fy, fy_month_order, CALENDAR_TO_FY,
    YEARS_HISTORY
)
from pdf_parser import parse_pdf_full, download_pdf
from excel_exporter import generate_office_excel

# ─────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(STATES_DIR).mkdir(parents=True, exist_ok=True)
Path(OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)
Path(INPUTS_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# URL SCRAPER
# ─────────────────────────────────────────────────────────
def get_pdf_urls(state_name, slug_or_id, url_type):
    """Scrape CAG page and return list of MKI PDF URLs."""
    page_url = get_state_url(slug_or_id, url_type)
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log.error(f"  [{state_name}] Page fetch failed: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    seen, urls = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "account-report-MKI" not in href and "MKI" not in href:
            continue
        full = href if href.startswith("http") else "https://cag.gov.in" + href
        if full not in seen:
            seen.add(full)
            urls.append(full)

    log.info(f"  [{state_name}] Found {len(urls)} MKI PDFs")
    return urls


# ─────────────────────────────────────────────────────────
# GSDP LOADER
# ─────────────────────────────────────────────────────────
def load_gsdp():
    """Load GSDP data from gsdp_input.xlsx. Returns dict: {state: {fy: value}}"""
    gsdp = {}
    if not Path(GSDP_FILE).exists():
        log.warning("gsdp_input.xlsx not found — GSDP columns will be empty")
        return gsdp

    try:
        df = pd.read_excel(GSDP_FILE, sheet_name="📊 GSDP_Data", header=2)
        # Columns: #, State/UT, Category, GSDP 2021-22, GSDP 2022-23 ...
        state_col = df.columns[1]
        for _, row in df.iterrows():
            state = str(row[state_col]).strip()
            if not state or state == "nan":
                continue
            gsdp[state] = {}
            for col in df.columns[3:]:
                fy = str(col).replace("GSDP ", "").replace(" (₹ Crore)", "").strip()
                val = row[col]
                if pd.notna(val) and str(val).strip() not in ("", "nan"):
                    try:
                        gsdp[state][fy] = float(val)
                    except:
                        pass
    except Exception as e:
        log.error(f"GSDP load error: {e}")

    log.info(f"GSDP loaded for {len(gsdp)} states")
    return gsdp


# ─────────────────────────────────────────────────────────
# MANUAL OVERRIDES LOADER
# ─────────────────────────────────────────────────────────
def load_manual_overrides():
    """
    Load manual_overrides.csv.
    Key: (state, fy, calendar_month, indicator_id)
    """
    overrides = {}
    if not Path(MANUAL_OVERRIDES).exists():
        return overrides

    try:
        df = pd.read_csv(MANUAL_OVERRIDES)
        required = ["state", "fy", "calendar_month", "indicator_id",
                    "be", "actuals_cumulative"]
        if not all(c in df.columns for c in required):
            log.error("manual_overrides.csv missing required columns")
            return overrides

        for _, row in df.iterrows():
            key = (
                str(row["state"]).strip(),
                str(row["fy"]).strip(),
                int(row["calendar_month"]),
                str(row["indicator_id"]).strip(),
            )
            overrides[key] = row
        log.info(f"Loaded {len(overrides)} manual overrides")
    except Exception as e:
        log.error(f"Manual overrides load error: {e}")

    return overrides


# ─────────────────────────────────────────────────────────
# EXISTING DATA TRACKER
# ─────────────────────────────────────────────────────────
def load_tracker():
    if Path(TRACKER_JSON).exists():
        with open(TRACKER_JSON) as f:
            return json.load(f)
    return {}


def save_tracker(tracker):
    with open(TRACKER_JSON, "w") as f:
        json.dump(tracker, f, indent=2)


def already_parsed(tracker, state, fy, month):
    key = f"{state}|{fy}|{month}"
    return tracker.get(key, {}).get("status") == DQ_OK


def mark_parsed(tracker, state, fy, month, status, url=""):
    key = f"{state}|{fy}|{month}"
    tracker[key] = {"status": status, "url": url, "updated": datetime.now().isoformat()}


# ─────────────────────────────────────────────────────────
# ROWS BUILDER
# ─────────────────────────────────────────────────────────
def build_rows(state_name, category, parse_result, gsdp_data, overrides):
    """Convert parse_result into list of rows (one per indicator)."""
    rows = []
    cal_month  = parse_result["calendar_month"]
    cal_year   = parse_result["calendar_year"]
    fy         = parse_result["fy"]
    fy_order   = parse_result["fy_month_order"]
    month_name = parse_result["month_name"]
    url        = parse_result.get("url", "")
    now        = datetime.now().isoformat()

    gsdp_val   = gsdp_data.get(state_name, {}).get(fy)
    status_pdf = parse_result.get("status", DQ_PARSE_ERROR)

    for ind_id in INDICATOR_IDS:
        override_key = (state_name, fy, cal_month, ind_id)
        ind_data     = parse_result.get("indicators", {}).get(ind_id, {})
        found        = ind_data.get("found", False)

        # Determine source
        if override_key in overrides:
            ov = overrides[override_key]
            be         = _safe_float(ov.get("be"))
            actuals_c  = _safe_float(ov.get("actuals_cumulative"))
            pct_cur    = _safe_float(ov.get("pct_be_current"))
            pct_prev   = _safe_float(ov.get("pct_be_prev_year"))
            dq         = DQ_MANUAL
        elif status_pdf == DQ_PDF_ERROR:
            be, actuals_c, pct_cur, pct_prev = None, None, None, None
            dq = DQ_PDF_ERROR
        elif not found:
            be, actuals_c, pct_cur, pct_prev = None, None, None, None
            dq = DQ_PARSE_ERROR
        else:
            be         = ind_data.get("be")
            actuals_c  = ind_data.get("actuals")
            pct_cur    = ind_data.get("pct_current")
            pct_prev   = ind_data.get("pct_prev")
            dq         = DQ_OK

        # YoY growth from pct columns
        yoy = None
        if pct_cur is not None and pct_prev is not None and pct_prev != 0:
            # pct_prev is % of BE achieved in prev year → use as proxy
            yoy = round(pct_cur - pct_prev, 2)

        # GSDP ratio
        gsdp_ratio = None
        if actuals_c and gsdp_val and gsdp_val > 0:
            gsdp_ratio = round((actuals_c / gsdp_val) * 100, 4)

        rows.append({
            "state":              state_name,
            "category":           category,
            "fy":                 fy,
            "calendar_year":      cal_year,
            "calendar_month":     cal_month,
            "month_name":         month_name,
            "fy_month_order":     fy_order,
            "indicator_id":       ind_id,
            "indicator_name":     INDICATOR_NAMES[ind_id],
            "indicator_group":    INDICATOR_GROUP[ind_id],
            "indicator_subgroup": INDICATOR_SUBGROUP[ind_id],
            "be":                 be,
            "actuals_cumulative": actuals_c,
            "actuals_monthly":    None,  # computed after sorting
            "pct_be_current":     pct_cur,
            "pct_be_prev_year":   pct_prev,
            "yoy_growth_pct":     yoy,
            "gsdp":               gsdp_val,
            "actuals_pct_gsdp":   gsdp_ratio,
            "data_quality":       dq,
            "pdf_url":            url,
            "last_updated":       now,
        })

    return rows


def _safe_float(val):
    try:
        return float(val) if pd.notna(val) else None
    except:
        return None


# ─────────────────────────────────────────────────────────
# MONTHLY DERIVATION (cumulative diff)
# ─────────────────────────────────────────────────────────
def compute_monthly_actuals(df):
    """
    Derive actuals_monthly from cumulative: current month - previous month.
    April (fy_month_order=1) monthly = cumulative itself.
    """
    df = df.sort_values(["state", "indicator_id", "fy", "fy_month_order"])
    df["actuals_monthly"] = df.groupby(
        ["state", "indicator_id", "fy"]
    )["actuals_cumulative"].diff()

    # For April (order=1), monthly = cumulative
    april_mask = df["fy_month_order"] == 1
    df.loc[april_mask, "actuals_monthly"] = df.loc[april_mask, "actuals_cumulative"]

    return df


# ─────────────────────────────────────────────────────────
# STATE PIPELINE
# ─────────────────────────────────────────────────────────
def run_state(state_name, slug, url_type, category,
              gsdp_data, overrides, tracker, mode="update"):
    """Process one state. Returns list of new rows."""
    log.info(f"\n{'='*50}\n  Processing: {state_name}\n{'='*50}")

    urls = get_pdf_urls(state_name, slug, url_type)
    if not urls:
        log.warning(f"  [{state_name}] No PDFs found")
        return []

    all_rows = []
    skipped  = 0

    for url in urls:
        # Skip if already parsed (update mode)
        # Rough month detection from URL to avoid full download
        url_lower = url.lower()

        # Try to detect year from URL to limit history (mode=historical: 2 years)
        year_match = re.search(r"(\d{4})", url_lower)
        if year_match:
            url_year = int(year_match.group(1))
            current_year = datetime.now().year
            if mode == "update" and url_year < current_year - 1:
                skipped += 1
                continue

        parse_result = parse_pdf_full(url)
        time.sleep(REQUEST_DELAY)

        if parse_result["status"] == DQ_PDF_ERROR:
            log.warning(f"    PDF error: {url}")
            continue

        if not parse_result.get("calendar_month"):
            log.warning(f"    Date parse failed: {url}")
            continue

        cal_month = parse_result["calendar_month"]
        fy        = parse_result["fy"]

        # Skip if already good in tracker
        if mode == "update" and already_parsed(tracker, state_name, fy, cal_month):
            skipped += 1
            continue

        rows = build_rows(state_name, category, parse_result, gsdp_data, overrides)
        all_rows.extend(rows)
        mark_parsed(tracker, state_name, fy, cal_month,
                    parse_result["status"], url)
        log.info(f"    ✓ {state_name} | {fy} | {parse_result['month_name']} "
                 f"| {parse_result.get('found_count',0)}/26 indicators")

    log.info(f"  [{state_name}] Done. {len(all_rows)//26} months parsed, {skipped} skipped")
    return all_rows


# ─────────────────────────────────────────────────────────
# SAVE / MERGE DATA
# ─────────────────────────────────────────────────────────
def save_master(new_rows):
    """Merge new_rows into master CSV."""
    if not new_rows:
        return None

    new_df = pd.DataFrame(new_rows, columns=MASTER_COLUMNS)

    if Path(MASTER_CSV).exists():
        existing = pd.read_csv(MASTER_CSV)
        # Drop rows that will be replaced by new data
        key_cols = ["state", "fy", "calendar_month", "indicator_id"]
        new_keys = new_df[key_cols].apply(tuple, axis=1)
        existing = existing[
            ~existing[key_cols].apply(tuple, axis=1).isin(new_keys)
        ]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = compute_monthly_actuals(combined)
    combined = combined.sort_values(
        ["state", "indicator_id", "fy", "fy_month_order"]
    ).reset_index(drop=True)
    combined.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")

    # Per-state CSV
    for state in combined["state"].unique():
        fname = f"{STATES_DIR}/{state_to_filename(state)}.csv"
        combined[combined["state"] == state].to_csv(
            fname, index=False, encoding="utf-8-sig"
        )

    log.info(f"Saved {len(combined)} rows to master CSV")
    return combined


def save_metadata(all_states_processed):
    meta = {
        "last_updated":     datetime.now().isoformat(),
        "total_states":     len(all_states_processed),
        "states":           all_states_processed,
        "indicators":       len(INDICATOR_IDS),
        "pipeline_version": "1.0.0",
    }
    with open(METADATA_JSON, "w") as f:
        json.dump(meta, f, indent=2)


# ─────────────────────────────────────────────────────────
# MANUAL OVERRIDE TEMPLATE GENERATOR
# ─────────────────────────────────────────────────────────
def create_override_template():
    """Create manual_overrides.csv with headers + example row if not exists."""
    if Path(MANUAL_OVERRIDES).exists():
        return

    Path(INPUTS_DIR).mkdir(parents=True, exist_ok=True)
    example = {
        "state":              "Chhattisgarh",
        "fy":                 "2024-25",
        "calendar_month":     4,
        "month_name":         "April",
        "indicator_id":       "revenue_receipts",
        "be":                 100000,
        "actuals_cumulative": 5000,
        "pct_be_current":     5.0,
        "pct_be_prev_year":   4.2,
        "data_quality":       DQ_MANUAL,
        "notes":              "Sourced from state treasury website",
    }
    df = pd.DataFrame([example])
    df.to_csv(MANUAL_OVERRIDES, index=False)
    log.info(f"Created manual_overrides.csv template at {MANUAL_OVERRIDES}")


# ─────────────────────────────────────────────────────────
# COMPLETENESS SCORE
# ─────────────────────────────────────────────────────────
def compute_completeness(df):
    """Returns per-state completeness scores."""
    scores = {}
    for state in df["state"].unique():
        sdf = df[df["state"] == state]
        total    = len(sdf)
        ok_count = len(sdf[sdf["data_quality"].isin([DQ_OK, DQ_MANUAL])])
        scores[state] = round((ok_count / total * 100) if total > 0 else 0, 1)
    return scores


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fiscal Pulse Pipeline")
    parser.add_argument("--mode", choices=["historical", "update", "state"],
                        default="update")
    parser.add_argument("--state", type=str, default=None,
                        help="State name for mode=state")
    args = parser.parse_args()

    log.info(f"\n{'#'*60}\n  Fiscal Pulse Pipeline | mode={args.mode}\n{'#'*60}")

    create_override_template()
    gsdp_data = load_gsdp()
    overrides = load_manual_overrides()
    tracker   = load_tracker()

    all_new_rows = []
    processed    = []

    if args.mode == "state":
        target = args.state
        state_cfg = next(
            ((n,s,t,c) for n,s,t,c,av in STATES if n.lower()==target.lower() and av),
            None
        )
        if not state_cfg:
            log.error(f"State '{target}' not found or no monthly CAG data")
            sys.exit(1)
        n, s, t, c = state_cfg
        rows = run_state(n, s, t, c, gsdp_data, overrides, tracker, args.mode)
        all_new_rows.extend(rows)
        processed.append(n)

    else:
        for name, slug, url_type, category, avail in STATES:
            if not avail:
                log.info(f"⏭  {name}: no monthly CAG data — skipping")
                continue
            rows = run_state(name, slug, url_type, category,
                             gsdp_data, overrides, tracker, args.mode)
            all_new_rows.extend(rows)
            processed.append(name)
            time.sleep(1)

    save_tracker(tracker)

    if all_new_rows:
        master_df = save_master(all_new_rows)
        if master_df is not None:
            scores = compute_completeness(master_df)
            log.info("\nCompleteness Scores:")
            for s, sc in sorted(scores.items(), key=lambda x: -x[1]):
                log.info(f"  {s:<25} {sc:>6.1f}%")

            # Generate office Excel
            try:
                generate_office_excel(master_df, OFFICE_EXCEL)
                log.info(f"Office Excel saved: {OFFICE_EXCEL}")
            except Exception as e:
                log.error(f"Excel export error: {e}")

    save_metadata(processed)
    log.info(f"\n✅ Pipeline complete. Processed {len(processed)} states.")


if __name__ == "__main__":
    main()
