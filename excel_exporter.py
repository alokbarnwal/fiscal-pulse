"""
Fiscal Pulse — Office Excel Exporter
Generates formatted .xlsx for EY office use.
"""

import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.styles.numbers import FORMAT_NUMBER_COMMA_SEPARATED1
from datetime import datetime
from pathlib import Path

from config import (
    INDICATOR_IDS, INDICATOR_NAMES, INDICATOR_GROUP,
    DQ_OK, DQ_MANUAL, DQ_PARSE_ERROR, DQ_PDF_ERROR, DQ_MISSING,
    MONTH_NAMES, state_to_filename
)

# ─── Style constants ───────────────────────────────────
C_DARK      = "1F4E79"
C_MED       = "2E75B6"
C_LIGHT     = "D6E4F0"
C_GREEN_H   = "375623"
C_GREEN_L   = "E2EFDA"
C_RED_H     = "843C0C"
C_RED_L     = "FCE4D6"
C_ORANGE    = "FF8C00"
C_YELLOW    = "FFF2CC"
C_GREY      = "F2F2F2"

DQ_COLORS = {
    DQ_OK:          ("E2EFDA", "375623"),
    DQ_MANUAL:      ("D9E1F2", "203864"),
    DQ_PARSE_ERROR: ("FFF2CC", "7F6000"),
    DQ_PDF_ERROR:   ("FCE4D6", "843C0C"),
    DQ_MISSING:     ("EDEDED", "595959"),
}

def thin_border():
    s = Side(border_style="thin", color="BFBFBF")
    return Border(left=s, right=s, top=s, bottom=s)

def header_border():
    s = Side(border_style="medium", color="1F4E79")
    return Border(left=s, right=s, top=s, bottom=s)

def fmt_cell(ws, r, c, val=None, bold=False, fg="000000", bg=None,
             num_fmt=None, center=True, wrap=True, size=9, italic=False):
    cell = ws.cell(row=r, column=c, value=val)
    cell.font = Font(name="Arial", bold=bold, color=fg, size=size, italic=italic)
    cell.border = thin_border()
    cell.alignment = Alignment(
        horizontal="center" if center else "left",
        vertical="center", wrap_text=wrap
    )
    if bg:
        cell.fill = PatternFill("solid", fgColor=bg)
    if num_fmt:
        cell.number_format = num_fmt
    return cell

def hdr_cell(ws, r, c, val, bg=C_DARK, fg="FFFFFF", bold=True,
             center=True, size=9, wrap=True):
    cell = ws.cell(row=r, column=c, value=val)
    cell.font = Font(name="Arial", bold=bold, color=fg, size=size)
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.border = header_border()
    cell.alignment = Alignment(
        horizontal="center" if center else "left",
        vertical="center", wrap_text=wrap
    )
    return cell


# ─────────────────────────────────────────────────────────
# SUMMARY SHEET
# ─────────────────────────────────────────────────────────
def add_summary_sheet(wb, df):
    ws = wb.active
    ws.title = "📊 Summary"
    ws.sheet_view.showGridLines = False

    # Title
    ws.merge_cells("A1:L1")
    t = ws.cell(row=1, column=1,
        value="Fiscal Pulse | CAG Monthly Key Indicators | All States Summary")
    t.font = Font(name="Arial", bold=True, size=14, color="FFFFFF")
    t.fill = PatternFill("solid", fgColor=C_DARK)
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    # Subtitle
    ws.merge_cells("A2:L2")
    s = ws.cell(row=2, column=1,
        value=f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}  |  Unit: ₹ Crore  |  Fiscal Pulse v1.0")
    s.font = Font(name="Arial", italic=True, size=9, color="595959")
    s.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 16

    # Headers row 4
    headers = ["State", "Category", "Data Available",
               "Latest Month", "Latest FY",
               "Revenue Receipts (Latest)", "Total Expenditure (Latest)",
               "Fiscal Deficit (Latest)", "Capex (Latest)",
               "Completeness %", "Parse Errors", "Status"]
    for i, h in enumerate(headers, 1):
        hdr_cell(ws, 4, i, h)

    ws.row_dimensions[4].height = 30

    # State summary rows
    row = 5
    all_states_config = __import__("config").STATES
    state_cat = {n: c for n, _, _, c, _ in all_states_config}
    state_avail = {n: av for n, _, _, _, av in all_states_config}

    for state_name, _, _, cat, avail in all_states_config:
        bg = C_GREY if row % 2 == 0 else None

        sdf = df[df["state"] == state_name] if avail else pd.DataFrame()
        total   = len(sdf)
        ok_cnt  = len(sdf[sdf["data_quality"].isin([DQ_OK, DQ_MANUAL])]) if total else 0
        err_cnt = len(sdf[sdf["data_quality"] == DQ_PARSE_ERROR]) if total else 0
        pct     = round(ok_cnt / total * 100, 1) if total > 0 else 0

        # Latest month
        if not sdf.empty:
            latest = sdf.sort_values("fy_month_order").iloc[-1]
            latest_month = latest["month_name"]
            latest_fy    = latest["fy"]

            def get_val(ind_id):
                r2 = sdf[(sdf["indicator_id"] == ind_id) &
                         (sdf["fy"] == latest_fy) &
                         (sdf["calendar_month"] == latest["calendar_month"])]
                return r2["actuals_cumulative"].values[0] if not r2.empty else None

            rev_rec = get_val("revenue_receipts")
            tot_exp = get_val("total_expenditure")
            fisc_def = get_val("fiscal_deficit")
            capex   = get_val("capital_expenditure")
        else:
            latest_month = latest_fy = "—"
            rev_rec = tot_exp = fisc_def = capex = None

        fmt_cell(ws, row, 1, state_name, bold=True, center=False, bg=bg)
        
        # Category badge
        cat_colors = {
            "Large":   ("E2EFDA", "375623"),
            "Special": ("FCE4D6", "843C0C"),
            "Hill":    ("EAD1DC", "4E1A2C"),
            "Small":   ("D9E1F2", "203864"),
            "UT":      (C_GREY, "595959"),
        }
        cc_bg, cc_fg = cat_colors.get(cat, ("FFFFFF", "000000"))
        c2 = ws.cell(row=row, column=2, value=cat)
        c2.font = Font(name="Arial", size=9, color=cc_fg)
        c2.fill = PatternFill("solid", fgColor=cc_bg)
        c2.border = thin_border()
        c2.alignment = Alignment(horizontal="center", vertical="center")

        avail_text = "✅ Monthly MKI" if avail else "⚠️ Annual only"
        avail_fg   = "375623" if avail else "843C0C"
        c3 = ws.cell(row=row, column=3, value=avail_text)
        c3.font = Font(name="Arial", size=9, color=avail_fg)
        c3.border = thin_border()
        c3.alignment = Alignment(horizontal="center", vertical="center")

        fmt_cell(ws, row, 4, latest_month, bg=bg)
        fmt_cell(ws, row, 5, latest_fy, bg=bg)

        for col_i, val in enumerate([rev_rec, tot_exp, fisc_def, capex], start=6):
            c = ws.cell(row=row, column=col_i, value=val)
            c.font = Font(name="Arial", size=9,
                          color="C00000" if (val and val < 0) else "000000")
            c.fill = PatternFill("solid", fgColor=bg or "FFFFFF")
            c.border = thin_border()
            c.number_format = '#,##0'
            c.alignment = Alignment(horizontal="center", vertical="center")

        # Completeness
        pct_bg = "E2EFDA" if pct >= 80 else ("FFF2CC" if pct >= 50 else "FCE4D6")
        pct_fg = "375623" if pct >= 80 else ("7F6000" if pct >= 50 else "843C0C")
        cp = ws.cell(row=row, column=10, value=f"{pct}%" if avail else "—")
        cp.font = Font(name="Arial", size=9, bold=True, color=pct_fg)
        cp.fill = PatternFill("solid", fgColor=pct_bg if avail else C_GREY)
        cp.border = thin_border()
        cp.alignment = Alignment(horizontal="center", vertical="center")

        fmt_cell(ws, row, 11, err_cnt if avail else "—",
                 fg="843C0C" if err_cnt > 0 else "000000", bg=bg)

        # Status
        if not avail:
            status_txt, s_bg, s_fg = "No monthly data", "EDEDED", "595959"
        elif pct >= 80:
            status_txt, s_bg, s_fg = "Good", "E2EFDA", "375623"
        elif pct >= 50:
            status_txt, s_bg, s_fg = "Partial", "FFF2CC", "7F6000"
        else:
            status_txt, s_bg, s_fg = "Needs review", "FCE4D6", "843C0C"

        c_st = ws.cell(row=row, column=12, value=status_txt)
        c_st.font = Font(name="Arial", size=9, bold=True, color=s_fg)
        c_st.fill = PatternFill("solid", fgColor=s_bg)
        c_st.border = thin_border()
        c_st.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[row].height = 18
        row += 1

    # Column widths
    widths = [22,14,18,14,10,20,20,20,18,14,12,14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A5"


# ─────────────────────────────────────────────────────────
# STATE SHEET — Wide Pivot (Indicators × Months)
# ─────────────────────────────────────────────────────────
def add_state_sheet(wb, df, state_name):
    safe = state_to_filename(state_name)[:25]
    ws = wb.create_sheet(title=f"📍{safe}")
    ws.sheet_view.showGridLines = False

    sdf = df[df["state"] == state_name].copy()
    if sdf.empty:
        ws.cell(row=1, column=1, value="No data available")
        return

    fys = sorted(sdf["fy"].unique())

    col = 1
    for fy in fys:
        fy_df = sdf[sdf["fy"] == fy].copy()
        months = sorted(fy_df["fy_month_order"].unique())
        month_cols = [(m, fy_df[fy_df["fy_month_order"]==m]["month_name"].iloc[0])
                      for m in months]

        num_month_cols = len(months)
        span_end = col + 1 + (num_month_cols * 2) - 1  # BE + actuals for each month

        # FY header
        ws.merge_cells(
            start_row=1, start_column=col,
            end_row=1, end_column=col + 1 + (num_month_cols * 2) - 1
        )
        fy_hdr = ws.cell(row=1, column=col,
            value=f"FY {fy}  |  {state_name}  |  ₹ Crore")
        fy_hdr.font = Font(name="Arial", bold=True, size=11, color="FFFFFF")
        fy_hdr.fill = PatternFill("solid", fgColor=C_DARK)
        fy_hdr.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 28

        # Group / Indicator header
        hdr_cell(ws, 2, col, "Group", bg=C_MED)
        hdr_cell(ws, 2, col+1, "Indicator", bg=C_MED)

        mc = col + 2
        for _, mname in month_cols:
            ws.merge_cells(start_row=2, start_column=mc, end_row=2, end_column=mc+1)
            hdr_cell(ws, 2, mc, mname, bg=C_MED)
            hdr_cell(ws, 3, mc,   "BE",      bg="4472C4", fg="FFFFFF", size=8)
            hdr_cell(ws, 3, mc+1, "Actuals", bg="4472C4", fg="FFFFFF", size=8)
            mc += 2

        ws.row_dimensions[2].height = 22
        ws.row_dimensions[3].height = 18

        # Data rows
        current_group = None
        data_row = 4
        for ind_id in INDICATOR_IDS:
            ind_name  = INDICATOR_NAMES[ind_id]
            ind_group = INDICATOR_GROUP[ind_id]
            is_total  = "Total" in ind_name

            # Group separator
            if ind_group != current_group:
                grp_col = col + 1 + (num_month_cols * 2)
                ws.merge_cells(
                    start_row=data_row, start_column=col,
                    end_row=data_row, end_column=grp_col
                )
                gc = ws.cell(row=data_row, column=col, value=f"  {ind_group}")
                gc.font = Font(name="Arial", bold=True, size=9, color="FFFFFF")
                gc.fill = PatternFill("solid", fgColor=C_MED)
                gc.alignment = Alignment(horizontal="left", vertical="center")
                ws.row_dimensions[data_row].height = 16
                data_row += 1
                current_group = ind_group

            row_bg = C_LIGHT if is_total else None

            fmt_cell(ws, data_row, col, ind_group, center=False,
                     bg=row_bg, size=8, fg="595959", italic=True)
            fmt_cell(ws, data_row, col+1, ind_name, center=False,
                     bold=is_total, bg=row_bg)

            dc = col + 2
            for m_order, _ in month_cols:
                mdf = fy_df[
                    (fy_df["indicator_id"] == ind_id) &
                    (fy_df["fy_month_order"] == m_order)
                ]

                be_val  = mdf["be"].values[0]  if not mdf.empty else None
                act_val = mdf["actuals_cumulative"].values[0] if not mdf.empty else None
                dq      = mdf["data_quality"].values[0] if not mdf.empty else "—"

                dq_bg, dq_fg = DQ_COLORS.get(dq, ("FFFFFF", "000000"))
                dq_bg = dq_bg if dq != DQ_OK else (C_LIGHT if is_total else None)

                for v in [be_val, act_val]:
                    c = ws.cell(row=data_row, column=dc, value=v)
                    c.font = Font(name="Arial", size=9,
                                  color="C00000" if (v and v < 0) else dq_fg)
                    c.fill = PatternFill("solid", fgColor=dq_bg or "FFFFFF")
                    c.border = thin_border()
                    c.number_format = "#,##0"
                    c.alignment = Alignment(horizontal="center", vertical="center")
                    dc += 1

            ws.row_dimensions[data_row].height = 16
            data_row += 1

        # DQ Legend below data
        data_row += 1
        ws.cell(row=data_row, column=col, value="Data Quality:").font = \
            Font(name="Arial", bold=True, size=8)
        dc = col + 1
        for dq_flag, (b, f) in DQ_COLORS.items():
            c = ws.cell(row=data_row, column=dc, value=dq_flag)
            c.font = Font(name="Arial", size=8, color=f)
            c.fill = PatternFill("solid", fgColor=b)
            c.border = thin_border()
            c.alignment = Alignment(horizontal="center", vertical="center")
            dc += 1

        col = span_end + 2  # gap between FYs

    # Column widths
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 28
    for i in range(3, col):
        ws.column_dimensions[get_column_letter(i)].width = 13

    ws.freeze_panes = "C4"


# ─────────────────────────────────────────────────────────
# DATA QUALITY SHEET
# ─────────────────────────────────────────────────────────
def add_dq_sheet(wb, df):
    ws = wb.create_sheet("🔍 Data Quality")
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:H1")
    t = ws.cell(row=1, column=1,
        value="Data Quality Review — Parse Errors & Missing Data")
    t.font = Font(name="Arial", bold=True, size=12, color="FFFFFF")
    t.fill = PatternFill("solid", fgColor="843C0C")
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    headers = ["State", "FY", "Month", "Indicator",
               "Data Quality", "BE", "Actuals", "PDF URL"]
    for i, h in enumerate(headers, 1):
        hdr_cell(ws, 2, i, h, bg=C_MED)

    issues = df[~df["data_quality"].isin([DQ_OK, DQ_MANUAL])].copy()
    issues = issues.sort_values(["state", "fy", "fy_month_order", "indicator_id"])

    for r, (_, row_data) in enumerate(issues.iterrows(), start=3):
        dq_bg, dq_fg = DQ_COLORS.get(row_data["data_quality"], ("FFFFFF", "000000"))
        bg = C_GREY if r % 2 == 0 else None

        fmt_cell(ws, r, 1, row_data["state"],          center=False, bg=bg)
        fmt_cell(ws, r, 2, row_data["fy"],              bg=bg)
        fmt_cell(ws, r, 3, row_data["month_name"],      bg=bg)
        fmt_cell(ws, r, 4, row_data["indicator_name"],  center=False, bg=bg)

        dq_c = ws.cell(row=r, column=5, value=row_data["data_quality"])
        dq_c.font = Font(name="Arial", size=9, bold=True, color=dq_fg)
        dq_c.fill = PatternFill("solid", fgColor=dq_bg)
        dq_c.border = thin_border()
        dq_c.alignment = Alignment(horizontal="center", vertical="center")

        fmt_cell(ws, r, 6, row_data["be"],              num_fmt="#,##0", bg=bg)
        fmt_cell(ws, r, 7, row_data["actuals_cumulative"], num_fmt="#,##0", bg=bg)
        url_c = ws.cell(row=r, column=8, value=row_data["pdf_url"])
        url_c.font = Font(name="Arial", size=8, color="0000EE", underline="single")
        url_c.border = thin_border()
        url_c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[r].height = 16

    widths = [22, 10, 12, 30, 15, 14, 14, 60]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A3"
    return ws


# ─────────────────────────────────────────────────────────
# MAIN EXPORTER
# ─────────────────────────────────────────────────────────
def generate_office_excel(df, output_path):
    wb = openpyxl.Workbook()

    # 1. Summary sheet
    add_summary_sheet(wb, df)

    # 2. Per-state sheets (only states with data)
    states_with_data = df["state"].unique()
    for state in sorted(states_with_data):
        add_state_sheet(wb, df, state)

    # 3. Data quality sheet
    add_dq_sheet(wb, df)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
