"""
Fiscal Pulse — Central Configuration
All states, indicators, and constants defined here.
"""

# ─────────────────────────────────────────────────────────
# PROJECT CONSTANTS
# ─────────────────────────────────────────────────────────
PROJECT_NAME    = "Fiscal Pulse"
VERSION         = "1.0.0"
UNIT            = "₹ Crore"
YEARS_HISTORY   = 2
REQUEST_DELAY   = 1.5   # seconds between HTTP requests

# Paths
DATA_DIR            = "data"
STATES_DIR          = "data/states"
MASTER_CSV          = "data/master.csv"
SUMMARY_CSV         = "data/summary.csv"
METADATA_JSON       = "data/metadata.json"
TRACKER_JSON        = "data/pipeline_tracker.json"

INPUTS_DIR          = "inputs"
GSDP_FILE           = "inputs/gsdp_input.xlsx"
MANUAL_OVERRIDES    = "inputs/manual_overrides.csv"

OUTPUTS_DIR         = "outputs"
OFFICE_EXCEL        = "outputs/CAG_Monthly_Key_Indicators_Office.xlsx"
LOG_FILE            = "data/pipeline.log"

# ─────────────────────────────────────────────────────────
# HTTP HEADERS
# ─────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ─────────────────────────────────────────────────────────
# STATES CONFIG
# Format: (display_name, slug_or_id, url_type, category, cag_available)
# url_type: "slug" = /ae/{slug}/... | "id" = ?defuat_state_id={id}
# ─────────────────────────────────────────────────────────
STATES = [
    # name                   slug/id             type   category         cag_monthly
    ("Andhra Pradesh",       "andhra-pradesh",   "slug", "Large",        True),
    ("Arunachal Pradesh",    "arunachal-pradesh","slug", "Special",      True),
    ("Assam",                "assam",            "slug", "Special",      True),
    ("Bihar",                "bihar",            "slug", "Large",        True),
    ("Chhattisgarh",         "chhattisgarh",     "slug", "Large",        True),
    ("Delhi",                "69",               "id",   "UT",           False),
    ("Goa",                  "70",               "id",   "Small",        False),
    ("Gujarat",              "gujarat",          "slug", "Large",        True),
    ("Haryana",              "haryana",          "slug", "Large",        True),
    ("Himachal Pradesh",     "himachal-pradesh", "slug", "Hill",         True),
    ("Jharkhand",            "jharkhand",        "slug", "Large",        True),
    ("Karnataka",            "karnataka",        "slug", "Large",        True),
    ("Kerala",               "kerala",           "slug", "Large",        True),
    ("Madhya Pradesh",       "78",               "id",   "Large",        False),
    ("Maharashtra",          "mumbai",           "slug", "Large",        True),
    ("Manipur",              "manipur",          "slug", "Special",      True),
    ("Meghalaya",            "meghalaya",        "slug", "Special",      True),
    ("Mizoram",              "mizoram",          "slug", "Special",      True),
    ("Nagaland",             "nagaland",         "slug", "Special",      True),
    ("Odisha",               "odisha",           "slug", "Large",        True),
    ("Punjab",               "85",               "id",   "Large",        False),
    ("Rajasthan",            "rajasthan",        "slug", "Large",        True),
    ("Sikkim",               "sikkim",           "slug", "Special",      True),
    ("Tamil Nadu",           "tamil-nadu",       "slug", "Large",        True),
    ("Telangana",            "telangana",        "slug", "Large",        True),
    ("Tripura",              "tripura",          "slug", "Special",      True),
    ("Uttar Pradesh",        "90",               "id",   "Large",        True),
    ("Uttarakhand",          "uttarakhand",      "slug", "Hill",         True),
    ("West Bengal",          "west-bengal",      "slug", "Large",        True),
]

# States where CAG has monthly MKI data
ACTIVE_STATES = [(n, s, t, c) for n, s, t, c, avail in STATES if avail]

# URL builders
def get_state_url(slug_or_id, url_type):
    if url_type == "slug":
        return f"https://cag.gov.in/ae/{slug_or_id}/en/state-accounts-report?defuat_account_report_type=360"
    else:
        return f"https://cag.gov.in/en/state-accounts-report?defuat_state_id={slug_or_id}"

# State name → slug map (for file naming)
def state_to_filename(state_name):
    return state_name.lower().replace(" ", "_").replace("/", "_")

# ─────────────────────────────────────────────────────────
# DATA QUALITY FLAGS
# ─────────────────────────────────────────────────────────
DQ_OK           = "OK"          # Auto-parsed successfully
DQ_PARSE_ERROR  = "PARSE_ERROR" # PDF downloaded, indicator not found
DQ_PDF_ERROR    = "PDF_ERROR"   # PDF download failed
DQ_MISSING      = "MISSING"     # Month not uploaded on CAG website
DQ_MANUAL       = "MANUAL"      # Manually entered via override
DQ_NA           = "N/A"         # Indicator not applicable for this state

# ─────────────────────────────────────────────────────────
# MONTH MAPPING
# ─────────────────────────────────────────────────────────
MONTH_NAMES = {
    1: "April", 2: "May", 3: "June", 4: "July",
    5: "August", 6: "September", 7: "October", 8: "November",
    9: "December", 10: "January", 11: "February", 12: "March"
}
# Financial year month order (Apr=1, Mar=12)
CALENDAR_TO_FY = {4:1, 5:2, 6:3, 7:4, 8:5, 9:6, 10:7, 11:8, 12:9, 1:10, 2:11, 3:12}
FY_TO_CALENDAR = {v: k for k, v in CALENDAR_TO_FY.items()}

MONTH_PARSE_MAP = {
    "january":1,"jan":1,"01":1,    "february":2,"feb":2,"02":2,
    "march":3,"mar":3,"03":3,      "april":4,"apr":4,"04":4,
    "may":5,"05":5,                "june":6,"jun":6,"06":6,
    "july":7,"jul":7,"07":7,       "august":8,"aug":8,"08":8,
    "september":9,"sep":9,"09":9,  "october":10,"oct":10,"10":10,
    "november":11,"nov":11,"11":11,"december":12,"dec":12,"12":12,
}

def make_fy(calendar_month, calendar_year):
    """Given calendar month and year, return financial year string."""
    if calendar_month >= 4:
        return f"{calendar_year}-{str(calendar_year+1)[2:]}"
    else:
        return f"{calendar_year-1}-{str(calendar_year)[2:]}"

def fy_month_order(calendar_month):
    """Position of month within financial year (Apr=1, Mar=12)."""
    return CALENDAR_TO_FY.get(calendar_month, 0)

# ─────────────────────────────────────────────────────────
# INDICATORS
# Each: (id, display_name, group, sub_group, is_deficit)
# ─────────────────────────────────────────────────────────
INDICATORS = [
    # id                         display name                           group              sub_group       deficit
    ("revenue_receipts",         "Revenue Receipts",                   "Receipts",        "Total",        False),
    ("tax_revenue",              "Tax Revenue",                         "Receipts",        "Tax",          False),
    ("sgst",                     "SGST / GST",                          "Receipts",        "Tax",          False),
    ("stamps_registration",      "Stamps & Registration",               "Receipts",        "Tax",          False),
    ("land_revenue",             "Land Revenue",                        "Receipts",        "Tax",          False),
    ("sales_tax",                "Sales Tax",                           "Receipts",        "Tax",          False),
    ("state_excise",             "State Excise Duties",                 "Receipts",        "Tax",          False),
    ("union_taxes_share",        "State Share of Union Taxes",          "Receipts",        "Tax",          False),
    ("other_taxes",              "Other Taxes & Duties",                "Receipts",        "Tax",          False),
    ("non_tax_revenue",          "Non-Tax Revenue",                     "Receipts",        "Non-Tax",      False),
    ("grants_in_aid",            "Grants-in-Aid & Contribution",        "Receipts",        "Grants",       False),
    ("capital_receipts",         "Capital Receipts",                    "Receipts",        "Capital",      False),
    ("recovery_loans",           "Recovery of Loans & Advances",        "Receipts",        "Capital",      False),
    ("borrowings",               "Borrowings & Other Liabilities",      "Receipts",        "Capital",      False),
    ("total_receipts",           "Total Receipts",                      "Receipts",        "Total",        False),
    ("revenue_expenditure",      "Revenue Expenditure",                 "Expenditure",     "Revenue",      False),
    ("interest_payments",        "Interest Payments",                   "Expenditure",     "Revenue",      False),
    ("salaries_wages",           "Salaries & Wages",                    "Expenditure",     "Revenue",      False),
    ("pension",                  "Pension",                             "Expenditure",     "Revenue",      False),
    ("subsidy",                  "Subsidy",                             "Expenditure",     "Revenue",      False),
    ("capital_expenditure",      "Capital Expenditure",                 "Expenditure",     "Capital",      False),
    ("total_expenditure",        "Total Expenditure",                   "Expenditure",     "Total",        False),
    ("loans_advances_disbursed", "Loans & Advances Disbursed",          "Expenditure",     "Loans",        False),
    ("revenue_surplus_deficit",  "Revenue Surplus (+) / Deficit (-)",   "Fiscal Position", "Revenue",      True),
    ("fiscal_deficit",           "Fiscal Surplus (+) / Deficit (-)",    "Fiscal Position", "Fiscal",       True),
    ("primary_deficit",          "Primary Deficit (-) / Surplus (+)",   "Fiscal Position", "Primary",      True),
]

INDICATOR_IDS   = [i[0] for i in INDICATORS]
INDICATOR_NAMES = {i[0]: i[1] for i in INDICATORS}
INDICATOR_GROUP = {i[0]: i[2] for i in INDICATORS}
INDICATOR_SUBGROUP = {i[0]: i[3] for i in INDICATORS}
INDICATOR_IS_DEFICIT = {i[0]: i[4] for i in INDICATORS}

# ─────────────────────────────────────────────────────────
# MASTER CSV COLUMNS (Long Format)
# ─────────────────────────────────────────────────────────
MASTER_COLUMNS = [
    "state", "category", "fy", "calendar_year", "calendar_month",
    "month_name", "fy_month_order", "indicator_id", "indicator_name",
    "indicator_group", "indicator_subgroup",
    "be", "actuals_cumulative", "actuals_monthly",
    "pct_be_current", "pct_be_prev_year",
    "yoy_growth_pct", "gsdp", "actuals_pct_gsdp",
    "data_quality", "pdf_url", "last_updated"
]
